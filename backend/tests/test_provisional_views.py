"""Provisional people in headline counts and the "To complete" view (ADR-0020 §8; issues #32, #33).

Headline member counts never include a pending provisional person (unnamed or unverified), for
any viewer. A separate administrative count, and the "To complete" filter on the people list,
show them only to people who may see them: the creator, tree admins and explicit grants.
"""

from __future__ import annotations

from typing import Any

from tests.conftest import new_tree
from tests.helpers import create_person, person_body
from tests.test_provisional_people import _mama_via_unknown_mother, _verify


def _to_complete(client: Any, t: str, *states: str, **params: Any) -> Any:
    return client.get(
        f"/trees/{t}/people",
        params=[("provisional_state", s) for s in (states or ("needs_details", "unverified"))]
        + list(params.items()),
    )


def _ids(resp: Any) -> list[str]:
    assert resp.status_code == 200, resp.text
    return [p["id"] for p in resp.json()["items"]]


# ------------------------------------------------------------------ #32 headline counts
def test_branch_and_household_counts_leave_out_pending_provisional_people(owner, tree, member_factory):
    t = tree["id"]
    branch = owner.post(f"/trees/{t}/branches", json={"name": "Verma"}).json()
    me = create_person(owner, t, "Aarav", status="deceased", sex="male", branch_ids=[branch["id"]])
    creator = member_factory(["CONTRIBUTOR"], name="Creator")
    other = member_factory(["CONTRIBUTOR"], name="Other")
    prov, _ = _mama_via_unknown_mother(creator, t, me["id"])
    assert (
        owner.post(
            f"/trees/{t}/branches/{branch['id']}/members", json={"person_ids": [prov["id"]]}
        ).status_code
        == 200
    )
    household = owner.post(f"/trees/{t}/households", json={"name": "Verma haveli"}).json()
    for pid in (me["id"], prov["id"]):
        r = owner.post(f"/trees/{t}/households/{household['id']}/members", json={"person_id": pid})
        assert r.status_code == 201, r.text

    def counts(client: Any) -> tuple[tuple[int, int], tuple[int, int], int]:
        b = client.get(f"/trees/{t}/branches/{branch['id']}").json()
        listed = next(x for x in client.get(f"/trees/{t}/branches").json() if x["id"] == branch["id"])
        assert (listed["member_count"], listed["provisional_member_count"]) == (
            b["member_count"],
            b["provisional_member_count"],
        )
        h = client.get(f"/trees/{t}/households/{household['id']}").json()
        return (
            (b["member_count"], b["provisional_member_count"]),
            (h["member_count"], h["provisional_member_count"]),
            b["hidden_member_count"] + h["hidden_member_count"],
        )

    # headline counts are the same for everyone: Aarav only
    assert counts(owner) == ((1, 1), (1, 1), 0)
    assert counts(creator) == ((1, 1), (1, 1), 0)
    # someone who cannot see her learns nothing: no administrative count, no hidden count
    assert counts(other) == ((1, 0), (1, 0), 0)

    # named and verified: an ordinary member, counted for everyone
    owner.post(f"/trees/{t}/people/{prov['id']}/names", json={"given_name": "Sunita"})
    _verify(owner, t, prov["id"])
    assert counts(owner) == ((2, 0), (2, 0), 0)
    # still CUSTOM privacy: the other contributor sees a private member, never who
    assert counts(other)[0] == (2, 0)


def test_fan_chart_summary_counts_pending_ancestors_as_to_complete(owner, tree, member_factory):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="deceased", sex="male")
    _mama_via_unknown_mother(owner, t, me["id"])
    r = owner.get(f"/trees/{t}/viz/ancestry", params={"root": me["id"], "generations": 2})
    assert r.status_code == 200, r.text
    assert "0 known, 1 to complete, 0 private" in r.json()["summary"]
    viewer = member_factory(["VIEWER"])
    summary = viewer.get(f"/trees/{t}/viz/ancestry", params={"root": me["id"], "generations": 2}).json()[
        "summary"
    ]
    assert "to complete" not in summary and "0 known, 0 private" in summary


# ------------------------------------------------------------------ #33 "To complete" view
def test_to_complete_lists_only_what_the_caller_may_see(owner, tree, member_factory):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="deceased", sex="male")
    creator = member_factory(["CONTRIBUTOR"], name="Creator")
    other = member_factory(["CONTRIBUTOR"], name="Other")
    viewer = member_factory(["VIEWER"], name="Viewer")
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    mine, _ = _mama_via_unknown_mother(creator, t, me["id"])
    owners, _ = _mama_via_unknown_mother(owner, t, create_person(owner, t, "Kabir", status="deceased")["id"])

    assert _ids(_to_complete(creator, t)) == [mine["id"]]
    assert sorted(_ids(_to_complete(owner, t))) == sorted([mine["id"], owners["id"]])
    assert sorted(_ids(_to_complete(admin, t))) == sorted([mine["id"], owners["id"]])
    for who in (other, viewer):
        r = _to_complete(who, t)
        assert _ids(r) == [] and r.json()["next_cursor"] is None
        assert mine["id"] not in r.text and owners["id"] not in r.text
    # the plain list never offers ordinary people under the filter
    assert me["id"] not in _ids(_to_complete(owner, t))


def test_to_complete_moves_from_needs_details_to_unverified_then_leaves(owner, tree):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="deceased", sex="male")
    prov, _ = _mama_via_unknown_mother(owner, t, me["id"])
    pid = prov["id"]
    assert _ids(_to_complete(owner, t, "needs_details")) == [pid]
    assert _ids(_to_complete(owner, t, "unverified")) == []

    owner.post(f"/trees/{t}/people/{pid}/names", json={"given_name": "Sunita"})
    assert _ids(_to_complete(owner, t, "needs_details")) == []
    items = _to_complete(owner, t, "unverified").json()["items"]
    assert [(p["id"], p["provisional_state"]) for p in items] == [(pid, "unverified")]

    _verify(owner, t, pid)
    assert _ids(_to_complete(owner, t)) == []
    assert _ids(_to_complete(owner, t, "verified")) == [pid]


def test_to_complete_works_with_search_status_and_pagination(owner, tree):
    t = tree["id"]
    anchors = [create_person(owner, t, f"Anchor{i}", status="deceased")["id"] for i in range(3)]
    provs = [_mama_via_unknown_mother(owner, t, a)[0]["id"] for a in anchors]
    first = _to_complete(owner, t, limit=2).json()
    assert len(first["items"]) == 2 and first["next_cursor"]
    second = _to_complete(owner, t, limit=2, cursor=first["next_cursor"]).json()
    assert len(second["items"]) == 1 and second["next_cursor"] is None
    assert sorted(p["id"] for p in first["items"] + second["items"]) == sorted(provs)
    # combined with the status filter (provisional people are "unknown")
    assert len(_ids(_to_complete(owner, t, status="unknown"))) == 3
    assert _ids(_to_complete(owner, t, status="living")) == []
    # combined with a name search: search matches name records, so unnamed people are not found
    # by name; once one is named (still unverified) the search finds exactly that person
    assert _ids(_to_complete(owner, t, q="Unnamed")) == []
    owner.post(f"/trees/{t}/people/{provs[0]}/names", json={"given_name": "Sunita"})
    assert _ids(_to_complete(owner, t, "unverified", q="Sunita")) == [provs[0]]
    assert _ids(_to_complete(owner, t, "needs_details", q="Sunita")) == []


def test_to_complete_is_tree_scoped_and_validated(owner, tree):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="deceased", sex="male")
    prov, _ = _mama_via_unknown_mother(owner, t, me["id"])
    other_tree = new_tree(owner, "Other family")
    assert prov["id"] not in _to_complete(owner, other_tree["id"]).text
    assert _to_complete(owner, t, "everything").status_code == 422


def test_to_complete_needs_tree_membership(owner, tree, client):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="deceased", sex="male")
    _mama_via_unknown_mother(owner, t, me["id"])
    client.register(name="Stranger")
    assert _to_complete(client, t).status_code == 404


def test_plain_people_list_is_unchanged(owner, tree):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="deceased", sex="male")
    prov, mama = _mama_via_unknown_mother(owner, t, me["id"])
    assert set(_ids(owner.get(f"/trees/{t}/people"))) == {me["id"], prov["id"], mama["id"]}
    assert owner.post(f"/trees/{t}/people", json=person_body("Ravi")).status_code == 201
