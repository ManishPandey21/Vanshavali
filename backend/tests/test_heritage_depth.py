"""Heritage depth (ADR-0026 §2-§5, §8): pravara links, new attributes, temples, offers and curation.

Threat T46: an offered entry never carries the family's identity into the common list; only a
tree admin may offer, only for their own tree; curation is an operator action through the packs.
"""

from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path
from typing import Any

import pytest

from app.models import AuditEvent, TreeVocabularyTerm, UserNotification
from app.models.enums import OfferStatus
from app.modules.masterdata import curation
from app.modules.masterdata.loader import (
    PACK_DIR,
    PackError,
    load_packs,
    read_packs,
    validate_pack,
    validate_pack_set,
)
from tests.conftest import new_tree, owner_session
from tests.helpers import create_person


@pytest.fixture
def vocab() -> list[dict[str, Any]]:
    packs = read_packs()
    with owner_session() as db:
        load_packs(db, packs)
    return packs


def _codes(resp: Any) -> list[str]:
    assert resp.status_code == 200, resp.text
    return [t["code"] for t in resp.json()["items"]]


def _pravara() -> dict[str, Any]:
    return copy.deepcopy(next(p for p in read_packs() if p["key"] == "pravara"))


# ---------------------------------------------------------------- pravara pack
def test_every_pravara_link_is_draft_until_sourced_and_names_a_known_gotra():
    pack = _pravara()
    gotras = {t["code"] for p in read_packs() if p["key"] == "gotra" for t in p["terms"]}
    assert pack["terms"], "the pack ships draft links"
    for t in pack["terms"]:
        assert t["parent"] in gotras, t["code"]
        # nothing shipped claims a source it does not have
        if t.get("status", "draft") == "reviewed":
            assert t["attributes"]["source"] and t["attributes"]["reviewer"], t["code"]
        else:
            assert not t["attributes"].get("source") and not t["attributes"].get("reviewer"), t["code"]


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda t: t.update(status="reviewed"), "without a cited source"),
        (
            lambda t: (t.update(status="reviewed"), t["attributes"].update(source="Baudhayana SS")),
            "without a cited source",
        ),
        (lambda t: t.pop("parent"), "must name its gotra"),
    ],
)
def test_pravara_links_need_a_parent_and_a_source_to_be_reviewed(mutate, message):
    pack = _pravara()
    mutate(pack["terms"][0])
    with pytest.raises(PackError, match=message):
        validate_pack(pack)


def test_pravara_link_to_an_unknown_gotra_is_rejected():
    packs = copy.deepcopy(read_packs())
    pravara = next(p for p in packs if p["key"] == "pravara")
    pravara["terms"][0]["parent"] = "no_such_gotra"
    with pytest.raises(PackError, match="unknown gotra"):
        validate_pack_set(packs)


def test_gotra_suggests_only_reviewed_pravara_links(owner, vocab):
    # every shipped link is draft: nothing is suggested from the gotra yet ...
    assert (
        _codes(owner.get("/vocabularies/pravara", params={"parent": "kashyapa", "reviewed_only": "true"}))
        == []
    )
    # ... but every pravara stays searchable regardless of gotra
    assert "kashyapa_avatsara_naidhruva" in _codes(
        owner.get("/vocabularies/pravara", params={"q": "naidhruva"})
    )
    # a link reviewed with a cited source and a reviewer becomes a suggestion
    packs = copy.deepcopy(vocab)
    pravara = next(p for p in packs if p["key"] == "pravara")
    term = next(t for t in pravara["terms"] if t["code"] == "kashyapa_avatsara_naidhruva")
    term.update(status="reviewed")
    term["attributes"].update(source="Test source, ed. 1, p. 1", reviewer="Test reviewer")
    with owner_session() as db:
        load_packs(db, packs)
    got = owner.get("/vocabularies/pravara", params={"parent": "kashyapa", "reviewed_only": "true"})
    assert _codes(got) == ["kashyapa_avatsara_naidhruva"]
    assert (
        _codes(owner.get("/vocabularies/pravara", params={"parent": "atri", "reviewed_only": "true"})) == []
    )


def test_scope_filter_and_etag(owner, vocab):
    packs = copy.deepcopy(vocab)
    gotra = next(p for p in packs if p["key"] == "gotra")
    gotra["terms"][0]["scope"] = ["region:south"]
    with owner_session() as db:
        load_packs(db, packs)
    assert _codes(owner.get("/vocabularies/gotra", params={"scope": "region:south"})) == [
        gotra["terms"][0]["code"]
    ]

    first = owner.get("/vocabularies/gotra")
    etag = first.headers["etag"]
    assert etag.startswith('W/"')
    again = owner.get("/vocabularies/gotra", headers={"If-None-Match": etag})
    assert again.status_code == 304 and again.content == b""
    # another query has another validator
    assert owner.get("/vocabularies/gotra", params={"q": "kash"}).headers["etag"] != etag
    # a reloaded pack changes it
    gotra["version"] += 1
    gotra["terms"][1]["aliases"].append("Test alias")
    with owner_session() as db:
        load_packs(db, packs)
    assert owner.get("/vocabularies/gotra", headers={"If-None-Match": etag}).status_code == 200


# ---------------------------------------------------------------- new heritage attributes
def test_new_attributes_are_recorded_like_other_heritage_claims(owner, tree, vocab):
    t = tree["id"]
    p = create_person(owner, t, "Shivaji", "Pawar")
    url = f"/trees/{t}/people/{p['id']}/heritage"
    for body in (
        {"attribute": "devak", "value_text": "Panchpallav"},
        {
            "attribute": "ancestral_occupation",
            "value_text": "Farming",
            "value_json": {"vocabulary": "occupation", "code": "agriculture"},
        },
        {
            "attribute": "family_language",
            "value_text": "Marathi",
            "value_json": {"vocabulary": "language", "code": "mr"},
        },
        {
            "attribute": "family_language",
            "value_text": "Hindi",
            "value_json": {"vocabulary": "language", "code": "hi"},
        },
    ):
        r = owner.post(url, json=body)
        assert r.status_code == 201, r.text
    prof = owner.get(url).json()
    langs = next(a for a in prof["attributes"] if a["attribute"] == "family_language")
    # several family languages are normal, never shown as a disagreement
    assert 1 + len(langs["alternatives"]) == 2 and langs["disputed"] is False
    # a pravara is never filled in from the gotra
    owner.post(
        url,
        json={
            "attribute": "gotra",
            "value_text": "Kashyapa",
            "value_json": {"vocabulary": "gotra", "code": "kashyapa"},
        },
    )
    assert not any(a["attribute"] == "pravara" for a in owner.get(url).json()["attributes"])


def test_a_value_must_come_from_its_own_attributes_list(owner, tree, vocab):
    t = tree["id"]
    p = create_person(owner, t, "Asha", "Pawar")
    url = f"/trees/{t}/people/{p['id']}/heritage"
    r = owner.post(
        url,
        json={
            "attribute": "family_language",
            "value_text": "Kashyapa",
            "value_json": {"vocabulary": "gotra", "code": "kashyapa"},
        },
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_vocabulary_reference"
    r = owner.post(
        url,
        json={"attribute": "devak", "value_text": "x", "value_json": {"vocabulary": "devak", "code": "nope"}},
    )
    assert r.status_code == 422


def test_family_deity_may_name_a_temple_but_only_a_temple(owner, tree, vocab):
    t = tree["id"]
    p = create_person(owner, t, "Ramesh", "Jadhav")
    url = f"/trees/{t}/people/{p['id']}/heritage"
    temple = owner.post(
        f"/trees/{t}/places", json={"canonical_name": "Jejuri temple", "place_type": "temple"}
    ).json()
    village = owner.post(
        f"/trees/{t}/places", json={"canonical_name": "Jejuri", "place_type": "village"}
    ).json()
    r = owner.post(url, json={"attribute": "kuladevata", "value_text": "Khandoba", "place_id": village["id"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "place_not_temple"
    r = owner.post(url, json={"attribute": "kuladevata", "value_text": "Khandoba", "place_id": temple["id"]})
    assert r.status_code == 201, r.text
    a = r.json()
    assert (
        owner.patch(f"/trees/{t}/assertions/{a['id']}", json={"place_id": village["id"]}).status_code == 422
    )
    # the deity alone is a complete claim too
    assert owner.post(url, json={"attribute": "kuladevi", "value_text": "Tulja Bhavani"}).status_code == 201
    # a temple in another tree is not found
    other = new_tree(owner, "Other family")
    far = owner.post(
        f"/trees/{other['id']}/places", json={"canonical_name": "Far temple", "place_type": "temple"}
    ).json()
    assert (
        owner.post(
            url, json={"attribute": "kuladevi", "value_text": "Ambabai", "place_id": far["id"]}
        ).status_code
        == 404
    )


# ---------------------------------------------------------------- offers (T46)
def _family_term(
    client: Any, t: str, key: str, label: str, aliases: list[str] | None = None
) -> dict[str, Any]:
    r = client.post(f"/trees/{t}/vocabularies/{key}/terms", json={"label": label, "aliases": aliases or []})
    assert r.status_code == 201, r.text
    return r.json()["term"]


def test_only_a_tree_admin_offers_and_only_their_own_entries(owner, tree, vocab, member_factory):
    t = tree["id"]
    term = _family_term(owner, t, "kuladevata", "Khandoba", ["खंडोबा"])
    url = f"/trees/{t}/vocabularies/kuladevata/terms/{term['code']}/offer"
    contributor = member_factory(["CONTRIBUTOR"], name="Contributor")
    assert contributor.post(url, json={}).status_code == 403
    assert contributor.get(f"/trees/{t}/vocabulary-offers").status_code == 403
    # another tree's admin cannot offer (or even see) this tree's entry
    other = new_tree(contributor, "Contributor's own family")
    assert (
        contributor.post(
            f"/trees/{other['id']}/vocabularies/kuladevata/terms/{term['code']}/offer", json={}
        ).status_code
        == 404
    )
    # global terms and closed lists cannot be offered
    assert owner.post(f"/trees/{t}/vocabularies/gotra/terms/kashyapa/offer", json={}).status_code == 404
    r = owner.post(f"/trees/{t}/vocabularies/occupation/terms/t:x/offer", json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "vocabulary_not_offerable"

    r = owner.post(url, json={"note": "  Worshipped at Jejuri  ", "temple": "Khandoba temple, Jejuri"})
    assert r.status_code == 200, r.text
    assert r.json()["offer_status"] == "offered" and r.json()["offer_note"] == "Worshipped at Jejuri"
    assert owner.post(url, json={}).status_code == 409
    assert [o["code"] for o in owner.get(f"/trees/{t}/vocabulary-offers").json()] == [term["code"]]
    assert contributor.get(f"/trees/{other['id']}/vocabulary-offers").json() == []
    with owner_session() as db:
        ev = db.query(AuditEvent).filter_by(action="vocabulary.family_term_offered").one()
        assert "Khandoba" not in str(ev.details)
    # withdraw, then offer again
    assert owner.delete(url).json()["offer_status"] == "none"
    assert owner.delete(url).status_code == 409
    assert owner.post(url, json={}).status_code == 200


def test_curation_merges_offers_into_the_pack_without_naming_families(
    owner, tree, vocab, make_client, tmp_path
):
    t = tree["id"]
    a = _family_term(owner, t, "kuladevata", "Khandoba", ["खंडोबा"])
    owner.post(f"/trees/{t}/vocabularies/kuladevata/terms/{a['code']}/offer", json={"temple": "Jejuri"})
    other = new_tree(owner, "Second family")
    b = _family_term(owner, other["id"], "kuladevata", "Khandoba of Jejuri")
    owner.post(f"/trees/{other['id']}/vocabularies/kuladevata/terms/{b['code']}/offer", json={})
    c = _family_term(owner, other["id"], "kuladevata", "Ekvira")
    owner.post(f"/trees/{other['id']}/vocabularies/kuladevata/terms/{c['code']}/offer", json={})

    pack_dir = tmp_path / "packs"
    pack_dir.mkdir()
    for f in Path(PACK_DIR).glob("*.json"):
        (pack_dir / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")

    with owner_session() as db:
        pending = curation.pending(db, "kuladevata")
        by_label = {p.row.label: p for p in pending}
        assert set(by_label) == {"Khandoba", "Khandoba of Jejuri", "Ekvira"}
        # likely duplicates are pointed out for merging
        assert by_label["Khandoba of Jejuri"].row.id in by_label["Khandoba"].similar_offers
        assert not by_label["Ekvira"].similar_offers
        ids = [by_label["Khandoba"].row.id, by_label["Khandoba of Jejuri"].row.id]
        with pytest.raises(PackError, match="--en and --hi"):
            curation.accept(db, ids, code="khandoba", en="Khandoba", pack_dir=pack_dir)
        term = curation.accept(db, ids, code="khandoba", en="Khandoba", hi="खंडोबा", pack_dir=pack_dir)
        curation.decline(db, [by_label["Ekvira"].row.id])
        db.commit()
        with pytest.raises(PackError, match="pending"):
            curation.decline(db, [by_label["Ekvira"].row.id])

    written = json.loads((pack_dir / "kuladevata.json").read_text(encoding="utf-8"))
    assert written["version"] == 2
    assert written["terms"] == [term]
    assert term["status"] == "reviewed" and "Khandoba of Jejuri" in term["aliases"]
    assert term["attributes"] == {"temple": "Jejuri"}
    blob = json.dumps(written, ensure_ascii=False)
    # the shared term never names a family, a tree or a person
    for secret in (t, other["id"], "Second family", "t:"):
        assert secret not in blob

    # the next load makes it a shared term; the family keeps its own code and sees one result
    packs = [p if p["key"] != "kuladevata" else written for p in read_packs()]
    with owner_session() as db:
        load_packs(db, packs)
        rows = {r.label: r for r in db.query(TreeVocabularyTerm).all()}
        assert rows["Khandoba"].offer_status == OfferStatus.ACCEPTED
        assert rows["Khandoba"].promoted_code == "khandoba"
        assert rows["Ekvira"].offer_status == OfferStatus.DECLINED
        assert db.query(UserNotification).count() == 3
    items = owner.get(f"/trees/{t}/vocabularies/kuladevata", params={"q": "khandoba"}).json()["items"]
    assert [(i["code"], i["origin"], i["promoted_code"]) for i in items] == [
        (a["code"], "family", "khandoba")
    ]
    # a family that never offered it now finds the shared term
    third = new_tree(owner, "Third family")
    assert _codes(owner.get(f"/trees/{third['id']}/vocabularies/kuladevata", params={"q": "खंडोबा"})) == [
        "khandoba"
    ]
    # the decision reaches whoever offered it, as a notification in their tree, without other families
    notes = owner.get(f"/trees/{other['id']}/inbox").json()["items"]
    texts = sorted(n["text"] for n in notes)
    assert any("“Ekvira” was not added" in x for x in texts)
    assert any("“Khandoba of Jejuri” was added" in x for x in texts)
    assert all(str(t) not in x and "Khandoba”" not in x for x in texts)


def test_a_promoted_term_does_not_leak_through_another_trees_notification(owner, tree, vocab, make_client):
    """A notification about an offered entry shows its label only inside the entry's own tree."""
    t = tree["id"]
    a = _family_term(owner, t, "devak", "Panchpallav")
    owner.post(f"/trees/{t}/vocabularies/devak/terms/{a['code']}/offer", json={})
    other = new_tree(owner, "Other family")
    with owner_session() as db:
        row = db.query(TreeVocabularyTerm).filter_by(code=a["code"]).one()
        user_id = row.offered_by
        # a forged row pointing at another tree's entry
        db.add(
            UserNotification(
                tree_id=uuid.UUID(other["id"]), user_id=user_id, kind="offer_declined", subject_id=row.id
            )
        )
        db.commit()
    text = owner.get(f"/trees/{other['id']}/inbox").json()["items"][0]["text"]
    assert "Panchpallav" not in text and "an entry" in text
