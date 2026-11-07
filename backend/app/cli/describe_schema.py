"""Generate docs/architecture/data-model.md from the ORM metadata (the canonical schema).

Usage: uv run python -m app.cli.describe_schema > ../docs/architecture/data-model.md
"""

from __future__ import annotations

import sys

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from app.models import Base

GROUPS = {
    "Identity & access": [
        "app_user",
        "user_session",
        "tree",
        "tree_membership",
        "tree_invitation",
        "access_grant",
    ],
    "Genealogy": [
        "person",
        "name_record",
        "relationship",
        "event",
        "event_participant",
        "place",
        "merge_record",
        "relative_age_order",
    ],
    "Heritage & family structure": [
        "assertion",
        "family_branch",
        "branch_membership",
        "household",
        "household_membership",
    ],
    "Master data": ["vocabulary", "vocabulary_term", "tree_vocabulary_term"],
    "Geography reference (LGD, India Post)": ["geo_snapshot", "geo_unit", "geo_unit_alias", "pincode_office"],
    "Evidence": ["source", "citation"],
    "Documents & extraction": [
        "document",
        "document_metadata_version",
        "document_derivative",
        "document_link",
        "extraction_proposal",
        "event_media",
    ],
    "Reminders & notifications": [
        "notification_preference",
        "event_reminder",
        "notification_delivery",
        "notification_contact",
    ],
    "Visualization & exports": ["chart_preset", "render_job", "render_artifact"],
    "Astrology": ["astrology_profile"],
    "Property": ["property", "land_parcel", "property_interest", "property_event", "property_event_parcel"],
    "Privacy & consent": [
        "consent_record",
        "profile_claim",
        "profile_claim_invite",
        "family_data_attestation",
    ],
    "Interchange": ["import_job", "export_job", "gedcom_extension"],
    "Audit": ["audit_event"],
}


def main() -> int:
    tables = Base.metadata.tables
    out: list[str] = [
        "# Data model (generated)",
        "",
        "> Generated from the SQLAlchemy models by `uv run python -m app.cli.describe_schema`. **Do not edit by hand.**",
        "> The Alembic migrations in `backend/alembic/versions/` are the deployable form of this schema; "
        "`tests/test_migrations.py` asserts that the two are identical.",
        "",
        "Conventions: every tree-scoped table has `tree_id` and a `UNIQUE (tree_id, id)`; cross-entity foreign keys are "
        "composite `(tree_id, x_id) → target(tree_id, id)` so rows cannot reference another tree (ADR-0002). "
        "Genealogical dates are JSONB `GenealogicalDate` objects with derived `*_sort*` DATE columns (ADR-0003).",
        "",
    ]
    seen: set[str] = set()
    for group, names in GROUPS.items():
        out += [f"## {group}", ""]
        for name in names:
            t = tables.get(name)
            if t is None:
                continue
            seen.add(name)
            out += [f"### `{name}`", "", "| Column | Type | Null | Notes |", "|---|---|---|---|"]
            fk_cols: dict[str, str] = {}
            for c in t.constraints:
                if isinstance(c, ForeignKeyConstraint):
                    target = c.elements[0].target_fullname.split(".")[0]
                    for key in c.column_keys:
                        if key != "tree_id" or len(c.column_keys) == 1:
                            fk_cols[key] = f"→ {target}" + (
                                " (composite, same tree)" if len(c.column_keys) > 1 else ""
                            )
            for col in t.columns:
                notes = []
                if col.primary_key:
                    notes.append("PK")
                if col.name in fk_cols:
                    notes.append(fk_cols[col.name])
                if col.unique:
                    notes.append("unique")
                typ = str(col.type)
                if hasattr(col.type, "enums") and col.type.enums:
                    typ = (
                        "enum("
                        + ", ".join(col.type.enums[:8])
                        + (", …" if len(col.type.enums) > 8 else "")
                        + ")"
                    )
                out.append(
                    f"| `{col.name}` | {typ} | {'yes' if col.nullable else 'no'} | {'; '.join(notes)} |"
                )
            extras = []
            for c in t.constraints:
                if isinstance(c, UniqueConstraint) and len(c.columns) > 1:
                    extras.append(f"UNIQUE ({', '.join(col.name for col in c.columns)})")
                elif isinstance(c, CheckConstraint) and "IN (" not in str(c.sqltext):
                    extras.append(f"CHECK {c.sqltext}")
            for ix in t.indexes:
                extras.append(
                    f"INDEX {ix.name} ({', '.join(col.name for col in ix.columns)})"
                    + (" UNIQUE" if ix.unique else "")
                )
            if extras:
                out += ["", "Constraints/indexes: " + "; ".join(f"`{e}`" for e in extras)]
            out.append("")
    rest = sorted(set(tables) - seen)
    if rest:
        out += ["## Other", ""] + [f"- `{r}`" for r in rest] + [""]
    sys.stdout.write("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
