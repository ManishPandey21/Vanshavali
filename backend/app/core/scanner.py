"""Malware scanning (ADR-0004). Production requires clamd; the EICAR test scanner is refused there."""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass
from functools import lru_cache

from app.core.config import get_settings

EICAR_SIGNATURE = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


@dataclass
class ScanResult:
    clean: bool
    engine: str
    signature: str | None = None
    error: str | None = None


class ClamdScanner:
    name = "clamd"

    def __init__(self, host: str, port: int, timeout: float = 30.0) -> None:
        self.host, self.port, self.timeout = host, port, timeout

    def scan(self, data: bytes) -> ScanResult:
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as s:
                s.sendall(b"zINSTREAM\0")
                chunk = 1 << 16
                for i in range(0, len(data), chunk):
                    part = data[i : i + chunk]
                    s.sendall(struct.pack("!L", len(part)) + part)
                s.sendall(struct.pack("!L", 0))
                reply = b""
                while not reply.endswith(b"\0"):
                    buf = s.recv(4096)
                    if not buf:
                        break
                    reply += buf
        except OSError as exc:
            return ScanResult(clean=False, engine=self.name, error=f"scanner unavailable: {exc}")
        text = reply.rstrip(b"\0").decode(errors="replace")
        if text.endswith("OK"):
            return ScanResult(clean=True, engine=self.name)
        if "FOUND" in text:
            return ScanResult(
                clean=False, engine=self.name, signature=text.split(":", 1)[-1].replace("FOUND", "").strip()
            )
        return ScanResult(clean=False, engine=self.name, error=text)


class EicarTestScanner:
    """Test/dev-only scanner: flags the EICAR test string. Never used when ENV=production."""

    name = "eicar_test"

    def scan(self, data: bytes) -> ScanResult:
        if EICAR_SIGNATURE in data:
            return ScanResult(clean=False, engine=self.name, signature="Eicar-Test-Signature")
        return ScanResult(clean=True, engine=self.name)


@lru_cache
def get_scanner() -> ClamdScanner | EicarTestScanner:
    s = get_settings()
    if s.scanner == "clamd":
        return ClamdScanner(s.clamd_host, s.clamd_port)
    return EicarTestScanner()
