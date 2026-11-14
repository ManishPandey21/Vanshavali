"""The complete family graph (ADR-0034 §4): connected and whole-tree scopes, paging, privacy.

Several cases started as draft PR #82's ``test_connected_tree.py`` and were rewritten for the paged
endpoint.
"""

from __future__ import annotations

import time
import uuid
from itertools import pairwise

import pytest

from tests.conftest import new_tree, owner_session
from tests.helpers import create_person, link


def page(client, t, **params):
    r = client.get(f"/trees/{t}/family-graph", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def load_all(client, t, **params):
    """Follow cursors to the end, as the SPA does. Returns the merged graph and the page count."""
    first = page(client, t, **params)
    nodes, edges, links, pages, cur = [*first["nodes"]], [*first["edges"]], [*first["links"]], 1, first
    while not cur["complete"]:
        assert cur["next_cursor"]
        cur = page(client, t, **{**params, "cursor": cur["next_cursor"]})
        assert cur["revision"] == first["revision"] and cur["total_nodes"] == first["total_nodes"]
        nodes += cur["nodes"]
        edges += cur["edges"]
        links += cur["links"]
        pages += 1
    assert cur["next_cursor"] is None
    return {**first, "nodes": nodes, "edges": edges, "links": links}, pages


def names(g):
    return sorted(n["person"]["display_name"].split()[0] for n in g["nodes"] if n["person"])


def gen(g, name):
    return next(
        n["generation"] for n in g["nodes"] if n["person"] and n["person"]["display_name"].startswith(name)
    )


@pytest.fixture
def family(owner, tree):
    """Three generations with both sides of two marriages, a second marriage and an unrelated pair.

    Nana = Nani          Dada = Dadi
      |      \\             |
    Mama     Anita ===== Ramesh ===== (2nd) Sita
                   |             |
                  Son === Bahu   Half          Samdhi -> Bahu,  Saala (Bahu's brother, explicit)
                       |
                    Grandkid                   Stranger = Other (not linked to anyone above)
    """
    t = tree["id"]
    p = {
        n: create_person(owner, t, n, "Pandey")["id"]
        for n in [
            "Nana",
            "Nani",
            "Mama",
            "Anita",
            "Ramesh",
            "Dada",
            "Dadi",
            "Sita",
            "Half",
            "Son",
            "Bahu",
            "Samdhi",
            "Saala",
            "Grandkid",
            "Stranger",
            "Other",
        ]
    }
    for par in ("Nana", "Nani"):
        link(owner, t, p[par], p["Anita"], "biological_parent")
        link(owner, t, p[par], p["Mama"], "biological_parent")
    for par in ("Dada", "Dadi"):
        link(owner, t, p[par], p["Ramesh"], "biological_parent")
    link(owner, t, p["Nana"], p["Nani"], "spouse")
    link(owner, t, p["Dada"], p["Dadi"], "spouse")
    link(owner, t, p["Anita"], p["Ramesh"], "spouse")
    link(owner, t, p["Ramesh"], p["Sita"], "divorced_spouse")
    link(owner, t, p["Ramesh"], p["Half"], "biological_parent")
    link(owner, t, p["Sita"], p["Half"], "biological_parent")
    for par in ("Anita", "Ramesh"):
        link(owner, t, p[par], p["Son"], "biological_parent")
    link(owner, t, p["Son"], p["Bahu"], "spouse")
    link(owner, t, p["Samdhi"], p["Bahu"], "biological_parent")
    link(owner, t, p["Bahu"], p["Saala"], "sibling")
    for par in ("Son", "Bahu"):
        link(owner, t, p[par], p["Grandkid"], "biological_parent")
    link(owner, t, p["Stranger"], p["Other"], "spouse")
    return t, p


CONNECTED = sorted(
    [
        "Nana",
        "Nani",
        "Mama",
        "Anita",
        "Ramesh",
        "Dada",
        "Dadi",
        "Sita",
        "Half",
        "Son",
        "Bahu",
        "Samdhi",
        "Saala",
        "Grandkid",
    ]
)


# ---------------------------------------------------------------- connected scope
def test_connected_family_reaches_every_linked_relative_from_any_member(owner, family):
    t, p = family
    for start in ("Anita", "Grandkid", "Samdhi", "Sita", "Mama"):
        g, _ = load_all(owner, t, scope="connected", person_id=p[start])
        assert names(g) == CONNECTED, start
        assert g["complete"] is True or g["total_nodes"] == len(g["nodes"])
        assert g["total_nodes"] == g["total_people"] == 14
        assert len({n["id"] for n in g["nodes"]}) == 14  # nobody is drawn twice
        assert not any(n["hidden"] for n in g["nodes"])


def test_generations_put_partners_on_one_row_and_children_below(owner, family):
    t, p = family
    g, _ = load_all(owner, t, scope="connected", person_id=p["Anita"])
    assert gen(g, "Anita") == 0 == gen(g, "Ramesh") == gen(g, "Sita") == gen(g, "Mama")
    assert gen(g, "Nana") == gen(g, "Nani") == gen(g, "Dada") == gen(g, "Dadi") == -1
    assert gen(g, "Son") == gen(g, "Bahu") == gen(g, "Half") == gen(g, "Saala") == 1
    assert gen(g, "Samdhi") == 0  # an in-law's parent sits one row above the in-law, not at the top
    assert gen(g, "Grandkid") == 2


def test_edges_keep_their_types_and_each_is_sent_once(owner, family):
    t, p = family
    g, pages = load_all(owner, t, scope="connected", person_id=p["Anita"], limit=3)
    assert pages == 5
    assert len(g["edges"]) == 13 and len({(e["source"], e["target"], e["type"]) for e in g["edges"]}) == 13
    kinds = sorted((ln["kind"], ln["type"]) for ln in g["links"])
    assert kinds == sorted([("union", "spouse")] * 4 + [("union", "divorced_spouse"), ("sibling", "sibling")])
    ids = {n["id"] for n in g["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in g["edges"])
    assert all(ln["a"] in ids and ln["b"] in ids for ln in g["links"])


def test_a_partial_result_never_claims_to_be_complete(owner, family):
    t, p = family
    first = page(owner, t, scope="connected", person_id=p["Anita"], limit=5)
    assert first["complete"] is False and first["next_cursor"]
    assert len(first["nodes"]) == 5 and first["total_nodes"] == 14 and first["offset"] == 0
    assert first["nodes"][0]["person"]["id"] == p["Anita"]  # nearest relatives first
    whole, _ = load_all(owner, t, scope="connected", person_id=p["Anita"], limit=5)
    one, pages = load_all(owner, t, scope="connected", person_id=p["Anita"])
    assert pages == 1 and one["complete"] is True
    assert [n["id"] for n in whole["nodes"]] == [n["id"] for n in one["nodes"]]  # stable order


def test_no_generation_limit(owner, tree):
    t = tree["id"]
    chain = [create_person(owner, t, f"G{i}")["id"] for i in range(40)]
    for a, b in pairwise(chain):
        link(owner, t, a, b, "biological_parent")
    g, _ = load_all(owner, t, scope="connected", person_id=chain[20])
    assert g["total_people"] == 40
    assert sorted(n["generation"] for n in g["nodes"]) == list(range(-20, 20))
    # the focused views keep their documented limit
    assert owner.get(f"/trees/{t}/people/{chain[0]}/descendants", params={"depth": 26}).status_code == 422
    assert len(owner.get(f"/trees/{t}/people/{chain[0]}/descendants").json()["nodes"]) == 5


def test_repeated_ancestors_and_cross_generation_marriage_do_not_loop_or_duplicate(owner, tree):
    t = tree["id"]
    p = {
        n: create_person(owner, t, n)["id"]
        for n in ["Root", "A", "B", "CousinA", "CousinB", "Child", "Uncle", "Niece"]
    }
    link(owner, t, p["Root"], p["A"], "biological_parent")
    link(owner, t, p["Root"], p["B"], "biological_parent")
    link(owner, t, p["A"], p["CousinA"], "biological_parent")
    link(owner, t, p["B"], p["CousinB"], "biological_parent")
    link(owner, t, p["CousinA"], p["CousinB"], "spouse")  # cousin marriage: Root is reached twice
    for par in ("CousinA", "CousinB"):
        link(owner, t, p[par], p["Child"], "biological_parent")
    link(owner, t, p["Root"], p["Uncle"], "biological_parent")
    link(owner, t, p["A"], p["Niece"], "biological_parent")
    link(owner, t, p["Uncle"], p["Niece"], "spouse")  # uncle-niece marriage: the rows contradict
    g, _ = load_all(owner, t, scope="connected", person_id=p["Child"])
    assert len(g["nodes"]) == 8 == len({n["id"] for n in g["nodes"]})
    assert gen(g, "Root") < gen(g, "A") < gen(g, "CousinA") < gen(g, "Child")


def test_adoptive_step_and_guardian_links_are_followed(owner, tree):
    t = tree["id"]
    p = {n: create_person(owner, t, n)["id"] for n in ["Child", "Adoptive", "Step", "Guardian", "Foster"]}
    for who, kind in (
        ("Adoptive", "adoptive_parent"),
        ("Step", "step_parent"),
        ("Guardian", "guardian"),
        ("Foster", "foster_parent"),
    ):
        link(owner, t, p[who], p["Child"], kind)
    g, _ = load_all(owner, t, scope="connected", person_id=p["Adoptive"])
    assert names(g) == sorted(p)
    assert sorted(e["type"] for e in g["edges"]) == [
        "adoptive_parent",
        "foster_parent",
        "guardian",
        "step_parent",
    ]


def test_disproven_links_do_not_connect(owner, tree):
    t = tree["id"]
    a, b = create_person(owner, t, "A")["id"], create_person(owner, t, "B")["id"]
    link(owner, t, a, b, "biological_parent", evidence_status="DISPROVEN")
    g, _ = load_all(owner, t, scope="connected", person_id=a)
    assert names(g) == ["A"]


# ---------------------------------------------------------------- whole tree
def test_all_scope_shows_disconnected_groups_separately(owner, family):
    t, p = family
    loner = create_person(owner, t, "Loner")["id"]
    g, _ = load_all(owner, t, scope="all", limit=4)
    assert g["root_id"] is None and g["total_people"] == 17
    assert [(c["size"], c["people"]) for c in g["components"]] == [(14, 14), (2, 2), (1, 1)]
    by_comp: dict[int, set[str]] = {}
    for n in g["nodes"]:
        by_comp.setdefault(n["component"], set()).add(n["person"]["id"])
    assert by_comp[1] == {p["Stranger"], p["Other"]} and by_comp[2] == {loner}
    ids_of = {n["id"]: n["component"] for n in g["nodes"]}
    # no edge or link joins two groups
    assert all(ids_of[e["source"]] == ids_of[e["target"]] for e in g["edges"])
    assert all(ids_of[ln["a"]] == ids_of[ln["b"]] for ln in g["links"])
    # the connected scope never includes the other groups
    assert "Stranger" not in names(load_all(owner, t, scope="connected", person_id=p["Anita"])[0])


def test_connected_requires_a_person(owner, tree):
    r = owner.get(f"/trees/{tree['id']}/family-graph", params={"scope": "connected"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "person_required"


# ---------------------------------------------------------------- removed and deleted people
def test_removed_linking_person_splits_the_family_and_leaves_no_placeholder(owner, family):
    t, p = family
    assert owner.delete(f"/trees/{t}/people/{p['Son']}").status_code == 200
    up, _ = load_all(owner, t, scope="connected", person_id=p["Anita"])
    assert names(up) == sorted(["Nana", "Nani", "Mama", "Anita", "Ramesh", "Dada", "Dadi", "Sita", "Half"])
    down, _ = load_all(owner, t, scope="connected", person_id=p["Grandkid"])
    assert names(down) == sorted(["Grandkid", "Bahu", "Samdhi", "Saala"])
    for g in (up, down):
        assert not any(n["hidden"] or n["person"] is None for n in g["nodes"])
        assert p["Son"] not in str(g)
    everything, _ = load_all(owner, t, scope="all")
    assert [c["people"] for c in everything["components"]] == [9, 4, 2]
    assert p["Son"] not in str(everything)
    # nobody else was removed, and no parent was invented for Grandkid
    assert [e for e in down["edges"] if e["target"] == p["Grandkid"]] == [
        {"source": p["Bahu"], "target": p["Grandkid"], "type": "biological_parent", "lineage": "biological"}
    ]
    # restoring brings back the person and the recorded links
    assert owner.post(f"/trees/{t}/people/{p['Son']}/restore").status_code == 200
    assert names(load_all(owner, t, scope="connected", person_id=p["Grandkid"])[0]) == CONNECTED


def test_permanently_deleted_person_is_absent_and_not_a_root(owner, family):
    t, p = family
    r = owner.post(f"/trees/{t}/people/{p['Son']}/erase", json={"reason": "request", "confirm": True})
    assert r.status_code == 200, r.text
    g, _ = load_all(owner, t, scope="all")
    assert "Erased person" not in str(g) and p["Son"] not in str(g)
    assert not any(n["hidden"] for n in g["nodes"])
    r = owner.get(f"/trees/{t}/family-graph", params={"scope": "connected", "person_id": p["Son"]})
    assert r.status_code == 404


def test_someone_really_named_erased_person_is_an_ordinary_person(owner, tree):
    """From PR #82: the state is the ``erased_at`` marker, never a display name."""
    t = tree["id"]
    named = owner.post(
        f"/trees/{t}/people",
        json={
            "profile_status": "deceased",
            "names": [{"full_name_as_recorded": "Erased person", "is_preferred": True}],
        },
    )
    assert named.status_code == 201, named.text
    g, _ = load_all(owner, t, scope="connected", person_id=named.json()["id"])
    assert [n["person"]["display_name"] for n in g["nodes"]] == ["Erased person"]


# ---------------------------------------------------------------- privacy
def _hide(owner, t, pid):
    r = owner.put(f"/trees/{t}/people/{pid}/privacy", json={"privacy_level": "PRIVATE_TREE_ADMINS"})
    assert r.status_code == 200, r.text


def test_hidden_person_on_the_line_of_descent_is_a_placeholder_and_is_walked_past(
    owner, family, member_factory
):
    t, p = family
    _hide(owner, t, p["Son"])
    viewer = member_factory(["VIEWER"])
    g, _ = load_all(viewer, t, scope="connected", person_id=p["Anita"])
    hidden = [n for n in g["nodes"] if n["hidden"]]
    assert len(hidden) == 1 and hidden[0]["person"] is None and hidden[0]["id"].startswith("hidden-")
    assert hidden[0]["generation"] == 1
    # descent continues past the hidden son to his child...
    assert "Grandkid" in names(g)
    # ...but not through his marriage into his wife's family (she is only there as the child's parent)
    assert "Bahu" in names(g) and "Samdhi" in names(g)
    raw = str(g)
    assert p["Son"] not in raw and "Son Pandey" not in raw
    assert g["total_people"] == 13 and g["total_nodes"] == 14
    # the owner sees the same person by name
    assert "Son" in names(load_all(owner, t, scope="connected", person_id=p["Anita"])[0])


def test_hidden_spouse_is_a_leaf_and_their_family_is_not_revealed(owner, tree, member_factory):
    t = tree["id"]
    p = {n: create_person(owner, t, n)["id"] for n in ["Wife", "Husband", "HusbandFather", "HusbandBrother"]}
    link(owner, t, p["Wife"], p["Husband"], "spouse")
    link(owner, t, p["HusbandFather"], p["Husband"], "biological_parent")
    link(owner, t, p["HusbandFather"], p["HusbandBrother"], "biological_parent")
    _hide(owner, t, p["Husband"])
    viewer = member_factory(["VIEWER"])
    g, _ = load_all(viewer, t, scope="connected", person_id=p["Wife"])
    assert names(g) == ["Wife"] and sum(n["hidden"] for n in g["nodes"]) == 1
    assert [ln["kind"] for ln in g["links"]] == ["union"] and g["edges"] == []
    assert g["total_people"] == 1
    # the in-laws are their own group in the whole tree; the hidden husband does not join the two
    everything, _ = load_all(viewer, t, scope="all")
    groups: dict[int, list[str]] = {}
    for n in everything["nodes"]:
        groups.setdefault(n["component"], []).append(
            n["person"]["display_name"].split()[0] if n["person"] else "?"
        )
    assert sorted(sorted(v) for v in groups.values()) == [
        ["?", "HusbandBrother", "HusbandFather"],
        ["?", "Wife"],
    ]
    for leak in (p["Husband"], "Husband Iyer"):
        assert leak not in str(everything)


def test_a_group_with_nobody_visible_is_not_shown_or_counted(owner, tree, member_factory):
    t = tree["id"]
    seen = create_person(owner, t, "Seen")["id"]
    a, b = create_person(owner, t, "SecretA")["id"], create_person(owner, t, "SecretB")["id"]
    link(owner, t, a, b, "spouse")
    _hide(owner, t, a)
    _hide(owner, t, b)
    viewer = member_factory(["VIEWER"])
    g, _ = load_all(viewer, t, scope="all")
    assert g["total_nodes"] == 1 == g["total_people"] and len(g["components"]) == 1
    assert names(g) == ["Seen"] and seen in str(g)
    r = viewer.get(f"/trees/{t}/family-graph", params={"scope": "connected", "person_id": a})
    assert r.status_code == 404  # a hidden person is never a root


def test_concealed_provisional_person_is_absent_and_not_a_bridge(owner, tree, member_factory):
    """ADR-0020 §6 still holds: a provisional person concealed from the viewer is not a placeholder."""
    from tests.test_provisional_people import _mama_via_unknown_mother

    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="deceased", sex="male")["id"]
    creator = member_factory(["CONTRIBUTOR"], name="Creator")
    prov, mama = _mama_via_unknown_mother(creator, t, me)
    mine, _ = load_all(creator, t, scope="connected", person_id=me)
    assert {n["id"] for n in mine["nodes"]} == {me, prov["id"], mama["id"]}
    viewer = member_factory(["VIEWER"])
    g, _ = load_all(viewer, t, scope="connected", person_id=me)
    assert [n["id"] for n in g["nodes"]] == [me] and prov["id"] not in str(g)
    everything, _ = load_all(viewer, t, scope="all")
    assert not any(n["hidden"] for n in everything["nodes"]) and prov["id"] not in str(everything)
    assert sorted(c["people"] for c in everything["components"]) == [1, 1]  # Mama is not joined to Aarav


def test_tree_isolation(owner, family, make_client):
    t, p = family
    stranger = make_client()
    stranger.register(name="Stranger")
    other = new_tree(stranger, "Other Family")
    assert stranger.get(f"/trees/{t}/family-graph", params={"scope": "all"}).status_code == 404
    # a person id from another tree is not a root here, and never appears in this tree's graph
    r = stranger.get(
        f"/trees/{other['id']}/family-graph", params={"scope": "connected", "person_id": p["Anita"]}
    )
    assert r.status_code == 404
    mine = create_person(stranger, other["id"], "Mine")["id"]
    g, _ = load_all(stranger, other["id"], scope="all")
    assert [n["person"]["id"] for n in g["nodes"]] == [mine]
    assert (
        owner.get(f"/trees/{t}/family-graph", params={"scope": "connected", "person_id": mine}).status_code
        == 404
    )


def test_unauthenticated_is_refused(client, family):
    t, _ = family
    assert client.get(f"/trees/{t}/family-graph", params={"scope": "all"}).status_code in (401, 404)


# ---------------------------------------------------------------- cursors
def test_cursor_is_refused_when_the_tree_changes_between_pages(owner, family):
    t, p = family
    first = page(owner, t, scope="connected", person_id=p["Anita"], limit=4)
    assert owner.delete(f"/trees/{t}/people/{p['Mama']}").status_code == 200
    r = owner.get(
        f"/trees/{t}/family-graph",
        params={"scope": "connected", "person_id": p["Anita"], "limit": 4, "cursor": first["next_cursor"]},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "graph_changed"
    # starting again never resurrects the removed person
    g, _ = load_all(owner, t, scope="connected", person_id=p["Anita"], limit=4)
    assert "Mama" not in names(g) and p["Mama"] not in str(g)


def test_forged_or_foreign_cursors_are_rejected_without_detail(owner, family):
    t, p = family
    first = page(owner, t, scope="connected", person_id=p["Anita"], limit=4)
    base = {"scope": "connected", "person_id": p["Anita"], "limit": 4}
    for bad in ("not-a-cursor", "e30=", "eyJvIjogLTF9"):
        r = owner.get(f"/trees/{t}/family-graph", params={**base, "cursor": bad})
        assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_cursor", bad
    # a cursor for one root or scope is not valid for another
    for other in ({**base, "person_id": p["Grandkid"]}, {"scope": "all", "limit": 4}):
        r = owner.get(f"/trees/{t}/family-graph", params={**other, "cursor": first["next_cursor"]})
        assert r.status_code == 422, other


def test_a_cursor_gives_another_member_only_what_they_may_see(owner, family, member_factory):
    t, p = family
    _hide(owner, t, p["Mama"])
    first = page(owner, t, scope="connected", person_id=p["Anita"], limit=2)
    viewer = member_factory(["VIEWER"])
    r = viewer.get(
        f"/trees/{t}/family-graph",
        params={"scope": "connected", "person_id": p["Anita"], "limit": 2, "cursor": first["next_cursor"]},
    )
    # the revision is bound to the viewer, so the owner's cursor is simply stale for anyone else
    assert r.status_code == 409
    g, _ = load_all(viewer, t, scope="connected", person_id=p["Anita"], limit=2)
    assert "Mama" not in names(g) and p["Mama"] not in str(g)


# ---------------------------------------------------------------- scale
def test_large_family_pages_to_completion_within_a_bounded_number_of_queries(owner, tree):
    """2,000 people over 11 generations, inserted directly; every page is counted for queries."""
    from sqlalchemy import event, text

    from app.core.db import get_engine

    t = uuid.UUID(tree["id"])
    rels = []
    levels: list[list[uuid.UUID]] = [[uuid.uuid4() for _ in range(2)]]
    while sum(len(lv) for lv in levels) < 2000:
        nxt = []
        for parent in levels[-1]:
            for _ in range(2):
                c = uuid.uuid4()
                nxt.append(c)
                rels.append((parent, c))
        levels.append(nxt)
    ids = [i for lv in levels for i in lv][:2000]
    keep = set(ids)
    rels = [(a, b) for a, b in rels if a in keep and b in keep]
    with owner_session() as s:
        s.execute(
            text(
                "INSERT INTO person (id, tree_id, preferred_display_name, profile_status, privacy_level)"
                " SELECT unnest(CAST(:ids AS uuid[])), :t, 'P', 'deceased', 'TREE_MEMBERS'"
            ),
            {"ids": [str(i) for i in ids], "t": t},
        )
        s.execute(
            text(
                "INSERT INTO relationship (id, tree_id, person_a_id, person_b_id, type, evidence_status)"
                " SELECT gen_random_uuid(), :t, a, b, 'biological_parent', 'USER_ASSERTION'"
                " FROM unnest(CAST(:a AS uuid[]), CAST(:b AS uuid[])) AS x(a, b)"
            ),
            {"t": t, "a": [str(a) for a, _ in rels], "b": [str(b) for _, b in rels]},
        )
        s.execute(
            text(
                "INSERT INTO relationship (id, tree_id, person_a_id, person_b_id, type, evidence_status)"
                " VALUES (gen_random_uuid(), :t, LEAST(CAST(:a AS uuid), CAST(:b AS uuid)),"
                " GREATEST(CAST(:a AS uuid), CAST(:b AS uuid)), 'spouse', 'USER_ASSERTION')"
            ),
            {"t": t, "a": str(levels[0][0]), "b": str(levels[0][1])},
        )
        s.commit()
    counts: list[int] = []
    n = 0

    def count(*_a, **_k):
        nonlocal n
        n += 1

    engine = get_engine()
    event.listen(engine, "before_cursor_execute", count)
    try:
        started = time.perf_counter()
        cur = page(owner, str(t), scope="connected", person_id=str(ids[-1]))
        seen = len(cur["nodes"])
        counts.append(n)
        while not cur["complete"]:
            n = 0
            cur = page(owner, str(t), scope="connected", person_id=str(ids[-1]), cursor=cur["next_cursor"])
            seen += len(cur["nodes"])
            counts.append(n)
        elapsed = time.perf_counter() - started
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert seen == 2000 == cur["total_nodes"] and len(counts) == 4
    # queries grow with the depth of the family (one frontier per hop), not with its size
    assert max(counts) < 150, counts
    assert elapsed < 30, elapsed


# ---------------------------------------------------------------- found by the independent review
def test_a_link_between_two_hidden_spouses_is_not_sent(owner, tree, member_factory):
    """Two visible siblings each have a hidden spouse, and those spouses are parent and child."""
    t = tree["id"]
    p = {n: create_person(owner, t, n)["id"] for n in ["Parent", "A", "B", "SpouseA", "SpouseB"]}
    link(owner, t, p["Parent"], p["A"], "biological_parent")
    link(owner, t, p["Parent"], p["B"], "biological_parent")
    link(owner, t, p["A"], p["SpouseA"], "spouse")
    link(owner, t, p["B"], p["SpouseB"], "spouse")
    link(owner, t, p["SpouseA"], p["SpouseB"], "biological_parent")
    _hide(owner, t, p["SpouseA"])
    _hide(owner, t, p["SpouseB"])
    g, _ = load_all(member_factory(["VIEWER"]), t, scope="connected", person_id=p["A"])
    assert sum(n["hidden"] for n in g["nodes"]) == 2
    assert not any(e["source"].startswith("hidden") and e["target"].startswith("hidden") for e in g["edges"])
    assert all(not (ln["a"].startswith("hidden") and ln["b"].startswith("hidden")) for ln in g["links"])


def test_hidden_line_of_descent_keeps_its_own_links(owner, tree, member_factory):
    """Two hidden generations in a row: the links the walk followed are still drawn."""
    t = tree["id"]
    chain = [create_person(owner, t, n)["id"] for n in ["Top", "HiddenOne", "HiddenTwo", "Bottom"]]
    for a, b in pairwise(chain):
        link(owner, t, a, b, "biological_parent")
    _hide(owner, t, chain[1])
    _hide(owner, t, chain[2])
    g, _ = load_all(member_factory(["VIEWER"]), t, scope="connected", person_id=chain[0])
    assert names(g) == ["Bottom", "Top"] and len(g["edges"]) == 3


def test_expired_grant_is_not_named_from_an_earlier_plan(owner, tree, member_factory):
    """The plan is reused across pages; a grant that ends in between changes no row of the tree.
    The person it made visible must not be named again, even as the far end of a link."""
    import datetime as dt

    from sqlalchemy import text

    t = tree["id"]
    x, child = create_person(owner, t, "Xavier")["id"], create_person(owner, t, "Child")["id"]
    link(owner, t, x, child, "biological_parent")
    _hide(owner, t, x)
    viewer = member_factory(["VIEWER"], name="Grantee")
    member = next(m for m in owner.get(f"/trees/{t}/members").json() if m["display_name"] == "Grantee")
    r = owner.post(
        f"/trees/{t}/grants",
        json={
            "user_id": member["user_id"],
            "resource_type": "person",
            "resource_id": x,
            "permission": "view",
        },
    )
    assert r.status_code == 201, r.text
    first = page(viewer, t, scope="connected", person_id=child, limit=1)
    assert x in str(page(viewer, t, scope="connected", person_id=child))  # visible while granted
    with owner_session() as s:  # the grant ends without any change to a person or relationship row
        s.execute(
            text("UPDATE access_grant SET expires_at = :e WHERE resource_id = :x"),
            {"e": dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1), "x": x},
        )
        s.commit()
    assert viewer.get(f"/trees/{t}/people/{x}").status_code == 404
    r = viewer.get(
        f"/trees/{t}/family-graph",
        params={"scope": "connected", "person_id": child, "limit": 1, "cursor": first["next_cursor"]},
    )
    assert x not in r.text
    assert r.status_code == 409 and r.json()["error"]["code"] == "graph_changed"
    g, _ = load_all(viewer, t, scope="connected", person_id=child, limit=1)
    assert x not in str(g) and sum(n["hidden"] for n in g["nodes"]) == 1


def test_cursor_with_a_non_integer_position_is_invalid(owner, family):
    import base64
    import json

    t, p = family
    for bad in (
        '{"o": 1e999, "r": "x", "s": "connected", "p": "' + p["Anita"] + '"}',
        json.dumps({"o": True, "r": "x", "s": "connected", "p": p["Anita"]}),
        json.dumps({"o": "2", "r": "x", "s": "connected", "p": p["Anita"]}),
    ):
        cur = base64.urlsafe_b64encode(bad.encode()).decode()
        r = owner.get(
            f"/trees/{t}/family-graph", params={"scope": "connected", "person_id": p["Anita"], "cursor": cur}
        )
        assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_cursor", bad
