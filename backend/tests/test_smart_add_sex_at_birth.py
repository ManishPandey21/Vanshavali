"""Smart Add and sex at birth (ADR-0020 §6, amended): a kinship term never fills in sex at birth,
and a recorded relative is never left out of the candidates because of their recorded sex."""

from __future__ import annotations

from tests.helpers import create_person, person_body


def test_candidates_are_not_dropped_for_their_recorded_sex(owner, tree):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="deceased", sex="male")
    # the recorded parent's sex at birth is male, but the family knows her as the mother
    parent = owner.post(
        f"/trees/{t}/people/{me['id']}/relatives",
        json={"relation": "parent", "new_person": person_body("Asha", sex="male")},
    ).json()["person"]
    plan = owner.post(
        f"/trees/{t}/people/{me['id']}/smart-add/plan", json={"term": "mama", "choices": []}
    ).json()
    step = plan["steps"][0]
    assert [c["id"] for c in step["candidates"]] == [parent["id"]]
    # nobody recorded could be "the mother" by sex at birth, so a new one may still be added…
    assert step["allow_new"] is True
    # …and the user may pick the recorded parent instead: the term is kept, identity untouched
    r = owner.post(
        f"/trees/{t}/people/{me['id']}/smart-add",
        json={"term": "mama", "new_person": person_body("Mohan"), "choices": [parent["id"]]},
    )
    assert r.status_code == 201, r.text
    assert owner.get(f"/trees/{t}/people/{parent['id']}").json()["sex_at_birth"] == "male"
    assert r.json()["person"]["sex_at_birth"] is None


def test_matching_candidates_are_listed_first(owner, tree):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="deceased", sex="male")
    father = owner.post(
        f"/trees/{t}/people/{me['id']}/relatives",
        json={"relation": "parent", "new_person": person_body("Ramesh", sex="male")},
    ).json()["person"]
    mother = owner.post(
        f"/trees/{t}/people/{me['id']}/relatives",
        json={"relation": "parent", "new_person": person_body("Sunita")},  # sex not recorded
    ).json()["person"]
    plan = owner.post(
        f"/trees/{t}/people/{me['id']}/smart-add/plan", json={"term": "mama", "choices": []}
    ).json()
    assert [c["id"] for c in plan["steps"][0]["candidates"]] == [mother["id"], father["id"]]
    assert plan["steps"][0]["allow_new"] is False  # Sunita could be the mother: no duplicate


def test_unknown_sex_gives_an_uncertain_term_not_a_guess(owner, tree):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="deceased", sex="male")
    r = owner.post(
        f"/trees/{t}/people/{me['id']}/smart-add",
        json={"term": "mama", "new_person": person_body("Mohan"), "choices": ["new"]},
    )
    out = r.json()
    assert all(p["sex_at_birth"] is None for p in out["created_people"])
    path = owner.get(
        f"/trees/{t}/relationship-path", params={"from": me["id"], "to": out["person"]["id"]}
    ).json()
    # neither person's sex is recorded: the engine says "parent's sibling", never mother/brother
    assert path["chain"] == ["parent", "sibling"]
    assert path["label"] != "uncle"
