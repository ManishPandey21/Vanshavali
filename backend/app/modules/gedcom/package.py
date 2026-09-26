"""GEDCOM import packages: a GEDZIP (.gdz) or a .zip with one .ged and its photos (ADR-0013).

Nothing is ever extracted to disk. Members are read into memory one at a time with bounded reads,
and member names are only used to match GEDCOM ``FILE`` references, never as filesystem paths.
"""

from __future__ import annotations

import io
import posixpath
import re
import zipfile
from dataclasses import dataclass, field
from urllib.parse import unquote, urlparse

from app.core.errors import Unprocessable

ZIP_MAGIC = b"PK\x03\x04"
MAX_ENTRIES = 5000
MAX_RATIO = 100  # uncompressed : compressed; above this an entry is treated as a zip bomb
GEDCOM_SUFFIXES = (".ged", ".gedcom")
_ARCHIVE_SUFFIXES = (".zip", ".gdz", ".7z", ".rar", ".tar", ".gz", ".tgz")


def is_package(data: bytes) -> bool:
    return data[:4] == ZIP_MAGIC


def normalise_path(ref: str) -> str:
    """A GEDCOM FILE value or member name as a lower-case relative POSIX path.

    Handles ``file://`` URLs, percent-encoding (GEDZIP), Windows drive letters and backslashes
    (MyHeritage writes ``C:\\Users\\…\\Photos\\P1.jpg``) and leading slashes.
    """
    s = ref.strip()
    if s.lower().startswith("file:"):
        s = urlparse(s).path
    s = unquote(s).replace("\\", "/")
    s = re.sub(r"^[a-zA-Z]:/", "", s)
    s = posixpath.normpath("/" + s).lstrip("/")
    return s.lower()


def basename(ref: str) -> str:
    """The file name of a reference or member, in its original case (for display and titles)."""
    s = ref.strip()
    if s.lower().startswith("file:"):
        s = urlparse(s).path
    return posixpath.basename(unquote(s).replace("\\", "/"))


@dataclass
class Package:
    zf: zipfile.ZipFile
    gedcom_name: str
    members: dict[str, zipfile.ZipInfo] = field(default_factory=dict)  # normalised path → entry
    by_name: dict[str, list[str]] = field(default_factory=dict)  # file name → normalised paths
    ignored: int = 0

    def gedcom_bytes(self, max_bytes: int) -> bytes:
        return self._read(self.zf.getinfo(self.gedcom_name), max_bytes)

    def match(self, ref: str) -> tuple[str | None, str]:
        """(normalised member path or None, outcome: matched | missing | ambiguous)."""
        path = normalise_path(ref)
        if path in self.members:
            return path, "matched"
        candidates = self.by_name.get(posixpath.basename(path), [])
        if len(candidates) == 1:
            return candidates[0], "matched"
        if not candidates:
            return None, "missing"
        # several files share the name: use the one whose path ends like the reference, if unique
        suffix = [c for c in candidates if path.endswith("/" + c) or c.endswith("/" + path)]
        if len(suffix) == 1:
            return suffix[0], "matched"
        return None, "ambiguous"

    def read(self, member: str, max_bytes: int) -> bytes:
        return self._read(self.members[member], max_bytes)

    def _read(self, info: zipfile.ZipInfo, max_bytes: int) -> bytes:
        if info.file_size > max_bytes:
            raise Unprocessable(
                f"{posixpath.basename(info.filename)} is larger than the upload limit", code="file_too_large"
            )
        with self.zf.open(info) as fh:
            data = fh.read(max_bytes + 1)  # never trust the declared size alone
        if len(data) > max_bytes:
            raise Unprocessable(
                f"{posixpath.basename(info.filename)} is larger than the upload limit", code="file_too_large"
            )
        return data


def open_package(data: bytes, *, max_total_bytes: int) -> Package:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        infos = zf.infolist()
    except (zipfile.BadZipFile, ValueError) as exc:
        raise Unprocessable("The zip file is damaged or not a zip file", code="bad_package") from exc
    if len(infos) > MAX_ENTRIES:
        raise Unprocessable(f"The zip file has more than {MAX_ENTRIES} entries", code="package_too_large")
    total = sum(i.file_size for i in infos)
    if total > max_total_bytes:
        raise Unprocessable(
            "The zip file expands to more than the package limit",
            code="package_too_large",
            details={"max_bytes": max_total_bytes},
        )
    members: dict[str, zipfile.ZipInfo] = {}
    ignored = 0
    gedcoms: list[zipfile.ZipInfo] = []
    for info in infos:
        name = normalise_path(info.filename)
        if info.is_dir() or not name:
            continue
        top = name.split("/", 1)[0]
        if top == "__macosx" or posixpath.basename(name).startswith("._"):
            continue  # macOS resource forks
        if info.flag_bits & 0x1 or name.endswith(_ARCHIVE_SUFFIXES):
            ignored += 1  # encrypted or nested archives are never opened
            continue
        if info.compress_size and info.file_size / info.compress_size > MAX_RATIO:
            raise Unprocessable("The zip file looks like a zip bomb", code="package_rejected")
        if name.endswith(GEDCOM_SUFFIXES):
            gedcoms.append(info)
            continue
        members[name] = info
    if not gedcoms:
        raise Unprocessable("The zip file does not contain a .ged file", code="no_gedcom_in_package")
    root = [g for g in gedcoms if normalise_path(g.filename) == "gedcom.ged"]  # GEDZIP
    chosen = root or gedcoms
    if len(chosen) > 1:
        raise Unprocessable(
            "The zip file contains more than one .ged file; keep only the one to import",
            code="multiple_gedcom",
        )
    by_name: dict[str, list[str]] = {}
    for name in members:
        by_name.setdefault(posixpath.basename(name), []).append(name)
    return Package(zf=zf, gedcom_name=chosen[0].filename, members=members, by_name=by_name, ignored=ignored)
