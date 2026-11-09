"""Document vault: upload pipeline, immutability, encryption at rest, authorisation, signed downloads."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import sign_payload
from app.core.storage import ObjectExists, get_store
from app.models import AuditEvent, Document
from tests.conftest import join_tree, new_tree, owner_session
from tests.doc_fixtures import (
    eicar_png,
    javascript_pdf,
    jpeg_with_exif,
    png_bytes,
    text_image,
    text_pdf,
    upload,
)
from tests.helpers import create_person


def _png() -> bytes:
    return png_bytes(text_image(["Family photo, Varanasi 1952"], width=900))


def _row(doc_id: str) -> Document:
    with owner_session() as db:
        doc = db.get(Document, doc_id)
        assert doc is not None
        return doc


def _audit_actions(tree_id: str) -> list[AuditEvent]:
    with owner_session() as db:
        return list(db.scalars(select(AuditEvent).where(AuditEvent.tree_id == tree_id)))


def _stored_files(tree_id: str) -> list[Path]:
    root = Path(get_settings().storage_local_path)
    return [p for p in root.rglob("*") if p.is_file() and tree_id in str(p)]


# ---------------------------------------------------------------- happy path
def test_upload_list_get_and_download(owner, tree):
    t = tree["id"]
    person = create_person(owner, t, "Kamala")
    data = _png()
    r = upload(
        owner,
        t,
        data,
        filename="family photo.png",
        mime="image/png",
        title="Wedding photo",
        document_date='{"precision": "year_only", "year": 1952}',
        link_target_type="person",
        link_target_id=person["id"],
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["storage_class"] == "STANDARD"
    assert doc["mime_type"] == "image/png"
    assert doc["scan_status"] == "clean"
    assert doc["preview_status"] == "completed"
    assert doc["ocr_status"] == "not_requested"  # photos are not OCR'd automatically
    assert doc["document_date"]["year"] == 1952
    assert doc["links"][0]["target_id"] == person["id"]
    assert set(doc["variants"]) == {"original", "preview", "thumbnail"}
    assert "storage_key" not in doc

    listing = owner.get(f"/trees/{t}/documents").json()["items"]
    assert [d["id"] for d in listing] == [doc["id"]]
    assert owner.get(f"/trees/{t}/documents", params={"q": "wedding"}).json()["items"][0]["id"] == doc["id"]
    assert owner.get(f"/trees/{t}/documents", params={"q": "nomatch"}).json()["items"] == []
    about = owner.get(f"/trees/{t}/documents", params={"target_type": "person", "target_id": person["id"]})
    assert [d["id"] for d in about.json()["items"]] == [doc["id"]]
    assert owner.get(f"/trees/{t}/documents/{doc['id']}").json()["title"] == "Wedding photo"

    r = owner.post(f"/trees/{t}/documents/{doc['id']}/download-url")
    assert r.status_code == 200, r.text
    url = r.json()["url"]
    assert url.startswith(get_settings().api_prefix + "/files/")
    got = owner.get(url)
    assert got.status_code == 200
    assert got.content == data
    assert got.headers["content-type"] == "image/png"
    assert got.headers["content-disposition"].startswith("attachment;")
    assert "family photo.png" in got.headers["content-disposition"].replace("%20", " ")
    assert got.headers["x-content-type-options"] == "nosniff"
    assert "no-store" in got.headers["cache-control"]

    thumb_url = owner.post(
        f"/trees/{t}/documents/{doc['id']}/download-url", params={"variant": "thumbnail"}
    ).json()["url"]
    thumb = owner.get(thumb_url)
    assert thumb.status_code == 200
    assert thumb.headers["content-type"] == "image/jpeg"
    assert thumb.headers["content-disposition"].startswith("inline;")
    assert max(Image.open(io.BytesIO(thumb.content)).size) <= 400

    actions = [a.action for a in _audit_actions(t)]
    assert "document.uploaded" in actions and "document.downloaded" in actions
    for a in _audit_actions(t):
        assert "Varanasi" not in str(a.details)  # never content in the audit log


def test_search_provider_lists_visible_documents_only(owner, tree, member_factory):
    t = tree["id"]
    upload(owner, t, _png(), mime="image/png", title="Sharma family letter", category="letter")
    upload(
        owner,
        t,
        png_bytes(text_image(["x"], width=300)),
        mime="image/png",
        title="Sharma secret deed",
        category="sale_deed",
    )
    hits = owner.get(f"/trees/{t}/search", params={"q": "Sharma", "kinds": "document"}).json()["hits"]
    assert {h["title"] for h in hits} == {"Sharma family letter", "Sharma secret deed"}
    assert all(h["kind"] == "document" for h in hits)
    viewer = member_factory(["VIEWER"])
    hits = viewer.get(f"/trees/{t}/search", params={"q": "Sharma", "kinds": "document"}).json()["hits"]
    assert {h["title"] for h in hits} == {"Sharma family letter"}


def test_preview_is_reencoded_without_exif(owner, tree):
    t = tree["id"]
    r = upload(owner, t, jpeg_with_exif(), filename="p.jpg", mime="image/jpeg", title="Scan")
    assert r.status_code == 201, r.text
    doc = r.json()
    url = owner.post(f"/trees/{t}/documents/{doc['id']}/download-url", params={"variant": "preview"}).json()[
        "url"
    ]
    preview = owner.get(url).content
    im = Image.open(io.BytesIO(preview))
    assert max(im.size) <= 1600
    assert len(im.getexif()) == 0
    assert b"SecretCameraMaker" not in preview
    # the original is untouched (bytes are stored exactly as uploaded)
    orig = owner.get(owner.post(f"/trees/{t}/documents/{doc['id']}/download-url").json()["url"]).content
    assert b"SecretCameraMaker" in orig


# ---------------------------------------------------------------- rejected uploads
def test_eicar_upload_rejected_audited_and_not_stored(owner, tree):
    t = tree["id"]
    r = upload(owner, t, eicar_png(), mime="image/png", title="Infected")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "malware_detected"
    assert owner.get(f"/trees/{t}/documents").json()["items"] == []
    assert _stored_files(t) == []
    rejected = [a for a in _audit_actions(t) if a.action == "document.malware_rejected"]
    assert len(rejected) == 1 and rejected[0].details["signature"]


def test_unsupported_type_rejected(owner, tree):
    r = upload(owner, tree["id"], b"just some plain text\n" * 10, filename="notes.txt", mime="text/plain")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "unsupported_type"
    # a lying extension/content-type does not help: type comes from magic bytes
    r = upload(owner, tree["id"], b"MZ\x90\x00" + b"\x00" * 200, filename="photo.png", mime="image/png")
    assert r.json()["error"]["code"] == "unsupported_type"


def test_pdf_with_javascript_rejected(owner, tree):
    r = upload(
        owner, tree["id"], javascript_pdf(), filename="x.pdf", mime="application/pdf", category="letter"
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "unsafe_pdf"
    assert _stored_files(tree["id"]) == []


def test_duplicate_upload_returns_existing_id(owner, tree):
    t = tree["id"]
    data = _png()
    first = upload(owner, t, data, mime="image/png").json()
    r = upload(owner, t, data, mime="image/png", title="Again")
    assert r.status_code == 409
    assert r.json()["error"]["details"]["existing_document_id"] == first["id"]


def test_property_categories_need_property_permission(owner, tree, member_factory):
    t = tree["id"]
    contributor = member_factory(["CONTRIBUTOR"])
    r = upload(contributor, t, _png(), mime="image/png", category="khatauni")
    assert r.status_code == 403
    custodian = member_factory(["PROPERTY_CUSTODIAN"])
    r = upload(custodian, t, _png(), mime="image/png", category="khatauni")
    assert r.status_code == 201, r.text
    viewer = member_factory(["VIEWER"])
    assert upload(viewer, t, _png(), mime="image/png").status_code == 403


# ---------------------------------------------------------------- immutability & encryption
def test_metadata_edits_are_versioned_and_original_never_changes(owner, tree):
    t = tree["id"]
    data = text_pdf(["A letter from 1947"])
    doc = upload(owner, t, data, filename="letter.pdf", mime="application/pdf", category="letter").json()
    r = owner.patch(f"/trees/{t}/documents/{doc['id']}", json={"title": "Letter from Dada", "language": "hi"})
    assert r.status_code == 200, r.text
    assert r.json()["metadata_version"] == 2
    r = owner.patch(f"/trees/{t}/documents/{doc['id']}", json={"description": "Written in Lahore"})
    assert r.json()["metadata_version"] == 3
    versions = owner.get(f"/trees/{t}/documents/{doc['id']}/versions").json()
    assert [v["version"] for v in versions] == [1, 2, 3]
    assert versions[0]["snapshot"]["title"] == "A document"
    assert versions[1]["snapshot"]["title"] == "Letter from Dada"
    assert versions[2]["current"] is True and versions[2]["snapshot"]["description"] == "Written in Lahore"
    # moving a document into another storage class is refused (would need a new encrypted original)
    r = owner.patch(f"/trees/{t}/documents/{doc['id']}", json={"category": "birth_certificate"})
    assert r.status_code == 422

    url = owner.post(f"/trees/{t}/documents/{doc['id']}/download-url").json()["url"]
    assert owner.get(url).content == data

    row = _row(doc["id"])
    assert row.storage_key == f"STANDARD/{t}/{row.checksum_sha256[:2]}/{doc['id']}/original"
    with pytest.raises(ObjectExists):
        get_store().put_immutable(row.storage_key, b"tampered", key_id="STANDARD")
    assert owner.get(url).content == data


def test_stored_bytes_are_encrypted_at_rest(owner, tree):
    t = tree["id"]
    data = text_pdf(["Registration No: B-1985-00432"])
    doc = upload(
        owner, t, data, filename="bc.pdf", mime="application/pdf", category="birth_certificate"
    ).json()
    row = _row(doc["id"])
    assert row.storage_class == "VAULT" and row.encryption_key_id == "VAULT"
    assert row.storage_key.startswith(f"VAULT/{t}/")
    raw = (Path(get_settings().storage_local_path) / row.storage_key).read_bytes()
    assert raw != data
    assert b"%PDF" not in raw and b"B-1985-00432" not in raw
    # derivatives (OCR text) are encrypted too
    for f in _stored_files(t):
        assert b"B-1985-00432" not in f.read_bytes()


# ---------------------------------------------------------------- authorisation
def _vault_doc(owner, t):  # type: ignore[no-untyped-def]
    r = upload(
        owner,
        t,
        text_pdf(["Birth certificate"]),
        filename="bc.pdf",
        mime="application/pdf",
        category="birth_certificate",
        title="Birth certificate",
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_vault_document_hidden_from_viewer_and_researcher(owner, tree, member_factory):
    t = tree["id"]
    doc = _vault_doc(owner, t)
    assert doc["privacy_level"] == "PRIVATE_TREE_ADMINS"
    viewer = member_factory(["VIEWER"])
    researcher = member_factory(["RESEARCHER"])
    custodian = member_factory(["DOCUMENT_CUSTODIAN"])
    contributor = member_factory(["CONTRIBUTOR"])
    for who in (viewer, researcher, contributor):
        assert who.get(f"/trees/{t}/documents/{doc['id']}").status_code == 404
        assert who.get(f"/trees/{t}/documents").json()["items"] == []
        assert who.post(f"/trees/{t}/documents/{doc['id']}/download-url").status_code == 404
        assert who.get(f"/trees/{t}/documents/{doc['id']}/ocr-text").status_code == 404
    # document custodians manage the vault
    assert custodian.get(f"/trees/{t}/documents/{doc['id']}").json()["can_access_content"] is True
    assert custodian.post(f"/trees/{t}/documents/{doc['id']}/download-url").status_code == 200

    # metadata shared with members: viewers see it, but vault bytes still need vault permission
    assert (
        owner.patch(f"/trees/{t}/documents/{doc['id']}", json={"privacy_level": "TREE_MEMBERS"}).status_code
        == 200
    )
    r = viewer.get(f"/trees/{t}/documents/{doc['id']}")
    assert r.status_code == 200
    assert r.json()["can_access_content"] is False and r.json()["variants"] == []
    assert viewer.post(f"/trees/{t}/documents/{doc['id']}/download-url").status_code == 403
    assert viewer.get(f"/trees/{t}/documents/{doc['id']}/ocr-text").status_code == 403
    assert viewer.get(f"/trees/{t}/documents/{doc['id']}/proposals").status_code == 403
    assert researcher.get(f"/trees/{t}/documents/{doc['id']}").status_code == 404  # TREE_MEMBERS excludes
    owner.patch(f"/trees/{t}/documents/{doc['id']}", json={"privacy_level": "INVITED_RESEARCHER"})
    assert researcher.get(f"/trees/{t}/documents/{doc['id']}").status_code == 200
    assert researcher.post(f"/trees/{t}/documents/{doc['id']}/download-url").status_code == 403
    # viewers cannot edit, delete or change privacy
    assert viewer.patch(f"/trees/{t}/documents/{doc['id']}", json={"title": "x"}).status_code == 403
    assert viewer.delete(f"/trees/{t}/documents/{doc['id']}").status_code == 403


def test_cross_tree_access_is_404(owner, tree, make_client):
    t = tree["id"]
    doc = upload(owner, t, _png(), mime="image/png").json()
    other = make_client()
    other.register()
    other_tree = new_tree(other, "Other")["id"]
    assert other.get(f"/trees/{other_tree}/documents/{doc['id']}").status_code == 404
    assert other.post(f"/trees/{other_tree}/documents/{doc['id']}/download-url").status_code == 404
    assert other.get(f"/trees/{t}/documents/{doc['id']}").status_code == 404
    assert other.get(f"/trees/{t}/documents").status_code == 404
    # an owner cannot link another tree's person
    foreign_person = create_person(other, other_tree, "Stranger")
    r = owner.post(
        f"/trees/{t}/documents/{doc['id']}/links",
        json={"target_type": "person", "target_id": foreign_person["id"]},
    )
    assert r.status_code == 404


def test_download_token_expired_tampered_or_other_user(owner, tree, member_factory, make_client):
    t = tree["id"]
    doc = upload(owner, t, _png(), mime="image/png").json()
    url = owner.post(f"/trees/{t}/documents/{doc['id']}/download-url").json()["url"]
    token = url.rsplit("/", 1)[1]
    prefix = get_settings().api_prefix

    expired = sign_payload(
        {"doc": doc["id"], "tree": t, "user": owner.user["id"], "variant": "original", "p": "dl"},
        ttl_seconds=-5,
    )
    r = owner.get(f"{prefix}/files/{expired}")
    assert r.status_code == 403 and r.json()["error"]["code"] == "invalid_download_token"

    tampered = token[:-3] + ("AAA" if not token.endswith("AAA") else "BBB")
    assert owner.get(f"{prefix}/files/{tampered}").status_code == 403
    raw, sig = token.split(".")
    assert owner.get(f"{prefix}/files/{raw}x.{sig}").status_code == 403

    admin = member_factory(["FAMILY_ADMIN"])  # can see the doc, but the token is not theirs
    assert admin.get(url).status_code == 403
    anon = make_client()
    assert anon.get(url).status_code == 401
    assert owner.get(url).status_code == 200


def test_revoked_grant_stops_download(owner, tree, member_factory):
    t = tree["id"]
    doc = _vault_doc(owner, t)
    viewer = member_factory(["VIEWER"])
    assert viewer.get(f"/trees/{t}/documents/{doc['id']}").status_code == 404
    g = owner.post(
        f"/trees/{t}/grants",
        json={
            "user_id": viewer.user["id"],
            "resource_type": "document",
            "resource_id": doc["id"],
            "permission": "download",
        },
    )
    assert g.status_code == 201, g.text
    assert viewer.get(f"/trees/{t}/documents/{doc['id']}").json()["can_access_content"] is True
    url = viewer.post(f"/trees/{t}/documents/{doc['id']}/download-url").json()["url"]
    assert viewer.get(url).status_code == 200
    assert owner.delete(f"/trees/{t}/grants/{g.json()['id']}").status_code == 200
    r = viewer.get(url)  # token not expired, but access was revoked
    assert r.status_code == 403
    assert viewer.post(f"/trees/{t}/documents/{doc['id']}/download-url").status_code == 404


def test_removed_member_token_fails(owner, tree, member_factory):
    t = tree["id"]
    doc = upload(owner, t, _png(), mime="image/png", privacy_level="TREE_MEMBERS").json()
    viewer = member_factory(["VIEWER"])
    url = viewer.post(f"/trees/{t}/documents/{doc['id']}/download-url").json()["url"]
    assert viewer.get(url).status_code == 200
    members = owner.get(f"/trees/{t}/members").json()
    mid = next(m["id"] for m in members if m["user_id"] == viewer.user["id"])
    assert owner.delete(f"/trees/{t}/members/{mid}").status_code == 200
    assert viewer.get(url).status_code == 403


def test_reinvited_member_does_not_get_old_grants_back(owner, tree, member_factory):
    """Regression: grants are keyed by user_id, so removal must delete them (ADR-0027 §3 stopgap)."""
    t = tree["id"]
    doc = upload(owner, t, _png(), mime="image/png", privacy_level="CUSTOM").json()
    viewer = member_factory(["VIEWER"])
    assert viewer.get(f"/trees/{t}/documents/{doc['id']}").status_code == 404
    g = owner.post(
        f"/trees/{t}/grants",
        json={
            "user_id": viewer.user["id"],
            "resource_type": "document",
            "resource_id": doc["id"],
            "permission": "view",
        },
    )
    assert g.status_code == 201, g.text
    assert viewer.get(f"/trees/{t}/documents/{doc['id']}").status_code == 200

    members = owner.get(f"/trees/{t}/members").json()
    mid = next(m["id"] for m in members if m["user_id"] == viewer.user["id"])
    assert owner.delete(f"/trees/{t}/members/{mid}").status_code == 200
    assert viewer.get(f"/trees/{t}/documents/{doc['id']}").status_code == 404
    assert g.json()["id"] not in {x["id"] for x in owner.get(f"/trees/{t}/grants").json()}
    cascade = [e for e in _audit_actions(t) if e.action == "grant.cascade_removed"]
    assert len(cascade) == 1
    assert cascade[0].details == {"count": 1}  # a count only: no resource ids or titles
    assert str(cascade[0].target_id) == mid

    join_tree(owner, viewer, t, ["VIEWER"])  # the same person, invited again
    assert viewer.get(f"/trees/{t}/documents/{doc['id']}").status_code == 404
    assert all(x["user_id"] != viewer.user["id"] for x in owner.get(f"/trees/{t}/grants").json())


def test_removing_a_member_keeps_their_grants_in_other_trees(owner, tree, member_factory):
    t = tree["id"]
    other = new_tree(owner, "Other tree")
    viewer = member_factory(["VIEWER"])
    join_tree(owner, viewer, other["id"], ["VIEWER"])
    grants = {}
    for tid in (t, other["id"]):
        doc = upload(owner, tid, _png(), mime="image/png", privacy_level="CUSTOM").json()
        r = owner.post(
            f"/trees/{tid}/grants",
            json={
                "user_id": viewer.user["id"],
                "resource_type": "document",
                "resource_id": doc["id"],
                "permission": "view",
            },
        )
        assert r.status_code == 201, r.text
        grants[tid] = (doc["id"], r.json()["id"])
    mid = next(m["id"] for m in owner.get(f"/trees/{t}/members").json() if m["user_id"] == viewer.user["id"])
    assert owner.delete(f"/trees/{t}/members/{mid}").status_code == 200
    other_doc, other_grant = grants[other["id"]]
    assert viewer.get(f"/trees/{other['id']}/documents/{other_doc}").status_code == 200
    assert other_grant in {x["id"] for x in owner.get(f"/trees/{other['id']}/grants").json()}


# ---------------------------------------------------------------- delete / restore / links
def test_soft_delete_and_restore(owner, tree, member_factory):
    t = tree["id"]
    doc = upload(owner, t, _png(), mime="image/png").json()
    url = owner.post(f"/trees/{t}/documents/{doc['id']}/download-url").json()["url"]
    assert owner.delete(f"/trees/{t}/documents/{doc['id']}").status_code == 200
    assert owner.get(f"/trees/{t}/documents/{doc['id']}").status_code == 404
    assert owner.get(f"/trees/{t}/documents").json()["items"] == []
    assert owner.get(url).status_code == 403  # deleted documents are not served
    deleted = owner.get(f"/trees/{t}/documents", params={"deleted": True}).json()["items"]
    assert [d["id"] for d in deleted] == [doc["id"]]
    viewer = member_factory(["VIEWER"])
    assert viewer.get(f"/trees/{t}/documents", params={"deleted": True}).status_code == 403
    r = owner.post(f"/trees/{t}/documents/{doc['id']}/restore")
    assert r.status_code == 200 and r.json()["deleted_at"] is None
    assert owner.get(url).status_code == 200
    assert _row(doc["id"]).storage_key  # the original was never removed


def test_links_crud_and_documents_about_target(owner, tree, member_factory):
    t = tree["id"]
    a = create_person(owner, t, "Asha")
    hidden = create_person(owner, t, "Hidden", status="living", privacy_level="PRIVATE_TREE_ADMINS")
    doc = upload(owner, t, _png(), mime="image/png", privacy_level="TREE_MEMBERS").json()
    r = owner.post(
        f"/trees/{t}/documents/{doc['id']}/links", json={"target_type": "person", "target_id": a["id"]}
    )
    assert r.status_code == 201, r.text
    link_id = r.json()["id"]
    assert (
        owner.post(
            f"/trees/{t}/documents/{doc['id']}/links", json={"target_type": "person", "target_id": a["id"]}
        ).status_code
        == 409
    )
    owner.post(
        f"/trees/{t}/documents/{doc['id']}/links", json={"target_type": "person", "target_id": hidden["id"]}
    )
    viewer = member_factory(["VIEWER"])
    # viewers do not learn about links to people they cannot see
    links = viewer.get(f"/trees/{t}/documents/{doc['id']}").json()["links"]
    assert [ln["target_id"] for ln in links] == [a["id"]]
    assert (
        viewer.get(
            f"/trees/{t}/documents", params={"target_type": "person", "target_id": hidden["id"]}
        ).status_code
        == 404
    )
    assert viewer.post(
        f"/trees/{t}/documents/{doc['id']}/links", json={"target_type": "person", "target_id": a["id"]}
    ).status_code in (403, 409)
    # property targets need property.read
    researcher = member_factory(["RESEARCHER"])
    assert (
        researcher.get(
            f"/trees/{t}/documents", params={"target_type": "property", "target_id": a["id"]}
        ).status_code
        == 404
    )
    assert owner.delete(f"/trees/{t}/documents/{doc['id']}/links/{link_id}").status_code == 200
    about = owner.get(f"/trees/{t}/documents", params={"target_type": "person", "target_id": a["id"]}).json()
    assert about["items"] == []
