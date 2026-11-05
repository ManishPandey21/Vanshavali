"""The threat model's IDs (T1, T2, …) are referenced from PRs, ADRs and reviews, so each must be
unique. Several pull requests can add threats at the same time and pick the same next number; this
test fails the second one instead of letting two different threats share an ID."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

THREAT_MODEL = Path(__file__).resolve().parents[2] / "docs" / "security" / "threat-model.md"
ROW = re.compile(r"^\|\s*(T\d+)\s*\|", re.MULTILINE)


def threat_ids(text: str) -> list[str]:
    return ROW.findall(text)


def duplicates(ids: list[str]) -> list[str]:
    return sorted((i for i, n in Counter(ids).items() if n > 1), key=lambda i: int(i[1:]))


def test_threat_ids_are_unique():
    ids = threat_ids(THREAT_MODEL.read_text(encoding="utf-8"))
    assert ids, "no threat rows found: has the table format changed?"
    assert duplicates(ids) == [], f"duplicate threat IDs in {THREAT_MODEL.name}: renumber the newer entry"


def test_the_check_catches_a_duplicate_and_allows_gaps():
    table = "| T1 | S | a | b | c |\n| T3 | I | a | b | c |\n| T3 | E | a | b | c |\n"
    assert threat_ids(table) == ["T1", "T3", "T3"]
    assert duplicates(threat_ids(table)) == ["T3"]
    # a gap (T2 missing, e.g. reserved by another open PR) is fine
    assert duplicates(threat_ids(table.replace("| T3 | E", "| T4 | E"))) == []
