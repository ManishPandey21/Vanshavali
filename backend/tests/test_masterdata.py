"""Master data vocabularies (ADR-0018): packs, loader, search, family entries, references, authz."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from app.core.config import get_settings
from app.models import AuditEvent, TreeVocabularyTerm, VocabularyTerm
from app.models.enums import VocabularyTermStatus
from app.modules.masterdata.loader import PackError, load_packs, read_packs, validate_pack
from app.modules.masterdata.match import loose_key, same_value
from tests.conftest import new_tree, owner_session
from tests.helpers import create_person, link


@pytest.fixture
def vocab() -> list[dict[str, Any]]:
    packs = read_packs()
    with owner_session() as db:
        load_packs(db, packs)
    return packs


def _codes(resp: Any) -> list[str]:
    assert resp.status_code == 200, resp.text
    return [t["code"] for t in resp.json()["items"]]


# ---------------------------------------------------------------- packs and loader
def test_every_shipped_pack_is_valid_and_bilingual():
    packs = read_packs()
    assert {p["key"] for p in packs} == {
        "gotra",
        "kula",
        "kuladevata",
        "kuladevi",
        "occupation",
        "honorific",
        "language",
    }
    for p in packs:
        for t in p["terms"]:
            assert t["labels"]["en"].strip() and t["labels"]["hi"].strip(), (p["key"], t["code"])
    language = next(p for p in packs if p["key"] == "language")
    assert len(language["terms"]) == 23  # English + the 22 Eighth-Schedule languages
    assert language["allows_custom"] is False
    # sensitive identity fields deliberately have no vocabulary (ADR-0018 §2)
    assert not {"community", "jati", "religion"} & {p["key"] for p in packs}


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda p: p["terms"][0]["labels"].pop("hi"), "no hi label"),
        (lambda p: p["terms"].append(copy.deepcopy(p["terms"][0])), "duplicate code"),
        (lambda p: p["terms"][0].update(status="approved"), "bad status"),
        (lambda p: p["terms"][0].update(gotra_of_surname="Iyer"), "unknown fields"),
        (lambda p: p["terms"][0].update(code="Bad Code"), "bad code"),
        (lambda p: p.pop("licence"), "missing licence"),
    ],
)
def test_malformed_packs_are_rejected(mutate, message):
    pack = copy.deepcopy(next(p for p in read_packs() if p["key"] == "gotra"))
    mutate(pack)
    with pytest.raises(PackError, match=message):
        validate_pack(pack)


def test_loader_is_idempotent_and_retires_instead_of_deleting():
    packs = read_packs()
    with owner_session() as db:
        first = load_packs(db, packs)
        assert first.inserted == sum(len(p["terms"]) for p in packs)
        again = load_packs(db, packs)
        assert (again.inserted, again.updated, again.retired) == (0, 0, 0)

        changed = copy.deepcopy(packs)
        gotra = next(p for p in changed if p["key"] == "gotra")
        gotra["terms"] = [t for t in gotra["terms"] if t["code"] != "kaushika"]
        gotra["terms"][0]["aliases"].append("Kasyap")
        report = load_packs(db, changed)
        assert (report.updated, report.retired) == (1, 1)
        kaushika = db.query(VocabularyTerm).filter_by(vocabulary_key="gotra", code="kaushika").one()
        assert kaushika.status == VocabularyTermStatus.RETIRED  # kept so stored references still resolve

        dry = load_packs(db, packs, dry_run=True)
        assert dry.updated == 2  # kaushika back from retired, aliases restored
        db.expire_all()
        assert (
            db.query(VocabularyTerm).filter_by(vocabulary_key="gotra", code="kaushika").one().status
            == VocabularyTermStatus.RETIRED
        )


def test_loose_key_matches_spellings_but_keeps_different_gotras_apart():
    for a, b in [
        ("Bhardwaj", "भरद्वाज"),
        ("Sandilya", "शाण्डिल्य"),
        ("Vasishtha", "वशिष्ठ"),
        ("Kashyap", "कश्यप"),
    ]:
        assert same_value(a, b), (a, b)
    for a, b in [("Kashyap", "Kaushik"), ("Atri", "Agastya"), ("Garg", "Gautam")]:
        assert not same_value(a, b), (a, b)
    assert loose_key("") == ""


# ---------------------------------------------------------------- global API
def test_global_vocabularies_need_sign_in(client, vocab):
    assert client.get("/vocabularies").status_code == 401
    assert client.get("/vocabularies/gotra").status_code == 401


def test_search_in_any_script_spelling_or_alias(owner, vocab):
    keys = {v["key"] for v in owner.get("/vocabularies").json()}
    assert keys == {p["key"] for p in vocab}
    assert _codes(owner.get("/vocabularies/gotra", params={"q": "भरद्वाज"})) == ["bharadwaja"]
    assert _codes(owner.get("/vocabularies/gotra", params={"q": "Bhardwaj"})) == ["bharadwaja"]
    assert _codes(owner.get("/vocabularies/gotra", params={"q": "sandil"})) == ["shandilya"]
    assert "kashyapa" in _codes(owner.get("/vocabularies/gotra", params={"q": "kash"}))
    assert _codes(owner.get("/vocabularies/occupation", params={"q": "kisan"})) == ["agriculture"]
    r = owner.get("/vocabularies/honorific", params={"q": "shrimati", "lang": "hi"}).json()
    assert r["items"][0]["label"] == "श्रीमती"
    assert owner.get("/vocabularies/nope").status_code == 404
    assert owner.get("/vocabularies/gotra", params={"lang": "x; drop"}).status_code == 422


def test_retired_terms_are_hidden_unless_asked_for(owner, vocab):
    with owner_session() as db:
        db.query(VocabularyTerm).filter_by(vocabulary_key="gotra", code="garga").update(
            {"status": VocabularyTermStatus.RETIRED}
        )
        db.commit()
    assert "garga" not in _codes(owner.get("/vocabularies/gotra"))
    assert "garga" in _codes(owner.get("/vocabularies/gotra", params={"include_retired": "true"}))


def test_disabled_flag_answers_404(owner, tree, vocab, monkeypatch):
    monkeypatch.setattr(get_settings(), "masterdata_enabled", False)
    assert owner.get("/vocabularies").status_code == 404
    assert owner.get(f"/trees/{tree['id']}/vocabularies/gotra").status_code == 404
    r = owner.post(f"/trees/{tree['id']}/vocabularies/kuladevata/terms", json={"label": "Khandoba"})
    assert r.status_code == 404


# ---------------------------------------------------------------- family entries
def test_family_entry_is_tree_private_and_deduplicated(owner, tree, vocab, member_factory):
    t = tree["id"]
    r = owner.post(
        f"/trees/{t}/vocabularies/kuladevata/terms", json={"label": "Khandoba", "aliases": ["खंडोबा"]}
    )
    assert r.status_code == 201, r.text
    term = r.json()["term"]
    assert term["origin"] == "family" and term["code"].startswith("t:") and r.json()["created"] is True
    # the same deity written another way is the same entry, not a duplicate
    again = owner.post(f"/trees/{t}/vocabularies/kuladevata/terms", json={"label": "खंडोबा"})
    assert again.status_code == 200 and again.json()["created"] is False
    assert again.json()["term"]["code"] == term["code"]
    # a label that names a global term returns the global term
    g = owner.post(f"/trees/{t}/vocabularies/gotra/terms", json={"label": "Bhardwaj"})
    assert g.status_code == 200 and g.json()["term"] == {
        **g.json()["term"],
        "code": "bharadwaja",
        "origin": "global",
    }

    assert _codes(owner.get(f"/trees/{t}/vocabularies/kuladevata", params={"q": "khand"})) == [term["code"]]
    viewer = member_factory(["VIEWER"])
    assert _codes(viewer.get(f"/trees/{t}/vocabularies/kuladevata")) == [term["code"]]

    # another family never sees it, and a stranger cannot read this tree's list
    other = new_tree(owner, "Other family")
    assert _codes(owner.get(f"/trees/{other['id']}/vocabularies/kuladevata")) == []
    assert _codes(owner.get("/vocabularies/kuladevata")) == []  # never leaks into the global list
    with owner_session() as db:
        ev = db.query(AuditEvent).filter_by(action="vocabulary.family_term_added").one()
        assert "Khandoba" not in str(ev.details)  # the value is family data; only the fact is audited


def test_family_entry_permissions(owner, tree, vocab, member_factory, make_client):
    t = tree["id"]
    viewer = member_factory(["VIEWER"])
    assert (
        viewer.post(f"/trees/{t}/vocabularies/kuladevata/terms", json={"label": "Khandoba"}).status_code
        == 403
    )
    contributor = member_factory(["CONTRIBUTOR"], name="Contributor")
    assert (
        contributor.post(f"/trees/{t}/vocabularies/kuladevata/terms", json={"label": "Khandoba"}).status_code
        == 201
    )
    # closed list
    r = owner.post(f"/trees/{t}/vocabularies/language/terms", json={"label": "Tulu"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "vocabulary_closed"
    # blank label
    assert owner.post(f"/trees/{t}/vocabularies/kuladevata/terms", json={"label": "   "}).status_code == 422
    # a non-member gets nothing (404, tree not revealed)
    outsider = make_client()
    outsider.register(name="Outsider")
    assert outsider.get(f"/trees/{t}/vocabularies/kuladevata").status_code == 404
    assert outsider.post(f"/trees/{t}/vocabularies/kuladevata/terms", json={"label": "X"}).status_code == 404


def test_family_entries_are_rls_isolated(owner, tree, vocab):
    a = owner.post(f"/trees/{tree['id']}/vocabularies/kuladevata/terms", json={"label": "Khandoba"}).json()
    other = new_tree(owner, "Other family")
    owner.post(f"/trees/{other['id']}/vocabularies/kuladevata/terms", json={"label": "Tulja Bhavani"})
    with owner_session() as db:
        assert db.query(TreeVocabularyTerm).count() == 2
    assert [x["code"] for x in owner.get(f"/trees/{tree['id']}/vocabularies/kuladevata").json()["items"]] == [
        a["term"]["code"]
    ]


# ---------------------------------------------------------------- stored references (heritage)
def test_heritage_value_references_a_real_entry(owner, tree, vocab):
    t = tree["id"]
    p = create_person(owner, t, "Ramesh", "Sharma")
    url = f"/trees/{t}/people/{p['id']}/heritage"
    ok = owner.post(
        url,
        json={
            "attribute": "gotra",
            "value_text": "Bhardwaj",
            "value_json": {"vocabulary": "gotra", "code": "bharadwaja"},
        },
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["value_text"] == "Bhardwaj"  # the label as entered is what is stored and shown

    fam = owner.post(f"/trees/{t}/vocabularies/kuladevata/terms", json={"label": "Khandoba"}).json()["term"]
    r = owner.post(
        url,
        json={
            "attribute": "kuladevata",
            "value_text": "Khandoba",
            "value_json": {"vocabulary": "kuladevata", "code": fam["code"]},
        },
    )
    assert r.status_code == 201, r.text

    bad = [
        {"vocabulary": "gotra", "code": "made_up"},
        {"vocabulary": "gotra"},
        {"vocabulary": "nope", "code": "x"},
    ]
    for value_json in bad:
        r = owner.post(url, json={"attribute": "gotra", "value_text": "X", "value_json": value_json})
        assert r.status_code == 422, (value_json, r.text)
    # a reference without its label is refused (nothing is filled in from the list)
    r = owner.post(
        url, json={"attribute": "gotra", "value_json": {"vocabulary": "gotra", "code": "kashyapa"}}
    )
    assert r.status_code == 422

    # another tree's family entry cannot be referenced
    other = new_tree(owner, "Other family")
    q = create_person(owner, other["id"], "Suresh", "Patil")
    r = owner.post(
        f"/trees/{other['id']}/people/{q['id']}/heritage",
        json={
            "attribute": "kuladevata",
            "value_text": "Khandoba",
            "value_json": {"vocabulary": "kuladevata", "code": fam["code"]},
        },
    )
    assert r.status_code == 422

    # a retired term keeps resolving for existing and new references
    with owner_session() as db:
        db.query(VocabularyTerm).filter_by(vocabulary_key="gotra", code="bharadwaja").update(
            {"status": VocabularyTermStatus.RETIRED}
        )
        db.commit()
    prof = owner.get(url).json()
    gotra = next(a for a in prof["attributes"] if a["attribute"] == "gotra")
    shown = [gotra["preferred"], *gotra["alternatives"]]
    assert any(v and v["value_text"] == "Bhardwaj" and v["value_json"]["code"] == "bharadwaja" for v in shown)


def test_vocabularies_never_infer_a_value(owner, tree, vocab):
    t = tree["id"]
    p = create_person(owner, t, "Ramesh", "Kashyap", status="living")
    q = create_person(owner, t, "Suresh", "Bhardwaj", status="living")
    link(owner, t, p["id"], q["id"], "biological_parent")
    owner.post(f"/trees/{t}/vocabularies/kuladevata/terms", json={"label": "Khandoba"})
    for person in (p, q):
        assert owner.get(f"/trees/{t}/people/{person['id']}/heritage").json()["attributes"] == []
