"""Living-person protection, role enforcement and tree isolation (PRS §6, §30, §32, §58)."""

from __future__ import annotations

import json

from tests.conftest import join_tree
from tests.helpers import create_person, exact, link, person_body

SECRET_DOB = {"precision": "exact", "year": 1985, "month": 7, "day": 23}
SECRET_TIME = {"value": "04:17", "precision": "exact", "source": "birth_certificate"}


def _living(owner, t, **kw):
    return create_person(
        owner,
        t,
        "Priya",
        status="living",
        sex="female",
        birth={"date": SECRET_DOB, "time": SECRET_TIME, "place_as_recorded": "Ward 7, Apollo Hospital"},
        contact_info="+91 98xxxxxx",
        residential_address="12 Secret Street",
        **kw,
    )


def test_viewer_sees_only_year_of_living_birth_and_no_time(owner, tree, member_factory):
    t = tree["id"]
    p = _living(owner, t)
    assert p["birth"]["date"]["day"] == 23  # owner sees everything
    viewer = member_factory(["VIEWER"])
    r = viewer.get(f"/trees/{t}/people/{p['id']}")
    assert r.status_code == 200
    body = r.json()
    assert body["birth"]["date"] == {
        "calendar": "gregorian",
        "precision": "year_only",
        "year": 1985,
        "redacted": True,
    }
    assert body["birth"]["time"] is None and body["birth"]["time_display"] is None
    assert body["contact_info"] is None and body["residential_address"] is None
    assert {"birth_date_full", "birth_time", "contact", "address"} <= set(body["redacted_fields"])
    raw = r.text
    for secret in ("04:17", "Secret Street", "98xxxxxx", "Apollo", '"day":23'):
        assert secret not in raw
    ev = viewer.get(f"/trees/{t}/people/{p['id']}/events").text
    assert "04:17" not in ev and '"day":23' not in ev


def test_field_override_can_share_full_dob(owner, tree, member_factory):
    t = tree["id"]
    p = _living(owner, t)
    viewer = member_factory(["VIEWER"])
    r = owner.put(
        f"/trees/{t}/people/{p['id']}/privacy", json={"field_privacy": {"birth_date_full": "TREE_MEMBERS"}}
    )
    assert r.status_code == 200
    assert viewer.get(f"/trees/{t}/people/{p['id']}").json()["birth"]["date"]["day"] == 23
    # time is still protected
    assert viewer.get(f"/trees/{t}/people/{p['id']}").json()["birth"]["time"] is None


def test_admin_only_person_is_invisible_to_viewer_everywhere(owner, tree, member_factory):
    t = tree["id"]
    parent = create_person(owner, t, "Visible", status="deceased")
    secret = create_person(owner, t, "Hidden", status="living", privacy_level="PRIVATE_TREE_ADMINS")
    link(owner, t, parent["id"], secret["id"], "biological_parent")
    viewer = member_factory(["VIEWER"])
    assert viewer.get(f"/trees/{t}/people/{secret['id']}").status_code == 404
    listing = viewer.get(f"/trees/{t}/people").json()["items"]
    assert secret["id"] not in {p["id"] for p in listing}
    assert viewer.get(f"/trees/{t}/people", params={"q": "Hidden"}).json()["items"] == []
    fam = viewer.get(f"/trees/{t}/people/{parent['id']}/family").json()
    kids = fam["other_children"]
    assert kids and kids[0]["hidden"] is True and kids[0]["person"] is None
    assert "Hidden" not in json.dumps(fam)
    desc = viewer.get(f"/trees/{t}/people/{parent['id']}/descendants").json()
    assert secret["id"] not in json.dumps(desc)


def test_researcher_sees_only_researcher_level(owner, tree, member_factory):
    t = tree["id"]
    normal = create_person(owner, t, "Members")
    shared = create_person(owner, t, "Shared", privacy_level="INVITED_RESEARCHER")
    researcher = member_factory(["RESEARCHER"])
    assert researcher.get(f"/trees/{t}/people/{normal['id']}").status_code == 404
    assert researcher.get(f"/trees/{t}/people/{shared['id']}").status_code == 200
    assert researcher.post(f"/trees/{t}/people", json=person_body("X")).status_code == 403


def test_viewer_cannot_modify_anything_via_api(owner, tree, member_factory):
    t = tree["id"]
    p = create_person(owner, t, "Target")
    viewer = member_factory(["VIEWER"])
    assert viewer.post(f"/trees/{t}/people", json=person_body("X")).status_code == 403
    assert viewer.patch(f"/trees/{t}/people/{p['id']}", json={"occupation": "hacked"}).status_code == 403
    assert viewer.delete(f"/trees/{t}/people/{p['id']}").status_code == 403
    assert viewer.post(f"/trees/{t}/people/{p['id']}/names", json={"given_name": "X"}).status_code == 403
    assert (
        viewer.put(
            f"/trees/{t}/people/{p['id']}/privacy", json={"privacy_level": "PUBLIC_DECEASED_ONLY"}
        ).status_code
        == 403
    )
    q = create_person(owner, t, "Other")
    assert (
        viewer.post(
            f"/trees/{t}/relationships",
            json={"person_a_id": p["id"], "person_b_id": q["id"], "type": "spouse"},
        ).status_code
        == 403
    )
    assert owner.get(f"/trees/{t}/people/{p['id']}").json()["occupation"] is None


def test_cross_tree_access_is_404(owner, tree, make_client):
    t = tree["id"]
    p = create_person(owner, t, "InTreeA")
    other = make_client()
    other.register()
    tb = other.post("/trees", json={"name": "Tree B"}).json()["id"]
    q = create_person(other, tb, "InTreeB")
    # person of tree A via tree B's URL
    assert other.get(f"/trees/{tb}/people/{p['id']}").status_code == 404
    # link across trees
    r = other.post(
        f"/trees/{tb}/relationships", json={"person_a_id": q["id"], "person_b_id": p["id"], "type": "spouse"}
    )
    assert r.status_code == 404
    # tree A directly
    assert other.get(f"/trees/{t}/people/{p['id']}").status_code == 404
    # owner of A using tree B URL with own ids
    assert owner.get(f"/trees/{tb}/people/{q['id']}").status_code == 404


def test_branch_scoped_contributor(owner, tree, make_client):
    t = tree["id"]
    from app.core.db import get_sessionmaker
    from app.models import BranchMembership, FamilyBranch

    inside = create_person(owner, t, "Inside")
    outside = create_person(owner, t, "Outside")
    with get_sessionmaker()() as db:
        import uuid

        b = FamilyBranch(tree_id=uuid.UUID(t), name="Madurai branch")
        db.add(b)
        db.flush()
        db.add(BranchMembership(tree_id=uuid.UUID(t), branch_id=b.id, person_id=uuid.UUID(inside["id"])))
        db.commit()
        branch_id = str(b.id)
    c = make_client()
    c.register()
    join_tree(owner, c, t, ["CONTRIBUTOR"], branch_id=branch_id)
    assert c.patch(f"/trees/{t}/people/{inside['id']}", json={"occupation": "Teacher"}).status_code == 200
    assert c.patch(f"/trees/{t}/people/{outside['id']}", json={"occupation": "Teacher"}).status_code == 403
    created = c.post(f"/trees/{t}/people", json=person_body("NewInBranch")).json()
    assert branch_id in created["branch_ids"]


def test_public_tree_never_exposes_living_or_private(owner, tree, client):
    t = tree["id"]
    slug = tree["slug"]
    anc = create_person(
        owner,
        t,
        "Ancestor",
        status="deceased",
        privacy_level="PUBLIC_DECEASED_ONLY",
        birth={"date": exact(1900, 1, 2)},
    )
    living = _living(owner, t, privacy_level="PUBLIC_DECEASED_ONLY")
    child = create_person(
        owner,
        t,
        "Child",
        status="living",
        privacy_level="PUBLIC_DECEASED_ONLY",
        birth={"date": exact(2016, 5, 5)},
    )
    members_only = create_person(owner, t, "MembersOnly", status="deceased")
    link(owner, t, anc["id"], living["id"], "biological_parent")
    link(owner, t, anc["id"], child["id"], "biological_parent")
    # public mode off → 404
    assert client.get(f"/public/trees/{slug}").status_code == 404
    owner.patch(f"/trees/{t}", json={"public_mode": "DECEASED_ONLY"})
    assert client.get(f"/public/trees/{slug}").status_code == 200
    listing = client.get(f"/public/trees/{slug}/people").json()["items"]
    assert [p["id"] for p in listing] == [anc["id"]]
    for pid in (living["id"], child["id"], members_only["id"]):
        assert client.get(f"/public/trees/{slug}/people/{pid}").status_code == 404
    page = client.get(f"/public/trees/{slug}/people/{anc['id']}")
    assert page.status_code == 200
    assert page.json()["birth"]["date"]["precision"] == "year_only"
    fam = client.get(f"/public/trees/{slug}/people/{anc['id']}/family").text
    anc_graph = client.get(f"/public/trees/{slug}/people/{anc['id']}/ancestors").text
    for leak in ("Priya", "Child", living["id"], child["id"], "Secret", "04:17", '"hidden":true'):
        assert leak not in fam and leak not in anc_graph


def test_minor_is_protected_even_if_marked_public(owner, tree, member_factory):
    t = tree["id"]
    kid = create_person(owner, t, "Kid", status="living", birth={"date": exact(2018, 2, 3)})
    viewer = member_factory(["VIEWER"])
    body = viewer.get(f"/trees/{t}/people/{kid['id']}").json()
    assert body["is_minor"] is True
    assert body["birth"]["date"]["precision"] == "year_only"
