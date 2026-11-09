"""Record visibility and selective sharing (ADR-0027).

Every test asks the same question from several sides: can someone outside a record's audience —
including an owner, a family admin, a branch admin or a custodian — learn anything about it by id,
URL, list, search, album, grant list, audit log or export? And does the chosen audience get exactly
what it was given (view vs download)?
"""

from __future__ import annotations

import io
import zipfile
from typing import Any

from sqlalchemy import select

from app.models import AccessGrant, AuditEvent
from tests.conftest import join_tree, new_tree, owner_session
from tests.doc_fixtures import unique_png, upload
from tests.helpers import create_person

_n = 0


def _png() -> bytes:
    global _n
    _n += 1  # distinct bytes: identical visible files are refused as duplicates
    return unique_png(_n, "Sharing test photo")


def _doc(client: Any, t: str, level: str | None = None, **form: Any) -> dict[str, Any]:
    r = upload(
        client,
        t,
        _png(),
        mime="image/png",
        title=form.pop("title", "Nani's photo"),
        privacy_level=level,
        **form,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _mid(owner: Any, t: str, client: Any) -> str:
    return next(m["id"] for m in owner.get(f"/trees/{t}/members").json() if m["user_id"] == client.user["id"])


def _share(client: Any, t: str, doc_id: str, level: str, **body: Any) -> Any:
    return client.put(
        f"/trees/{t}/documents/{doc_id}/sharing",
        json={"privacy_level": level, "confirm_wider": True, **body},
    )


def _sees(client: Any, t: str, doc_id: str) -> bool:
    r = client.get(f"/trees/{t}/documents/{doc_id}")
    assert r.status_code in (200, 404), r.text
    return r.status_code == 200


def _url(client: Any, t: str, doc_id: str, variant: str = "original") -> Any:
    return client.post(f"/trees/{t}/documents/{doc_id}/download-url", params={"variant": variant})


def _everyone(member_factory: Any, branch_id: str | None = None) -> dict[str, Any]:
    return {
        "family_admin": member_factory(["FAMILY_ADMIN"], name="Family Admin"),
        "branch_admin": member_factory(["BRANCH_ADMIN"], branch_id=branch_id, name="Branch Admin")
        if branch_id
        else None,
        "custodian": member_factory(["DOCUMENT_CUSTODIAN"], name="Custodian"),
        "viewer": member_factory(["VIEWER"], name="Viewer"),
        "researcher": member_factory(["RESEARCHER"], name="Researcher"),
    }


# ---------------------------------------------------------------- Only me
def test_only_me_is_invisible_to_every_role_on_every_route(owner, tree, member_factory):
    t = tree["id"]
    b = owner.post(f"/trees/{t}/branches", json={"name": "Pune"}).json()
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    doc = _doc(uploader, t, "ONLY_ME", title="Dadi letter zzqx")
    assert doc["is_owner"] is True and doc["can_download"] is True
    others = {k: v for k, v in _everyone(member_factory, b["id"]).items() if v} | {"tree_owner": owner}
    for name, c in others.items():
        assert not _sees(c, t, doc["id"]), name
        for variant in ("original", "preview", "thumbnail"):
            assert _url(c, t, doc["id"], variant).status_code == 404, (name, variant)
        assert c.get(f"/trees/{t}/documents/{doc['id']}/sharing").status_code == 404, name
        listed = [d["id"] for d in c.get(f"/trees/{t}/documents").json()["items"]]
        assert doc["id"] not in listed, name
        hits = c.get(f"/trees/{t}/search", params={"q": "zzqx"}).json()
        assert doc["id"] not in str(hits), name
    assert _sees(uploader, t, doc["id"])


def test_promotion_to_admin_reveals_no_private_record(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    doc = _doc(uploader, t, "ONLY_ME")
    cousin = member_factory(["VIEWER"], name="Cousin")
    r = owner.patch(f"/trees/{t}/members/{_mid(owner, t, cousin)}", json={"roles": ["FAMILY_ADMIN"]})
    assert r.status_code == 200, r.text
    assert not _sees(cousin, t, doc["id"])
    r = owner.patch(f"/trees/{t}/members/{_mid(owner, t, cousin)}", json={"roles": ["OWNER"]})
    assert r.status_code == 200, r.text
    assert not _sees(cousin, t, doc["id"])


# ---------------------------------------------------------------- Selected members, view vs download
def test_selected_members_view_and_download_are_separate(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    doc = _doc(uploader, t, "ONLY_ME")
    asha, bhola = member_factory(["VIEWER"], name="Asha"), member_factory(["VIEWER"], name="Bhola")
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    r = _share(uploader, t, doc["id"], "SELECTED_MEMBERS", members=[{"membership_id": _mid(owner, t, asha)}])
    assert r.status_code == 200, r.text
    names = {a["display_name"]: a["access"] for a in r.json()["audience"]}
    assert names == {"Uploader": "owner", "Asha": "selected"}  # exactly who has access

    got = asha.get(f"/trees/{t}/documents/{doc['id']}").json()
    assert got["can_access_content"] is True and got["can_download"] is False
    assert "original" not in got["variants"]
    assert _url(asha, t, doc["id"], "thumbnail").status_code == 200
    r = _url(asha, t, doc["id"], "original")
    assert r.status_code == 403 and r.json()["error"]["code"] == "download_not_allowed"
    assert not _sees(bhola, t, doc["id"]) and not _sees(admin, t, doc["id"])

    r = _share(
        uploader,
        t,
        doc["id"],
        "SELECTED_MEMBERS",
        members=[{"membership_id": _mid(owner, t, asha), "can_download": True}],
    )
    assert r.status_code == 200, r.text
    url = _url(asha, t, doc["id"], "original")
    assert url.status_code == 200
    assert asha.get(url.json()["url"]).status_code == 200


def test_stale_signed_url_fails_after_revoke(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    doc = _doc(uploader, t, "ONLY_ME")
    asha = member_factory(["VIEWER"], name="Asha")
    members = [{"membership_id": _mid(owner, t, asha), "can_download": True}]
    assert _share(uploader, t, doc["id"], "SELECTED_MEMBERS", members=members).status_code == 200
    url = _url(asha, t, doc["id"]).json()["url"]
    assert asha.get(url).status_code == 200
    assert _share(uploader, t, doc["id"], "ONLY_ME").status_code == 200
    assert asha.get(url).status_code == 403  # not expired, but access is gone


def test_grants_die_with_the_membership(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    doc = _doc(uploader, t, "ONLY_ME")
    asha = member_factory(["VIEWER"], name="Asha")
    mid = _mid(owner, t, asha)
    assert (
        _share(uploader, t, doc["id"], "SELECTED_MEMBERS", members=[{"membership_id": mid}]).status_code
        == 200
    )
    assert _sees(asha, t, doc["id"])
    assert owner.delete(f"/trees/{t}/members/{mid}").status_code == 200
    with owner_session() as db:
        assert db.scalars(select(AccessGrant).where(AccessGrant.resource_id == doc["id"])).all() == []
    join_tree(owner, asha, t, ["VIEWER"])  # the same person, invited again
    assert not _sees(asha, t, doc["id"])


def test_no_cross_tree_members(owner, tree, member_factory, make_client):
    t = tree["id"]
    doc = _doc(owner, t, "ONLY_ME")
    other = new_tree(owner, "Other family")
    stranger = make_client()
    stranger.register(name="Stranger")
    join_tree(owner, stranger, other["id"], ["VIEWER"])
    foreign = _mid(owner, other["id"], stranger)
    r = _share(owner, t, doc["id"], "SELECTED_MEMBERS", members=[{"membership_id": foreign}])
    assert r.status_code == 404
    # and the record is not reachable from the other tree by id
    assert stranger.get(f"/trees/{other['id']}/documents/{doc['id']}").status_code == 404
    assert stranger.get(f"/trees/{t}/documents/{doc['id']}").status_code == 404


def test_only_me_cannot_be_granted_through_the_grants_api(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    doc = _doc(uploader, t, "ONLY_ME")
    asha = member_factory(["VIEWER"], name="Asha")
    body = {
        "user_id": asha.user["id"],
        "resource_type": "document",
        "resource_id": doc["id"],
        "permission": "view",
    }
    assert owner.post(f"/trees/{t}/grants", json=body).status_code == 404  # an admin cannot even see it
    r = uploader.post(f"/trees/{t}/grants", json=body)
    assert r.status_code == 409 and r.json()["error"]["code"] == "only_me_record"


def test_grant_list_does_not_reveal_private_records(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    doc = _doc(uploader, t, "ONLY_ME")
    asha = member_factory(["VIEWER"], name="Asha")
    assert (
        _share(
            uploader, t, doc["id"], "SELECTED_MEMBERS", members=[{"membership_id": _mid(owner, t, asha)}]
        ).status_code
        == 200
    )
    assert doc["id"] not in str(owner.get(f"/trees/{t}/grants").json())
    mine = uploader.get(f"/trees/{t}/grants").json()
    assert {g["resource_id"] for g in mine} == {doc["id"]}
    gid = mine[0]["id"]
    assert owner.delete(f"/trees/{t}/grants/{gid}").status_code == 404
    assert uploader.delete(f"/trees/{t}/grants/{gid}").status_code == 200
    assert not _sees(asha, t, doc["id"])


# ---------------------------------------------------------------- Selected branch, All family
def test_selected_branch(owner, tree, member_factory):
    t = tree["id"]
    pune = owner.post(f"/trees/{t}/branches", json={"name": "Pune"}).json()
    kashi = owner.post(f"/trees/{t}/branches", json={"name": "Kashi"}).json()
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    doc = _doc(uploader, t, "ONLY_ME")
    inside = member_factory(["VIEWER"], branch_id=pune["id"], name="Pune cousin")
    outside = member_factory(["VIEWER"], branch_id=kashi["id"], name="Kashi cousin")
    kashi_admin = member_factory(["BRANCH_ADMIN"], branch_id=kashi["id"], name="Kashi admin")
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    r = _share(uploader, t, doc["id"], "FAMILY_BRANCH")
    assert r.status_code == 422 and r.json()["error"]["code"] == "branch_required"
    r = _share(uploader, t, doc["id"], "FAMILY_BRANCH", audience_branch_id=pune["id"])
    assert r.status_code == 200, r.text
    assert _sees(inside, t, doc["id"])
    assert not _sees(outside, t, doc["id"]) and not _sees(kashi_admin, t, doc["id"])
    assert _sees(admin, t, doc["id"])  # Selected branch keeps ADR-0006's meaning (open point 1)
    who = {a["display_name"]: a["access"] for a in r.json()["audience"]}
    assert who["Pune cousin"] == "branch" and who["Admin"] == "role" and "Kashi cousin" not in who


def test_all_family_members(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    doc = _doc(uploader, t, "ONLY_ME")
    viewer, researcher = member_factory(["VIEWER"], name="Viewer"), member_factory(["RESEARCHER"], name="R")
    assert _share(uploader, t, doc["id"], "TREE_MEMBERS", allow_download=True).status_code == 200
    assert _sees(viewer, t, doc["id"]) and not _sees(researcher, t, doc["id"])
    assert _url(viewer, t, doc["id"]).status_code == 200


def test_public_records_are_not_supported(owner, tree):
    t = tree["id"]
    doc = _doc(owner, t, "ONLY_ME")
    r = _share(owner, t, doc["id"], "PUBLIC_DECEASED_ONLY")
    assert r.status_code == 422 and r.json()["error"]["code"] == "public_not_supported"
    r = upload(owner, t, _png(), mime="image/png", privacy_level="PUBLIC_DECEASED_ONLY")
    assert r.status_code == 422


# ---------------------------------------------------------------- who may change what
def test_widening_needs_confirmation_and_is_audited_without_content(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    member_factory(["VIEWER"], name="Viewer")
    doc = _doc(uploader, t, "ONLY_ME", title="Secret title qwerty")
    r = uploader.put(f"/trees/{t}/documents/{doc['id']}/sharing", json={"privacy_level": "TREE_MEMBERS"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "confirm_wider"
    assert r.json()["error"]["details"]["viewers_added"] >= 2
    preview = uploader.post(
        f"/trees/{t}/documents/{doc['id']}/sharing/preview", json={"privacy_level": "TREE_MEMBERS"}
    )
    assert preview.status_code == 200 and len(preview.json()["audience"]) >= 3
    assert not _sees(owner, t, doc["id"])  # the preview changed nothing
    assert _share(uploader, t, doc["id"], "TREE_MEMBERS").status_code == 200
    with owner_session() as db:
        ev = db.scalars(
            select(AuditEvent).where(
                AuditEvent.action == "record.visibility_changed", AuditEvent.target_id == doc["id"]
            )
        ).all()
    assert len(ev) == 1 and ev[0].details["from"] == "ONLY_ME" and ev[0].details["to"] == "TREE_MEMBERS"
    assert "qwerty" not in str(ev[0].details) and "Uploader" not in str(ev[0].details)


def test_managers_may_only_narrow_shared_records(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    viewer = member_factory(["VIEWER"], name="Viewer")
    doc = _doc(uploader, t, "TREE_MEMBERS")
    assert (
        viewer.put(f"/trees/{t}/documents/{doc['id']}/sharing", json={"privacy_level": "ONLY_ME"}).status_code
        == 403
    )
    pune = owner.post(f"/trees/{t}/branches", json={"name": "Pune"}).json()
    r = _share(admin, t, doc["id"], "FAMILY_BRANCH", audience_branch_id=pune["id"])
    assert r.status_code == 200, r.text  # narrowing a shared record (admins stay in a branch audience)
    assert not _sees(viewer, t, doc["id"])
    r = _share(admin, t, doc["id"], "TREE_MEMBERS")
    assert r.status_code == 403 and r.json()["error"]["code"] == "owner_only_widening"
    r = _share(admin, t, doc["id"], "ONLY_ME")
    assert r.status_code == 200
    assert not _sees(admin, t, doc["id"])  # narrowed out of their own sight
    # PATCH follows the same rules
    doc2 = _doc(uploader, t, "TREE_MEMBERS")
    assert (
        admin.patch(f"/trees/{t}/documents/{doc2['id']}", json={"privacy_level": "FAMILY_BRANCH"}).status_code
        == 200
    )
    r = admin.patch(f"/trees/{t}/documents/{doc2['id']}", json={"privacy_level": "TREE_MEMBERS"})
    assert r.status_code == 403
    assert (
        uploader.patch(f"/trees/{t}/documents/{doc2['id']}", json={"privacy_level": "ONLY_ME"}).status_code
        == 200
    )


# ---------------------------------------------------------------- ceilings: tagged people (§5)
def test_tagging_a_private_living_person_narrows_the_record(owner, tree, member_factory):
    t = tree["id"]
    viewer = member_factory(["VIEWER"], name="Viewer")
    doc = _doc(owner, t, "TREE_MEMBERS")
    aunt = create_person(owner, t, "Kamla", status="living", privacy_level="PRIVATE_TREE_ADMINS")
    assert _sees(viewer, t, doc["id"])
    r = owner.post(
        f"/trees/{t}/documents/{doc['id']}/links", json={"target_type": "person", "target_id": aunt["id"]}
    )
    assert r.status_code == 201, r.text
    assert not _sees(viewer, t, doc["id"])
    got = owner.get(f"/trees/{t}/documents/{doc['id']}/sharing").json()
    assert got["privacy_level"] == "SELECTED_MEMBERS" and got["ceiling"]["max_level"] == "SELECTED_MEMBERS"
    r = _share(owner, t, doc["id"], "TREE_MEMBERS")
    assert r.status_code == 422 and r.json()["error"]["code"] == "privacy_too_open"
    # a new upload tagged with her defaults to Only me, without download
    r = upload(owner, t, _png(), mime="image/png", link_target_type="person", link_target_id=aunt["id"])
    assert (
        r.status_code == 201
        and r.json()["privacy_level"] == "ONLY_ME"
        and r.json()["allow_download"] is False
    )


def test_making_a_person_private_narrows_their_records(owner, tree, member_factory):
    t = tree["id"]
    viewer = member_factory(["VIEWER"], name="Viewer")
    cousin = create_person(owner, t, "Ravi", status="living", privacy_level="TREE_MEMBERS")
    doc = _doc(owner, t, "TREE_MEMBERS", link_target_type="person", link_target_id=cousin["id"])
    assert _sees(viewer, t, doc["id"])
    r = owner.put(f"/trees/{t}/people/{cousin['id']}/privacy", json={"privacy_level": "PRIVATE_TREE_ADMINS"})
    assert r.status_code == 200, r.text
    assert not _sees(viewer, t, doc["id"])


def test_people_cannot_take_record_only_levels(owner, tree):
    t = tree["id"]
    r = owner.post(
        f"/trees/{t}/people",
        json={
            "profile_status": "living",
            "privacy_level": "ONLY_ME",
            "names": [{"given_name": "X", "is_preferred": True}],
        },
    )
    assert r.status_code == 422


# ---------------------------------------------------------------- albums (§6), exports, audit
def test_album_shows_each_viewer_only_their_photos(owner, tree, member_factory):
    t = tree["id"]
    viewer = member_factory(["VIEWER"], name="Viewer")
    bride = create_person(owner, t, "Sita", privacy_level="TREE_MEMBERS")
    ev = owner.post(
        f"/trees/{t}/events",
        json={"category": "marriage", "participants": [{"person_id": bride["id"], "role": "principal"}]},
    ).json()

    def add(level: str, cover: bool) -> dict[str, Any]:
        r = owner.post(
            f"/trees/{t}/events/{ev['id']}/media",
            data={"privacy_level": level, "is_cover": str(cover).lower()},
            files={"file": ("p.png", _png(), "image/png")},
        )
        assert r.status_code == 201, r.text
        return r.json()

    shared = add("TREE_MEMBERS", False)
    restricted = add("TREE_MEMBERS", True)
    assert _share(owner, t, restricted["document_id"], "ONLY_ME").status_code == 200
    album = viewer.get(f"/trees/{t}/events/{ev['id']}/media").json()
    assert [m["document_id"] for m in album] == [shared["document_id"]]
    got = viewer.get(f"/trees/{t}/events/{ev['id']}").json()
    assert got["media_count"] == 1 and got["cover_document_id"] == shared["document_id"]
    mine = owner.get(f"/trees/{t}/events/{ev['id']}").json()
    assert mine["media_count"] == 2 and mine["cover_document_id"] == restricted["document_id"]


def test_archive_export_excludes_records_outside_the_exporters_audience(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    private = _doc(uploader, t, "ONLY_ME")
    view_only = _doc(uploader, t, "TREE_MEMBERS", allow_download="false")
    z = zipfile.ZipFile(io.BytesIO(owner.get(f"/trees/{t}/exports/archive").content))
    index = z.read(next(n for n in z.namelist() if n.endswith("documents/index.json"))).decode()
    assert private["id"] not in index
    entry = next(e for e in __import__("json").loads(index) if e["id"] == view_only["id"])
    assert entry["included"] is False  # viewing is not downloading
    assert not any(view_only["id"] in n for n in z.namelist())


def test_audit_log_hides_private_records_from_admins(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    doc = _doc(uploader, t, "ONLY_ME")
    items = owner.get(f"/trees/{t}/audit").json()["items"]
    assert doc["id"] not in str(items)
    assert any(i["target_type"] == "private_record" for i in items)


# ---------------------------------------------------------------- defaults and legacy levels
def test_new_vault_upload_is_only_me_without_download(owner, tree, member_factory):
    t = tree["id"]
    custodian = member_factory(["DOCUMENT_CUSTODIAN"], name="Custodian")
    r = upload(owner, t, _png(), mime="image/png", category="birth_certificate", title="Birth certificate")
    assert r.status_code == 201, r.text
    assert r.json()["privacy_level"] == "ONLY_ME" and r.json()["allow_download"] is False
    assert not _sees(custodian, t, r.json()["id"])


def test_legacy_custom_keeps_its_meaning(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    doc = _doc(uploader, t, "CUSTOM")
    assert _sees(admin, t, doc["id"])  # not silently tightened (ADR-0027 §1)
    got = uploader.get(f"/trees/{t}/documents/{doc['id']}/sharing").json()
    assert got["legacy"] is True


def test_patching_privacy_keeps_the_old_level_in_version_history(owner, tree, member_factory):
    """Regression: the metadata snapshot is taken before the sharing change is applied."""
    t = tree["id"]
    doc = _doc(owner, t, "TREE_MEMBERS")
    r = owner.patch(
        f"/trees/{t}/documents/{doc['id']}", json={"privacy_level": "ONLY_ME", "title": "Renamed"}
    )
    assert r.status_code == 200, r.text
    versions = owner.get(f"/trees/{t}/documents/{doc['id']}/versions").json()
    assert [v["snapshot"]["privacy_level"] for v in versions] == ["TREE_MEMBERS", "ONLY_ME"]
    assert versions[-1]["current"] is True
