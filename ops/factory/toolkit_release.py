#!/usr/bin/env python3
"""Build and verify the Infra Code Factory release this repository has reviewed (ADR-0029/0030).

The toolkit is not vendored (it must stay outside builders' write scope), and its own SHA256SUMS
proves nothing about a modified copy. So the reviewed upgrade is kept here as *source*: the
pinned upstream archive (``BASE_ARCHIVE_SHA256``) plus a reviewed patch
(``toolkit/infra-code-factory-<base>-to-<version>.patch``). ``build`` reproduces the release from
those two and checks every hash; ``verify`` checks an extracted toolkit directory:

    python3 ops/factory/toolkit_release.py build --archive ~/Downloads/infra-code-factory-v0.3.3.zip --out ~/tools/infra-code-factory-0.3.4
    python3 ops/factory/toolkit_release.py verify --toolkit ~/tools/infra-code-factory-0.3.4

A toolkit passes only if its SHA256SUMS lists exactly the files present (and no bytecode),
every listed hash matches, and its runtime files match ``TOOLKIT_SHA256`` in configure_factory.py.

About 0.3.3's own manifest: it is the 0.3.1 list. Its four mismatches (CHANGELOG.md, README.md,
factory.py, tests/test_regressions_v031.py) are exactly the files 0.3.2 and 0.3.3 changed; the
reviewed 0.3.3 runtime hashes are pinned below (``BASE_RUNTIME_SHA256``) and are what ``build``
checks. The 0.3.4 manifest is regenerated from the reviewed tree, so ``verify`` holds it to the rule.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
BASE_VERSION = "0.3.3"
BASE_ARCHIVE_SHA256 = "1247c45bf63b072e878c394f19958bc5bbcd2d0c632573aa22f648f23ddf4884"
BASE_ROOT = "infra-code-factory"
# Reviewed 0.3.3 runtime files (commit 33476e3); the archive's own manifest is stale for these.
BASE_RUNTIME_SHA256 = {
    "factory.py": "188bd15b7bc3b37b2383fdb7adf5306d37db411d8786b549abca9ee1aff2de76",
    "verification_policy.py": "a984427a17e4e3636fe2a3bf054d9da7b226058d55e5d7f0bfbc2617fdabfcd6",
    "cold_workspace.py": "2f687c221d1b0226b5a9c3976967cba367bd7df2e2edb53fa80b31f1c3fa0faf",
    "test_report.py": "192b01fb39c01fda0a384d165df31c4a070a7d37347d2b4c9f2d50dabc9b67da",
    "agent_bridge.py": "365e7de1ed686c731e0fcddb6ec2e5fa610e398f0cf9f9745af33c94abca0c04",
}
MANIFEST = "SHA256SUMS"


class ReleaseError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def target() -> tuple[str, dict[str, str]]:
    """(version, runtime pins) from configure_factory.py: one source of truth for what is trusted."""
    spec = importlib.util.spec_from_file_location("vsh_configure_factory", HERE / "configure_factory.py")
    if spec is None or spec.loader is None:
        raise ReleaseError("cannot load configure_factory.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TOOLKIT_VERSION, dict(module.TOOLKIT_SHA256)


def patch_path(version: str) -> Path:
    return HERE / "toolkit" / f"infra-code-factory-{BASE_VERSION}-to-{version}.patch"


def tree_files(root: Path) -> list[str]:
    files = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if "__pycache__" in rel.parts or path.suffix in (".pyc", ".pyo"):
            # Python may load cached bytecode instead of the reviewed source
            raise ReleaseError(
                f"{rel} is compiled bytecode; remove it (find DIR -name __pycache__ -exec rm -rf {{}} +) "
                "and run the toolkit with PYTHONDONTWRITEBYTECODE=1"
            )
        if path.is_dir():
            continue
        if path.is_symlink():
            raise ReleaseError(f"{rel} is a symlink; a release contains regular files only")
        files.append(rel.as_posix())
    return files


def check_runtime(root: Path, pins: dict[str, str], label: str) -> None:
    for name, digest in pins.items():
        path = root / name
        if not path.is_file() or sha256(path) != digest:
            raise ReleaseError(f"{label}: {name} is not the reviewed file (see the pinned SHA-256)")


def verify(root: Path, pins: dict[str, str] | None = None) -> None:
    """Manifest lists exactly the files present, every hash matches, runtime files are the pinned ones."""
    if pins is None:
        _, pins = target()
    manifest = root / MANIFEST
    if not manifest.is_file():
        raise ReleaseError(f"{root} has no {MANIFEST}")
    listed: dict[str, str] = {}
    for n, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        digest, sep, name = line.partition("  ")
        if not sep or len(digest) != 64:
            raise ReleaseError(f"{MANIFEST}:{n} is not a sha256sum line")
        listed[name] = digest
    present = set(tree_files(root)) - {MANIFEST}
    if missing := sorted(set(listed) - present):
        raise ReleaseError(f"listed in {MANIFEST} but missing: {', '.join(missing)}")
    if unlisted := sorted(present - set(listed)):
        raise ReleaseError(f"present but not in {MANIFEST}: {', '.join(unlisted)}")
    if wrong := sorted(name for name, digest in listed.items() if sha256(root / name) != digest):
        raise ReleaseError(f"{MANIFEST} mismatch (modified or stale manifest): {', '.join(wrong)}")
    check_runtime(root, pins, "toolkit")


def safe_extract(archive: Path, dest: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            name = PurePosixPath(info.filename)
            if name.is_absolute() or ".." in name.parts or "\\" in info.filename:
                raise ReleaseError(f"unsafe path in archive: {info.filename}")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ReleaseError(f"symlink in archive: {info.filename}")
        zf.extractall(dest)  # every member checked above


def build(
    archive: Path,
    out: Path,
    version: str | None = None,
    pins: dict[str, str] | None = None,
    patch: Path | None = None,
) -> Path:
    if version is None or pins is None:
        version, pins = target()
    patch = patch or patch_path(version)
    if out.exists():
        raise ReleaseError(f"{out} already exists; choose a new directory")
    if sha256(archive) != BASE_ARCHIVE_SHA256:
        raise ReleaseError(f"{archive} is not the reviewed Infra Code Factory {BASE_VERSION} archive")
    if not patch.is_file():
        raise ReleaseError(f"reviewed patch {patch.name} is missing")
    with tempfile.TemporaryDirectory(prefix="icf-release-") as tmp:
        safe_extract(archive, Path(tmp))
        root = Path(tmp) / BASE_ROOT
        check_runtime(root, BASE_RUNTIME_SHA256, f"{BASE_VERSION} archive")
        applied = subprocess.run(  # noqa: S603 (fixed argv; the patch is a reviewed repository file)
            ["git", "apply", "--whitespace=nowarn", str(patch)],  # noqa: S607 (git from PATH, fixed argv)
            cwd=root,
            capture_output=True,
            text=True,
        )
        if applied.returncode:
            raise ReleaseError(f"{patch.name} does not apply to {BASE_VERSION}: {applied.stderr.strip()}")
        verify(root, pins)
        shutil.move(str(root), str(out))
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="action", required=True)
    b = sub.add_parser("build", help="reproduce the reviewed release from the pinned archive + patch")
    b.add_argument("--archive", required=True, type=Path)
    b.add_argument("--out", required=True, type=Path)
    v = sub.add_parser("verify", help="check an extracted toolkit against its manifest and the pins")
    v.add_argument("--toolkit", required=True, type=Path)
    a = p.parse_args(argv)
    try:
        if a.action == "build":
            out = build(a.archive.expanduser().resolve(), a.out.expanduser().resolve())
            print(f"built and verified Infra Code Factory {target()[0]} at {out}")
        else:
            verify(a.toolkit.expanduser().resolve())
            print(f"{a.toolkit}: manifest consistent and runtime files match the reviewed pins")
        return 0
    except ReleaseError as exc:
        print(f"toolkit_release: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
