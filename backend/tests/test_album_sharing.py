"""Event photo albums on the record sharing model (ADR-0027, increment 3; threat T58).

An album's photos are documents with their own audience; the album shows each viewer only what
they may see. A photo in an event's album is never more visible than the event and the people in
it, and an event made more private narrows its photos.
"""

from __future__ import annotations

import io
from typing import Any

from PIL import Image

from tests.helpers import create_person

_n = 0


def _jpg() -> bytes:
    global _n
    _n += 1
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), ((_n * 37) % 255, (_n * 91) % 255, (_n * 53) % 255)).save(buf, "JPEG")
    return buf.getvalue()


def _event(client: Any, t: str, pid: str, **body: Any) -> dict[str, Any]:
    r = client.post(
        f"/trees/{t}/events",
        json={"category": "marriage", "participants": [{"person_id": pid, "role": "principal"}], **body},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _photo(client: Any, t: str, eid: str, **form: Any) -> Any:
    data = {k: str(v).lower() if isinstance(v, bool) else v for k, v in form.items() if v is not None}
    return client.post(
        f"/trees/{t}/events/{eid}/media", data=data, files={"file": ("p.jpg", _jpg(), "image/jpeg")}
    )


def _album(client: Any, t: str, eid: str) -> list[str]:
    r = client.get(f"/trees/{t}/events/{eid}/media")
    assert r.status_code == 200, r.text
    return [m["document_id"] for m in r.json()]


def _sees(client: Any, t: str, doc_id: str) -> bool:
    return client.get(f"/trees/{t}/documents/{doc_id}").status_code == 200


def _share(client: Any, t: str, doc_id: str, level: str, **body: Any) -> Any:
    return client.put(
        f"/trees/{t}/documents/{doc_id}/sharing", json={"privacy_level": level, "confirm_wider": True, **body}
    )


def test_choose_an_audience_when_adding_a_photo(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    viewer = member_factory(["VIEWER"], name="Viewer")
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    bride = create_person(owner, t, "Sita")  # deceased by default: no cap from her
    ev = _event(owner, t, bride["id"])
    shared = _photo(uploader, t, ev["id"], privacy_level="TREE_MEMBERS")
    mine = _photo(uploader, t, ev["id"], privacy_level="ONLY_ME")
    assert shared.status_code == 201 and mine.status_code == 201, mine.text
    assert mine.json()["document"]["privacy_level"] == "ONLY_ME"
    s, m = shared.json()["document_id"], mine.json()["document_id"]
    assert _album(uploader, t, ev["id"]) == [s, m]
    for c in (viewer, admin, owner):  # nobody but the uploader sees the Only-me photo, whatever their role
        assert _album(c, t, ev["id"]) == [s]
        assert not _sees(c, t, m)
        assert c.get(f"/trees/{t}/events/{ev['id']}").json()["media_count"] == 1


def test_a_photo_is_never_wider_than_its_event(owner, tree, member_factory):
    t = tree["id"]
    viewer = member_factory(["VIEWER"], name="Viewer")
    p = create_person(owner, t, "Kamla")
    ev = _event(owner, t, p["id"], category="illness", title="Hospital", privacy_level="PRIVATE_TREE_ADMINS")
    r = _photo(owner, t, ev["id"], privacy_level="TREE_MEMBERS")
    assert r.status_code == 422 and r.json()["error"]["code"] == "privacy_too_open"
    m = _photo(owner, t, ev["id"], privacy_level="SELECTED_MEMBERS").json()
    # later sharing cannot go past the event either
    r = _share(owner, t, m["document_id"], "TREE_MEMBERS")
    assert r.status_code == 422 and r.json()["error"]["code"] == "privacy_too_open"
    got = owner.get(f"/trees/{t}/documents/{m['document_id']}/sharing").json()
    assert got["ceiling"]["max_level"] == "SELECTED_MEMBERS"
    assert not _sees(viewer, t, m["document_id"])


def test_a_protected_person_in_the_photo_makes_it_only_me_by_default(owner, tree, member_factory):
    t = tree["id"]
    viewer = member_factory(["VIEWER"], name="Viewer")
    couple = create_person(owner, t, "Ravi", status="living", privacy_level="TREE_MEMBERS")
    ev = _event(owner, t, couple["id"])
    m = _photo(owner, t, ev["id"]).json()
    assert (m["document"]["privacy_level"], m["document"]["allow_download"]) == ("ONLY_ME", False)
    assert not _sees(viewer, t, m["document_id"])
    # one click widens it to the family, as far as the people in it allow
    assert _share(owner, t, m["document_id"], "TREE_MEMBERS").status_code == 200
    assert _sees(viewer, t, m["document_id"])
    # a privately kept relative in the photo caps it
    aunt = create_person(owner, t, "Kamla", status="living", privacy_level="PRIVATE_TREE_ADMINS")
    r = _photo(owner, t, ev["id"], person_ids=aunt["id"], privacy_level="TREE_MEMBERS")
    assert r.status_code == 422 and r.json()["error"]["code"] == "privacy_too_open"


def test_making_an_event_private_narrows_its_photos(owner, tree, member_factory):
    t = tree["id"]
    viewer = member_factory(["VIEWER"], name="Viewer")
    p = create_person(owner, t, "Gopal")
    ev = _event(owner, t, p["id"])
    m = _photo(owner, t, ev["id"], privacy_level="TREE_MEMBERS").json()
    assert _sees(viewer, t, m["document_id"])
    r = owner.patch(f"/trees/{t}/events/{ev['id']}", json={"privacy_level": "PRIVATE_TREE_ADMINS"})
    assert r.status_code == 200, r.text
    assert not _sees(viewer, t, m["document_id"])
    got = owner.get(f"/trees/{t}/documents/{m['document_id']}").json()
    assert got["privacy_level"] == "SELECTED_MEMBERS"


def test_adding_a_wider_photo_to_a_private_album_is_refused(owner, tree, member_factory):
    """Adding to an album never narrows someone's photo silently: its owner narrows it first."""
    t = tree["id"]
    p = create_person(owner, t, "Gopal")
    private_ev = _event(owner, t, p["id"], title="Private", privacy_level="PRIVATE_TREE_ADMINS")
    open_ev = _event(owner, t, p["id"], title="Open")
    m = _photo(owner, t, open_ev["id"], privacy_level="TREE_MEMBERS").json()
    body = {"document_id": m["document_id"]}
    r = owner.post(f"/trees/{t}/events/{private_ev['id']}/media/link", json=body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "privacy_too_open"
    assert _share(owner, t, m["document_id"], "ONLY_ME").status_code == 200
    assert owner.post(f"/trees/{t}/events/{private_ev['id']}/media/link", json=body).status_code == 201


def test_cover_and_counts_follow_each_viewer(owner, tree, member_factory):
    t = tree["id"]
    asha = member_factory(["VIEWER"], name="Asha")
    viewer = member_factory(["VIEWER"], name="Viewer")
    p = create_person(owner, t, "Gopal")
    ev = _event(owner, t, p["id"])
    first = _photo(owner, t, ev["id"], privacy_level="TREE_MEMBERS").json()
    cover = _photo(owner, t, ev["id"], privacy_level="ONLY_ME", is_cover=True).json()
    mid = next(x["id"] for x in owner.get(f"/trees/{t}/members").json() if x["user_id"] == asha.user["id"])
    assert (
        _share(
            owner, t, cover["document_id"], "SELECTED_MEMBERS", members=[{"membership_id": mid}]
        ).status_code
        == 200
    )
    for who, count, shown in ((asha, 2, cover), (viewer, 1, first), (owner, 2, cover)):
        got = who.get(f"/trees/{t}/events/{ev['id']}").json()
        assert (got["media_count"], got["cover_document_id"]) == (count, shown["document_id"])
