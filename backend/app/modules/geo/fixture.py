"""Load the committed SYNTHETIC geography fixture (tests, E2E, local development only).

The fixture lives in ``tests/fixtures/geo`` (see its README): two snapshots in the published LGD
and India Post layouts, with a rename, a split and an unmatched PIN district. Refused in
production, so it can never be mistaken for reference data.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.geo import importer

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "geo"
SNAPSHOTS = ("2026-02", "2026-05")


def _f(path: Path) -> tuple[Path, str]:
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def load(db: Session, until: str = "2026-05", operator: str = "fixture") -> None:
    if get_settings().env == "production":
        raise importer.ImportRefused("the synthetic geography fixture is never loaded in production")
    for snap in SNAPSHOTS:
        if snap > until:
            break
        d = FIXTURE_DIR / snap
        stage1 = [_f(d / n) for n in ("states.csv", "districts.csv", "subdistricts.csv")]
        importer.import_files(
            db, stage=1, snapshot=snap, files=stage1, operator=operator, source_url="synthetic fixture"
        )
        stage2 = [_f(p) for p in (d / "villages_9.csv", d / "urban_9.csv") if p.exists()]
        succ = d / "successors.csv"
        importer.import_files(
            db,
            stage=2,
            snapshot=snap,
            state="9",
            files=stage2,
            successors_file=_f(succ) if succ.exists() else None,
            operator=operator,
            source_url="synthetic fixture",
        )
        importer.import_files(
            db,
            stage=3,
            snapshot=snap,
            files=[_f(d / "pincodes.csv")],
            operator=operator,
            source_url="synthetic fixture",
        )
        # the fixture's split retires 1 of 6 villages: a "large change" by design
        importer.activate(db, snap, operator=operator, accept_large_change=True)
