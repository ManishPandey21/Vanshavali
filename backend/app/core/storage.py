"""Object storage with app-level envelope encryption (ADR-0004).

Objects are written once under a caller-chosen key and never overwritten. Each storage class
(STANDARD, VAULT, SYSTEM) has its own AES-256-GCM data key, so a leaked bucket without the keys
reveals nothing. Backends: local filesystem (dev/tests) and S3-compatible (MinIO/AWS).
"""

from __future__ import annotations

import base64
import os
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

_MAGIC = b"VSHE1"  # format marker + version
_NONCE_LEN = 12


class StorageError(Exception):
    pass


class ObjectExists(StorageError):
    pass


def _key_for(key_id: str) -> bytes:
    s = get_settings()
    raw = {"STANDARD": s.standard_data_key, "VAULT": s.vault_data_key, "SYSTEM": s.standard_data_key}.get(
        key_id
    )
    if raw is None:
        raise StorageError(f"unknown encryption key id {key_id}")
    key = base64.b64decode(raw)
    if len(key) != 32:
        raise StorageError("data keys must be 32 bytes (base64-encoded)")
    return key


def encrypt(data: bytes, key_id: str, aad: str) -> bytes:
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(_key_for(key_id)).encrypt(nonce, data, aad.encode())
    return _MAGIC + key_id.encode().ljust(8, b" ") + nonce + ct


def decrypt(blob: bytes, aad: str) -> bytes:
    if not blob.startswith(_MAGIC):
        raise StorageError("object is not in the expected encrypted format")
    key_id = blob[len(_MAGIC) : len(_MAGIC) + 8].decode().strip()
    rest = blob[len(_MAGIC) + 8 :]
    nonce, ct = rest[:_NONCE_LEN], rest[_NONCE_LEN:]
    return AESGCM(_key_for(key_id)).decrypt(nonce, ct, aad.encode())


class ObjectStore(ABC):
    @abstractmethod
    def _put(self, key: str, data: bytes) -> None: ...

    @abstractmethod
    def _get(self, key: str) -> bytes: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    def put_immutable(self, key: str, data: bytes, *, key_id: str) -> None:
        """Encrypt and store; refuses to overwrite (originals are immutable)."""
        if self.exists(key):
            raise ObjectExists(key)
        self._put(key, encrypt(data, key_id, aad=key))

    def get(self, key: str) -> bytes:
        return decrypt(self._get(key), aad=key)


class LocalObjectStore(ObjectStore):
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents:
            raise StorageError("invalid storage key")
        return p

    def _put(self, key: str, data: bytes) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "xb") as f:  # "x": fail if it already exists
            f.write(data)
        os.chmod(p, 0o440)

    def _get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError as exc:
            raise StorageError(f"object not found: {key}") from exc

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            os.chmod(p, 0o640)
            p.unlink()


class S3ObjectStore(ObjectStore):
    def __init__(self) -> None:
        import boto3

        s = get_settings()
        self.bucket = s.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint_url,
            region_name=s.s3_region,
            aws_access_key_id=s.s3_access_key,
            aws_secret_access_key=s.s3_secret_key,
        )

    def _put(self, key: str, data: bytes) -> None:
        # IfNoneMatch='*' makes the write conditional (no overwrite) on S3 and MinIO.
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                IfNoneMatch="*",
                ContentType="application/octet-stream",
            )
        except self.client.exceptions.ClientError as exc:  # pragma: no cover - backend specific
            code = exc.response.get("Error", {}).get("Code")
            if code in ("PreconditionFailed", "412"):
                raise ObjectExists(key) from exc
            raise StorageError(str(exc)) from exc

    def _get(self, key: str) -> bytes:
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except self.client.exceptions.NoSuchKey as exc:
            raise StorageError(f"object not found: {key}") from exc

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except self.client.exceptions.ClientError:
            return False

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


@lru_cache
def get_store() -> ObjectStore:
    s = get_settings()
    if s.storage_backend == "s3":
        return S3ObjectStore()
    return LocalObjectStore(s.storage_local_path)
