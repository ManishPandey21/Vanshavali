"""Visualization data APIs and chart presets (ADR-0017): shaping and privacy."""

from __future__ import annotations

from typing import Any

from tests.helpers import create_person, exact, link
from tests.test_life_events import add_place, life_event, upload_photo


def family(owner: Any, tid: str) -> dict[str, dict[str, Any]]:
    """Root Raju; father Mohan, mother Sita; Mohan's parents Hari and Gita (Gita's place private);
    Sita's father hidden (living, admins only)."""
    village = add_place(
        owner,
        tid,
        canonical_name="Bhadohi",
        place_type="village",
        latitude=25.39,
        longitude=82.57,
        district="Bhadohi",
        state="Uttar Pradesh",
    )
    people = {
        "raju": create_person(
            owner,
            tid,
            "Raju",
            status="living",
            sex="male",
            birth={"date": exact(1990, 5, 1), "place_id": village["id"]},
        ),
        "mohan": create_person(
            owner,
            tid,
            "Mohan",
            sex="male",
            birth={"date": exact(1955, 1, 2), "place_id": village["id"]},
            death={"date": exact(2015, 3, 4)},
        ),
        "sita": create_person(
            owner, tid, "Sita", sex="female", birth={"date": {"precision": "circa", "year": 1960}}
        ),
        "hari": create_person(
            owner, tid, "Hari", sex="male", birth={"date": {"precision": "year_only", "year": 1925}}
        ),
        "gita": create_person(owner, tid, "Gita", sex="female"),
        "secret": create_person(
            owner, tid, "Secretfather", status="living", sex="male", privacy_level="PRIVATE_TREE_ADMINS"
        ),
        "wife": create_person(owner, tid, "Meena", status="living", sex="female"),
    }
    link(owner, tid, people["mohan"]["id"], people["raju"]["id"], "biological_parent")
    link(owner, tid, people["sita"]["id"], people["raju"]["id"], "biological_parent")
    link(owner, tid, people["hari"]["id"], people["mohan"]["id"], "biological_parent")
    link(owner, tid, people["gita"]["id"], people["mohan"]["id"], "biological_parent")
    link(owner, tid, people["secret"]["id"], people["sita"]["id"], "biological_parent")
    link(owner, tid, people["raju"]["id"], people["wife"]["id"], "spouse")
    r = owner.post(
        f"/trees/{tid}/people/{people['mohan']['id']}/heritage",
        json={"attribute": "ancestral_village", "place_id": village["id"]},
    )
    assert r.status_code == 201, r.text
    people["village"] = village
    return people


def test_ancestry_slots_sides_gaps_and_completeness(owner, tree):
    tid = tree["id"]
    f = family(owner, tid)
    r = owner.get(f"/trees/{tid}/viz/ancestry?root={f['raju']['id']}&generations=3")
    assert r.status_code == 200, r.text
    a = r.json()
    by_slot = {n["slot"]: n for n in a["nodes"]}
    assert by_slot[1]["side"] == "self" and by_slot[1]["person"]["display_name"] == "Raju Iyer"
    assert by_slot[2]["person"]["display_name"] == "Mohan Iyer" and by_slot[2]["side"] == "paternal"
    assert by_slot[3]["person"]["display_name"] == "Sita Iyer" and by_slot[3]["side"] == "maternal"
    assert (
        by_slot[4]["person"]["display_name"] == "Hari Iyer"
        and by_slot[5]["person"]["display_name"] == "Gita Iyer"
    )
    assert by_slot[6]["hidden"] is False  # the owner sees everyone
    mohan = by_slot[2]["person"]
    assert mohan["village"] == "Bhadohi" and mohan["birth_place"]["name"] == "Bhadohi"
    assert mohan["birth_place"]["geo"]["latitude"] == 25.39
    assert mohan["completeness"]["missing"] == ["sources"]
    assert "parents" in by_slot[4]["person"]["completeness"]["missing"]
    # research gaps: Hari's and Gita's parents, Sita's mother
    assert set(a["missing_slots"]) >= {7, 8, 9, 10, 11}
    assert "3 generations" in a["summary"]


def test_ancestry_hides_private_people_and_redacts_living(owner, tree, member_factory):
    tid = tree["id"]
    f = family(owner, tid)
    viewer = member_factory(["VIEWER"])
    r = viewer.get(f"/trees/{tid}/viz/ancestry?root={f['raju']['id']}&generations=3")
    a = r.json()
    by_slot = {n["slot"]: n for n in a["nodes"]}
    assert by_slot[6]["hidden"] is True and by_slot[6]["person"] is None
    assert "Secretfather" not in r.text
    assert 12 not in a["missing_slots"]  # gaps behind a hidden person are not reported
    raju = by_slot[1]["person"]
    assert raju["birth_year"] == 1990 and raju["birth_display"] == "1990"  # living: year only
    assert raju["birth_place"] is None  # living: birthplace detail withheld
    # a hidden root is a 404, like everywhere else
    assert viewer.get(f"/trees/{tid}/viz/ancestry?root={f['secret']['id']}").status_code == 404


def test_neighbourhood_progressive_and_private(owner, tree, member_factory):
    tid = tree["id"]
    f = family(owner, tid)
    r = owner.get(f"/trees/{tid}/viz/neighbourhood?root={f['raju']['id']}&radius=1")
    g = r.json()
    names = {n["person"]["display_name"] for n in g["nodes"] if n["person"]}
    assert names == {"Raju Iyer", "Mohan Iyer", "Sita Iyer", "Meena Iyer"}
    kinds = {e["kind"] for e in g["edges"]}
    assert kinds == {"parent", "union"}
    expandable = {n["person"]["display_name"] for n in g["nodes"] if n["expandable"]}
    assert expandable == {"Mohan Iyer", "Sita Iyer"}
    # expanding Sita as a viewer: her father is a placeholder and is not expandable
    viewer = member_factory(["VIEWER"])
    r = viewer.get(f"/trees/{tid}/viz/neighbourhood?root={f['sita']['id']}&radius=2")
    assert "Secretfather" not in r.text
    hidden = [n for n in r.json()["nodes"] if n["hidden"]]
    assert len(hidden) == 1 and hidden[0]["expandable"] is False and hidden[0]["id"].startswith("hidden-")


def test_lifespans_and_branch_filter(owner, tree):
    tid = tree["id"]
    f = family(owner, tid)
    life_event(
        owner,
        tid,
        f["mohan"]["id"],
        category="migration",
        title="Moved to Delhi",
        date={"precision": "year_only", "year": 1980},
        significance="milestone",
    )
    r = owner.get(f"/trees/{tid}/viz/lifespans?root={f['raju']['id']}&generations=3&include_events=true")
    ls = r.json()
    rows = {row["person"]["display_name"]: row for row in ls["rows"]}
    assert list(rows)[:2] == ["Hari Iyer", "Mohan Iyer"]  # by birth year
    assert rows["Mohan Iyer"]["end_year"] == 2015 and rows["Mohan Iyer"]["generation"] == -1
    assert rows["Raju Iyer"]["end_year"] is None and rows["Raju Iyer"]["end_known"] is True
    assert rows["Sita Iyer"]["approximate"] is True
    assert [e["label"] for e in rows["Mohan Iyer"]["events"]] == ["Moved to Delhi"]
    assert ls["without_dates"] >= 1  # Gita has no birth year
    assert ls["min_year"] == 1925 and "lifespans" in ls["summary"]
    branch = owner.post(f"/trees/{tid}/branches", json={"name": "Bhadohi Iyers"}).json()
    owner.post(f"/trees/{tid}/branches/{branch['id']}/members", json={"person_ids": [f["hari"]["id"]]})
    r = owner.get(f"/trees/{tid}/viz/lifespans?branch_id={branch['id']}").json()
    assert [row["person"]["display_name"] for row in r["rows"]] == ["Hari Iyer"]


def test_story_with_photos_and_relatives(owner, tree, member_factory):
    tid = tree["id"]
    f = family(owner, tid)
    wedding = life_event(
        owner,
        tid,
        f["mohan"]["id"],
        category="marriage",
        title="Wedding at Bhadohi",
        date=exact(1985, 2, 10),
        place_id=f["village"]["id"],
        participants=[
            {"person_id": f["mohan"]["id"], "role": "principal"},
            {"person_id": f["sita"]["id"], "role": "spouse"},
        ],
    )
    upload_photo(owner, tid, wedding["id"], caption="Jaimala")
    s = owner.get(f"/trees/{tid}/viz/people/{f['mohan']['id']}/story").json()
    labels = [e["label"] for e in s["events"]]
    assert labels[0] == "Birth" and "Wedding at Bhadohi" in labels and labels[-1] == "Death"
    w = next(e for e in s["events"] if e["id"] == wedding["id"])
    assert w["place"]["geo"]["latitude"] == 25.39
    assert w["relatives"][0]["display_name"] == "Sita Iyer"
    assert w["photos"][0]["caption"] == "Jaimala" and w["photos"][0]["is_cover"] is True
    viewer = member_factory(["VIEWER"])
    assert viewer.get(f"/trees/{tid}/viz/people/{f['secret']['id']}/story").status_code == 404


def test_map_points_paths_and_coordinate_privacy(owner, tree, member_factory):
    tid = tree["id"]
    f = family(owner, tid)
    delhi = add_place(
        owner, tid, canonical_name="Delhi", place_type="city", latitude=28.6139, longitude=77.209
    )
    house = add_place(
        owner,
        tid,
        canonical_name="Haveli",
        place_type="ancestral_house",
        latitude=25.394321,
        longitude=82.571234,
        location_precision="exact",
        coordinate_privacy="PRIVATE_TREE_ADMINS",
    )
    life_event(
        owner,
        tid,
        f["mohan"]["id"],
        category="migration",
        title="To Delhi",
        date={"precision": "year_only", "year": 1980},
        origin_place_id=f["village"]["id"],
        place_id=delhi["id"],
    )
    life_event(
        owner,
        tid,
        f["hari"]["id"],
        category="property_acquisition",
        title="Built the haveli",
        place_id=house["id"],
    )
    life_event(
        owner,
        tid,
        f["hari"]["id"],
        category="award",
        title="Secret award",
        place_id=delhi["id"],
        privacy_level="PRIVATE_TREE_ADMINS",
    )
    m = owner.get(f"/trees/{tid}/viz/map").json()
    kinds = {p["kind"] for p in m["points"]}
    assert {"event", "heritage"} <= kinds
    assert [p["label"] for p in m["paths"]] == ["To Delhi"]
    assert (
        m["paths"][0]["origin"]["latitude"] == 25.39 and m["paths"][0]["destination"]["latitude"] == 28.6139
    )
    viewer = member_factory(["VIEWER"])
    vr = viewer.get(f"/trees/{tid}/viz/map")
    assert "Secret award" not in vr.text and "25.394321" not in vr.text
    haveli = next(p for p in vr.json()["points"] if p["label"].startswith("Built the haveli"))
    assert haveli["geo"]["coarsened"] is True and haveli["geo"]["latitude"] == 25.4
    # person filter
    mine = owner.get(f"/trees/{tid}/viz/map?person_id={f['mohan']['id']}&layer=events").json()
    assert {p["event_id"] for p in mine["points"]} <= {
        e["id"] for e in owner.get(f"/trees/{tid}/life-events?person_id={f['mohan']['id']}").json()["items"]
    }


def test_chart_presets_private_shared_and_validated(owner, tree, member_factory):
    tid = tree["id"]
    r = owner.post(
        f"/trees/{tid}/chart-presets",
        json={
            "name": "Paternal 6 gen",
            "chart_type": "fan",
            "settings": {"generations": 6, "colorBy": "birthplace"},
        },
    )
    assert r.status_code == 201, r.text
    mine = r.json()
    shared = owner.post(
        f"/trees/{tid}/chart-presets",
        json={"name": "Family map", "chart_type": "map", "settings": {}, "shared": True},
    ).json()
    other = member_factory(["CONTRIBUTOR"])
    seen = {p["name"]: p for p in other.get(f"/trees/{tid}/chart-presets").json()}
    assert set(seen) == {"Family map"} and seen["Family map"]["mine"] is False
    assert other.patch(f"/trees/{tid}/chart-presets/{shared['id']}", json={"name": "x"}).status_code == 403
    assert other.patch(f"/trees/{tid}/chart-presets/{mine['id']}", json={"name": "x"}).status_code == 404
    assert other.delete(f"/trees/{tid}/chart-presets/{mine['id']}").status_code == 404
    big = {"x": "a" * 9000}
    assert (
        owner.post(
            f"/trees/{tid}/chart-presets", json={"name": "big", "chart_type": "fan", "settings": big}
        ).status_code
        == 422
    )
    r = owner.patch(f"/trees/{tid}/chart-presets/{mine['id']}", json={"settings": {"generations": 4}})
    assert r.json()["settings"] == {"generations": 4}
    only_fan = owner.get(f"/trees/{tid}/chart-presets?chart_type=fan").json()
    assert [p["name"] for p in only_fan] == ["Paternal 6 gen"]
    assert owner.delete(f"/trees/{tid}/chart-presets/{mine['id']}").status_code == 200


def test_viz_endpoints_leak_nothing_hidden(owner, tree, member_factory):
    tid = tree["id"]
    f = family(owner, tid)
    viewer = member_factory(["VIEWER"])
    root = f["raju"]["id"]
    for url in (
        f"/trees/{tid}/viz/ancestry?root={root}&generations=4",
        f"/trees/{tid}/viz/neighbourhood?root={f['sita']['id']}&radius=3",
        f"/trees/{tid}/viz/lifespans",
        f"/trees/{tid}/viz/lifespans?root={root}",
        f"/trees/{tid}/viz/map",
        f"/trees/{tid}/viz/people/{root}/story",
    ):
        r = viewer.get(url)
        assert r.status_code == 200, (url, r.text)
        assert "Secretfather" not in r.text and str(f["secret"]["id"]) not in r.text, url
        assert "1990-05-01" not in r.text and '"month":5,"day":1' not in r.text.replace(" ", ""), url
