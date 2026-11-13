"""Regression tests for full-tree navigation and removed-person graph privacy."""

from __future__ import annotations

from tests.conftest import new_tree
from tests.helpers import create_person, link


def ids(graph):
    return {n["person"]["id"] for n in graph["nodes"] if n["person"]}


def test_connected_view_includes_ancestors_descendants_side_branches_and_partner(owner, tree):
    t = tree["id"]
    grandfather = create_person(owner, t, "Grandfather")
    grandmother = create_person(owner, t, "Grandmother")
    father = create_person(owner, t, "Father")
    aunt = create_person(owner, t, "Aunt")
    mother = create_person(owner, t, "Mother")
    daughter = create_person(owner, t, "Daughter")
    grandson = create_person(owner, t, "Grandson")
    unrelated = create_person(owner, t, "Unrelated")
    for parent, child in [
        (grandfather, father),
        (grandmother, father),
        (grandfather, aunt),
        (grandmother, aunt),
        (father, daughter),
        (mother, daughter),
        (daughter, grandson),
    ]:
        link(owner, t, parent["id"], child["id"], "biological_parent")
    link(owner, t, father["id"], mother["id"], "spouse")
    reply = owner.get(f"/trees/{t}/people/{daughter['id']}/connected")
    assert reply.status_code == 200, reply.text
    data = reply.json()
    assert data["direction"] == "connected"
    assert data["truncated"] is False
    assert ids(data) == {
        grandfather["id"],
        grandmother["id"],
        father["id"],
        aunt["id"],
        mother["id"],
        daughter["id"],
        grandson["id"],
    }
    assert unrelated["id"] not in ids(data)
    assert data["edges"] and data["unions"]


def test_soft_removed_person_does_not_return_as_private_placeholder_or_bridge(owner, tree):
    t = tree["id"]
    grandfather = create_person(owner, t, "Grandfather")
    middle = create_person(owner, t, "Middle")
    grandchild = create_person(owner, t, "Grandchild")
    link(owner, t, grandfather["id"], middle["id"], "biological_parent")
    link(owner, t, middle["id"], grandchild["id"], "biological_parent")
    assert len(ids(owner.get(f"/trees/{t}/people/{grandfather['id']}/connected").json())) == 3
    removed = owner.delete(f"/trees/{t}/people/{middle['id']}")
    assert removed.status_code == 200, removed.text
    for path in ("descendants", "connected"):
        graph = owner.get(f"/trees/{t}/people/{grandfather['id']}/{path}").json()
        assert ids(graph) == {grandfather["id"]}
        assert all(not node["hidden"] for node in graph["nodes"])
        assert not graph["edges"]
    ancestor_graph = owner.get(f"/trees/{t}/people/{grandchild['id']}/ancestors").json()
    assert ids(ancestor_graph) == {grandchild["id"]}
    assert all(not node["hidden"] for node in ancestor_graph["nodes"])
    fam = owner.get(f"/trees/{t}/people/{grandfather['id']}/family").json()
    assert fam["other_children"] == []
    restored = owner.post(f"/trees/{t}/people/{middle['id']}/restore")
    assert restored.status_code == 200, restored.text
    assert ids(owner.get(f"/trees/{t}/people/{grandfather['id']}/connected").json()) == {
        grandfather["id"],
        middle["id"],
        grandchild["id"],
    }


def test_erased_person_is_not_drawn_or_listed(owner, tree):
    t = tree["id"]
    parent = create_person(owner, t, "Parent")
    erased = create_person(owner, t, "DeleteMe")
    link(owner, t, parent["id"], erased["id"], "biological_parent")
    reply = owner.post(
        f"/trees/{t}/people/{erased['id']}/erase",
        json={"reason": "Requested deletion", "confirm": True},
    )
    assert reply.status_code == 200, reply.text
    for direction in ("descendants", "connected"):
        graph = owner.get(f"/trees/{t}/people/{parent['id']}/{direction}").json()
        assert ids(graph) == {parent["id"]}
        assert not any(n["hidden"] for n in graph["nodes"])
    assert all(p["display_name"] != "Erased person" for p in owner.get(f"/trees/{t}/people").json()["items"])


def test_connected_view_does_not_expose_hidden_names_or_cross_tree_data(owner, tree, member_factory):
    t = tree["id"]
    public = create_person(owner, t, "PublicAncestor")
    secret = create_person(owner, t, "PrivateName", privacy_level="PRIVATE_TREE_ADMINS")
    link(owner, t, public["id"], secret["id"], "biological_parent")
    viewer = member_factory(["VIEWER"])
    result = viewer.get(f"/trees/{t}/people/{public['id']}/connected")
    assert result.status_code == 200
    assert "PrivateName" not in result.text
    assert secret["id"] not in result.text
    assert any(node["hidden"] for node in result.json()["nodes"])
    other_tree = new_tree(owner, "Separate Family")
    foreign = create_person(owner, other_tree["id"], "OtherTree")
    assert viewer.get(f"/trees/{other_tree['id']}/people/{foreign['id']}/connected").status_code == 404
