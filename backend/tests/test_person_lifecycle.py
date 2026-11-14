"""Remove from tree, restore and permanent delete (ADR-0034 §1–§3).

A removed or permanently deleted person is absent: no node, no "Private person" placeholder, no
count, and nothing is reached through them. A person hidden by privacy keeps their placeholder.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text

from tests.conftest import new_tree, owner_session
from tests.helpers import create_person, link


def _family(owner, t):
    p = {
        n: create_person(owner, t, n, "Pandey")["id"] for n in ["Anita", "Ramesh", "Son", "Bahu", "Grandkid"]
    }
    union = link(owner, t, p["Anita"], p["Ramesh"], "spouse")
    link(owner, t, p["Anita"], p["Son"], "biological_parent", union_id=union["id"])
    link(owner, t, p["Ramesh"], p["Son"], "biological_parent", union_id=union["id"])
    link(owner, t, p["Son"], p["Bahu"], "spouse")
    link(owner, t, p["Son"], p["Grandkid"], "biological_parent")
    link(owner, t, p["Bahu"], p["Grandkid"], "biological_parent")
    return p


def _projections(client, t, p, gedcom=True):
    """Every person-shaped thing the tree views return, as raw text and as placeholder counts."""
    out = {
        "descendants": client.get(f"/trees/{t}/people/{p['Anita']}/descendants", params={"depth": 8}),
        "ancestors": client.get(f"/trees/{t}/people/{p['Grandkid']}/ancestors", params={"depth": 8}),
        "family_up": client.get(f"/trees/{t}/people/{p['Anita']}/family"),
        "family_down": client.get(f"/trees/{t}/people/{p['Grandkid']}/family"),
        "family_spouse": client.get(f"/trees/{t}/people/{p['Bahu']}/family"),
        "connected": client.get(
            f"/trees/{t}/family-graph", params={"scope": "connected", "person_id": p["Anita"]}
        ),
        "all": client.get(f"/trees/{t}/family-graph", params={"scope": "all"}),
        "neighbourhood": client.get(
            f"/trees/{t}/viz/neighbourhood", params={"root": p["Anita"], "radius": 3}
        ),
        "ancestry": client.get(f"/trees/{t}/viz/ancestry", params={"root": p["Grandkid"]}),
        "people": client.get(f"/trees/{t}/people"),
        "search": client.get(f"/trees/{t}/search", params={"q": "Son"}),
    }
    if gedcom:  # exporting needs gedcom.export, which a viewer does not have
        out["gedcom"] = client.get(f"/trees/{t}/exports/gedcom", params={"exclude_living": "false"})
    for name, r in out.items():
        assert r.status_code == 200, (name, r.text)
    return {k: r.text for k, r in out.items()}


@pytest.mark.parametrize("role", ["OWNER", "VIEWER"])
@pytest.mark.parametrize("how", ["remove", "delete"])
def test_removed_or_deleted_person_is_absent_from_every_view(owner, tree, member_factory, role, how):
    t = tree["id"]
    p = _family(owner, t)
    if how == "remove":
        assert owner.delete(f"/trees/{t}/people/{p['Son']}").status_code == 200
    else:
        r = owner.post(f"/trees/{t}/people/{p['Son']}/erase", json={"reason": "asked", "confirm": True})
        assert r.status_code == 200, r.text
    client = owner if role == "OWNER" else member_factory(["VIEWER"])
    for name, raw in _projections(client, t, p, gedcom=role == "OWNER").items():
        assert p["Son"] not in raw, name
        assert "Son Pandey" not in raw and "Erased person" not in raw, name
        assert '"hidden":true' not in raw, name  # no placeholder stands in for them
    # nothing is reached through them: Grandkid's ancestors stop at the recorded mother
    anc = client.get(f"/trees/{t}/people/{p['Grandkid']}/ancestors", params={"depth": 8}).json()
    assert {n["id"] for n in anc["nodes"]} == {p["Grandkid"], p["Bahu"]}
    desc = client.get(f"/trees/{t}/people/{p['Anita']}/descendants", params={"depth": 8}).json()
    assert {n["id"] for n in desc["nodes"]} == {p["Anita"], p["Ramesh"]}
    fam = client.get(f"/trees/{t}/people/{p['Grandkid']}/family").json()
    assert [x["person"]["id"] for x in fam["parents"]] == [p["Bahu"]]  # no parent is invented
    assert client.get(f"/trees/{t}/people/{p['Bahu']}/family").json()["unions"] == []
    for path in ("", "/family", "/descendants", "/ancestors", "/events"):
        assert client.get(f"/trees/{t}/people/{p['Son']}{path}").status_code == 404, path
    assert (
        client.get(f"/trees/{t}/relationship-path", params={"from": p["Anita"], "to": p["Grandkid"]}).json()[
            "found"
        ]
        is False
    )


def test_privacy_hidden_person_keeps_the_placeholder(owner, tree, member_factory):
    t = tree["id"]
    p = _family(owner, t)
    r = owner.put(f"/trees/{t}/people/{p['Son']}/privacy", json={"privacy_level": "PRIVATE_TREE_ADMINS"})
    assert r.status_code == 200
    viewer = member_factory(["VIEWER"])
    desc = viewer.get(f"/trees/{t}/people/{p['Anita']}/descendants", params={"depth": 8}).json()
    assert sum(n["hidden"] for n in desc["nodes"]) == 1
    fam = viewer.get(f"/trees/{t}/people/{p['Anita']}/family").json()
    kids = [c for u in fam["unions"] for c in u["children"]]
    assert len(kids) == 1 and kids[0]["hidden"] is True and kids[0]["person"] is None
    assert p["Son"] not in str(desc) + str(fam)
    # hidden, then removed: the placeholder goes too
    assert owner.delete(f"/trees/{t}/people/{p['Son']}").status_code == 200
    desc = viewer.get(f"/trees/{t}/people/{p['Anita']}/descendants", params={"depth": 8}).json()
    assert not any(n["hidden"] for n in desc["nodes"])


def test_restore_brings_back_the_person_and_their_recorded_links(owner, tree):
    t = tree["id"]
    p = _family(owner, t)
    before = owner.get(f"/trees/{t}/people/{p['Anita']}/descendants", params={"depth": 8}).json()
    assert owner.delete(f"/trees/{t}/people/{p['Son']}").status_code == 200
    assert [x["id"] for x in owner.get(f"/trees/{t}/people/deleted").json()] == [p["Son"]]
    assert owner.post(f"/trees/{t}/people/{p['Son']}/restore").status_code == 200
    after = owner.get(f"/trees/{t}/people/{p['Anita']}/descendants", params={"depth": 8}).json()
    assert sorted(n["id"] for n in after["nodes"]) == sorted(n["id"] for n in before["nodes"])
    assert len(after["edges"]) == len(before["edges"]) and after["unions"] == before["unions"]
    assert owner.get(f"/trees/{t}/people/deleted").json() == []


def test_remove_and_restore_are_state_checked(owner, tree):
    t = tree["id"]
    p = _family(owner, t)
    # restoring someone who is not removed changes nothing and is not audited as a restore
    r = owner.post(f"/trees/{t}/people/{p['Son']}/restore")
    assert r.status_code == 409 and r.json()["error"]["code"] == "person_not_removed"
    assert owner.delete(f"/trees/{t}/people/{p['Son']}").status_code == 200
    assert owner.delete(f"/trees/{t}/people/{p['Son']}").status_code == 404  # already removed
    with owner_session() as s:
        rows = s.execute(
            text("SELECT action FROM audit_event WHERE target_id = :p ORDER BY created_at"), {"p": p["Son"]}
        ).scalars()
        assert [a for a in rows if a.startswith("person.") and a != "person.created"] == ["person.deleted"]


def test_concurrent_removals_have_one_winner(owner, tree, make_client):
    t = tree["id"]
    p = _family(owner, t)

    def remove(_):
        return owner.delete(f"/trees/{t}/people/{p['Son']}").status_code

    with ThreadPoolExecutor(max_workers=6) as pool:
        codes = sorted(pool.map(remove, range(6)))
    assert codes == [200, 404, 404, 404, 404, 404]
    with owner_session() as s:
        n = s.execute(
            text("SELECT count(*) FROM audit_event WHERE target_id = :p AND action = 'person.deleted'"),
            {"p": p["Son"]},
        ).scalar()
    assert n == 1


def test_removed_parent_can_be_replaced(owner, tree):
    """A removed parent no longer counts towards the two-biological-parents limit."""
    t = tree["id"]
    p = _family(owner, t)
    assert owner.delete(f"/trees/{t}/people/{p['Son']}").status_code == 200
    father = create_person(owner, t, "Father")["id"]
    link(owner, t, father, p["Grandkid"], "biological_parent")
    fam = owner.get(f"/trees/{t}/people/{p['Grandkid']}/family").json()
    assert sorted(x["person"]["id"] for x in fam["parents"]) == sorted([p["Bahu"], father])


# ---------------------------------------------------------------- permanent delete
def test_permanent_delete_removes_the_persons_links_and_nobody_elses_records(owner, tree):
    t = tree["id"]
    p = _family(owner, t)
    branch = owner.post(f"/trees/{t}/branches", json={"name": "Pandey", "founder_person_id": p["Son"]}).json()
    assert (
        owner.post(
            f"/trees/{t}/branches/{branch['id']}/members", json={"person_ids": [p["Son"], p["Grandkid"]]}
        ).status_code
        == 200
    )
    house = owner.post(f"/trees/{t}/households", json={"name": "Haveli"}).json()
    for pid in (p["Son"], p["Bahu"]):
        assert (
            owner.post(f"/trees/{t}/households/{house['id']}/members", json={"person_id": pid}).status_code
            == 201
        )
    assert owner.get(f"/trees/{t}/branches/{branch['id']}").json()["member_count"] == 2
    r = owner.post(f"/trees/{t}/people/{p['Son']}/erase", json={"reason": "family request", "confirm": True})
    assert r.status_code == 200 and "placeholder" not in r.json()["message"]
    with owner_session() as s:
        row = s.execute(
            text(
                "SELECT preferred_display_name, deleted_at IS NOT NULL, erased_at IS NOT NULL, notes,"
                " sex_at_birth FROM person WHERE id = :p"
            ),
            {"p": p["Son"]},
        ).one()
        assert tuple(row) == ("Erased person", True, True, None, None)  # an inert tombstone
        left = s.execute(
            text("SELECT count(*) FROM relationship WHERE person_a_id = :p OR person_b_id = :p"),
            {"p": p["Son"]},
        ).scalar()
        assert left == 0
        # everybody else, and every link between them, is untouched
        assert (
            s.execute(
                text("SELECT count(*) FROM person WHERE tree_id = :t AND deleted_at IS NULL"), {"t": t}
            ).scalar()
            == 4
        )
        others = s.execute(
            text("SELECT type FROM relationship WHERE tree_id = :t ORDER BY type"), {"t": t}
        ).scalars()
        assert list(others) == ["biological_parent", "spouse"]
        for table in ("branch_membership", "household_membership", "name_record"):
            n = s.execute(
                text(f"SELECT count(*) FROM {table} WHERE person_id = :p"), {"p": p["Son"]}
            ).scalar()
            assert n == (1 if table == "name_record" else 0), table
    b = owner.get(f"/trees/{t}/branches/{branch['id']}").json()
    assert b["member_count"] == 1 and b["hidden_member_count"] == 0 and b["founder_person_id"] is None
    h = owner.get(f"/trees/{t}/households/{house['id']}").json()
    assert h["member_count"] == 1 and h["hidden_member_count"] == 0
    # gone for admins too: not listed, not restorable, not deletable twice, not openable
    assert owner.get(f"/trees/{t}/people/deleted").json() == []
    assert owner.post(f"/trees/{t}/people/{p['Son']}/restore").status_code == 404
    assert owner.get(f"/trees/{t}/people/{p['Son']}").status_code == 404
    again = owner.post(f"/trees/{t}/people/{p['Son']}/erase", json={"reason": "again", "confirm": True})
    assert again.status_code == 404


def test_a_removed_person_can_then_be_permanently_deleted(owner, tree):
    t = tree["id"]
    p = _family(owner, t)
    assert owner.delete(f"/trees/{t}/people/{p['Son']}").status_code == 200
    r = owner.post(f"/trees/{t}/people/{p['Son']}/erase", json={"reason": "duplicate", "confirm": True})
    assert r.status_code == 200
    assert owner.get(f"/trees/{t}/people/deleted").json() == []


def test_permanent_delete_needs_explicit_confirmation_and_a_reason(owner, tree):
    t = tree["id"]
    p = _family(owner, t)
    assert (
        owner.post(
            f"/trees/{t}/people/{p['Son']}/erase", json={"reason": "x" * 5, "confirm": False}
        ).status_code
        == 422
    )
    assert (
        owner.post(f"/trees/{t}/people/{p['Son']}/erase", json={"reason": "no", "confirm": True}).status_code
        == 422
    )
    assert owner.get(f"/trees/{t}/people/{p['Son']}").status_code == 200


def test_removed_members_leave_branch_and_household_counts(owner, tree):
    t = tree["id"]
    p = _family(owner, t)
    branch = owner.post(f"/trees/{t}/branches", json={"name": "Pandey"}).json()
    owner.post(f"/trees/{t}/branches/{branch['id']}/members", json={"person_ids": [p["Son"], p["Bahu"]]})
    assert owner.delete(f"/trees/{t}/people/{p['Son']}").status_code == 200
    detail = owner.get(f"/trees/{t}/branches/{branch['id']}").json()
    assert detail["member_count"] == 1 and detail["hidden_member_count"] == 0
    assert [b["member_count"] for b in owner.get(f"/trees/{t}/branches").json()] == [1]
    assert owner.post(f"/trees/{t}/people/{p['Son']}/restore").status_code == 200
    assert owner.get(f"/trees/{t}/branches/{branch['id']}").json()["member_count"] == 2


# ---------------------------------------------------------------- authorisation
def test_roles(owner, tree, member_factory):
    t = tree["id"]
    p = _family(owner, t)
    viewer, contributor = member_factory(["VIEWER"]), member_factory(["CONTRIBUTOR"])
    erase = {"reason": "request", "confirm": True}
    assert viewer.delete(f"/trees/{t}/people/{p['Son']}").status_code == 403
    assert viewer.post(f"/trees/{t}/people/{p['Son']}/erase", json=erase).status_code == 403
    assert contributor.post(f"/trees/{t}/people/{p['Son']}/erase", json=erase).status_code == 403
    assert contributor.delete(f"/trees/{t}/people/{p['Son']}").status_code == 200
    assert contributor.post(f"/trees/{t}/people/{p['Son']}/restore").status_code == 403
    assert contributor.get(f"/trees/{t}/people/deleted").status_code == 403
    assert viewer.post(f"/trees/{t}/people/{p['Son']}/restore").status_code == 403
    assert member_factory(["FAMILY_ADMIN"]).post(f"/trees/{t}/people/{p['Son']}/restore").status_code == 200


def test_branch_admin_cannot_remove_or_delete_outside_their_branch(owner, tree, member_factory):
    t = tree["id"]
    p = _family(owner, t)
    branch = owner.post(f"/trees/{t}/branches", json={"name": "Bahu's side"}).json()
    owner.post(f"/trees/{t}/branches/{branch['id']}/members", json={"person_ids": [p["Bahu"]]})
    admin = member_factory(["BRANCH_ADMIN"], branch["id"])
    assert admin.delete(f"/trees/{t}/people/{p['Son']}").status_code == 403
    assert admin.post(
        f"/trees/{t}/people/{p['Bahu']}/erase", json={"reason": "no", "confirm": True}
    ).status_code in (403, 422)
    assert (
        admin.post(
            f"/trees/{t}/people/{p['Bahu']}/erase", json={"reason": "mine", "confirm": True}
        ).status_code
        == 403
    )
    assert admin.delete(f"/trees/{t}/people/{p['Bahu']}").status_code == 200
    assert admin.post(f"/trees/{t}/people/{p['Bahu']}/restore").status_code == 403


def test_other_trees_cannot_remove_restore_or_delete(owner, tree, make_client):
    t = tree["id"]
    p = _family(owner, t)
    outsider = make_client()
    outsider.register(name="Outsider")
    theirs = new_tree(outsider, "Other Family")["id"]
    erase = {"reason": "request", "confirm": True}
    for tree_id in (t, theirs):  # neither through this tree nor by smuggling the id into their own
        assert outsider.delete(f"/trees/{tree_id}/people/{p['Son']}").status_code == 404
        assert outsider.post(f"/trees/{tree_id}/people/{p['Son']}/erase", json=erase).status_code == 404
        assert outsider.post(f"/trees/{tree_id}/people/{p['Son']}/restore").status_code == 404
    assert owner.delete(f"/trees/{t}/people/{p['Son']}").status_code == 200
    assert outsider.post(f"/trees/{theirs}/people/{p['Son']}/restore").status_code == 404
    assert owner.get(f"/trees/{t}/people/{p['Anita']}").status_code == 200


def test_unauthenticated_cannot_remove(client, owner, tree):
    t = tree["id"]
    p = _family(owner, t)
    assert client.delete(f"/trees/{t}/people/{p['Son']}").status_code in (401, 403, 404)
    assert owner.get(f"/trees/{t}/people/{p['Son']}").status_code == 200
