"""Change proposals, family review, revision history and challenges (ADR-0021; threat T45)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.models import RecordRevision
from tests.conftest import ApiClient, new_tree, owner_session
from tests.helpers import create_person, exact, link


def set_policy(owner: ApiClient, tid: str, policy: str) -> None:
    r = owner.put(f"/trees/{tid}/review-policy", json={"review_policy": policy})
    assert r.status_code == 200, r.text


def person(client: ApiClient, tid: str, pid: str) -> dict[str, Any]:
    r = client.get(f"/trees/{tid}/people/{pid}")
    assert r.status_code == 200, r.text
    return r.json()


def propose(
    client: ApiClient, tid: str, items: list[dict[str, Any]], rationale: str = "Family records"
) -> Any:
    return client.post(f"/trees/{tid}/proposals", json={"rationale": rationale, "items": items})


def rel_type_change(rel_id: str, notes: str) -> dict[str, Any]:
    return {"target_type": "relationship", "op": "update", "target_id": rel_id, "patch": {"notes": notes}}


def family(owner: ApiClient, tid: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    father = create_person(owner, tid, "Ramesh", "Sharma", sex="male")
    son = create_person(owner, tid, "Suresh", "Sharma", sex="male")
    rel = link(owner, tid, father["id"], son["id"], "biological_parent")
    return father, son, rel


# ------------------------------------------------------------------ revisions and history
def test_every_write_increments_revisions_and_records_history(owner: ApiClient, tree: dict[str, Any]) -> None:
    tid = tree["id"]
    p = create_person(owner, tid, "Kamla", "Devi")
    name_id = person(owner, tid, p["id"])["names"][0]["id"]
    r = owner.patch(f"/trees/{tid}/people/{p['id']}/names/{name_id}", json={"given_name": "Kamala"})
    assert r.status_code == 200, r.text
    with owner_session() as db:
        revs = list(
            db.scalars(
                select(RecordRevision)
                .where(RecordRevision.record_id == name_id)
                .order_by(RecordRevision.revision)
            )
        )
    assert [(r.op.value, r.revision) for r in revs] == [("create", 1), ("update", 2)]
    assert revs[1].before == {"given_name": "Kamla"} and revs[1].after == {"given_name": "Kamala"}
    assert str(revs[1].actor_id) == owner.user["id"]  # type: ignore[index]
    # a name change also moves the person's revision (what proposals bind to)
    h = owner.get(f"/trees/{tid}/people/{p['id']}/history").json()["items"]
    name_entries = [e for e in h if e["record_type"] == "name" and e["op"] == "update"]
    assert name_entries[0]["changes"] == [
        {"field": "given_name", "before": "Kamla", "after": "Kamala", "hidden": False}
    ]
    assert name_entries[0]["actor"]["display_name"] == "Tree Owner" and name_entries[0]["revertible"] is True


def test_history_hides_fields_the_reader_may_not_see(
    owner: ApiClient, tree: dict[str, Any], member_factory: Any
) -> None:
    tid = tree["id"]
    p = create_person(owner, tid, "Asha", "Rao", status="living", birth={"date": exact(1990, 5, 6)})
    birth = {"id": person(owner, tid, p["id"])["birth"]["event_id"]}
    r = owner.patch(f"/trees/{tid}/events/{birth['id']}", json={"date": exact(1991, 5, 6)})
    assert r.status_code == 200, r.text
    viewer = member_factory(["VIEWER"])
    entries = viewer.get(f"/trees/{tid}/people/{p['id']}/history").json()["items"]
    date_changes = [c for e in entries for c in e["changes"] if c["field"] == "date"]
    assert date_changes and all(
        c["hidden"] and c["before"] is None and c["after"] is None for c in date_changes
    )
    admin_view = owner.get(f"/trees/{tid}/people/{p['id']}/history").json()["items"]
    assert any(
        c["after"] and c["after"]["year"] == 1991
        for e in admin_view
        for c in e["changes"]
        if c["field"] == "date"
    )


def test_erasure_removes_history_and_stales_open_proposals(
    owner: ApiClient, tree: dict[str, Any], member_factory: Any
) -> None:
    tid = tree["id"]
    set_policy(owner, tid, "all")
    p = create_person(owner, tid, "Vimla", "Joshi")
    name_id = person(owner, tid, p["id"])["names"][0]["id"]
    contributor = member_factory(["CONTRIBUTOR"])
    prop = propose(
        contributor,
        tid,
        [{"target_type": "name", "op": "update", "target_id": name_id, "patch": {"given_name": "Vimala"}}],
    )
    assert prop.status_code == 201, prop.text
    assert (
        owner.post(
            f"/trees/{tid}/people/{p['id']}/erase", json={"reason": "request", "confirm": True}
        ).status_code
        == 200
    )
    with owner_session() as db:
        left = db.scalars(select(RecordRevision).where(RecordRevision.person_id == p["id"])).all()
        assert left == []
        assert db.scalars(select(RecordRevision).where(RecordRevision.record_id == name_id)).all() == []
    out = contributor.get(f"/trees/{tid}/proposals/{prop.json()['id']}").json()
    assert out["status"] == "stale" and "erased" in out["stale_reason"]
    assert all(c["proposed"] is None for i in out["items"] for c in i["changes"])  # values dropped


# ------------------------------------------------------------------ policy
def test_policy_off_changes_nothing(owner: ApiClient, tree: dict[str, Any], member_factory: Any) -> None:
    tid = tree["id"]
    _, _, rel = family(owner, tid)
    contributor = member_factory(["CONTRIBUTOR"])
    assert (
        contributor.patch(f"/trees/{tid}/relationships/{rel['id']}", json={"notes": "x"}).status_code == 200
    )


def test_policy_routes_changes_but_not_additions(
    owner: ApiClient, tree: dict[str, Any], member_factory: Any
) -> None:
    tid = tree["id"]
    father, son, rel = family(owner, tid)
    set_policy(owner, tid, "structure")
    contributor = member_factory(["CONTRIBUTOR"])
    r = contributor.patch(f"/trees/{tid}/relationships/{rel['id']}", json={"notes": "x"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "review_required"
    # linking two existing people is a change
    other = create_person(owner, tid, "Mahesh", "Sharma", sex="male")
    r = contributor.post(
        f"/trees/{tid}/relationships",
        json={"person_a_id": father["id"], "person_b_id": other["id"], "type": "biological_parent"},
    )
    assert r.status_code == 409
    # adding a new relative stays direct
    r = contributor.post(
        f"/trees/{tid}/people/{son['id']}/relatives",
        json={
            "relation": "child",
            "new_person": {
                "names": [{"given_name": "Aarav", "surname": "Sharma", "is_preferred": True}],
                "profile_status": "living",
            },
        },
    )
    assert r.status_code == 201, r.text
    # "structure" does not cover names; "all" does
    name_id = person(owner, tid, father["id"])["names"][0]["id"]
    assert (
        contributor.patch(
            f"/trees/{tid}/people/{father['id']}/names/{name_id}", json={"given_name": "R."}
        ).status_code
        == 200
    )
    set_policy(owner, tid, "all")
    assert (
        contributor.patch(
            f"/trees/{tid}/people/{father['id']}/names/{name_id}", json={"given_name": "Ra"}
        ).status_code
        == 409
    )
    # the member's own unreviewed work stays editable
    mine = create_person(contributor, tid, "Gita", "Sharma")
    mine_name = person(contributor, tid, mine["id"])["names"][0]["id"]
    assert (
        contributor.patch(
            f"/trees/{tid}/people/{mine['id']}/names/{mine_name}", json={"given_name": "Geeta"}
        ).status_code
        == 200
    )
    # owners write directly
    assert owner.patch(f"/trees/{tid}/relationships/{rel['id']}", json={"notes": "owner"}).status_code == 200


def test_only_tree_managers_set_the_policy(
    owner: ApiClient, tree: dict[str, Any], member_factory: Any
) -> None:
    contributor = member_factory(["CONTRIBUTOR"])
    assert (
        contributor.put(f"/trees/{tree['id']}/review-policy", json={"review_policy": "off"}).status_code
        == 403
    )
    assert owner.get(f"/trees/{tree['id']}").json()["review_policy"] == "off"


# ------------------------------------------------------------------ proposals
def test_propose_review_and_apply(owner: ApiClient, tree: dict[str, Any], member_factory: Any) -> None:
    tid = tree["id"]
    _, son, rel = family(owner, tid)
    set_policy(owner, tid, "structure")
    contributor = member_factory(["CONTRIBUTOR"], name="Cousin Ravi")
    reviewer = member_factory(["REVIEWER"], name="Dadi")
    viewer = member_factory(["VIEWER"])
    assert propose(contributor, tid, [rel_type_change(rel["id"], "adopted")], rationale="").status_code == 422
    r = propose(contributor, tid, [rel_type_change(rel["id"], "adopted, per the 1962 deed")])
    assert r.status_code == 201, r.text
    prop = r.json()
    assert prop["status"] == "awaiting_review" and prop["can_decide"] is False
    assert prop["items"][0]["changes"] == [
        {"field": "notes", "current": None, "proposed": "adopted, per the 1962 deed", "hidden": False}
    ]
    # self-approval refused; a viewer cannot even see it; a reviewer is notified and sees it to review
    r = contributor.post(f"/trees/{tid}/proposals/{prop['id']}/approve", json={})
    assert r.status_code == 403 and r.json()["error"]["code"] == "self_approval"
    assert viewer.get(f"/trees/{tid}/proposals/{prop['id']}").status_code == 404
    assert [
        p["id"] for p in reviewer.get(f"/trees/{tid}/proposals", params={"view": "to_review"}).json()["items"]
    ] == [prop["id"]]
    notes = reviewer.get(f"/trees/{tid}/notifications").json()
    assert notes["unread"] == 1 and "Cousin Ravi proposed 1 change(s)" in notes["items"][0]["text"]
    # a reviewer cannot write directly
    assert reviewer.patch(f"/trees/{tid}/relationships/{rel['id']}", json={"notes": "x"}).status_code == 403
    r = reviewer.post(f"/trees/{tid}/proposals/{prop['id']}/approve", json={"note": "Matches the deed"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "accepted" and r.json()["decided_by"]["display_name"] == "Dadi"
    after = owner.get(f"/trees/{tid}/people/{son['id']}/history").json()["items"][0]
    assert after["proposal_id"] == prop["id"] and after["reviewer"]["display_name"] == "Dadi"
    assert after["actor"]["display_name"] == "Cousin Ravi"  # applied as the proposer
    with owner_session() as db:
        from app.models import Relationship

        stored = db.get(Relationship, rel["id"])
        assert stored is not None and stored.notes == "adopted, per the 1962 deed"
        assert stored.review_state.value == "family_reviewed"
    assert contributor.get(f"/trees/{tid}/notifications").json()["items"][0]["kind"] == "proposal_accepted"


def test_a_stale_proposal_is_never_applied_and_can_be_rebased(
    owner: ApiClient, tree: dict[str, Any], member_factory: Any
) -> None:
    tid = tree["id"]
    _, _, rel = family(owner, tid)
    set_policy(owner, tid, "structure")
    contributor = member_factory(["CONTRIBUTOR"])
    prop = propose(contributor, tid, [rel_type_change(rel["id"], "proposed note")]).json()
    # the record changes after the proposal was made
    assert (
        owner.patch(f"/trees/{tid}/relationships/{rel['id']}", json={"notes": "owner's note"}).status_code
        == 200
    )
    seen = owner.get(f"/trees/{tid}/proposals/{prop['id']}").json()
    assert seen["items"][0]["outdated"] is True
    assert seen["items"][0]["changes"][0]["current"] == "owner's note"  # diff against today's record
    r = owner.post(f"/trees/{tid}/proposals/{prop['id']}/approve", json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "proposal_stale"
    assert owner.get(f"/trees/{tid}/proposals/{prop['id']}").json()["status"] == "stale"  # committed
    with owner_session() as db:
        from app.models import Relationship

        assert db.get(Relationship, rel["id"]).notes == "owner's note"  # type: ignore[union-attr]
    assert contributor.get(f"/trees/{tid}/notifications").json()["items"][0]["kind"] == "proposal_stale"
    # rebase: a fresh proposal, needing a fresh review
    assert owner.post(f"/trees/{tid}/proposals/{prop['id']}/rebase").status_code == 403
    new = contributor.post(f"/trees/{tid}/proposals/{prop['id']}/rebase")
    assert new.status_code == 201, new.text
    assert new.json()["supersedes_id"] == prop["id"] and new.json()["status"] == "awaiting_review"
    assert owner.post(f"/trees/{tid}/proposals/{new.json()['id']}/approve", json={}).status_code == 200


def test_apply_is_all_or_nothing(owner: ApiClient, tree: dict[str, Any], member_factory: Any) -> None:
    tid = tree["id"]
    father, son, rel = family(owner, tid)
    set_policy(owner, tid, "structure")
    contributor = member_factory(["CONTRIBUTOR"])
    # the second item would make the son his father's parent: a cycle the service refuses
    prop = propose(
        contributor,
        tid,
        [
            rel_type_change(rel["id"], "first item"),
            {
                "target_type": "relationship",
                "op": "create",
                "patch": {"person_a_id": son["id"], "person_b_id": father["id"], "type": "biological_parent"},
            },
        ],
    ).json()
    r = owner.post(f"/trees/{tid}/proposals/{prop['id']}/approve", json={})
    assert r.status_code in (409, 422), r.text
    with owner_session() as db:
        from app.models import Relationship

        assert db.get(Relationship, rel["id"]).notes is None  # type: ignore[union-attr]
    assert owner.get(f"/trees/{tid}/proposals/{prop['id']}").json()["status"] == "awaiting_review"


def test_branch_admins_review_only_inside_their_branch(
    owner: ApiClient, tree: dict[str, Any], member_factory: Any
) -> None:
    tid = tree["id"]
    father, son, rel = family(owner, tid)
    outsider = create_person(owner, tid, "Other", "Verma")
    branch = owner.post(f"/trees/{tid}/branches", json={"name": "Sharma"}).json()
    assert (
        owner.post(
            f"/trees/{tid}/branches/{branch['id']}/members", json={"person_ids": [father["id"], son["id"]]}
        ).status_code
        == 200
    )
    set_policy(owner, tid, "all")
    branch_admin = member_factory(["BRANCH_ADMIN"], branch_id=branch["id"])
    contributor = member_factory(["CONTRIBUTOR"])
    inside = propose(contributor, tid, [rel_type_change(rel["id"], "inside")]).json()
    out_name = person(owner, tid, outsider["id"])["names"][0]["id"]
    outside = propose(
        contributor,
        tid,
        [{"target_type": "name", "op": "update", "target_id": out_name, "patch": {"given_name": "O."}}],
    ).json()
    assert branch_admin.post(f"/trees/{tid}/proposals/{inside['id']}/approve", json={}).status_code == 200
    assert branch_admin.post(f"/trees/{tid}/proposals/{outside['id']}/approve", json={}).status_code in (
        403,
        404,
    )


def test_a_reviewer_who_cannot_see_a_field_cannot_decide(
    owner: ApiClient, tree: dict[str, Any], member_factory: Any
) -> None:
    tid = tree["id"]
    p = create_person(owner, tid, "Neha", "Gupta", status="living", birth={"date": exact(2001, 2, 3)})
    birth = {"id": person(owner, tid, p["id"])["birth"]["event_id"]}
    set_policy(owner, tid, "all")
    contributor = member_factory(["CONTRIBUTOR"])
    prop = propose(
        contributor,
        tid,
        [
            {
                "target_type": "event",
                "op": "update",
                "target_id": birth["id"],
                "patch": {"date": exact(2001, 2, 4)},
            }
        ],
    )
    # a contributor may propose it (they may write this person); the reviewer must see it to decide
    assert prop.status_code == 201, prop.text
    reviewer = member_factory(["REVIEWER"])
    seen = reviewer.get(f"/trees/{tid}/proposals/{prop.json()['id']}").json()
    assert seen["can_decide"] is False and "hidden" in (seen["cannot_decide_reason"] or "")
    assert all(c["hidden"] and c["proposed"] is None for i in seen["items"] for c in i["changes"])
    assert reviewer.post(f"/trees/{tid}/proposals/{prop.json()['id']}/approve", json={}).status_code == 403
    assert owner.post(f"/trees/{tid}/proposals/{prop.json()['id']}/approve", json={}).status_code == 200


def test_proposals_stay_in_their_tree(
    owner: ApiClient, tree: dict[str, Any], make_client: Any, member_factory: Any
) -> None:
    tid = tree["id"]
    _, _, rel = family(owner, tid)
    set_policy(owner, tid, "structure")
    contributor = member_factory(["CONTRIBUTOR"])
    prop = propose(contributor, tid, [rel_type_change(rel["id"], "x")]).json()
    stranger = make_client()
    stranger.register()
    other = new_tree(stranger, "Other family")
    assert stranger.get(f"/trees/{other['id']}/proposals/{prop['id']}").status_code == 404
    assert stranger.post(f"/trees/{other['id']}/proposals/{prop['id']}/approve", json={}).status_code == 404
    # nor can a proposal in another tree point at this tree's records
    assert propose(stranger, other["id"], [rel_type_change(rel["id"], "x")]).status_code == 404


def test_proposals_are_rate_limited(owner: ApiClient, tree: dict[str, Any], member_factory: Any) -> None:
    tid = tree["id"]
    _, _, rel = family(owner, tid)
    contributor = member_factory(["CONTRIBUTOR"])
    codes = [propose(contributor, tid, [rel_type_change(rel["id"], f"n{i}")]).status_code for i in range(22)]
    assert codes[:20] == [201] * 20 and 429 in codes[20:]


# ------------------------------------------------------------------ challenges and review state
def test_a_challenge_marks_nothing_until_upheld(
    owner: ApiClient, tree: dict[str, Any], member_factory: Any
) -> None:
    tid = tree["id"]
    _, son, rel = family(owner, tid)
    viewer = member_factory(["VIEWER"], name="Nana")
    r = viewer.post(
        f"/trees/{tid}/challenges",
        json={"target_type": "relationship", "target_id": rel["id"], "rationale": "He was adopted"},
    )
    assert r.status_code == 201, r.text
    ch = r.json()
    with owner_session() as db:
        from app.models import Relationship

        assert db.get(Relationship, rel["id"]).review_state.value == "unreviewed"  # type: ignore[union-attr]
    assert owner.get(f"/trees/{tid}/notifications").json()["items"][0]["kind"] in (
        "challenge_opened",
        "proposal_to_review",
    )
    assert viewer.post(f"/trees/{tid}/proposals/{ch['id']}/uphold", json={}).status_code == 403
    r = owner.post(
        f"/trees/{tid}/proposals/{ch['id']}/uphold", json={"note": "Deed found", "mark_disputed": True}
    )
    assert r.status_code == 200, r.text
    with owner_session() as db:
        from app.models import Relationship

        stored = db.get(Relationship, rel["id"])
        assert stored is not None and stored.review_state.value == "contested"
        assert stored.evidence_status.value == "DISPUTED"
    assert viewer.get(f"/trees/{tid}/notifications").json()["items"][0]["kind"] == "challenge_upheld"


def test_open_challenges_are_capped_per_member(
    owner: ApiClient, tree: dict[str, Any], member_factory: Any
) -> None:
    from app.core.ratelimit import get_limiter

    tid = tree["id"]
    _, _, rel = family(owner, tid)
    viewer = member_factory(["VIEWER"])
    for i in range(20):
        if i == 15:
            get_limiter().reset()  # the per-minute limit is tested separately
        assert (
            viewer.post(
                f"/trees/{tid}/challenges",
                json={"target_type": "relationship", "target_id": rel["id"], "rationale": f"reason {i}"},
            ).status_code
            == 201
        )
    get_limiter().reset()
    r = viewer.post(
        f"/trees/{tid}/challenges",
        json={"target_type": "relationship", "target_id": rel["id"], "rationale": "one more"},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "too_many_challenges"


def test_only_reviewers_confirm_facts_and_a_change_resets_them(
    owner: ApiClient, tree: dict[str, Any], member_factory: Any
) -> None:
    tid = tree["id"]
    _, _, rel = family(owner, tid)
    contributor = member_factory(["CONTRIBUTOR"])
    body = {"target_type": "relationship", "target_id": rel["id"], "state": "family_reviewed"}
    assert contributor.post(f"/trees/{tid}/review-state", json=body).status_code == 403
    r = owner.post(f"/trees/{tid}/review-state", json=body)
    assert r.status_code == 200 and r.json()["review_state"] == "family_reviewed"
    assert (
        owner.patch(f"/trees/{tid}/relationships/{rel['id']}", json={"notes": "changed"}).status_code == 200
    )
    with owner_session() as db:
        from app.models import Relationship

        assert db.get(Relationship, rel["id"]).review_state.value == "unreviewed"  # type: ignore[union-attr]


# ------------------------------------------------------------------ revert
def test_revert_applies_directly_or_proposes(
    owner: ApiClient, tree: dict[str, Any], member_factory: Any
) -> None:
    tid = tree["id"]
    _, son, rel = family(owner, tid)
    assert owner.patch(f"/trees/{tid}/relationships/{rel['id']}", json={"notes": "wrong"}).status_code == 200
    rev = owner.get(f"/trees/{tid}/people/{son['id']}/history").json()["items"][0]
    r = owner.post(f"/trees/{tid}/revisions/{rev['id']}/revert")
    assert r.status_code == 200 and r.json() == {"outcome": "applied", "proposal_id": None}
    with owner_session() as db:
        from app.models import Relationship

        assert db.get(Relationship, rel["id"]).notes is None  # type: ignore[union-attr]
    assert owner.patch(f"/trees/{tid}/relationships/{rel['id']}", json={"notes": "again"}).status_code == 200
    set_policy(owner, tid, "structure")
    contributor = member_factory(["CONTRIBUTOR"])
    rev = owner.get(f"/trees/{tid}/people/{son['id']}/history").json()["items"][0]
    r = contributor.post(f"/trees/{tid}/revisions/{rev['id']}/revert")
    assert r.status_code == 200 and r.json()["outcome"] == "proposed"
    viewer = member_factory(["VIEWER"])
    assert viewer.post(f"/trees/{tid}/revisions/{rev['id']}/revert").status_code == 403


def test_writes_outside_the_person_endpoints_are_recorded_too(owner: ApiClient, tree: dict[str, Any]) -> None:
    """The flush hook covers every path: here a merge moves a heritage claim to the survivor."""
    tid = tree["id"]
    a = create_person(owner, tid, "Ram", "Iyer")
    b = create_person(owner, tid, "Rama", "Iyer")
    claim = owner.post(
        f"/trees/{tid}/people/{b['id']}/heritage", json={"attribute": "gotra", "value_text": "Atri"}
    ).json()
    r = owner.post(
        f"/trees/{tid}/merges", json={"survivor_id": a["id"], "merged_id": b["id"], "reason": "same person"}
    )
    assert r.status_code == 201, r.text
    with owner_session() as db:
        moved = db.scalars(
            select(RecordRevision).where(
                RecordRevision.record_id == claim["id"], RecordRevision.op == "update"
            )
        ).all()
    assert any(m.before.get("person_id") == b["id"] and m.after.get("person_id") == a["id"] for m in moved)
