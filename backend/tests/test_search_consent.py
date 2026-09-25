from __future__ import annotations

from tests.helpers import create_person, exact


def test_search_explains_matches_and_respects_privacy(owner, tree, member_factory):
    t = tree["id"]
    create_person(owner, t, "Ramaswamy", "Iyer")
    create_person(owner, t, "Ramaswami", "Ayyar", status="living", privacy_level="PRIVATE_TREE_ADMINS")
    r = owner.get(f"/trees/{t}/search", params={"q": "Ramaswamy"}).json()
    person_hits = [h for h in r["hits"] if h["kind"] == "person"]
    assert len(person_hits) == 2
    assert person_hits[0]["match_tier"] in ("exact", "prefix")
    assert all(h["match_reason"] for h in person_hits)
    viewer = member_factory(["VIEWER"])
    vr = viewer.get(f"/trees/{t}/search", params={"q": "Ramaswamy"})
    assert "Ayyar" not in vr.text and len([h for h in vr.json()["hits"] if h["kind"] == "person"]) == 1


def test_phonetic_and_transliterated_search(owner, tree):
    t = tree["id"]
    owner.post(
        f"/trees/{t}/people",
        json={"profile_status": "deceased", "names": [{"full_name_as_recorded": "लक्ष्मी", "language": "hi"}]},
    )
    hits = owner.get(f"/trees/{t}/search", params={"q": "Lakshmi", "kinds": "person"}).json()["hits"]
    assert hits and hits[0]["title"] == "लक्ष्मी"


def test_historical_place_name_search(owner, tree):
    t = tree["id"]
    owner.post(
        f"/trees/{t}/places",
        json={"canonical_name": "Mumbai", "place_type": "city", "historical_names": [{"name": "Bombay"}]},
    )
    hits = owner.get(f"/trees/{t}/search", params={"q": "bombay", "kinds": "place"}).json()["hits"]
    assert hits[0]["title"] == "Mumbai" and "Bombay" in hits[0]["match_reason"]


def test_duplicate_candidates_never_auto_merge(owner, tree):
    t = tree["id"]
    a = create_person(owner, t, "Subramanian", "Iyer", sex="male", birth={"date": exact(1930, 1, 1)})
    b = create_person(
        owner, t, "Subramaniam", "Iyer", sex="male", birth={"date": {"precision": "year_only", "year": 1930}}
    )
    create_person(owner, t, "Subramanian", "Iyer", sex="female", birth={"date": exact(1990, 1, 1)})
    d = owner.get(f"/trees/{t}/duplicates").json()
    assert len(d) == 1
    assert {d[0]["person_a"]["id"], d[0]["person_b"]["id"]} == {a["id"], b["id"]}
    assert d[0]["outcome"] in ("possible", "probable") and d[0]["reasons"]
    assert owner.get(f"/trees/{t}/people/{a['id']}").status_code == 200
    assert owner.get(f"/trees/{t}/people/{b['id']}").status_code == 200


def test_consent_ledger(owner, tree, member_factory):
    t = tree["id"]
    kid = create_person(owner, t, "Kid", status="living", birth={"date": exact(2015, 1, 1)})
    r = owner.post(
        f"/trees/{t}/people/{kid['id']}/consents",
        json={
            "granted_by_name": "Parent",
            "authority_basis": "parent_guardian",
            "purpose": "Include in family tree",
            "data_categories": ["name", "birth_year"],
        },
    )
    assert r.status_code == 201 and r.json()["active"] is True
    w = owner.post(f"/trees/{t}/consents/{r.json()['id']}/withdraw")
    assert w.json()["active"] is False
    viewer = member_factory(["VIEWER"])
    assert viewer.get(f"/trees/{t}/people/{kid['id']}/consents").status_code == 403


def test_claim_profile_links_but_does_not_escalate(owner, tree, member_factory):
    t = tree["id"]
    me = create_person(owner, t, "Me", status="living")
    viewer = member_factory(["VIEWER"])
    c = viewer.post(f"/trees/{t}/people/{me['id']}/claims", json={"message": "This is me"})
    assert c.status_code == 201
    assert viewer.post(f"/trees/{t}/claims/{c.json()['id']}/approve", json={}).status_code == 403
    assert owner.post(f"/trees/{t}/claims/{c.json()['id']}/approve", json={}).status_code == 200
    tr = viewer.get(f"/trees/{t}").json()
    assert tr["my_roles"] == ["VIEWER"] and tr["my_linked_person_id"] == me["id"]
    # claimant now controls own privacy settings
    assert (
        viewer.put(
            f"/trees/{t}/people/{me['id']}/privacy", json={"field_privacy": {"contact": "PRIVATE_SELF"}}
        ).status_code
        == 200
    )
    assert viewer.post(f"/trees/{t}/people", json={"names": [{"given_name": "x"}]}).status_code == 403
