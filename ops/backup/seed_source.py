"""Seed the drill's *source* database: demo tree, a synthetic tree, and one STANDARD + one VAULT document.

Called by ops/backup/drill.sh (step "seed"). Reads the target database and storage directory from
the usual VSH_DATABASE_URL / VSH_STORAGE_LOCAL_PATH variables, and writes a manifest (JSON) that
verify.py uses: the login credentials and the ids and checksums of the uploaded documents.

    cd backend && VSH_DATABASE_URL=... VSH_STORAGE_LOCAL_PATH=... \
        uv run python ../ops/backup/seed_source.py --people 2000 --manifest /tmp/manifest.json

All people are fictional; the images are random noise.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))


def _png() -> bytes:
    from PIL import Image

    img = Image.frombytes("RGB", (64, 64), os.urandom(64 * 64 * 3))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--people", type=int, default=2000, help="size of the extra synthetic tree (0 to skip)")
    ap.add_argument("--email", default="demo@example.com")
    ap.add_argument("--password", default="demo-password-123")
    ap.add_argument("--manifest", type=Path, required=True)
    args = ap.parse_args(argv)

    from fastapi.testclient import TestClient

    from app.cli.benchmark import build
    from app.cli.seed_demo import seed
    from app.main import create_app

    tree_id = seed(args.email, args.password)
    if args.people:
        build(args.people)

    client = TestClient(create_app())
    r = client.post("/api/v1/auth/login", json={"email": args.email, "password": args.password})
    r.raise_for_status()
    client.headers["X-CSRF-Token"] = client.cookies.get("vsh_csrf") or ""
    docs = []
    for category, title in (
        ("photo", "Drill photo (STANDARD)"),
        ("birth_certificate", "Drill certificate (VAULT)"),
    ):
        data = _png()
        r = client.post(
            f"/api/v1/trees/{tree_id}/documents",
            data={"category": category, "title": title},
            files={"file": (f"{category}.png", data, "image/png")},
        )
        if r.status_code != 201:
            raise SystemExit(f"upload {category} failed: {r.status_code} {r.text[:300]}")
        body = r.json()
        docs.append({"id": body["id"], "category": category, "storage_class": body.get("storage_class")})
    manifest = {"email": args.email, "password": args.password, "tree_id": tree_id, "documents": docs}
    args.manifest.write_text(json.dumps(manifest, indent=2))
    print(f"seeded source: tree {tree_id}, documents {[d['storage_class'] for d in docs]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
