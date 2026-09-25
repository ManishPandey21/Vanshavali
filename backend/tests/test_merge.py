from __future__ import annotations

from tests.helpers import create_person, exact, link


def test_merge_and_revert_restores_everything(owner, tree, member_factory):
    t = tree["id"]
    dad = create_person(owner, t, "Dad", sex="male")
    a = create_person(owner, t, "Subramanian", sex="male", birth={"date": exact(1930, 1, 1)})
    b = create_person(
        owner, t, "Subramaniam", sex="male", birth={"date": {"precision": "year_only", "year": 1930}}
    )
    wife = create_person(owner, t, "Wife", sex="female")
    link(owner, t, dad["id"], a["id"], "biological_parent")
    link(owner, t, dad["id"], b["id"], "biological_parent")  # duplicate edge after merge
    link(owner, t, b["id"], wife["id"], "spouse")
    owner.post(f"/trees/{t}/people/{b['id']}/heritage", json={"attribute": "gotra", "value_text": "Atri"})

    viewer = member_factory(["VIEWER"])
    assert (
        viewer.post(f"/trees/{t}/merges", json={"survivor_id": a["id"], "merged_id": b["id"]}).status_code
        == 403
    )

    prev = owner.get(f"/trees/{t}/merges/preview", params={"survivor": a["id"], "merged": b["id"]}).json()
    assert prev["references_to_move"]["name_record"] == 1

    r = owner.post(
        f"/trees/{t}/merges", json={"survivor_id": a["id"], "merged_id": b["id"], "reason": "same person"}
    )
    assert r.status_code == 201, r.text
    merge_id = r.json()["id"]
    assert owner.get(f"/trees/{t}/people/{b['id']}").status_code == 404
    person = owner.get(f"/trees/{t}/people/{a['id']}").json()
    assert {n["given_name"] for n in person["names"]} == {"Subramanian", "Subramaniam"}
    assert person["display_name"] == "Subramanian Iyer"  # survivor's preferred name kept
    events = owner.get(f"/trees/{t}/people/{a['id']}/events?type=birth").json()
    assert len(events) == 2  # both birth claims preserved (conflict retained)
    fam = owner.get(f"/trees/{t}/people/{a['id']}/family").json()
    assert len(fam["parents"]) == 1 and fam["unions"][0]["partner"]["person"]["id"] == wife["id"]
    assert (
        owner.get(f"/trees/{t}/people/{a['id']}/heritage").json()["attributes"][0]["preferred"]["value_text"]
        == "Atri"
    )

    rv = owner.post(f"/trees/{t}/merges/{merge_id}/revert")
    assert rv.status_code == 200 and rv.json()["reverted_at"]
    assert owner.post(f"/trees/{t}/merges/{merge_id}/revert").status_code == 409
    restored = owner.get(f"/trees/{t}/people/{b['id']}").json()
    assert [n["given_name"] for n in restored["names"]] == ["Subramaniam"]
    assert restored["display_name"] == "Subramaniam Iyer"
    fam_b = owner.get(f"/trees/{t}/people/{b['id']}/family").json()
    assert fam_b["parents"][0]["person"]["id"] == dad["id"]
    assert fam_b["unions"][0]["partner"]["person"]["id"] == wife["id"]
    fam_a = owner.get(f"/trees/{t}/people/{a['id']}/family").json()
    assert fam_a["unions"] == []
    assert len(owner.get(f"/trees/{t}/people/{a['id']}/events?type=birth").json()) == 1
