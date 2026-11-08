"""Regional kinship packs and family words (ADR-0026 §6).

The golden matrix below moved here from ``frontend/src/lib/kinship.test.ts``: every shipped pack is
validated, and the Hindi (North) pack must give the same words families saw before packs existed.
Threat T48: a family's word never reaches another tree, and a word never sets anything about a person.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from app.models import AuditEvent
from app.modules.kinship import packs
from app.modules.kinship.packs import KinshipPackError, validate
from app.modules.kinship.resolve import Age, describe, resolve
from tests.conftest import new_tree, owner_session
from tests.helpers import create_person, exact, link

HI = "kinship-hi-north"


def _pack(key: str = HI) -> dict[str, Any]:
    return copy.deepcopy(next(p for p in packs.all_packs() if p["key"] == key))


def _age(i: int, order: str, basis: str | None = None) -> Age:
    return Age(i, order, basis or ("unknown" if order == "unknown" else "birth_dates"))  # type: ignore[arg-type]


# ---------------------------------------------------------------- packs
def test_every_shipped_pack_is_valid_and_describes_its_review():
    shipped = packs.all_packs()
    assert HI in {p["key"] for p in shipped}
    for p in shipped:
        validate(p, p["key"])
        assert p["source"].strip() and p["licence"].strip()
        if p["status"] == "reviewed":
            assert p["reviewer"] and p["reviewed_on"]
    # the Hindi words already shown since R1 await their native review: shown, labelled unreviewed
    hi = _pack()
    assert hi["status"] == "draft" and hi["in_use"] is True and packs.review_status(hi) == "unreviewed"


@pytest.mark.parametrize(
    "mutate, message",
    [
        (
            lambda p: p["terms"].update({"father.cousin": {"term": "x", "transliteration": "x"}}),
            "bad pattern",
        ),
        (lambda p: p["terms"]["father.brother"]["age"].update(index=0), "sibling word"),
        (lambda p: p["terms"]["mother"].pop("transliteration"), "no transliteration"),
        (lambda p: p.update(status="reviewed"), "reviewer and review date"),
        (
            lambda p: p["terms"]["mother"].update(speaker={"other": {"term": "x", "transliteration": "x"}}),
            "male or female",
        ),
    ],
)
def test_malformed_packs_are_rejected(mutate, message):
    pack = _pack()
    mutate(pack)
    with pytest.raises(KinshipPackError, match=message):
        validate(pack)


# ---------------------------------------------------------------- golden matrix (from kinship.test.ts)
@pytest.mark.parametrize(
    "chain, term",
    [
        (["father", "brother"], "चाचा / ताऊ"),
        (["mother", "brother"], "मामा"),
        (["father", "sister"], "बुआ"),
        (["mother", "sister"], "मौसी"),
        (["father", "father"], "दादा"),
        (["mother", "father"], "नाना"),
        (["father", "mother"], "दादी"),
        (["mother", "mother"], "नानी"),
        (["wife", "father"], "ससुर"),
        (["husband", "mother"], "सास"),
        (["brother", "wife"], "भाभी"),
        (["sister", "son"], "भांजा"),
        (["son", "wife", "father"], "समधी"),
        (["husband", "sister", "husband"], "ननदोई"),
    ],
)
def test_hindi_terms(chain, term):
    r = resolve(_pack(), chain, [])
    assert r is not None and r.term == term and r.transliteration


def test_unknown_and_neutral_chains_get_no_word():
    pack = _pack()
    assert resolve(pack, ["parent", "father"], []) is None  # a hidden/neutral hop: never a guess
    assert resolve(pack, ["sibling"], []) is None
    assert resolve(pack, [], []) is None


@pytest.mark.parametrize(
    "chain, index, elder, younger, unknown",
    [
        (["father", "brother"], 1, "ताऊ", "चाचा", "चाचा / ताऊ"),
        (["father", "brother", "wife"], 1, "ताई", "चाची", "चाची / ताई"),
        (["husband", "brother"], 1, "जेठ", "देवर", "देवर / जेठ"),
        (["husband", "brother", "wife"], 1, "जेठानी", "देवरानी", "देवरानी / जेठानी"),
        (["wife", "brother"], 1, "भाई साहब", "साला", "साला / भाई साहब"),
        (["brother"], 0, "भैया", "भाई", "भाई"),
        (["sister"], 0, "दीदी", "बहन", "बहन"),
        (["sister", "husband"], 0, "जीजा", "बहनोई", "जीजा"),
    ],
)
def test_age_aware_hindi_terms_use_the_right_word(chain, index, elder, younger, unknown):
    pack = _pack()
    assert resolve(pack, chain, [_age(index, "elder")]).term == elder  # type: ignore[union-attr]
    r = resolve(pack, chain, [_age(index, "younger", "family_confirmed")])
    assert r is not None and (r.term, r.basis, r.alternatives) == (younger, "family_confirmed", [])
    r = resolve(pack, chain, [_age(index, "unknown")])
    assert r is not None and (r.term, r.basis, r.alternatives) == (unknown, "unknown", [elder, younger])
    # no age data at all (e.g. a hidden relative on the path): both words
    r = resolve(pack, chain, [])
    assert r is not None and (r.term, r.basis) == (unknown, None)


def test_age_of_another_word_or_irrelevant_ages_never_decide():
    pack = _pack()
    assert resolve(pack, ["father", "brother"], [_age(0, "elder")]).term == "चाचा / ताऊ"  # type: ignore[union-attr]
    assert resolve(pack, ["mother", "brother"], [_age(1, "elder")]).term == "मामा"  # type: ignore[union-attr]
    assert resolve(pack, ["mother", "sister"], [_age(1, "younger")]).term == "मौसी"  # type: ignore[union-attr]


def test_describe_chain_literally():
    pack = _pack()
    assert describe(pack, ["mother", "brother"]) == "माता के भाई"
    assert describe(pack, ["father", "brother"], [_age(1, "younger")]) == "पिता के छोटे भाई"
    assert describe(pack, ["father", "brother"], [_age(1, "unknown")]) == "पिता के भाई"


def test_speaker_dependent_words_need_the_speakers_own_profile():
    pack = _pack()
    pack["terms"]["brother.wife"]["speaker"] = {
        "male": {"term": "भाभी", "transliteration": "bhabhi"},
        "female": {"term": "भौजाई", "transliteration": "bhaujai"},
    }
    validate(pack)
    assert resolve(pack, ["brother", "wife"], [], "female").term == "भौजाई"  # type: ignore[union-attr]
    both = resolve(pack, ["brother", "wife"], [], None)
    assert both is not None and both.alternatives == ["भाभी", "भौजाई"]


# ---------------------------------------------------------------- API
def _family(client: Any, t: str) -> dict[str, dict[str, Any]]:
    dada = create_person(client, t, "Dada", sex="male")
    father = create_person(client, t, "Ramesh", sex="male", birth={"date": exact(1960, 3, 12)})
    uncle = create_person(client, t, "Suresh", sex="male", birth={"date": exact(1955, 1, 2)})
    me = create_person(client, t, "Aarav", sex="male", status="living")
    for child in (father, uncle):
        link(client, t, dada["id"], child["id"], "biological_parent")
    link(client, t, father["id"], me["id"], "biological_parent")
    return {"dada": dada, "father": father, "uncle": uncle, "me": me}


def _terms(client: Any, t: str, a: str, b: str) -> list[dict[str, Any]]:
    r = client.get(f"/trees/{t}/relationship-path", params={"from": a, "to": b})
    assert r.status_code == 200, r.text
    return r.json()["terms"]


def test_words_follow_the_readers_choice_then_the_tree_then_the_ui(owner, tree):
    t = tree["id"]
    f = _family(owner, t)
    me, uncle = f["me"]["id"], f["uncle"]["id"]
    assert _terms(owner, t, me, uncle) == []  # English UI: the English label is the word
    # ... but the age that decides Tau or Chacha is known in every language
    path = owner.get(f"/trees/{t}/relationship-path", params={"from": me, "to": uncle}).json()
    assert (path["age_decision"]["chain_index"], path["age_decision"]["order"]) == (1, "elder")
    mama = owner.get(f"/trees/{t}/relationship-path", params={"from": uncle, "to": me}).json()
    assert mama["age_decision"] is None  # brother's son: no age-dependent word
    # the page's UI language is the last fallback
    hi = owner.get(f"/trees/{t}/relationship-path", params={"from": me, "to": uncle, "lang": "hi"}).json()
    assert hi["terms"][0]["term"] == "ताऊ"
    assert owner.patch(f"/trees/{t}", json={"kinship_lang": "hi"}).json()["kinship_lang"] == "hi"
    [term] = _terms(owner, t, me, uncle)
    assert (term["term"], term["basis"], term["review_status"], term["pack"]) == (
        "ताऊ",
        "birth_dates",
        "unreviewed",
        HI,
    )
    assert term["transliteration"] == "tau" and term["description"] == "पिता के बड़े भाई"
    # the reader's own choice wins over the tree's
    r = owner.put("/me/kinship-preference", json={"lang": "en"})
    assert r.status_code == 200 and r.json() == {"lang": "en", "region": None}
    assert _terms(owner, t, me, uncle) == []
    owner.put("/me/kinship-preference", json={"lang": None})
    assert _terms(owner, t, me, uncle)[0]["term"] == "ताऊ"
    # a language without a pack has no word, never another language's
    owner.put("/me/kinship-preference", json={"lang": "ta"})
    assert _terms(owner, t, me, uncle) == []
    assert owner.put("/me/kinship-preference", json={"lang": "Hindi!"}).status_code == 422
    assert owner.patch(f"/trees/{t}", json={"kinship_lang": "<x>"}).status_code == 422


def test_draft_packs_are_for_reviewers_only(owner, tree, monkeypatch):
    t = tree["id"]
    f = _family(owner, t)
    draft = _pack()
    draft["in_use"] = False
    monkeypatch.setattr(packs, "all_packs", lambda: (draft,))
    owner.patch(f"/trees/{t}", json={"kinship_lang": "hi"})
    assert _terms(owner, t, f["me"]["id"], f["uncle"]["id"]) == []
    assert owner.get("/kinship/packs").json() == []
    with owner_session() as db:
        from app.models import User

        db.query(User).filter_by(email=owner.user["email"]).update({"is_system_admin": True})
        db.commit()
    assert [p["key"] for p in owner.get("/kinship/packs").json()] == [HI]
    assert _terms(owner, t, f["me"]["id"], f["uncle"]["id"])[0]["term"] == "ताऊ"


def test_family_words_come_first_and_stay_in_their_tree(owner, tree, member_factory):
    t = tree["id"]
    f = _family(owner, t)
    me = f["me"]["id"]
    aunt = create_person(owner, t, "Kanta", sex="female")
    link(owner, t, f["uncle"]["id"], aunt["id"], "spouse")
    owner.patch(f"/trees/{t}", json={"kinship_lang": "hi"})

    r = owner.put(
        f"/trees/{t}/kinship-overrides",
        json={"pattern": "father.brother:elder", "lang": "hi", "word": "  बड़े बाबूजी "},
    )
    assert r.status_code == 200, r.text
    assert r.json()["word"] == "बड़े बाबूजी"
    [term] = _terms(owner, t, me, f["uncle"]["id"])
    assert (term["term"], term["family_word"], term["pack_term"], term["review_status"]) == (
        "बड़े बाबूजी",
        True,
        "ताऊ",
        "family",
    )
    # the age-specific word does not apply to the aunt's chain; the pack's word does
    assert _terms(owner, t, me, aunt["id"])[0]["term"] == "ताई"
    # upsert, not a duplicate
    owner.put(
        f"/trees/{t}/kinship-overrides",
        json={"pattern": "father.brother:elder", "lang": "hi", "word": "बाबूजी"},
    )
    assert [o["word"] for o in owner.get(f"/trees/{t}/kinship-overrides").json()] == ["बाबूजी"]

    # another family never sees it (T48)
    other = new_tree(owner, "Other family")
    o = other["id"]
    g = _family(owner, o)
    owner.patch(f"/trees/{o}", json={"kinship_lang": "hi"})
    assert owner.get(f"/trees/{o}/kinship-overrides").json() == []
    assert _terms(owner, o, g["me"]["id"], g["uncle"]["id"])[0]["term"] == "ताऊ"
    word_id = owner.get(f"/trees/{t}/kinship-overrides").json()[0]["id"]
    assert owner.delete(f"/trees/{o}/kinship-overrides/{word_id}").status_code == 404

    # permissions: family.write to change, members read, strangers get nothing
    viewer = member_factory(["VIEWER"])
    assert len(viewer.get(f"/trees/{t}/kinship-overrides").json()) == 1
    bad = {"pattern": "brother.wife", "lang": "hi", "word": "भौजी"}
    assert viewer.put(f"/trees/{t}/kinship-overrides", json=bad).status_code == 403
    assert viewer.delete(f"/trees/{t}/kinship-overrides/{word_id}").status_code == 403
    stranger = member_factory(["VIEWER"], name="Stranger")
    assert stranger.get(f"/trees/{o}/kinship-overrides").status_code in (403, 404)
    # words are plain text with a valid pattern
    for body in (
        {"pattern": "father.cousin!", "lang": "hi", "word": "x"},
        {"pattern": "brother.wife", "lang": "hi", "word": "<b>x</b>"},
        {"pattern": "brother.wife", "lang": "HI", "word": "x"},
    ):
        assert owner.put(f"/trees/{t}/kinship-overrides", json=body).status_code == 422
    # a word never changes a person
    before = owner.get(f"/trees/{t}/people/{f['uncle']['id']}").json()
    owner.put(f"/trees/{t}/kinship-overrides", json={"pattern": "father.sister", "lang": "hi", "word": "फूफी"})
    assert owner.get(f"/trees/{t}/people/{f['uncle']['id']}").json()["sex_at_birth"] == before["sex_at_birth"]
    with owner_session() as db:
        assert db.query(AuditEvent).filter_by(action="kinship.family_word_set").count() == 3

    assert owner.delete(f"/trees/{t}/kinship-overrides/{word_id}").status_code == 200
    assert _terms(owner, t, me, f["uncle"]["id"])[0]["term"] == "ताऊ"


def test_a_branch_word_applies_to_that_branch_only(owner, tree):
    t = tree["id"]
    f = _family(owner, t)
    owner.patch(f"/trees/{t}", json={"kinship_lang": "hi"})
    cousin = create_person(owner, t, "Vikram", sex="male")
    link(owner, t, f["uncle"]["id"], cousin["id"], "biological_parent")
    branch = owner.post(f"/trees/{t}/branches", json={"name": "Ramesh's line"}).json()
    owner.post(f"/trees/{t}/branches/{branch['id']}/members", json={"person_ids": [f["me"]["id"]]})
    owner.put(
        f"/trees/{t}/kinship-overrides",
        json={"pattern": "father.brother", "lang": "hi", "word": "काका", "branch_id": branch["id"]},
    )
    owner.put(
        f"/trees/{t}/kinship-overrides", json={"pattern": "father.brother", "lang": "hi", "word": "चच्चा"}
    )
    assert _terms(owner, t, f["me"]["id"], f["uncle"]["id"])[0]["term"] == "काका"
    # the uncle's own son is not in the branch: the tree-wide word
    assert _terms(owner, t, cousin["id"], f["father"]["id"])[0]["term"] == "चच्चा"
    bogus = {"pattern": "father.sister", "lang": "hi", "word": "x", "branch_id": new_tree(owner, "X")["id"]}
    assert owner.put(f"/trees/{t}/kinship-overrides", json=bogus).status_code == 404


def test_family_words_are_reviewed_when_the_family_reviews_everything(owner, tree, member_factory):
    t = tree["id"]
    assert owner.put(f"/trees/{t}/review-policy", json={"review_policy": "all"}).status_code == 200
    contributor = member_factory(["CONTRIBUTOR"], name="Cousin")
    body = {"pattern": "brother.wife", "lang": "hi", "word": "भौजी"}
    r = contributor.put(f"/trees/{t}/kinship-overrides", json=body)
    assert r.status_code == 409 and r.json()["error"]["code"] == "review_required"
    assert owner.put(f"/trees/{t}/kinship-overrides", json=body).status_code == 200


def test_a_family_word_can_be_proposed_and_approved(owner, tree, member_factory):
    t = tree["id"]
    owner.put(f"/trees/{t}/review-policy", json={"review_policy": "all"})
    contributor = member_factory(["CONTRIBUTOR"], name="Cousin")
    prop = contributor.post(
        f"/trees/{t}/proposals",
        json={
            "rationale": "We have always said Bhauji",
            "items": [
                {
                    "target_type": "kinship_word",
                    "op": "create",
                    "patch": {"pattern": "brother.wife", "lang": "hi", "word": "भौजी"},
                }
            ],
            "submit": True,
        },
    )
    assert prop.status_code == 201, prop.text
    assert "the family's relationship words" in owner.get(f"/trees/{t}/inbox").json()["items"][0]["text"]
    assert owner.get(f"/trees/{t}/kinship-overrides").json() == []
    r = owner.post(f"/trees/{t}/proposals/{prop.json()['id']}/approve", json={})
    assert r.status_code == 200, r.text
    [word] = owner.get(f"/trees/{t}/kinship-overrides").json()
    assert word["word"] == "भौजी"
    # an invalid word is refused when proposed, not when approved
    bad = contributor.post(
        f"/trees/{t}/proposals",
        json={
            "rationale": "x",
            "items": [
                {
                    "target_type": "kinship_word",
                    "op": "create",
                    "patch": {"pattern": "x!", "lang": "hi", "word": "y"},
                }
            ],
        },
    )
    assert bad.status_code == 422
