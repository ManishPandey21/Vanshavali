"""Reference vocabularies (ADR-0019): seed data integrity, idempotent loading, LGD import, read-only API."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select

from app.models import Vocabulary, VocabularyTerm
from app.modules.astrology import vocab as jyotish
from app.modules.vocabulary.loader import (
    DATA_DIR,
    import_lgd_districts,
    import_lgd_subdistricts,
    load_vocabularies,
    read_documents,
)
from tests.conftest import owner_session


@pytest.fixture
def loaded() -> None:
    with owner_session() as db, db.begin():
        load_vocabularies(db)


def _docs() -> dict[str, dict[str, Any]]:
    return {d["code"]: d for d in read_documents()}


# --------------------------------------------------------------------------- seed data


def test_seed_files_are_well_formed():
    docs = _docs()
    for code, doc in docs.items():
        codes = [t["code"] for t in doc["terms"]]
        assert len(codes) == len(set(codes)), code
        for t in doc["terms"]:
            assert t["label"].strip(), (code, t["code"])
            assert len(t["code"]) <= 120 and len(t["label"]) <= 300
            if t.get("parent"):
                assert doc["parent_vocabulary"], (code, t["code"])


def test_jyotish_lists_come_from_the_validation_vocab():
    docs = _docs()
    assert [t["label"] for t in docs["nakshatra"]["terms"]] == list(jyotish.NAKSHATRAS)
    assert len(docs["nakshatra"]["terms"]) == 27
    assert [t["label"] for t in docs["rashi"]["terms"]] == list(jyotish.RASHIS)
    assert docs["rashi"]["terms"][0]["attributes"]["western_gloss"] == "Aries"
    assert docs["rashi"]["terms"][0]["labels"]["hi"] == "मेष"
    tithis = {t["code"]: t["attributes"] for t in docs["tithi"]["terms"]}
    assert tithis["purnima"] == {"paksha": "shukla", "number": 15}
    assert tithis["amavasya"] == {"paksha": "krishna", "number": 15}
    assert {t["code"] for t in docs["paksha"]["terms"]} == {"shukla", "krishna"}


def test_states_and_union_territories_of_india():
    current = [t for t in _docs()["state"]["terms"] if "historical" not in t.get("tags", [])]
    kinds = [t["tags"][0] for t in current]
    assert kinds.count("state") == 28 and kinds.count("union_territory") == 8
    lgd = [t["attributes"]["lgd_code"] for t in current]
    assert len(set(lgd)) == 36
    assert all(t["parent"] == "IN" and t["code"] == t["attributes"]["iso_3166_2"] for t in current)


def test_months_per_calendar():
    docs = _docs()
    calendars = {t["code"] for t in docs["calendar_system"]["terms"]}
    by_parent: dict[str, int] = {}
    for t in docs["month"]["terms"]:
        assert t["parent"] in calendars
        by_parent[t["parent"]] = by_parent.get(t["parent"], 0) + 1
    assert by_parent == {
        "gregorian": 12,
        "hindu_lunar": 13,  # + adhik maas
        "hijri": 12,
        "tamil_solar": 12,
        "bengali": 12,
        "kollam": 12,
        "nanakshahi": 12,
    }
    for t in docs["calendar_system"]["terms"]:
        if "months" in t["attributes"]:
            assert t["attributes"]["months"] in by_parent


def test_kin_term_paths_are_primitive_and_seniority_is_explicit():
    """ADR-0018: every kin term expands to parent/child/sibling/spouse steps; seniority only on siblings."""
    for t in _docs()["kin_term"]["terms"]:
        path = t["attributes"]["path"]
        assert 1 <= len(path) <= 3, t["code"]
        for step in path:
            assert step["rel"] in {"parent", "child", "sibling", "spouse"}
            assert step.get("sex") in {None, "male", "female"}
            if "seniority" in step:
                assert step["rel"] == "sibling" and step["seniority"] in {"elder", "younger"}
        has_seniority = any("seniority" in s for s in path)
        assert has_seniority == ("needs_seniority" in t["tags"]), t["code"]
    terms = {t["code"]: t["attributes"]["path"] for t in _docs()["kin_term"]["terms"]}
    assert terms["tau"] == [
        {"rel": "parent", "sex": "male"},
        {"rel": "sibling", "sex": "male", "seniority": "elder"},
    ]
    assert terms["mama"] == [{"rel": "parent", "sex": "female"}, {"rel": "sibling", "sex": "male"}]


def test_no_global_community_or_jati_vocabulary():
    """Q4 / ADR-0019: jati suggestions are tree-local only; there is no national caste list."""
    codes = set(_docs())
    assert not codes & {"jati", "caste", "community", "jati_or_subgroup"}


# --------------------------------------------------------------------------- loading


def test_load_is_idempotent_and_never_deletes(tmp_path: Path):
    data = tmp_path / "data"
    shutil.copytree(DATA_DIR, data)
    with owner_session() as db, db.begin():
        first = load_vocabularies(db, data)
        assert first.created > 800 and first.updated == 0
    with owner_session() as db, db.begin():
        again = load_vocabularies(db, data)
        assert (again.created, again.updated, again.deactivated) == (0, 0, 0)

    gotra = json.loads((data / "gotra.json").read_text())
    gotra["terms"] = [t for t in gotra["terms"] if t["code"] != "vatsa"]
    gotra["terms"][0]["aliases"].append("Agathiyar")
    (data / "gotra.json").write_text(json.dumps(gotra, ensure_ascii=False))
    with owner_session() as db, db.begin():
        third = load_vocabularies(db, data)
        # the alias edit, plus later terms whose list position moved up
        assert (third.created, third.deactivated) == (0, 1) and third.updated >= 1
    with owner_session() as db:
        vatsa = db.scalar(select(VocabularyTerm).where(VocabularyTerm.code == "vatsa"))
        assert vatsa is not None and vatsa.is_active is False
        agastya = db.scalar(select(VocabularyTerm).where(VocabularyTerm.code == "agastya"))
        assert agastya is not None and "agathiyar" in agastya.search_text


def test_search_text_covers_every_script(loaded: None):
    with owner_session() as db:
        t = db.scalar(select(VocabularyTerm).where(VocabularyTerm.code == "bharadwaja"))
        assert t is not None
        keys = t.search_text.split(" | ")
        assert "bharadwaja" in keys and "bhardwaj" in keys


_DISTRICTS_CSV = """District Details
S.No.,State Code,State Name (In English),District Code,District Name (In English),District Name (In Local language),Census 2011 Code
1,9,UTTAR PRADESH,118,AGRA,आगरा,146
2,9,UTTAR PRADESH,178,Prayagraj,प्रयागराज,162
3,27,Maharashtra,490,Pune,पुणे,521
4,99,Nowhere,1,Ghost,,0
"""

_SUBDISTRICTS_CSV = """S.No.,State Code,District Code,District Name (In English),Sub-District Code,Sub-District Name (In English),Sub-District Name (In Local language)
1,9,118,Agra,780,Etmadpur,एत्मादपुर
2,9,118,Agra,781,Kiraoli,किरावली
3,9,555,Unknown,999,Orphan,
"""


def test_lgd_import_links_districts_to_states(tmp_path: Path, loaded: None, client):
    d, s = tmp_path / "d.csv", tmp_path / "s.csv"
    d.write_text(_DISTRICTS_CSV, encoding="utf-8")
    s.write_text(_SUBDISTRICTS_CSV, encoding="utf-8")
    with owner_session() as db, db.begin():
        stats = import_lgd_districts(db, d)
        assert (stats.created, len(stats.skipped)) == (3, 1)
        sub = import_lgd_subdistricts(db, s)
        assert (sub.created, len(sub.skipped)) == (2, 1)
    with owner_session() as db, db.begin():  # re-import is a no-op
        assert import_lgd_districts(db, d).created == 0

    client.register()
    r = client.get("/vocabularies/district/terms", params={"parent": "IN-UP"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["label"] for i in items] == ["Agra", "Prayagraj"]  # upper-case LGD names tidied
    agra = items[0]
    assert agra["code"] == "lgd:118" and agra["parent_code"] == "IN-UP"
    assert agra["labels"] == {"native": "आगरा"}
    assert agra["attributes"] == {"lgd_code": "118", "census_2011_code": "146"}
    r = client.get("/vocabularies/sub_district/terms", params={"parent": "lgd:118", "q": "किरावली"})
    assert [i["label"] for i in r.json()["items"]] == ["Kiraoli"]


# --------------------------------------------------------------------------- API


def test_vocabulary_api_requires_sign_in(loaded: None, make_client):
    anon = make_client()
    assert anon.get("/vocabularies").status_code == 401
    r = anon.get("/vocabularies/gotra/terms", params={"q": "kash"})
    assert r.status_code == 401
    assert r.json()["error"]["code"]


def test_vocabulary_api_is_read_only(loaded: None, client):
    client.register()
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert client.request(method, "/vocabularies", json={}).status_code == 405
        assert client.request(method, "/vocabularies/gotra/terms", json={}).status_code == 405


def test_list_vocabularies(loaded: None, client):
    client.register()
    r = client.get("/vocabularies")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "private, max-age=3600"
    by_code = {v["code"]: v for v in r.json()}
    assert by_code["nakshatra"]["term_count"] == 27
    assert by_code["district"]["parent_vocabulary"] == "state"
    assert by_code["district"]["term_count"] == 0  # until an LGD download is imported


@pytest.mark.parametrize(
    ("vocabulary", "q", "first"),
    [
        ("gotra", "bhardwaj", "bharadwaja"),
        ("gotra", "भारद्वाज", "bharadwaja"),
        ("gotra", "KASHYAP", "kashyapa"),
        ("kin_term", "चाचा", "chacha"),
        ("kin_term", "tau", "tau"),
        ("month", "sawan", "hindu_lunar:shravana"),
        ("month", "Bhadon", "hindu_lunar:bhadrapada"),
        ("state", "orissa", "IN-OD"),
        ("country", "ceylon", "LK"),
        ("country", "भारत", "IN"),
        ("nakshatra", "thiruvathirai", "ardra"),
        ("rashi", "aries", "mesha"),
        ("language", "bangla", "bn"),
        ("tithi", "gyaras", "ekadashi"),
        ("script", "kaithi", "Kthi"),
    ],
)
def test_search_matches_aliases_and_scripts(loaded: None, client, vocabulary: str, q: str, first: str):
    client.register()
    r = client.get(f"/vocabularies/{vocabulary}/terms", params={"q": q})
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["code"] == first


def test_exact_name_ranks_before_prefix_and_fuzzy(loaded: None, client):
    client.register()
    items = client.get("/vocabularies/kin_term/terms", params={"q": "chacha"}).json()["items"]
    assert [i["code"] for i in items[:2]] == ["chacha", "chachi"]


def test_cascade_tag_and_pagination(loaded: None, client):
    client.register()
    r = client.get("/vocabularies/sampradaya/terms", params={"parent": "jain"})
    assert {i["code"] for i in r.json()["items"]} == {"shvetambara", "digambara", "sthanakvasi", "terapanthi"}
    assert all(i["parent_code"] == "jain" for i in r.json()["items"])

    r = client.get("/vocabularies/gotra/terms", params={"tag": "community:agrawal", "limit": 10})
    first = r.json()
    assert len(first["items"]) == 10 and first["next_cursor"]
    rest = client.get(
        "/vocabularies/gotra/terms",
        params={"tag": "community:agrawal", "limit": 10, "cursor": first["next_cursor"]},
    ).json()
    codes = [i["code"] for i in first["items"] + rest["items"]]
    assert len(codes) == len(set(codes)) == 18  # Agrawal's 18 gotras
    assert rest["next_cursor"] is None

    countries = client.get("/vocabularies/country/terms", params={"limit": 3}).json()["items"]
    assert [c["code"] for c in countries] == ["IN", "NP", "PK"]


def test_unknown_vocabulary_and_parent_are_structured_404s(loaded: None, client):
    client.register()
    r = client.get("/vocabularies/caste/terms")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert client.get("/vocabularies/district/terms", params={"parent": "IN-XX"}).status_code == 404
    assert client.get("/vocabularies/gotra/terms", params={"parent": "x"}).status_code == 404
    assert client.get("/vocabularies/gotra/terms", params={"q": "x" * 101}).status_code == 422
    assert client.get("/vocabularies/gotra/terms", params={"limit": 0}).status_code == 422


def test_inactive_terms_hidden_unless_asked(loaded: None, client):
    with owner_session() as db, db.begin():
        t = db.scalar(select(VocabularyTerm).where(VocabularyTerm.code == "vatsa"))
        assert t is not None
        t.is_active = False
    client.register()
    assert (
        client.get("/vocabularies/gotra/terms", params={"q": "vatsa"}).json()["items"][0]["code"] != "vatsa"
    )
    r = client.get("/vocabularies/gotra/terms", params={"q": "vatsa", "include_inactive": True})
    top = r.json()["items"][0]
    assert top["code"] == "vatsa" and top["is_active"] is False


def test_punctuation_only_query_lists_everything(loaded: None, client):
    client.register()
    r = client.get("/vocabularies/paksha/terms", params={"q": "%_.*"})
    assert r.status_code == 200 and len(r.json()["items"]) == 2


def test_vocabulary_rows_hold_no_tree_data():
    for model in (Vocabulary, VocabularyTerm):
        assert "tree_id" not in model.__table__.columns
    with owner_session() as db:
        assert db.scalar(select(func.count()).select_from(VocabularyTerm)) == 0  # tables truncated per test
