"""Provisional people (ADR-0020 §4, amended): who can see them, completing vs verifying, exports.

A provisional person is created by Smart Add's "unknown for now". Only tree admins and the user who
created them may see them; nobody else can discover them through any view, count or export.
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

from tests.conftest import new_tree
from tests.helpers import create_person, person_body


def _mama_via_unknown_mother(client: Any, t: str, anchor: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Add Mama through a new provisional mother; returns (provisional mother, Mama)."""
    r = client.post(
        f"/trees/{t}/people/{anchor}/smart-add",
        json={"term": "mama", "new_person": person_body("Mohan"), "choices": ["new"]},
    )
    assert r.status_code == 201, r.text
    out = r.json()
    prov = next(p for p in out["created_people"] if p["id"] != out["person"]["id"])
    return prov, out["person"]


def _relationship_ids(client: Any, t: str, pid: str) -> list[str]:
    fam = client.get(f"/trees/{t}/people/{pid}/family").json()
    related = (
        fam["parents"]
        + fam["siblings"]
        + fam["other_children"]
        + [u["partner"] for u in fam["unions"]]
        + [c for u in fam["unions"] for c in u["children"]]
    )
    return [r["relationship_id"] for r in related if r["relationship_id"]]


def _verify(client: Any, t: str, pid: str, evidence: str = "FAMILY_RECOLLECTION") -> None:
    for rid in _relationship_ids(client, t, pid):
        r = client.patch(f"/trees/{t}/relationships/{rid}", json={"evidence_status": evidence})
        assert r.status_code == 200, r.text


def _gedcom(client: Any, t: str) -> str:
    r = client.get(f"/trees/{t}/exports/gedcom", params={"exclude_living": "false"})
    assert r.status_code == 200, r.text
    return r.text


def _archive(client: Any, t: str) -> tuple[dict[str, Any], dict[str, Any]]:
    r = client.get(f"/trees/{t}/exports/archive", params={"exclude_living": "false"})
    assert r.status_code == 200, r.text
    z = zipfile.ZipFile(io.BytesIO(r.content))
    return json.loads(z.read("family-export/genealogy/canonical-data.json")), json.loads(
        z.read("family-export/manifest.json")
    )


# ------------------------------------------------------------------ who can see them
def test_creator_and_tree_admins_see_a_provisional_person_nobody_else(owner, tree, member_factory):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="deceased", sex="male")
    creator = member_factory(["CONTRIBUTOR"], name="Creator")
    other = member_factory(["CONTRIBUTOR"], name="Other")
    viewer = member_factory(["VIEWER"], name="Viewer")
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    prov, mama = _mama_via_unknown_mother(creator, t, me["id"])
    pid = prov["id"]
    assert prov["privacy_level"] == "CUSTOM"

    for who in (creator, owner, admin):
        assert who.get(f"/trees/{t}/people/{pid}").status_code == 200
    for who in (other, viewer):
        # IDOR/BOLA: knowing the id does not help
        assert who.get(f"/trees/{t}/people/{pid}").status_code == 404
        assert who.get(f"/trees/{t}/people/{pid}/family").status_code == 404
        assert who.post(f"/trees/{t}/people/{pid}/names", json={"given_name": "X"}).status_code in (403, 404)
        # Mama, an ordinary person, stays visible: only the provisional link is concealed
        assert who.get(f"/trees/{t}/people/{mama['id']}").status_code == 200


def test_concealed_everywhere_no_placeholder_no_count(owner, tree, member_factory):
    t = tree["id"]
    branch = owner.post(f"/trees/{t}/branches", json={"name": "Iyer"}).json()
    me = create_person(owner, t, "Aarav", status="deceased", sex="male", branch_ids=[branch["id"]])
    nani = create_person(owner, t, "Kamala", status="deceased", sex="female")
    creator = member_factory(["CONTRIBUTOR"], name="Creator")
    other = member_factory(["CONTRIBUTOR"], name="Other")
    prov, mama = _mama_via_unknown_mother(creator, t, me["id"])
    pid = prov["id"]
    # the creator links the provisional mother to her own mother, and into the branch
    r = creator.post(
        f"/trees/{t}/people/{pid}/relatives", json={"relation": "parent", "existing_person_id": nani["id"]}
    )
    assert r.status_code == 201, r.text
    r = owner.post(f"/trees/{t}/branches/{branch['id']}/members", json={"person_ids": [pid]})
    assert r.status_code == 200, r.text

    def leaks(resp: Any) -> bool:
        return pid in resp.text

    # family: no parent at all, not even an anonymous "private relative"
    fam = other.get(f"/trees/{t}/people/{me['id']}/family").json()
    assert fam["parents"] == []
    assert not any(s["hidden"] for s in fam["siblings"])
    # graphs and charts: no hidden node, and nothing reached through her
    anc = other.get(f"/trees/{t}/people/{me['id']}/ancestors", params={"depth": 4})
    assert [n for n in anc.json()["nodes"] if n["hidden"]] == []
    assert nani["id"] not in {n["id"] for n in anc.json()["nodes"]}
    fan = other.get(f"/trees/{t}/viz/ancestry", params={"root": me["id"], "generations": 3})
    assert fan.status_code == 200, fan.text
    assert [n for n in fan.json()["nodes"] if n["hidden"]] == []
    assert " 0 private" in fan.json()["summary"]
    hood = other.get(f"/trees/{t}/viz/neighbourhood", params={"root": me["id"], "radius": 2})
    assert hood.status_code == 200, hood.text
    assert [n for n in hood.json()["nodes"] if n["hidden"]] == []
    life = other.get(f"/trees/{t}/viz/lifespans", params={"root": me["id"]})
    assert life.status_code == 200, life.text
    assert nani["id"] not in life.text
    # relationship path: not found through her, never named or placeheld
    path = other.get(f"/trees/{t}/relationship-path", params={"from": me["id"], "to": mama["id"]})
    assert path.status_code == 200, path.text
    assert None not in path.json()["path"]
    # lists, search, counts and candidate lists
    for resp in (
        other.get(f"/trees/{t}/people"),
        other.get(f"/trees/{t}/search", params={"q": "Unnamed"}),
        other.get(f"/trees/{t}/people/{mama['id']}/family"),
        other.get(f"/trees/{t}/branches/{branch['id']}"),
        other.post(f"/trees/{t}/people/{me['id']}/smart-add/plan", json={"term": "mama", "choices": []}),
        fan,
        hood,
        path,
        anc,
    ):
        assert resp.status_code == 200, resp.text
        assert not leaks(resp)
    detail = other.get(f"/trees/{t}/branches/{branch['id']}").json()
    assert detail["hidden_member_count"] == 0
    assert detail["member_count"] == 1
    plan = other.post(
        f"/trees/{t}/people/{me['id']}/smart-add/plan", json={"term": "mama", "choices": []}
    ).json()
    assert plan["steps"][0]["hidden_candidates"] == 0
    # ...while the owner sees her in the same places
    assert pid in owner.get(f"/trees/{t}/people/{me['id']}/family").text
    owner_branch = owner.get(f"/trees/{t}/branches/{branch['id']}").json()
    # headline count leaves her out for everyone (#32); the admin count shows her to the owner
    assert (owner_branch["member_count"], owner_branch["provisional_member_count"]) == (1, 1)
    assert pid in {m["person"]["id"] for m in owner_branch["members"] if m["person"]}


def test_cross_tree_ids_and_grants_do_not_carry_over(owner, tree, member_factory):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="deceased", sex="male")
    creator = member_factory(["CONTRIBUTOR"], name="Creator")
    prov, _ = _mama_via_unknown_mother(creator, t, me["id"])
    other_tree = new_tree(owner, "Other family")
    o = other_tree["id"]
    assert owner.get(f"/trees/{o}/people/{prov['id']}").status_code == 404
    assert creator.get(f"/trees/{o}/people/{prov['id']}").status_code == 404
    # nor can the provisional person be used as a choice from another tree
    there = create_person(owner, o, "Ravi", status="deceased", sex="male")
    r = owner.post(
        f"/trees/{o}/people/{there['id']}/smart-add/plan", json={"term": "mama", "choices": [prov["id"]]}
    )
    assert r.status_code == 422


def test_a_public_tree_never_shows_a_provisional_person(owner, tree, client):
    t, slug = tree["id"], tree["slug"]
    me = create_person(owner, t, "Aarav", status="deceased", sex="male", privacy_level="PUBLIC_DECEASED_ONLY")
    prov, _ = _mama_via_unknown_mother(owner, t, me["id"])
    assert owner.patch(f"/trees/{t}", json={"public_mode": "DECEASED_ONLY"}).status_code == 200
    assert client.get(f"/public/trees/{slug}").status_code == 200
    assert client.get(f"/public/trees/{slug}/people/{prov['id']}").status_code == 404
    for path in ("people", f"people/{me['id']}/family", f"people/{me['id']}/ancestors"):
        r = client.get(f"/public/trees/{slug}/{path}")
        assert r.status_code == 200, r.text
        assert prov["id"] not in r.text and '"hidden":true' not in r.text


def test_creator_can_complete_and_undo_takes_their_grant(owner, tree, member_factory):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="deceased", sex="male")
    creator = member_factory(["CONTRIBUTOR"], name="Creator")
    r = creator.post(
        f"/trees/{t}/people/{me['id']}/smart-add",
        json={"term": "mama", "new_person": person_body("Mohan"), "choices": ["new"]},
    )
    out = r.json()
    pid = next(p["id"] for p in out["created_people"] if p["id"] != out["person"]["id"])
    assert creator.post(f"/trees/{t}/people/{pid}/names", json={"given_name": "Sunita"}).status_code == 201
    assert creator.patch(f"/trees/{t}/people/{pid}", json={"profile_status": "deceased"}).status_code == 200
    assert creator.get(f"/trees/{t}/people/{pid}").json()["display_name"].startswith("Sunita")
    # the creator cannot widen who sees her: that stays a tree-admin decision
    r = creator.put(f"/trees/{t}/people/{pid}/privacy", json={"privacy_level": "TREE_MEMBERS"})
    assert r.status_code == 403
    assert creator.post(f"/trees/{t}/smart-add/{out['operation_id']}/undo").status_code == 200
    from app.models import AccessGrant
    from tests.conftest import owner_session

    with owner_session() as db:
        assert db.query(AccessGrant).filter(AccessGrant.resource_id == pid).count() == 0


# ------------------------------------------------------------------ completing is not verifying
def test_name_completes_details_evidence_verifies(owner, tree, member_factory):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="deceased", sex="male")
    prov, _ = _mama_via_unknown_mother(owner, t, me["id"])
    pid = prov["id"]
    viewer = member_factory(["VIEWER"])
    assert prov["provisional_state"] == "needs_details"

    owner.post(f"/trees/{t}/people/{pid}/names", json={"given_name": "Sunita"})
    p = owner.get(f"/trees/{t}/people/{pid}").json()
    assert (p["is_provisional"], p["provisional_state"]) == (True, "unverified")
    # naming changed no relationship's evidence
    for rid in _relationship_ids(owner, t, pid):
        assert owner.get(f"/trees/{t}/relationships/{rid}").json()["evidence_status"] == "USER_ASSERTION"
    # still concealed from the viewer while unverified
    assert viewer.get(f"/trees/{t}/people/{me['id']}/family").json()["parents"] == []

    _verify(owner, t, pid)
    p = owner.get(f"/trees/{t}/people/{pid}").json()
    assert (p["is_provisional"], p["provisional_state"]) == (True, "verified")
    # verified: an ordinary CUSTOM-privacy person now; the viewer sees that a private parent
    # exists, never who
    parents = viewer.get(f"/trees/{t}/people/{me['id']}/family").json()["parents"]
    assert [x["hidden"] for x in parents] == [True]
    assert pid not in json.dumps(parents)
    # a tree admin can then open her up through the ordinary privacy setting
    assert (
        owner.put(f"/trees/{t}/people/{pid}/privacy", json={"privacy_level": "TREE_MEMBERS"}).status_code
        == 200
    )
    assert viewer.get(f"/trees/{t}/people/{pid}").status_code == 200


def test_a_disputed_relationship_keeps_a_provisional_person_unverified(owner, tree):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="deceased", sex="male")
    prov, _ = _mama_via_unknown_mother(owner, t, me["id"])
    pid = prov["id"]
    owner.post(f"/trees/{t}/people/{pid}/names", json={"given_name": "Sunita"})
    ids = _relationship_ids(owner, t, pid)
    owner.patch(f"/trees/{t}/relationships/{ids[0]}", json={"evidence_status": "SOURCED"})
    owner.patch(f"/trees/{t}/relationships/{ids[1]}", json={"evidence_status": "DISPUTED"})
    assert owner.get(f"/trees/{t}/people/{pid}").json()["provisional_state"] == "unverified"


# ------------------------------------------------------------------ exports
def test_default_exports_leave_out_pending_provisional_people(owner, tree):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="deceased", sex="male")
    prov, mama = _mama_via_unknown_mother(owner, t, me["id"])
    pid = prov["id"]

    ged = _gedcom(owner, t)
    assert ged.count("0 @I") == 2  # Aarav and Mohan, not the unnamed mother
    assert "Unnamed" not in ged
    assert "FAMC" not in ged  # no family record is left pointing at a parent who is not there
    data, manifest = _archive(owner, t)
    assert pid not in json.dumps(data)
    assert {p["id"] for p in data["people"]} == {me["id"], mama["id"]}
    assert all(pid not in (r["person_a_id"], r["person_b_id"]) for r in data["relationships"])
    assert manifest["counts"]["excluded_provisional"] == 1

    # named but unverified: still left out
    owner.post(f"/trees/{t}/people/{pid}/names", json={"given_name": "Sunita"})
    assert "Sunita" not in _gedcom(owner, t)
    assert pid not in json.dumps(_archive(owner, t)[0])

    # named and verified: exported like anyone else (at their privacy level)
    _verify(owner, t, pid, "SOURCED")
    ged = _gedcom(owner, t)
    assert "Sunita" in ged
    assert "FAMC" in ged
    data, manifest = _archive(owner, t)
    assert pid in {p["id"] for p in data["people"]}
    assert manifest["counts"]["excluded_provisional"] == 0


def test_an_exporter_who_cannot_see_them_learns_nothing(owner, tree, member_factory):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="deceased", sex="male")
    prov, _ = _mama_via_unknown_mother(owner, t, me["id"])
    _verify(owner, t, prov["id"])  # unnamed, so still pending
    exporter = member_factory(["CONTRIBUTOR"], name="Exporter")  # may export (GEDCOM_EXPORT)
    data, manifest = _archive(exporter, t)
    assert prov["id"] not in json.dumps(data)
    assert manifest["counts"]["excluded_provisional"] == 0  # not even counted
    assert "Unnamed" not in _gedcom(exporter, t)
