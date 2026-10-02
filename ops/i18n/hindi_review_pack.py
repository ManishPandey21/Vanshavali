"""Build the Hindi review pack (docs/localization/hindi-review-checklist.md).

    cd backend && uv run python ../ops/i18n/hindi_review_pack.py

Writes one CSV per priority group into docs/localization/hindi-review/. Each row pairs the English
source with the current Hindi text. Every user-facing Hindi string appears exactly once:
- the SPA locale (frontend/src/i18n/locales/hi.json);
- the kinship terms (frontend/src/lib/kinship.ts);
- the server-owned consent statements;
- the account emails.

Blank columns are left for the reviewer. Re-run it after any wording change: rows keep their
`source` + `key`, so a reviewer can diff the new pack against the reviewed one.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
OUT = ROOT / "docs/localization/hindi-review"

COLUMNS = [
    "priority",
    "area",
    "source",
    "key",
    "english",
    "hindi",
    "legal_review",
    "language_ok (yes/no)",
    "suggested_hindi",
    "reviewer",
    "notes",
]

# (priority, area, legal review?, key patterns) — first match wins
GROUPS: list[tuple[int, str, bool, list[str]]] = [
    (
        1,
        "consent",
        True,
        [
            r"^consent\.",
            r"^onboarding\.",
            r"^claimLink\.",
            r"^claimInvite\.",
            r"^claim\.",
            r"^claims\.",
            r"^erase\.",
            r"^enum\.consent",
        ],
    ),
    (
        2,
        "privacy",
        True,
        [
            r"^privacy\.",
            r"^enum\.privacy",
            r"^enum\.publicMode",
            r"^share\.",
            r"^public\.",
            r"^landing\..*(privacy|private|consent|data|safe|secure|trust)",
            r"^grants\.",
            r"^enum\.grantPermission",
        ],
    ),
    (3, "registration", False, [r"^auth\.", r"^account\.", r"^invitations?\.", r"^invite\."]),
    (
        5,
        "relationships",
        False,
        [
            r"^kin\.",
            r"^enum\.(relType|siblingKind|lineage|householdRole|descentRule|"
            r"branchBasis)",
            r"^relationship\.",
            r"^relatives\.",
            r"^family\.",
            r"^jointFamily\.",
            r"^households\.",
            r"^branches\.",
        ],
    ),
    (
        6,
        "property",
        False,
        [
            r"^property\.",
            r"^partition\.",
            r"^enum\.(propertyType|classification|holderType|"
            r"interestType|interestStatus|propertyEventType|areaUnit)",
            r"^lineage\.",
        ],
    ),
    (
        7,
        "errors",
        False,
        [
            r"^errors\.",
            r"(error|Error|invalid|Invalid|failed|Failed|required|Required|"
            r"tooLarge|notAllowed|forbidden)",
        ],
    ),
]
LEGAL_KEY = re.compile(r"(legal|Legal|disclaimer|terms|dpdp|DPDP)")


def flatten(d: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(flatten(v, f"{prefix}{k}."))
        else:
            out[f"{prefix}{k}"] = str(v)
    return out


def classify(key: str) -> tuple[int, str, bool]:
    for prio, area, legal, patterns in GROUPS:
        if any(re.search(p, key) for p in patterns):
            return prio, area, legal or bool(LEGAL_KEY.search(key))
    return 8, "other", bool(LEGAL_KEY.search(key))


def rows() -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    loc = ROOT / "frontend/src/i18n/locales"
    en = flatten(json.loads((loc / "en.json").read_text(encoding="utf-8")))
    hi = flatten(json.loads((loc / "hi.json").read_text(encoding="utf-8")))
    for key in sorted(hi):
        prio, area, legal = classify(key)
        out.append(
            {
                "priority": prio,
                "area": area,
                "source": "frontend/src/i18n/locales/hi.json",
                "key": key,
                "english": en.get(key, ""),
                "hindi": hi[key],
                "legal_review": "yes" if legal else "",
            }
        )

    # Server-owned consent statements (shown verbatim; their SHA-256 is stored with each attestation)
    from app.modules.consent.statements import _STATEMENTS

    for kind, (version, texts) in _STATEMENTS.items():
        out.append(
            {
                "priority": 1,
                "area": "consent",
                "source": "backend/app/modules/consent/statements.py",
                "key": f"{kind.value}@{version}",
                "english": texts["en"],
                "hindi": texts["hi"],
                "legal_review": "yes",
            }
        )

    # Account emails (verification, existing-account notice, password reset)
    from app.modules.identity.emails import _copy

    for kind in ("verify", "exists", "reset"):
        en_c, hi_c = _copy(kind, "en", 48, 60), _copy(kind, "hi", 48, 60)
        for field in ("subject", "greeting", "action", "footer"):
            out.append(
                {
                    "priority": 4,
                    "area": "email",
                    "source": "backend/app/modules/identity/emails.py",
                    "key": f"{kind}.{field}",
                    "english": en_c[field],
                    "hindi": hi_c[field],  # type: ignore[literal-required]
                    "legal_review": "",
                }
            )
        for i, (e, h) in enumerate(zip(en_c["body"], hi_c["body"], strict=True)):
            out.append(
                {
                    "priority": 4,
                    "area": "email",
                    "source": "backend/app/modules/identity/emails.py",
                    "key": f"{kind}.body[{i}]",
                    "english": e,
                    "hindi": h,
                    "legal_review": "",
                }
            )

    # Regional kinship terms shown by the relationship calculator (no English source strings)
    kin = (ROOT / "frontend/src/lib/kinship.ts").read_text(encoding="utf-8")
    for chain, term in re.findall(r'^\s*"([a-z,]+)":\s*"([^"]+)"', kin, re.M):
        out.append(
            {
                "priority": 5,
                "area": "relationships",
                "source": "frontend/src/lib/kinship.ts",
                "key": chain,
                "english": " → ".join(chain.split(",")) + " (chain)",
                "hindi": term,
                "legal_review": "",
            }
        )
    # Any other Hindi written directly in SPA code (landing page words, month names, picker vocabularies)
    src = ROOT / "frontend/src"
    for path in sorted(src.rglob("*.ts*")):
        rel = path.relative_to(ROOT).as_posix()
        if (
            "/locales/" in rel
            or ".test." in rel
            or rel.endswith("schema.d.ts")
            or rel.endswith("lib/kinship.ts")
        ):
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search("[\u0900-\u097f]", line):
                vocab = "/masterData/" in rel  # typing-aid vocabularies (CLAUDE.md): spelling review only
                out.append(
                    {
                        "priority": 8 if vocab else 5 if "landing" in rel else 8,
                        "area": "inline-code",
                        "source": rel,
                        "key": f"line {n}",
                        "english": "",
                        "hindi": line.strip()[:300],
                        "legal_review": "",
                    }
                )
    return out


def main() -> int:
    data = rows()
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("p*.csv"):
        old.unlink()
    by_file: dict[str, list[dict[str, object]]] = {}
    for r in data:
        by_file.setdefault(f"p{r['priority']}-{r['area']}.csv", []).append(r)
    for name, items in sorted(by_file.items()):
        with open(OUT / name, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
            w.writeheader()
            for r in items:
                w.writerow({c: r.get(c, "") for c in COLUMNS})
    counts = Counter((r["priority"], r["area"]) for r in data)
    legal = Counter((r["priority"], r["area"]) for r in data if r["legal_review"])
    print("| Priority | Area | File | Strings | Legal review |")
    print("|---|---|---|---|---|")
    for (p, a), n in sorted(counts.items()):
        print(f"| {p} | {a} | `hindi-review/p{p}-{a}.csv` | {n} | {legal.get((p, a), 0)} |")
    print(f"| | **total** | | **{len(data)}** | **{sum(legal.values())}** |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
