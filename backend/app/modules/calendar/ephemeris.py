"""The JPL DE440s ephemeris file used by the calendar engine (ADR-0022 §1).

The file is not in git (32 MB). It is downloaded from NASA JPL and accepted only if its SHA-256
matches the pinned value, by the CLI (``python -m app.cli.calendar fetch-ephemeris``) or, in the
image build, by running this file directly: ``python ephemeris.py fetch <dest>``. Standard library
only, so the Dockerfile can use it before the application is installed.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

URL = "https://ssd.jpl.nasa.gov/ftp/eph/planets/bsp/de440s.bsp"
SHA256 = "c1c7feeab882263fc493a9d5a5b2ddd71b54826cdf65d8d17a76126b260a49f2"
NAME = "de440s"
SIZE = 32_726_016


class EphemerisError(RuntimeError):
    pass


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(path: Path) -> None:
    if not path.is_file():
        raise EphemerisError(f"ephemeris not found at {path}")
    digest = sha256_of(path)
    if digest != SHA256:
        raise EphemerisError(f"ephemeris checksum mismatch at {path}: {digest}")


def fetch(dest: Path, url: str = URL) -> Path:
    """Download to ``dest`` (atomically), verifying size and checksum; a valid file is kept."""
    dest = Path(dest)
    if dest.is_file():
        try:
            verify(dest)
            return dest
        except EphemerisError:
            pass
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=".de440s-")
    try:
        with os.fdopen(fd, "wb") as out, urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 -- pinned https URL
            shutil.copyfileobj(resp, out, length=1 << 20)
        tmp_path = Path(tmp)
        if tmp_path.stat().st_size != SIZE:
            raise EphemerisError(f"unexpected ephemeris size {tmp_path.stat().st_size}")
        verify(tmp_path)
        tmp_path.chmod(0o644)  # mkstemp makes it 0600; the app runs as another user in the image
        tmp_path.replace(dest)
        return dest
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


if __name__ == "__main__":  # image build: python ephemeris.py fetch /app/ephemeris/de440s.bsp
    if len(sys.argv) != 3 or sys.argv[1] != "fetch":
        sys.exit("usage: ephemeris.py fetch <dest>")
    print(fetch(Path(sys.argv[2])))
