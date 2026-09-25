from __future__ import annotations

from tests.helpers import create_person, exact, link, person_body


def test_core_flow_add_parents_spouse_child_and_view_tree(owner, tree):
    t = tree["id"]
    me = create_person(
        owner,
        t,
        "Krishnan",
        sex="male",
        status="living",
        birth={
            "date": exact(1950, 6, 12),
            "time": {"value": "05:30", "precision": "approximate", "source": "verbal"},
            "place_as_recorded": "Kanchipuram, Madras Presidency",
        },
    )
    assert me["birth"]["time_display"] == "05:30 (approximate)"
    # parents
    r = owner.post(
        f"/trees/{t}/people/{me['id']}/relatives",
        json={"relation": "parent", "new_person": person_body("Ramaswamy", sex="male")},
    )
    assert r.status_code == 201, r.text
    father = r.json()["person"]
    r = owner.post(
        f"/trees/{t}/people/{me['id']}/relatives",
        json={"relation": "parent", "new_person": person_body("Lakshmi", sex="female")},
    )
    mother = r.json()["person"]
    # spouse
    r = owner.post(
        f"/trees/{t}/people/{me['id']}/relatives",
        json={
            "relation": "spouse",
            "new_person": person_body("Meena", "Iyer", status="living", sex="female"),
        },
    )
    assert r.status_code == 201
    union = r.json()["relationships"][0]
    spouse = r.json()["person"]
    # child of this union → both parents linked
    r = owner.post(
        f"/trees/{t}/people/{me['id']}/relatives",
        json={
            "relation": "child",
            "union_id": union["id"],
            "new_person": person_body("Anand", status="living", sex="male"),
        },
    )
    assert r.status_code == 201
    assert len(r.json()["relationships"]) == 2
    child = r.json()["person"]

    fam = owner.get(f"/trees/{t}/people/{me['id']}/family").json()
    assert {p["person"]["id"] for p in fam["parents"]} == {father["id"], mother["id"]}
    assert fam["unions"][0]["partner"]["person"]["id"] == spouse["id"]
    assert [c["person"]["id"] for c in fam["unions"][0]["children"]] == [child["id"]]

    anc = owner.get(f"/trees/{t}/people/{child['id']}/ancestors?depth=3").json()
    ids = {n["id"] for n in anc["nodes"]}
    assert {father["id"], mother["id"], me["id"], spouse["id"], child["id"]} <= ids
    desc = owner.get(f"/trees/{t}/people/{father['id']}/descendants?depth=3").json()
    assert {me["id"], child["id"]} <= {n["id"] for n in desc["nodes"]}

    path = owner.get(f"/trees/{t}/relationship-path", params={"from": child["id"], "to": father["id"]}).json()
    assert path["label"] == "grandfather"
    path = owner.get(f"/trees/{t}/relationship-path", params={"from": me["id"], "to": spouse["id"]}).json()
    assert path["label"] == "wife"
    path = owner.get(
        f"/trees/{t}/relationship-path", params={"from": spouse["id"], "to": father["id"]}
    ).json()
    assert path["label"] == "father-in-law"


def test_approximate_time_cannot_be_marked_exact(owner, tree):
    r = owner.post(
        f"/trees/{tree['id']}/people",
        json=person_body(
            "Asha",
            birth={
                "date": exact(1990, 1, 1),
                "time": {"value": "05:00", "precision": "exact", "source": "verbal"},
            },
        ),
    )
    assert r.status_code == 422


def test_incomplete_dates_are_not_padded(owner, tree):
    p = create_person(owner, tree["id"], "Old", birth={"date": {"precision": "year_only", "year": 1880}})
    assert p["birth"]["date"] == {
        "calendar": "gregorian",
        "precision": "year_only",
        "year": 1880,
        "redacted": False,
    }
    r = owner.post(
        f"/trees/{tree['id']}/people",
        json=person_body("Bad", birth={"date": {"precision": "exact", "year": 1900}}),
    )
    assert r.status_code == 422
    c = create_person(owner, tree["id"], "Circa", birth={"date": {"precision": "circa", "year": 1900}})
    assert c["birth"]["date_display"] == "c. 1900"
    vs = create_person(
        owner,
        tree["id"],
        "Samvat",
        birth={
            "date": {
                "calendar": "vikram_samvat",
                "precision": "year_only",
                "year": 1990,
                "original_text": "संवत् १९९०",
            }
        },
    )
    assert "vikram_samvat" in vs["birth"]["date_display"]


def test_biological_and_adoptive_parents_coexist_with_lineage_views(owner, tree):
    t = tree["id"]
    child = create_person(owner, t, "Ravi", status="living")
    bio = create_person(owner, t, "BioDad", sex="male")
    adopt = create_person(owner, t, "AdoptDad", sex="male")
    link(owner, t, bio["id"], child["id"], "biological_parent")
    link(owner, t, adopt["id"], child["id"], "adoptive_parent", subtype="dattak")
    fam = owner.get(f"/trees/{t}/people/{child['id']}/family").json()
    assert {p["relationship_type"] for p in fam["parents"]} == {"biological_parent", "adoptive_parent"}
    bio_only = owner.get(f"/trees/{t}/people/{child['id']}/family?lineage=biological").json()
    assert [p["person"]["id"] for p in bio_only["parents"]] == [bio["id"]]
    legal = owner.get(f"/trees/{t}/people/{child['id']}/ancestors?lineage=legal").json()
    assert adopt["id"] in {n["id"] for n in legal["nodes"]} and bio["id"] not in {
        n["id"] for n in legal["nodes"]
    }
    path = owner.get(f"/trees/{t}/relationship-path", params={"from": child["id"], "to": adopt["id"]}).json()
    assert path["label"] == "adoptive-father"


def test_multiple_spouses_and_half_siblings(owner, tree):
    t = tree["id"]
    dad = create_person(owner, t, "Dad", sex="male")
    w1 = create_person(owner, t, "Wife1", sex="female")
    w2 = create_person(owner, t, "Wife2", sex="female")
    u1 = link(owner, t, dad["id"], w1["id"], "divorced_spouse")
    u2 = link(owner, t, dad["id"], w2["id"], "spouse")
    k1 = owner.post(
        f"/trees/{t}/people/{dad['id']}/relatives",
        json={"relation": "child", "union_id": u1["id"], "new_person": person_body("Kid1", sex="male")},
    ).json()["person"]
    k2 = owner.post(
        f"/trees/{t}/people/{dad['id']}/relatives",
        json={"relation": "child", "union_id": u2["id"], "new_person": person_body("Kid2", sex="female")},
    ).json()["person"]
    fam = owner.get(f"/trees/{t}/people/{dad['id']}/family").json()
    assert len(fam["unions"]) == 2
    kid_fam = owner.get(f"/trees/{t}/people/{k1['id']}/family").json()
    assert kid_fam["siblings"][0]["kind"] == "half"
    path = owner.get(f"/trees/{t}/relationship-path", params={"from": k1["id"], "to": k2["id"]}).json()
    assert path["label"] == "half-sister"


def test_cousins_and_uncles(owner, tree):
    t = tree["id"]
    gp = create_person(owner, t, "Grandpa", sex="male")
    a = create_person(owner, t, "A", sex="male")
    b = create_person(owner, t, "B", sex="male")
    for x in (a, b):
        link(owner, t, gp["id"], x["id"], "biological_parent")
    a1 = create_person(owner, t, "A1", sex="male")
    b1 = create_person(owner, t, "B1", sex="female")
    link(owner, t, a["id"], a1["id"], "biological_parent")
    link(owner, t, b["id"], b1["id"], "biological_parent")
    b2 = create_person(owner, t, "B2", sex="male")
    link(owner, t, b1["id"], b2["id"], "biological_parent")
    get = lambda x, y: owner.get(
        f"/trees/{t}/relationship-path", params={"from": x["id"], "to": y["id"]}
    ).json()
    assert get(a1, b1)["label"] == "first cousin"
    assert get(a1, b)["label"] == "uncle"
    assert get(a1, b)["chain"] == ["father", "brother"]
    assert get(a1, b2)["label"] == "first cousin once removed"
    assert get(b, a1)["label"] == "nephew"


def test_cycle_prevented(owner, tree):
    t = tree["id"]
    x = create_person(owner, t, "X")
    y = create_person(owner, t, "Y")
    z = create_person(owner, t, "Z")
    link(owner, t, x["id"], y["id"], "biological_parent")
    link(owner, t, y["id"], z["id"], "biological_parent")
    r = owner.post(
        f"/trees/{t}/relationships",
        json={"person_a_id": z["id"], "person_b_id": x["id"], "type": "biological_parent"},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "relationship_cycle"
    r = owner.post(
        f"/trees/{t}/relationships", json={"person_a_id": x["id"], "person_b_id": x["id"], "type": "spouse"}
    )
    assert r.status_code == 422


def test_duplicate_and_third_biological_parent_rejected(owner, tree):
    t = tree["id"]
    c = create_person(owner, t, "C")
    p1, p2, p3 = (create_person(owner, t, n) for n in ("P1", "P2", "P3"))
    link(owner, t, p1["id"], c["id"], "biological_parent")
    r = owner.post(
        f"/trees/{t}/relationships",
        json={"person_a_id": p1["id"], "person_b_id": c["id"], "type": "biological_parent"},
    )
    assert r.status_code == 409
    link(owner, t, p2["id"], c["id"], "biological_parent")
    r = owner.post(
        f"/trees/{t}/relationships",
        json={"person_a_id": p3["id"], "person_b_id": c["id"], "type": "biological_parent"},
    )
    assert r.status_code == 409
    # recorded as a disputed claim instead — preserved, not overwritten
    link(owner, t, p3["id"], c["id"], "biological_parent", evidence_status="DISPUTED")


def test_competing_birth_claims_are_preserved(owner, tree):
    t = tree["id"]
    p = create_person(owner, t, "Kavya", birth={"date": exact(1960, 3, 1)})
    r = owner.post(
        f"/trees/{t}/events",
        json={
            "type": "birth",
            "date": exact(1960, 3, 4),
            "participants": [{"person_id": p["id"]}],
            "evidence_status": "SOURCED",
        },
    )
    assert r.status_code == 201
    assert r.json()["is_preferred"] is False
    events = owner.get(f"/trees/{t}/people/{p['id']}/events?type=birth").json()
    assert len(events) == 2
    assert owner.get(f"/trees/{t}/people/{p['id']}").json()["birth"]["date"]["day"] == 1


def test_names_multilingual_and_search(owner, tree):
    t = tree["id"]
    r = owner.post(
        f"/trees/{t}/people",
        json={
            "profile_status": "deceased",
            "names": [
                {"full_name_as_recorded": "रामस्वामी अय्यर", "language": "hi", "type": "birth"},
                {
                    "given_name": "Ramaswamy",
                    "surname": "Iyer",
                    "type": "transliteration",
                    "is_preferred": True,
                },
            ],
        },
    )
    assert r.status_code == 201
    p = r.json()
    assert p["display_name"] == "Ramaswamy Iyer"
    scripts = {n["script"] for n in p["names"]}
    assert {"Deva", "Latn"} <= scripts
    found = owner.get(f"/trees/{t}/people", params={"q": "ramaswami"}).json()["items"]
    assert found and found[0]["id"] == p["id"]
    found_deva = owner.get(f"/trees/{t}/people", params={"q": "रामस्वामी"}).json()["items"]
    assert found_deva and found_deva[0]["id"] == p["id"]


def test_place_history_preserved_on_rename(owner, tree):
    t = tree["id"]
    r = owner.post(f"/trees/{t}/places", json={"canonical_name": "Madras", "place_type": "city"})
    pl = r.json()
    r = owner.patch(f"/trees/{t}/places/{pl['id']}", json={"canonical_name": "Chennai"})
    assert r.json()["canonical_name"] == "Chennai"
    assert any(h["name"] == "Madras" for h in r.json()["historical_names"])
    assert owner.get(f"/trees/{t}/places", params={"q": "madras"}).json()["items"][0]["id"] == pl["id"]


def test_migration_event(owner, tree):
    t = tree["id"]
    p = create_person(owner, t, "Traveller")
    origin = owner.post(f"/trees/{t}/places", json={"canonical_name": "Lahore", "place_type": "city"}).json()
    dest = owner.post(f"/trees/{t}/places", json={"canonical_name": "Delhi", "place_type": "city"}).json()
    r = owner.post(
        f"/trees/{t}/events",
        json={
            "type": "migration",
            "date": {"precision": "year_only", "year": 1947},
            "origin_place_id": origin["id"],
            "place_id": dest["id"],
            "reason": "Partition",
            "participants": [{"person_id": p["id"]}],
        },
    )
    assert r.status_code == 201
    assert r.json()["origin_place_name"] == "Lahore" and r.json()["place_name"] == "Delhi"


def test_soft_delete_and_restore(owner, tree):
    t = tree["id"]
    p = create_person(owner, t, "Temp")
    assert owner.delete(f"/trees/{t}/people/{p['id']}").status_code == 200
    assert owner.get(f"/trees/{t}/people/{p['id']}").status_code == 404
    assert owner.post(f"/trees/{t}/people/{p['id']}/restore").status_code == 200
    assert owner.get(f"/trees/{t}/people/{p['id']}").status_code == 200
