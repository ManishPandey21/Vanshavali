from __future__ import annotations

from tests.helpers import create_person, link, person_body


def test_gotra_is_never_inferred_from_surname(owner, tree):
    t = tree["id"]
    # Surname strongly associated with communities/gotras in popular belief — must not produce facts
    p = create_person(owner, t, "Ramesh", "Iyer", status="living")
    q = create_person(owner, t, "Suresh", "Bharadwaj", status="living")
    link(owner, t, p["id"], q["id"], "biological_parent")
    owner.post(f"/trees/{t}/people/{p['id']}/heritage", json={"attribute": "gotra", "value_text": "Kashyapa"})
    for person in (q,):
        prof = owner.get(f"/trees/{t}/people/{person['id']}/heritage").json()
        assert prof["attributes"] == []  # nothing copied from the parent, nothing derived from surname


def test_assertions_preferred_alternatives_and_dispute(owner, tree):
    t = tree["id"]
    p = create_person(owner, t, "Venkat")
    a1 = owner.post(
        f"/trees/{t}/people/{p['id']}/heritage",
        json={"attribute": "gotra", "value_text": "Kashyapa", "evidence_status": "FAMILY_RECOLLECTION"},
    )
    assert a1.status_code == 201 and a1.json()["is_preferred"] is True
    a2 = owner.post(
        f"/trees/{t}/people/{p['id']}/heritage",
        json={"attribute": "gotra", "value_text": "Bharadwaja", "evidence_status": "SOURCED"},
    )
    assert a2.json()["is_preferred"] is False
    prof = owner.get(f"/trees/{t}/people/{p['id']}/heritage").json()
    gotra = prof["attributes"][0]
    assert gotra["disputed"] is True
    assert gotra["preferred"]["value_text"] == "Kashyapa" and len(gotra["alternatives"]) == 1
    # switch preference; nothing is deleted
    owner.patch(f"/trees/{t}/assertions/{a2.json()['id']}", json={"is_preferred": True})
    prof = owner.get(f"/trees/{t}/people/{p['id']}/heritage").json()
    assert prof["attributes"][0]["preferred"]["value_text"] == "Bharadwaja"
    assert prof["attributes"][0]["alternatives"][0]["value_text"] == "Kashyapa"


def test_unknown_withheld_not_applicable_states(owner, tree):
    t = tree["id"]
    p = create_person(owner, t, "Anon")
    for status in ("unknown", "withheld", "not_applicable"):
        r = owner.post(
            f"/trees/{t}/people/{p['id']}/heritage", json={"attribute": "kuladevata", "value_status": status}
        )
        assert r.status_code == 201, r.text
    bad = owner.post(
        f"/trees/{t}/people/{p['id']}/heritage",
        json={"attribute": "kuladevata", "value_status": "withheld", "value_text": "x"},
    )
    assert bad.status_code == 422


def test_jati_is_private_by_default(owner, tree, member_factory):
    t = tree["id"]
    p = create_person(owner, t, "Private", status="living")
    owner.post(
        f"/trees/{t}/people/{p['id']}/heritage",
        json={"attribute": "jati_or_subgroup", "value_text": "Vadama"},
    )
    owner.post(f"/trees/{t}/people/{p['id']}/heritage", json={"attribute": "gotra", "value_text": "Atri"})
    viewer = member_factory(["VIEWER"])
    prof = viewer.get(f"/trees/{t}/people/{p['id']}/heritage")
    assert "Vadama" not in prof.text
    assert [a["attribute"] for a in prof.json()["attributes"]] == ["gotra"]


def test_researcher_proposals_are_not_preferred(owner, tree, member_factory):
    t = tree["id"]
    p = create_person(owner, t, "Researched", privacy_level="INVITED_RESEARCHER")
    researcher = member_factory(["RESEARCHER"])
    r = researcher.post(
        f"/trees/{t}/people/{p['id']}/heritage", json={"attribute": "gotra", "value_text": "Vasishtha"}
    )
    assert r.status_code == 201 and r.json()["is_preferred"] is False
    assert (
        researcher.patch(f"/trees/{t}/assertions/{r.json()['id']}", json={"is_preferred": True}).status_code
        == 403
    )


def test_ancestral_village_assertion_with_place(owner, tree):
    t = tree["id"]
    p = create_person(owner, t, "Villager")
    village = owner.post(
        f"/trees/{t}/places", json={"canonical_name": "Thiruvaiyaru", "place_type": "village"}
    ).json()
    r = owner.post(
        f"/trees/{t}/people/{p['id']}/heritage",
        json={"attribute": "ancestral_village", "place_id": village["id"]},
    )
    assert r.status_code == 201
    assert r.json()["place_name"] == "Thiruvaiyaru"


def test_branch_heritage_independent_of_person(owner, tree):
    t = tree["id"]
    b = owner.post(
        f"/trees/{t}/branches", json={"name": "Tharavad branch", "descent_rule": "matrilineal"}
    ).json()
    r = owner.post(
        f"/trees/{t}/branches/{b['id']}/heritage",
        json={"attribute": "tharavad_or_equivalent", "value_text": "Puthenveedu"},
    )
    assert r.status_code == 201
    assert (
        owner.get(f"/trees/{t}/branches/{b['id']}/heritage").json()["attributes"][0]["preferred"][
            "value_text"
        ]
        == "Puthenveedu"
    )


def test_branch_derivation_follows_descent_rule(owner, tree):
    t = tree["id"]
    founder = create_person(owner, t, "Founder", sex="male")
    son = create_person(owner, t, "Son", sex="male")
    daughter = create_person(owner, t, "Daughter", sex="female")
    sons_kid = create_person(owner, t, "SonsKid", sex="female")
    daughters_kid = create_person(owner, t, "DaughtersKid", sex="male")
    link(owner, t, founder["id"], son["id"], "biological_parent")
    link(owner, t, founder["id"], daughter["id"], "biological_parent")
    link(owner, t, son["id"], sons_kid["id"], "biological_parent")
    link(owner, t, daughter["id"], daughters_kid["id"], "biological_parent")
    patri = owner.post(
        f"/trees/{t}/branches",
        json={"name": "Patri", "founder_person_id": founder["id"], "descent_rule": "patrilineal"},
    ).json()
    owner.post(f"/trees/{t}/branches/{patri['id']}/derive-members")
    members = {m["person"]["id"] for m in owner.get(f"/trees/{t}/branches/{patri['id']}").json()["members"]}
    assert members == {founder["id"], son["id"], daughter["id"], sons_kid["id"]}
    matri = owner.post(
        f"/trees/{t}/branches",
        json={"name": "Matri", "founder_person_id": founder["id"], "descent_rule": "matrilineal"},
    ).json()
    owner.post(f"/trees/{t}/branches/{matri['id']}/derive-members")
    members = {m["person"]["id"] for m in owner.get(f"/trees/{t}/branches/{matri['id']}").json()["members"]}
    assert members == {founder["id"], son["id"], daughter["id"], daughters_kid["id"]}


def test_household_membership_over_time_independent_of_biology(owner, tree):
    t = tree["id"]
    a = create_person(owner, t, "Karta", sex="male")
    b = create_person(owner, t, "Cousin", sex="male")
    h1 = owner.post(
        f"/trees/{t}/households",
        json={
            "name": "Joint household",
            "house_name": "Gokulam",
            "start_date": {"precision": "year_only", "year": 1940},
        },
    ).json()
    h2 = owner.post(f"/trees/{t}/households", json={"name": "City flat"}).json()
    assert (
        owner.post(
            f"/trees/{t}/households/{h1['id']}/members", json={"person_id": a["id"], "role": "karta"}
        ).status_code
        == 201
    )
    m = owner.post(f"/trees/{t}/households/{h1['id']}/members", json={"person_id": b["id"]}).json()
    owner.post(
        f"/trees/{t}/households/{h1['id']}/members/{m['id']}/end",
        json={"end_date": {"precision": "year_only", "year": 1965}},
    )
    owner.post(f"/trees/{t}/households/{h2['id']}/members", json={"person_id": b["id"]})
    detail = owner.get(f"/trees/{t}/households/{h1['id']}").json()
    assert detail["members"][0]["role"] == "karta"
    assert [x["current"] for x in detail["members"]] == [True, False]
    assert len(owner.get(f"/trees/{t}/people/{b['id']}/households").json()) == 2


def test_sources_and_citations(owner, tree, member_factory):
    t = tree["id"]
    p = create_person(owner, t, "Cited", birth={"date": {"precision": "year_only", "year": 1901}})
    s = owner.post(
        f"/trees/{t}/sources",
        json={
            "title": "Haridwar Panda register",
            "source_type": "traditional_register",
            "tradition": {
                "tradition_type": "panda_register",
                "pilgrimage_place": "Haridwar",
                "volume": "12",
                "page": "44",
            },
        },
    )
    assert s.status_code == 201
    ev = p["birth"]["event_id"]
    c = owner.post(
        f"/trees/{t}/citations",
        json={
            "source_id": s.json()["id"],
            "target_type": "event",
            "target_id": ev,
            "page_or_image": "p. 44",
            "confidence": "medium",
        },
    )
    assert c.status_code == 201
    cites = owner.get(f"/trees/{t}/citations", params={"target_type": "event", "target_id": ev}).json()
    assert cites[0]["source_title"] == "Haridwar Panda register"
    assert owner.get(f"/trees/{t}/people/{p['id']}/events").json()[0]["citation_count"] == 1
    viewer = member_factory(["VIEWER"])
    assert viewer.post(f"/trees/{t}/sources", json={"title": "x"}).status_code == 403


def test_citation_cannot_target_other_tree(owner, tree, make_client):
    other = make_client()
    other.register()
    tb = other.post("/trees", json={"name": "B"}).json()["id"]
    foreign = create_person(other, tb, "Foreign")
    s = owner.post(f"/trees/{tree['id']}/sources", json={"title": "Mine"}).json()
    r = owner.post(
        f"/trees/{tree['id']}/citations",
        json={"source_id": s["id"], "target_type": "person", "target_id": foreign["id"]},
    )
    assert r.status_code == 404


def test_add_person_with_name_only_body(owner, tree):
    r = owner.post(f"/trees/{tree['id']}/people", json=person_body("Only"))
    assert r.status_code == 201
