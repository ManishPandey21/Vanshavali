"""Smart Add Relative (ADR-0020): plan without writes, confirmed commit, undo, privacy and authz."""

from __future__ import annotations

from typing import Any

from app.models import AuditEvent, Person, RelativeAgeOrder
from tests.conftest import new_tree, owner_session
from tests.helpers import create_person, link, person_body


def _plan(client: Any, t: str, anchor: str, term: str, choices: list[str] | None = None) -> Any:
    return client.post(
        f"/trees/{t}/people/{anchor}/smart-add/plan", json={"term": term, "choices": choices or []}
    )


def _commit(client: Any, t: str, anchor: str, term: str, new: dict[str, Any], **kw: Any) -> Any:
    return client.post(f"/trees/{t}/people/{anchor}/smart-add", json={"term": term, "new_person": new, **kw})


def _path(client: Any, t: str, a: str, b: str) -> dict[str, Any]:
    r = client.get(f"/trees/{t}/relationship-path", params={"from": a, "to": b})
    assert r.status_code == 200, r.text
    return r.json()


def _count_people() -> int:
    with owner_session() as db:
        return db.query(Person).count()


def test_terms_catalogue(owner, tree):
    r = owner.get(f"/trees/{tree['id']}/smart-add/terms")
    assert r.status_code == 200
    terms = {x["code"]: x for x in r.json()}
    assert terms["mama"]["hops"] == [
        {"relation": "parent", "sex": "female", "age": None},
        {"relation": "sibling", "sex": "male", "age": None},
    ]
    assert terms["tau"]["hops"][1]["age"] == "elder"
    assert terms["brother"]["asks_relative_age"] is True
    assert terms["tau"]["asks_relative_age"] is False


def test_plan_writes_nothing_and_offers_the_recorded_mother(owner, tree):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="living", sex="male")
    mother = owner.post(
        f"/trees/{t}/people/{me['id']}/relatives",
        json={"relation": "parent", "new_person": person_body("Sunita", sex="female")},
    ).json()["person"]
    before = _count_people()
    r = _plan(owner, t, me["id"], "mama")
    assert r.status_code == 200, r.text
    plan = r.json()
    assert plan["complete"] is False
    step = plan["steps"][0]
    assert [c["id"] for c in step["candidates"]] == [mother["id"]]
    assert step["allow_new"] is False  # a mother is recorded: never invite a duplicate
    r = _plan(owner, t, me["id"], "mama", [mother["id"]])
    plan = r.json()
    assert plan["complete"] is True
    assert [i["kind"] for i in plan["preview"]] == ["existing", "existing", "new"]
    assert plan["target"]["link"] == "explicit_sibling"
    assert _count_people() == before
    # "new" is refused where a matching parent is recorded
    assert _plan(owner, t, me["id"], "mama", ["new"]).status_code == 422


def test_mama_through_recorded_grandparents_is_a_real_sibling(owner, tree):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="living", sex="male")
    mother = owner.post(
        f"/trees/{t}/people/{me['id']}/relatives",
        json={"relation": "parent", "new_person": person_body("Sunita", sex="female")},
    ).json()["person"]
    nana = owner.post(
        f"/trees/{t}/people/{mother['id']}/relatives",
        json={"relation": "parent", "new_person": person_body("Gopal", sex="male")},
    ).json()["person"]
    union = owner.post(
        f"/trees/{t}/people/{nana['id']}/relatives",
        json={"relation": "spouse", "new_person": person_body("Kamala", sex="female")},
    ).json()
    nani = union["person"]
    link(owner, t, nani["id"], mother["id"], "biological_parent", union_id=union["relationships"][0]["id"])

    plan = _plan(owner, t, me["id"], "mama", [mother["id"]]).json()
    assert plan["target"]["link"] == "shared_parents"
    assert {p["id"] for p in plan["target"]["shared_parents"]} == {nana["id"], nani["id"]}

    r = _commit(owner, t, me["id"], "mama", person_body("Mohan", sex="male"), choices=[mother["id"]])
    assert r.status_code == 201, r.text
    mama = r.json()["person"]
    assert len(r.json()["relationships"]) == 2  # child of Nana and Nani, in their union
    fam = owner.get(f"/trees/{t}/people/{mother['id']}/family").json()
    assert {s["person"]["id"]: s["kind"] for s in fam["siblings"]} == {mama["id"]: "full"}
    path = _path(owner, t, me["id"], mama["id"])
    assert path["label"] == "uncle"
    assert path["chain"] == ["mother", "brother"]


def test_mama_with_unknown_mother_creates_a_provisional_parent(owner, tree):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="living", sex="male")
    plan = _plan(owner, t, me["id"], "mama").json()
    assert plan["steps"][0]["candidates"] == []
    assert plan["steps"][0]["allow_new"] is True
    plan = _plan(owner, t, me["id"], "mama", ["new"]).json()
    assert [i["kind"] for i in plan["preview"]] == ["existing", "provisional", "new"]

    r = _commit(
        owner,
        t,
        me["id"],
        "mama",
        person_body("Mohan", sex="male"),
        choices=["new"],
        provisional_sex_at_birth=["female"],
    )
    assert r.status_code == 201, r.text
    out = r.json()
    provisional = next(p for p in out["created_people"] if p["id"] != out["person"]["id"])
    assert provisional["is_provisional"] is True
    assert provisional["display_name"] == "Unnamed"
    assert provisional["sex_at_birth"] == "female"
    assert out["person"]["is_provisional"] is False
    # explicit sibling edge: the calculator still resolves मामा through the shared virtual parent
    path = _path(owner, t, me["id"], out["person"]["id"])
    assert path["label"] == "uncle"
    assert path["chain"] == ["mother", "brother"]
    assert path["path"] == [me["id"], provisional["id"], out["person"]["id"]]

    assert provisional["privacy_level"] == "CUSTOM"  # tree admins + the creator only
    assert provisional["provisional_state"] == "needs_details"

    # a name completes the details, but the origin stays recorded and nothing becomes verified
    r = owner.post(f"/trees/{t}/people/{provisional['id']}/names", json={"given_name": "Sunita"})
    assert r.status_code == 201, r.text
    p = owner.get(f"/trees/{t}/people/{provisional['id']}").json()
    assert p["is_provisional"] is True
    assert p["provisional_state"] == "unverified"
    assert p["display_name"].startswith("Sunita")


def test_sex_is_only_what_the_client_sends(owner, tree):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="living", sex="male")
    new = person_body("Mohan")  # no sex given
    r = _commit(owner, t, me["id"], "mama", new, choices=["new"])
    assert r.status_code == 201, r.text
    assert r.json()["person"]["sex_at_birth"] is None
    assert all(p["sex_at_birth"] is None for p in r.json()["created_people"])


def test_tau_records_age_order_and_contradiction_is_refused(owner, tree):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="living", sex="male")
    father = owner.post(
        f"/trees/{t}/people/{me['id']}/relatives",
        json={"relation": "parent", "new_person": person_body("Ramesh", sex="male")},
    ).json()["person"]
    r = _commit(owner, t, me["id"], "tau", person_body("Suresh", sex="male"), choices=[father["id"]])
    assert r.status_code == 201, r.text
    tau = r.json()["person"]
    with owner_session() as db:
        rows = db.query(RelativeAgeOrder).all()
        assert [(str(x.elder_person_id), str(x.younger_person_id)) for x in rows] == [
            (tau["id"], father["id"])
        ]
    assert _path(owner, t, me["id"], tau["id"])["label"] == "uncle"

    # "Chachi" (wife of the father's *younger* brother) through Suresh contradicts the family record
    plan = _plan(owner, t, me["id"], "chachi", [father["id"]]).json()
    assert tau["id"] in [c["id"] for c in plan["steps"][1]["candidates"]]
    r = _commit(
        owner, t, me["id"], "chachi", person_body("Geeta", sex="female"), choices=[father["id"], tau["id"]]
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "age_order_conflict"
    # nothing was written by the refused commit
    names = [p["display_name"] for p in owner.get(f"/trees/{t}/people").json()["items"]]
    assert "Suresh Iyer" in names and not any(n.startswith("Geeta") for n in names)

    # "Tai" through Suresh agrees and adds his wife
    r = _commit(
        owner, t, me["id"], "tai", person_body("Kamla", sex="female"), choices=[father["id"], tau["id"]]
    )
    assert r.status_code == 201, r.text
    assert _path(owner, t, me["id"], r.json()["person"]["id"])["chain"] == ["father", "brother", "wife"]


def test_brother_relative_age_is_optional_and_only_for_siblings(owner, tree):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="living", sex="male")
    r = _commit(owner, t, me["id"], "brother", person_body("Vikram", sex="male"), relative_age="elder")
    assert r.status_code == 201, r.text
    assert len(r.json()["relative_age_order_ids"]) == 1
    r = _commit(owner, t, me["id"], "son", person_body("Kabir", sex="male"), relative_age="younger")
    assert r.status_code == 422


def test_dada_blocked_when_two_biological_parents_recorded(owner, tree):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="living", sex="male")
    father = owner.post(
        f"/trees/{t}/people/{me['id']}/relatives",
        json={"relation": "parent", "new_person": person_body("Ramesh", sex="male")},
    ).json()["person"]
    for given, sex in (("Suresh", "male"), ("Kamala", "female")):
        owner.post(
            f"/trees/{t}/people/{father['id']}/relatives",
            json={"relation": "parent", "new_person": person_body(given, sex=sex)},
        )
    plan = _plan(owner, t, me["id"], "dada", [father["id"]]).json()
    assert plan["target"]["blocked"] == "two_biological_parents"
    r = _commit(owner, t, me["id"], "dada", person_body("Other", sex="male"), choices=[father["id"]])
    assert r.status_code == 409


def test_child_other_parent_must_be_a_partner(owner, tree):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="living", sex="male")
    wife = owner.post(
        f"/trees/{t}/people/{me['id']}/relatives",
        json={"relation": "spouse", "new_person": person_body("Meera", sex="female", status="living")},
    ).json()["person"]
    stranger = create_person(owner, t, "Stranger")
    plan = _plan(owner, t, me["id"], "son").json()
    assert [p["id"] for p in plan["target"]["other_parent_options"]] == [wife["id"]]
    r = _commit(owner, t, me["id"], "son", person_body("Kabir", sex="male"), other_parent_id=stranger["id"])
    assert r.status_code == 422
    r = _commit(owner, t, me["id"], "son", person_body("Kabir", sex="male"), other_parent_id=wife["id"])
    assert r.status_code == 201, r.text
    assert len(r.json()["relationships"]) == 2
    # bahu through the new son
    son = r.json()["person"]
    r = _commit(owner, t, me["id"], "bahu", person_body("Isha", sex="female"), choices=[son["id"]])
    assert r.status_code == 201, r.text
    assert _path(owner, t, me["id"], r.json()["person"]["id"])["label"] == "daughter-in-law"


def test_invalid_and_cross_tree_choices_are_refused(owner, tree):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="living", sex="male")
    unrelated = create_person(owner, t, "Unrelated", sex="female")
    other_tree = new_tree(owner, "Other family")
    foreign = create_person(owner, other_tree["id"], "Foreign", sex="female")
    assert _plan(owner, t, me["id"], "mama", [unrelated["id"]]).status_code == 422
    assert _plan(owner, t, me["id"], "mama", [foreign["id"]]).status_code == 422
    # anchor from another tree
    assert _plan(owner, t, foreign["id"], "mama").status_code == 404
    r = _commit(owner, t, foreign["id"], "mama", person_body("X"), choices=["new"])
    assert r.status_code == 404
    assert _plan(owner, t, me["id"], "no_such_term").status_code == 422
    assert _plan(owner, t, me["id"], "mama", ["new", "new"]).status_code == 422
    r = _commit(owner, t, me["id"], "mama", person_body("X"))  # incomplete
    assert r.status_code == 422


def test_viewer_cannot_plan_commit_or_undo(owner, tree, member_factory):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="living", sex="male")
    viewer = member_factory(["VIEWER"])
    assert _plan(viewer, t, me["id"], "mama").status_code == 403
    assert _commit(viewer, t, me["id"], "mama", person_body("X"), choices=["new"]).status_code == 403
    op = _commit(owner, t, me["id"], "brother", person_body("Vikram", sex="male")).json()["operation_id"]
    assert viewer.post(f"/trees/{t}/smart-add/{op}/undo").status_code == 403


def test_hidden_parent_is_counted_never_shown_and_blocks_a_duplicate(owner, tree, member_factory):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="deceased", sex="male")
    secret = create_person(
        owner, t, "Secret", sex="female", status="living", privacy_level="PRIVATE_TREE_ADMINS"
    )
    link(owner, t, secret["id"], me["id"], "biological_parent")
    contributor = member_factory(["CONTRIBUTOR"])
    plan = _plan(contributor, t, me["id"], "mama").json()
    step = plan["steps"][0]
    assert step["candidates"] == []
    assert step["hidden_candidates"] == 1
    assert step["allow_new"] is False
    assert secret["id"] not in str(plan)
    assert _plan(contributor, t, me["id"], "mama", ["new"]).status_code == 422


def test_undo_removes_exactly_what_was_added(owner, tree, member_factory):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="living", sex="male")
    r = _commit(
        owner,
        t,
        me["id"],
        "chacha",
        person_body("Mahesh", sex="male"),
        choices=["new"],
        provisional_sex_at_birth=["male"],
    )
    assert r.status_code == 201, r.text
    out = r.json()
    op = out["operation_id"]
    other = member_factory(["FAMILY_ADMIN"])
    assert other.post(f"/trees/{t}/smart-add/{op}/undo").status_code == 403
    r = owner.post(f"/trees/{t}/smart-add/{op}/undo")
    assert r.status_code == 200, r.text
    for p in out["created_people"]:
        assert owner.get(f"/trees/{t}/people/{p['id']}").status_code == 404
    with owner_session() as db:
        assert db.query(RelativeAgeOrder).count() == 0
        assert db.query(AuditEvent).filter(AuditEvent.action == "smart_add.undone").count() == 1
    assert owner.get(f"/trees/{t}/people/{me['id']}/family").json()["parents"] == []
    assert owner.post(f"/trees/{t}/smart-add/{op}/undo").status_code == 409
    # an operation id from nowhere
    assert owner.post(f"/trees/{t}/smart-add/{me['id']}/undo").status_code == 404


def test_undo_refused_once_the_new_person_is_connected_elsewhere(owner, tree):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="living", sex="male")
    out = _commit(owner, t, me["id"], "brother", person_body("Vikram", sex="male")).json()
    owner.post(
        f"/trees/{t}/people/{out['person']['id']}/relatives",
        json={"relation": "spouse", "new_person": person_body("Priya", sex="female")},
    )
    r = owner.post(f"/trees/{t}/smart-add/{out['operation_id']}/undo")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "changed_since"


def test_undo_is_tree_scoped(owner, tree):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="living", sex="male")
    op = _commit(owner, t, me["id"], "brother", person_body("Vikram", sex="male")).json()["operation_id"]
    other_tree = new_tree(owner, "Other family")
    assert owner.post(f"/trees/{other_tree['id']}/smart-add/{op}/undo").status_code == 404


def test_explicit_sibling_from_the_classic_dialog_resolves_uncle_and_cousin(owner, tree):
    t = tree["id"]
    me = create_person(owner, t, "Aarav", status="living", sex="male")
    father = owner.post(
        f"/trees/{t}/people/{me['id']}/relatives",
        json={"relation": "parent", "new_person": person_body("Ramesh", sex="male")},
    ).json()["person"]
    uncle = owner.post(
        f"/trees/{t}/people/{father['id']}/relatives",
        json={"relation": "sibling", "new_person": person_body("Mahesh", sex="male")},
    ).json()["person"]
    cousin = owner.post(
        f"/trees/{t}/people/{uncle['id']}/relatives",
        json={"relation": "child", "new_person": person_body("Rohan", sex="male")},
    ).json()["person"]
    path = _path(owner, t, me["id"], uncle["id"])
    assert (path["label"], path["chain"]) == ("uncle", ["father", "brother"])
    assert None not in path["path"] and len(path["path"]) == 3
    path = _path(owner, t, me["id"], cousin["id"])
    assert path["label"] == "first cousin"
    assert path["chain"] == ["father", "brother", "son"]
    assert path["common_ancestor_ids"] == []  # the shared parent is virtual, never returned
