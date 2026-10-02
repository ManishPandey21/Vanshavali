"""Geo-tagged places, important life events and event photo albums (ADR-0015)."""

from __future__ import annotations

import io
import json
from typing import Any

from PIL import Image

from tests.doc_fixtures import fetch
from tests.helpers import create_person, exact


def photo(color: tuple[int, int, int] = (200, 40, 40), size: tuple[int, int] = (64, 48)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


def add_place(client: Any, tid: str, **body: Any) -> dict[str, Any]:
    r = client.post(f"/trees/{tid}/places", json={"canonical_name": "Bhadohi", **body})
    assert r.status_code == 201, r.text
    return r.json()


def life_event(client: Any, tid: str, pid: str, **body: Any) -> dict[str, Any]:
    r = client.post(
        f"/trees/{tid}/events",
        json={"participants": [{"person_id": pid, "role": "principal"}], **body},
    )
    assert r.status_code == 201, r.text
    return r.json()


def upload_photo(client: Any, tid: str, eid: str, **form: Any) -> Any:
    data = {k: (json.dumps(v) if isinstance(v, dict) else v) for k, v in form.items() if v is not None}
    color = data.pop("color", (10, 120, 200))
    return client.post(
        f"/trees/{tid}/events/{eid}/media",
        data=data,
        files={"file": ("p.jpg", photo(color), "image/jpeg")},
    )


# ---------------------------------------------------------------- places
def test_place_geotag_fields_and_defaults(owner, tree):
    tid = tree["id"]
    p = add_place(
        owner,
        tid,
        place_type="village",
        latitude=25.39,
        longitude=82.57,
        district="Bhadohi",
        state="Uttar Pradesh",
        country="India",
        map_label="Pandey ka gaon",
        geo_note="From the 1931 census map",
        local_names=[{"name": "भदोही", "script": "Deva"}],
    )
    assert p["location_precision"] == "approximate"  # coordinates without precision are never "exact"
    assert p["district"] == "Bhadohi" and p["map_label"] == "Pandey ka gaon"
    assert p["coordinates_coarsened"] is False
    unknown = add_place(owner, tid, canonical_name="Somewhere in Bihar", state="Bihar")
    assert unknown["latitude"] is None and unknown["location_precision"] == "unknown"
    r = owner.get(f"/trees/{tid}/places?geotagged=true").json()
    assert [x["id"] for x in r["items"]] == [p["id"]]
    for pt in ("ancestral_house", "shrine", "land_parcel", "neighbourhood"):
        add_place(owner, tid, canonical_name=f"x-{pt}", place_type=pt)


def test_coordinates_must_come_in_pairs(owner, tree):
    r = owner.post(f"/trees/{tree['id']}/places", json={"canonical_name": "Half", "latitude": 20.0})
    assert r.status_code == 422
    p = add_place(owner, tree["id"], latitude=20.0, longitude=80.0)
    r = owner.patch(f"/trees/{tree['id']}/places/{p['id']}", json={"latitude": 21.0})
    assert r.status_code == 422


def test_coordinate_privacy_coarsens_for_lower_roles(owner, tree, member_factory):
    tid = tree["id"]
    house = add_place(
        owner,
        tid,
        canonical_name="Ancestral haveli",
        place_type="ancestral_house",
        latitude=25.123456,
        longitude=82.654321,
        location_precision="exact",
        coordinate_privacy="PRIVATE_TREE_ADMINS",
        geo_note="gate GPS",
    )
    assert house["latitude"] == 25.123456
    viewer = member_factory(["VIEWER"])
    seen = viewer.get(f"/trees/{tid}/places/{house['id']}").json()
    assert seen["latitude"] == 25.1 and seen["longitude"] == 82.7
    assert seen["coordinates_coarsened"] is True and seen["location_precision"] == "approximate"
    assert seen["geo_note"] is None
    assert "25.123456" not in viewer.get(f"/trees/{tid}/places").text
    # only privacy managers may loosen coordinate privacy
    contributor = member_factory(["CONTRIBUTOR"])
    r = contributor.patch(f"/trees/{tid}/places/{house['id']}", json={"coordinate_privacy": None})
    assert r.status_code == 403


# ---------------------------------------------------------------- life events
def test_life_event_with_category_title_and_geotag(owner, tree):
    tid = tree["id"]
    raju = create_person(owner, tid, "Raju", status="living", birth={"date": exact(1990, 5, 1)})
    temple = add_place(
        owner,
        tid,
        canonical_name="Vindhyavasini temple",
        place_type="temple",
        latitude=25.17,
        longitude=82.51,
    )
    ev = life_event(
        owner,
        tid,
        raju["id"],
        category="mundan",
        title="Raju's mundan at Vindhyachal",
        significance="milestone",
        date={"precision": "circa", "year": 1993},
        place_id=temple["id"],
        description="First haircut at the family temple",
    )
    assert ev["type"] == "religious_ceremony"  # category implies the structural type
    assert ev["category"] == "mundan" and ev["significance"] == "milestone"
    assert ev["title"] == "Raju's mundan at Vindhyachal"
    assert ev["date_display"].startswith("c.")
    r = owner.patch(f"/trees/{tid}/events/{ev['id']}", json={"title": "Mundan", "significance": None})
    assert r.status_code == 200 and r.json()["title"] == "Mundan" and r.json()["significance"] == "milestone"
    # neither type nor category: rejected
    r = owner.post(f"/trees/{tid}/events", json={"participants": [{"person_id": raju["id"]}]})
    assert r.status_code == 422


def test_tree_wide_life_events_listing_filters(owner, tree):
    tid = tree["id"]
    a = create_person(owner, tid, "Asha")
    b = create_person(owner, tid, "Bhola")
    life_event(owner, tid, a["id"], category="marriage", date=exact(1950, 2, 3), significance="important")
    life_event(
        owner,
        tid,
        b["id"],
        category="migration",
        date={"precision": "year_only", "year": 1947},
        latitude=28.6,
        longitude=77.2,
    )
    life_event(owner, tid, b["id"], type="residence", date={"precision": "year_only", "year": 1960})
    items = owner.get(f"/trees/{tid}/life-events").json()["items"]
    assert [e["category"] for e in items] == ["migration", "marriage", None]  # chronological
    imp = owner.get(f"/trees/{tid}/life-events?important_only=true").json()["items"]
    assert len(imp) == 2
    geo = owner.get(f"/trees/{tid}/life-events?geotagged=true").json()["items"]
    assert [e["category"] for e in geo] == ["migration"]
    mine = owner.get(f"/trees/{tid}/life-events?person_id={a['id']}").json()["items"]
    assert len(mine) == 1
    win = owner.get(f"/trees/{tid}/life-events?from_year=1948&to_year=1955").json()["items"]
    assert [e["category"] for e in win] == ["marriage"]
    page = owner.get(f"/trees/{tid}/life-events?limit=2").json()
    assert len(page["items"]) == 2 and page["next_cursor"]
    rest = owner.get(f"/trees/{tid}/life-events?limit=2&cursor={page['next_cursor']}").json()
    assert len(rest["items"]) == 1 and rest["next_cursor"] is None


def test_private_events_and_people_never_listed(owner, tree, member_factory):
    tid = tree["id"]
    hidden = create_person(owner, tid, "Secret", privacy_level="PRIVATE_TREE_ADMINS")
    open_p = create_person(owner, tid, "Open")
    life_event(owner, tid, hidden["id"], category="award", title="Hidden award")
    life_event(
        owner,
        tid,
        open_p["id"],
        category="illness",
        title="Private illness",
        privacy_level="PRIVATE_TREE_ADMINS",
    )
    life_event(owner, tid, open_p["id"], category="award", title="Public award")
    viewer = member_factory(["VIEWER"])
    r = viewer.get(f"/trees/{tid}/life-events")
    assert [e["title"] for e in r.json()["items"]] == ["Public award"]
    assert "Hidden award" not in r.text and "Private illness" not in r.text


# ---------------------------------------------------------------- photos
def test_event_album_upload_cover_tags_and_removal(owner, tree):
    tid = tree["id"]
    a = create_person(owner, tid, "Asha")
    b = create_person(owner, tid, "Bhola")
    ev = life_event(owner, tid, a["id"], category="marriage", title="Wedding")
    r1 = upload_photo(
        owner,
        tid,
        ev["id"],
        caption="Varmala",
        taken_date={"precision": "year_only", "year": 1950},
        person_ids=b["id"],
    )
    assert r1.status_code == 201, r1.text
    m1 = r1.json()
    assert m1["is_cover"] is True  # the first photo becomes the cover
    assert m1["document"]["category"] == "photo"
    assert {p["display_name"] for p in m1["people"]} == {"Asha Iyer", "Bhola Iyer"}  # principal tagged too
    assert m1["taken_date_display"] == "1950"
    m2 = upload_photo(owner, tid, ev["id"], caption="Pheras", is_cover="true", color=(1, 2, 3)).json()
    album = owner.get(f"/trees/{tid}/events/{ev['id']}/media").json()
    assert [m["caption"] for m in album] == ["Varmala", "Pheras"]
    assert [m["is_cover"] for m in album] == [False, True]  # one cover only
    got = owner.get(f"/trees/{tid}/events/{ev['id']}").json()
    assert got["media_count"] == 2 and got["cover_document_id"] == m2["document_id"]
    # one photo, many people: Bhola's documents include it
    docs = owner.get(f"/trees/{tid}/documents?target_type=person&target_id={b['id']}").json()["items"]
    assert [d["id"] for d in docs] == [m1["document_id"]]
    assert len(owner.get(f"/trees/{tid}/people/{a['id']}/photos").json()) == 2
    # thumbnails are produced by the normal pipeline and served through signed URLs
    url = owner.post(
        f"/trees/{tid}/documents/{m2['document_id']}/download-url", json={"variant": "thumbnail"}
    )
    assert url.status_code == 200, url.text
    assert fetch(owner, url.json()["url"]).status_code == 200
    # removing the cover promotes the next photo; the document stays in the vault
    assert owner.delete(f"/trees/{tid}/events/{ev['id']}/media/{m2['id']}").status_code == 200
    album = owner.get(f"/trees/{tid}/events/{ev['id']}/media").json()
    assert len(album) == 1 and album[0]["is_cover"] is True
    assert owner.get(f"/trees/{tid}/documents/{m2['document_id']}").status_code == 200
    # captions and order can be edited
    r = owner.patch(
        f"/trees/{tid}/events/{ev['id']}/media/{m1['id']}", json={"caption": "Jaimala", "sort_order": 5}
    )
    assert r.status_code == 200 and r.json()["caption"] == "Jaimala"


def test_photo_privacy_inherits_from_event_and_person(owner, tree, member_factory):
    tid = tree["id"]
    p = create_person(owner, tid, "Kamla")
    ev = life_event(
        owner, tid, p["id"], category="illness", title="Hospital", privacy_level="PRIVATE_TREE_ADMINS"
    )
    m = upload_photo(owner, tid, ev["id"]).json()
    assert m["document"]["privacy_level"] == "PRIVATE_TREE_ADMINS"
    # a photo can never be looser than what it inherits
    r = upload_photo(owner, tid, ev["id"], privacy_level="TREE_MEMBERS", color=(9, 9, 9))
    assert r.status_code == 422 and r.json()["error"]["code"] == "privacy_too_open"
    viewer = member_factory(["VIEWER"])
    assert viewer.get(f"/trees/{tid}/events/{ev['id']}/media").status_code == 404
    assert viewer.get(f"/trees/{tid}/documents/{m['document_id']}").status_code == 404
    # visible event, hidden photo: the album and the counts leave it out
    ev2 = life_event(owner, tid, p["id"], category="award", title="Award")
    upload_photo(owner, tid, ev2["id"], privacy_level="PRIVATE_TREE_ADMINS", color=(5, 5, 5))
    assert viewer.get(f"/trees/{tid}/events/{ev2['id']}/media").json() == []
    assert viewer.get(f"/trees/{tid}/events/{ev2['id']}").json()["media_count"] == 0


def test_album_write_permissions_and_validation(owner, tree, member_factory):
    tid = tree["id"]
    p = create_person(owner, tid, "Ravi")
    ev = life_event(owner, tid, p["id"], category="graduation")
    viewer = member_factory(["VIEWER"])
    assert upload_photo(viewer, tid, ev["id"]).status_code == 403
    # not an image
    r = owner.post(
        f"/trees/{tid}/events/{ev['id']}/media",
        files={"file": ("x.pdf", b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF", "application/pdf")},
    )
    assert r.status_code == 422
    # tagging a hidden person is a 404 before anything is stored
    hidden = create_person(owner, tid, "Hidden", privacy_level="PRIVATE_TREE_ADMINS")
    contributor = member_factory(["CONTRIBUTOR"])
    r = upload_photo(contributor, tid, ev["id"], person_ids=hidden["id"])
    assert r.status_code == 404
    # linking an existing non-photo document is refused; linking a photo works once
    m = upload_photo(owner, tid, ev["id"]).json()
    ev2 = life_event(owner, tid, p["id"], category="award")
    r = owner.post(
        f"/trees/{tid}/events/{ev2['id']}/media/link",
        json={"document_id": m["document_id"], "caption": "Same photo"},
    )
    assert r.status_code == 201
    r = owner.post(f"/trees/{tid}/events/{ev2['id']}/media/link", json={"document_id": m["document_id"]})
    assert r.status_code == 409


def test_album_is_tree_isolated(owner, tree, make_client):
    from tests.conftest import new_tree

    tid = tree["id"]
    p = create_person(owner, tid, "Ravi")
    ev = life_event(owner, tid, p["id"], category="award")
    m = upload_photo(owner, tid, ev["id"]).json()
    other = new_tree(owner, "Other")
    q = create_person(owner, other["id"], "Q")
    ev_other = life_event(owner, other["id"], q["id"], category="award")
    # cross-tree: the event and the document do not exist in the other tree
    assert owner.get(f"/trees/{other['id']}/events/{ev['id']}/media").status_code == 404
    r = owner.post(
        f"/trees/{other['id']}/events/{ev_other['id']}/media/link", json={"document_id": m["document_id"]}
    )
    assert r.status_code == 404
