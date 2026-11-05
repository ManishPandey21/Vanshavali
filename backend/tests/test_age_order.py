"""Age-aware kinship (ADR-0020 §5): age order between the right pair, family-confirmed order over
birth dates, honest "unknown", privacy, and the "older or younger?" record endpoints."""

from __future__ import annotations

from typing import Any

from tests.conftest import new_tree
from tests.helpers import create_person, exact, link, person_body


def _path(client: Any, t: str, a: str, b: str) -> dict[str, Any]:
    r = client.get(f"/trees/{t}/relationship-path", params={"from": a, "to": b})
    assert r.status_code == 200, r.text
    return r.json()


def _age(path: dict[str, Any]) -> list[tuple[int, str, str, str]]:
    return [(a["chain_index"], a["person_id"], a["order"], a["basis"]) for a in path["age_orders"]]


def _year(y: int) -> dict[str, Any]:
    return {"precision": "year_only", "year": y}


def _family(
    client: Any, t: str, uncle_birth: dict[str, Any] | None, *, uncle_status: str = "deceased", **uncle: Any
) -> dict[str, dict[str, Any]]:
    """Dada → father (b. 12 Mar 1960) and an uncle; me = the father's son."""
    dada = create_person(client, t, "Dada", sex="male")
    father = create_person(client, t, "Ramesh", sex="male", birth={"date": exact(1960, 3, 12)})
    uncle_person = create_person(
        client,
        t,
        "Suresh",
        sex="male",
        status=uncle_status,
        birth={"date": uncle_birth} if uncle_birth else None,
        **uncle,
    )
    me = create_person(client, t, "Aarav", sex="male", status="living")
    for child in (father, uncle_person):
        link(client, t, dada["id"], child["id"], "biological_parent")
    link(client, t, father["id"], me["id"], "biological_parent")
    return {"dada": dada, "father": father, "uncle": uncle_person, "me": me}


def test_uncle_is_compared_with_the_father_not_the_viewer(owner, tree):
    t = tree["id"]
    f = _family(owner, t, exact(1955, 1, 2))
    path = _path(owner, t, f["me"]["id"], f["uncle"]["id"])
    assert path["chain"] == ["father", "brother"]
    a = path["age_orders"][0]
    # chain word 1 ("brother") joins the father and the uncle: the uncle is older → ताऊ
    assert (a["chain_index"], a["person_id"], a["relative_to_id"]) == (1, f["uncle"]["id"], f["father"]["id"])
    assert (a["order"], a["basis"]) == ("elder", "birth_dates")


def test_younger_by_dates_and_unknown_when_dates_overlap_or_are_missing(owner, tree):
    t = tree["id"]
    f = _family(owner, t, exact(1966, 8, 1))
    assert _age(_path(owner, t, f["me"]["id"], f["uncle"]["id"])) == [
        (1, f["uncle"]["id"], "younger", "birth_dates")
    ]

    g = _family(owner, t, {"precision": "circa", "year": 1961})  # c. 1961 overlaps 1960
    assert _age(_path(owner, t, g["me"]["id"], g["uncle"]["id"])) == [
        (1, g["uncle"]["id"], "unknown", "unknown")
    ]

    h = _family(owner, t, None)
    assert _age(_path(owner, t, h["me"]["id"], h["uncle"]["id"])) == [
        (1, h["uncle"]["id"], "unknown", "unknown")
    ]

    i = _family(owner, t, {"precision": "after", "year": 1950})  # open-ended: not enough
    assert _age(_path(owner, t, i["me"]["id"], i["uncle"]["id"]))[0][2] == "unknown"


def test_conflicting_birth_claims_never_force_an_answer(owner, tree):
    t = tree["id"]
    f = _family(owner, t, exact(1955, 1, 2))
    r = owner.post(
        f"/trees/{t}/events",
        json={"type": "birth", "date": exact(1968, 1, 1), "participants": [{"person_id": f["uncle"]["id"]}]},
    )
    assert r.status_code == 201
    assert _age(_path(owner, t, f["me"]["id"], f["uncle"]["id"]))[0][2:] == ("unknown", "unknown")


def test_family_confirmed_order_wins_and_disagreement_is_flagged(owner, tree):
    t = tree["id"]
    f = _family(owner, t, exact(1955, 1, 2))
    r = owner.post(
        f"/trees/{t}/relative-age-orders",
        json={"person_id": f["uncle"]["id"], "relative_to_id": f["father"]["id"], "order": "younger"},
    )
    assert r.status_code == 201, r.text
    a = _path(owner, t, f["me"]["id"], f["uncle"]["id"])["age_orders"][0]
    assert (a["order"], a["basis"], a["dates_disagree"]) == ("younger", "family_confirmed", True)
    assert a["record_id"] == r.json()["id"]
    # same order again is a no-op; the opposite order is refused
    again = owner.post(
        f"/trees/{t}/relative-age-orders",
        json={"person_id": f["father"]["id"], "relative_to_id": f["uncle"]["id"], "order": "elder"},
    )
    assert again.status_code == 200 and again.json()["id"] == r.json()["id"]
    clash = owner.post(
        f"/trees/{t}/relative-age-orders",
        json={"person_id": f["uncle"]["id"], "relative_to_id": f["father"]["id"], "order": "elder"},
    )
    assert clash.status_code == 409 and clash.json()["error"]["code"] == "age_order_conflict"
    # removing the record falls back to the birth dates
    assert owner.delete(f"/trees/{t}/relative-age-orders/{r.json()['id']}").status_code == 200
    a = _path(owner, t, f["me"]["id"], f["uncle"]["id"])["age_orders"][0]
    assert (a["order"], a["basis"]) == ("elder", "birth_dates")


def test_dates_are_compared_only_as_the_viewer_may_see_them(owner, tree, member_factory):
    t = tree["id"]
    # living father and uncle born in the same year: only the month orders them
    dada = create_person(owner, t, "Dada", sex="male")
    father = create_person(owner, t, "Ramesh", sex="male", status="living", birth={"date": exact(1960, 9, 1)})
    uncle = create_person(owner, t, "Suresh", sex="male", status="living", birth={"date": exact(1960, 2, 1)})
    me = create_person(owner, t, "Aarav", sex="male", status="living")
    for child in (father, uncle):
        link(owner, t, dada["id"], child["id"], "biological_parent")
    link(owner, t, father["id"], me["id"], "biological_parent")
    assert _age(_path(owner, t, me["id"], uncle["id"]))[0][2:] == ("elder", "birth_dates")
    # a viewer sees living people's birth year only, so the month must not leak through the term
    viewer = member_factory(["VIEWER"])
    assert _age(_path(viewer, t, me["id"], uncle["id"]))[0][2:] == ("unknown", "unknown")


def test_hidden_people_are_never_compared(owner, tree, member_factory):
    t = tree["id"]
    f = _family(owner, t, exact(1955, 1, 2), uncle_status="living", privacy_level="PRIVATE_TREE_ADMINS")
    cousin = create_person(owner, t, "Rohan", sex="male")
    link(owner, t, f["uncle"]["id"], cousin["id"], "biological_parent")
    contributor = member_factory(["CONTRIBUTOR"])
    path = _path(contributor, t, f["me"]["id"], cousin["id"])
    assert None in path["path"]  # the uncle is hidden
    assert path["age_orders"] == []
    r = contributor.post(
        f"/trees/{t}/relative-age-orders",
        json={"person_id": f["uncle"]["id"], "relative_to_id": f["father"]["id"], "order": "elder"},
    )
    assert r.status_code == 404


def test_jeth_and_devar_compare_with_the_husband(owner, tree):
    t = tree["id"]
    husband = create_person(owner, t, "Mahesh", sex="male")
    wife = create_person(owner, t, "Sunita", sex="female", status="living")
    bil = owner.post(
        f"/trees/{t}/people/{husband['id']}/relatives",
        json={"relation": "sibling", "new_person": person_body("Dinesh", sex="male")},
    ).json()["person"]
    owner.post(
        f"/trees/{t}/people/{wife['id']}/relatives",
        json={"relation": "spouse", "existing_person_id": husband["id"]},
    )
    owner.post(
        f"/trees/{t}/relative-age-orders",
        json={"person_id": bil["id"], "relative_to_id": husband["id"], "order": "elder"},
    )
    path = _path(owner, t, wife["id"], bil["id"])
    assert path["chain"] == ["husband", "brother"]
    a = path["age_orders"][0]
    assert (a["chain_index"], a["person_id"], a["relative_to_id"], a["order"]) == (
        1,
        bil["id"],
        husband["id"],
        "elder",
    )


def test_own_elder_sister_and_no_sibling_word_no_age(owner, tree):
    t = tree["id"]
    mother = create_person(owner, t, "Kamala", sex="female")
    me = create_person(owner, t, "Aarav", sex="male", status="living", birth={"date": _year(1990)})
    didi = create_person(owner, t, "Priya", sex="female", status="living", birth={"date": _year(1986)})
    for c in (me, didi):
        link(owner, t, mother["id"], c["id"], "biological_parent")
    assert _age(_path(owner, t, me["id"], didi["id"])) == [(0, didi["id"], "elder", "birth_dates")]
    assert _path(owner, t, me["id"], mother["id"])["age_orders"] == []  # "mother": nothing to compare


def test_record_endpoint_rules(owner, tree, member_factory):
    t = tree["id"]
    f = _family(owner, t, None)
    body = {"person_id": f["uncle"]["id"], "relative_to_id": f["father"]["id"], "order": "elder"}
    viewer = member_factory(["VIEWER"])
    assert viewer.post(f"/trees/{t}/relative-age-orders", json=body).status_code == 403
    # not siblings
    r = owner.post(f"/trees/{t}/relative-age-orders", json={**body, "relative_to_id": f["me"]["id"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "not_siblings"
    # self
    assert (
        owner.post(
            f"/trees/{t}/relative-age-orders", json={**body, "relative_to_id": f["uncle"]["id"]}
        ).status_code
        == 422
    )
    # another tree's people
    other = new_tree(owner, "Other family")
    stranger = create_person(owner, other["id"], "X")
    assert (
        owner.post(
            f"/trees/{t}/relative-age-orders", json={**body, "relative_to_id": stranger["id"]}
        ).status_code
        == 404
    )
    created = owner.post(f"/trees/{t}/relative-age-orders", json=body)
    assert created.status_code == 201
    rid = created.json()["id"]
    assert viewer.delete(f"/trees/{t}/relative-age-orders/{rid}").status_code == 403
    assert owner.delete(f"/trees/{other['id']}/relative-age-orders/{rid}").status_code == 404
    assert owner.delete(f"/trees/{t}/relative-age-orders/{rid}").status_code == 200
    assert owner.delete(f"/trees/{t}/relative-age-orders/{rid}").status_code == 404
