"""Load the reference vocabularies (ADR-0019) and, optionally, LGD district/sub-district downloads.

Usage (as the schema owner, after ``alembic upgrade head``):

    python -m app.cli.load_vocabularies
    python -m app.cli.load_vocabularies --lgd-districts districts.csv [--lgd-subdistricts subdistricts.csv]

Idempotent: re-running updates changed terms and deactivates removed ones (never deletes them).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.db import get_engine
from app.modules.vocabulary.loader import (
    LoadStats,
    import_lgd_districts,
    import_lgd_subdistricts,
    load_vocabularies,
)


def _report(what: str, s: LoadStats) -> None:
    print(
        f"{what}: {s.vocabularies} vocabularies, {s.created} created, {s.updated} updated, "
        f"{s.deactivated} deactivated, {len(s.skipped)} skipped"
    )
    for line in s.skipped[:20]:
        print(f"  skipped {line}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lgd-districts", type=Path, help="LGD district download (CSV)")
    p.add_argument("--lgd-subdistricts", type=Path, help="LGD sub-district download (CSV)")
    args = p.parse_args(argv)
    with Session(get_engine()) as db, db.begin():
        _report("vocabularies", load_vocabularies(db))
        if args.lgd_districts:
            _report("LGD districts", import_lgd_districts(db, args.lgd_districts))
        if args.lgd_subdistricts:
            _report("LGD sub-districts", import_lgd_subdistricts(db, args.lgd_subdistricts))


if __name__ == "__main__":
    main()
