"""ADR-0013: importing photos with a GEDCOM package (.zip / GEDZIP)."""

from __future__ import annotations

import io
import zipfile
from typing import Any

from PIL import Image

from app.core.scanner import EICAR_SIGNATURE
from tests.conftest import join_tree
from tests.helpers import create_person

WIN = "C:\\Users\\someone\\Downloads\\Verma Family Tree_Photos\\"


def _jpeg(color: tuple[int, int, int]) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(buf, "JPEG")
    return buf.getvalue()


def _png(color: tuple[int, int, int]) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), color).save(buf, "PNG")
    return buf.getvalue()


RED, BLUE, GREEN, GREY = _jpeg((200, 0, 0)), _jpeg((0, 0, 200)), _png((0, 160, 0)), _jpeg((90, 90, 90))

# MyHeritage-style: absolute Windows paths to a sibling "…_Photos" folder, one photo shared by two
# people, one photo not in the zip, and the "Unassociated photos" album record.
MYHERITAGE_GED = "\r\n".join(
    [
        "0 HEAD",
        "1 GEDC",
        "2 VERS 5.5.1",
        "1 CHAR UTF-8",
        "1 SOUR MYHERITAGE",
        "0 @I1@ INDI",
        "1 NAME Arjun /Verma/",
        "1 SEX M",
        "1 BIRT",
        "2 DATE 3 MAR 1980",
        "1 FAMC @F1@",
        "1 OBJE",
        "2 FORM jpg",
        "2 TITL Arjun at school",
        f"2 FILE {WIN}P1_64_48.jpg",
        "2 _PRIM Y",
        "1 OBJE",
        "2 FORM jpg",
        f"2 FILE {WIN}P9_family.jpg",
        "0 @I2@ INDI",
        "1 NAME Ramesh /Verma/",
        "1 SEX M",
        "1 DEAT Y",
        "1 FAMS @F1@",
        "1 OBJE",
        "2 FORM jpg",
        f"2 FILE {WIN}P9_family.jpg",
        "1 OBJE",
        "2 FORM jpg",
        f"2 FILE {WIN}P404_missing.jpg",
        "0 @I3@ INDI",
        "1 NAME Sita /Verma/",
        "1 SEX F",
        "1 RESN confidential",
        "1 FAMS @F1@",
        "1 OBJE",
        "2 FORM png",
        f"2 FILE {WIN}P3_sita.png",
        "0 @I88888888@ INDI",
        "1 _UID Unassociated photos",
        "1 SEX U",
        "1 OBJE",
        "2 FORM jpg",
        f"2 FILE {WIN}P17_whatsapp.jpg",
        "0 @F1@ FAM",
        "1 HUSB @I2@",
        "1 WIFE @I3@",
        "1 CHIL @I1@",
        "0 TRLR",
        "",
    ]
)


def _zip(files: dict[str, bytes], *, compress: int = zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compress) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _myheritage_zip(**extra: bytes) -> bytes:
    folder = "Verma Family Tree_Photos/"
    return _zip(
        {
            "Verma Family Tree.ged": MYHERITAGE_GED.encode("utf-8-sig"),
            folder + "P1_64_48.jpg": RED,
            folder + "P9_family.jpg": BLUE,
            folder + "P3_sita.png": GREEN,
            folder + "P17_whatsapp.jpg": GREY,
            **extra,
        }
    )


def _upload(client: Any, tree_id: str, data: bytes, name: str = "Verma.zip") -> Any:
    return client.post(f"/trees/{tree_id}/imports", files={"file": (name, data, "application/zip")})


def _commit(client: Any, tree_id: str, job_id: str, decisions: dict | None = None) -> dict[str, Any]:
    r = client.post(f"/trees/{tree_id}/imports/{job_id}/commit", json={"decisions": decisions or {}})
    assert r.status_code == 200, r.text
    return r.json()


def _people(client: Any, tree_id: str) -> dict[str, str]:
    return {p["display_name"]: p["id"] for p in client.get(f"/trees/{tree_id}/people").json()["items"]}


def _photos_of(client: Any, tree_id: str, person_id: str) -> list[dict[str, Any]]:
    docs = client.get(f"/trees/{tree_id}/documents?limit=100").json()["items"]
    return [d for d in docs if any(lk["target_id"] == person_id for lk in d["links"])]


def test_myheritage_zip_imports_photos_linked_to_people(owner, tree) -> None:
    t = tree["id"]
    r = _upload(owner, t, _myheritage_zip())
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["status"] == "ready"
    photos = job["report"]["photos"]
    assert photos["package"] is True
    # 5 references on people: 4 in the zip (one shared by two people), 1 missing
    assert (photos["referenced"], photos["matched"], photos["missing"]) == (5, 4, 1)
    assert photos["missing_files"] == ["P404_missing.jpg"]
    assert job["report"]["counts"]["photos_unlinked"] == 1  # the "Unassociated photos" album
    assert job["report"]["file"]["package"] is True

    done = _commit(owner, t, job["id"])
    counts = done["commit_result"]["counts"]
    assert counts["photos_imported"] == 3  # P1, P9 (stored once), P3
    assert counts["photos_linked"] == 1  # P9 linked to its second person
    people = _people(owner, t)
    arjun = _photos_of(owner, t, people["Arjun Verma"])
    assert sorted(d["title"] for d in arjun) == ["Arjun at school", "P9_family.jpg"]
    assert all(d["category"] == "photo" and d["mime_type"] == "image/jpeg" for d in arjun)
    ramesh = _photos_of(owner, t, people["Ramesh Verma"])
    assert [d["title"] for d in ramesh] == ["P9_family.jpg"]
    assert {d["id"] for d in arjun} & {d["id"] for d in ramesh}  # the shared photo is one document
    # the album's photo was not imported, and nothing is unlinked in the vault
    all_docs = owner.get(f"/trees/{t}/documents?limit=100").json()["items"]
    assert len(all_docs) == 3 and all(d["links"] for d in all_docs)


def test_photo_privacy_follows_the_person(owner, tree, member_factory) -> None:
    t = tree["id"]
    job = _upload(owner, t, _myheritage_zip()).json()
    _commit(owner, t, job["id"])
    people = _people(owner, t)
    sita_photos = _photos_of(owner, t, people["Sita Verma"])  # RESN confidential → admins only
    assert len(sita_photos) == 1 and sita_photos[0]["privacy_level"] == "PRIVATE_TREE_ADMINS"
    viewer = member_factory(["VIEWER"])
    visible = {d["id"] for d in viewer.get(f"/trees/{t}/documents?limit=100").json()["items"]}
    assert sita_photos[0]["id"] not in visible
    assert viewer.get(f"/trees/{t}/documents/{sita_photos[0]['id']}").status_code == 404
    # a shared photo is never less private than the most private person it shows
    shared = {d["id"]: d for d in _photos_of(owner, t, people["Ramesh Verma"])}
    arjun_level = {d["id"]: d["privacy_level"] for d in _photos_of(owner, t, people["Arjun Verma"])}
    for doc_id, d in shared.items():
        assert d["privacy_level"] == arjun_level[doc_id]


def test_gedzip_with_pointer_records_and_relative_paths(owner, tree) -> None:
    t = tree["id"]
    ged = "\n".join(
        [
            "0 HEAD",
            "1 GEDC",
            "2 VERS 7.0",
            "0 @I1@ INDI",
            "1 NAME Ram /Lal/",
            "1 OBJE @O1@",
            "0 @O1@ OBJE",
            "1 FILE media/Ram%20Lal%20portrait.jpg",
            "2 FORM image/jpeg",
            "2 TITL Ram Lal, 1950",
            "0 TRLR",
            "",
        ]
    )
    data = _zip({"gedcom.ged": ged.encode(), "media/Ram Lal portrait.jpg": RED, "other/unused.jpg": BLUE})
    job = _upload(owner, t, data, "family.gdz").json()
    assert job["report"]["photos"]["matched"] == 1
    _commit(owner, t, job["id"])
    photos = _photos_of(owner, t, _people(owner, t)["Ram Lal"])
    assert [d["title"] for d in photos] == ["Ram Lal, 1950"]
    # files no one references are never stored
    assert len(owner.get(f"/trees/{t}/documents").json()["items"]) == 1


def test_a_photo_with_malware_is_skipped_and_the_rest_imports(owner, tree) -> None:
    t = tree["id"]
    infected = GREEN + EICAR_SIGNATURE  # a valid PNG with the EICAR test string appended
    data = _myheritage_zip(**{"Verma Family Tree_Photos/P3_sita.png": infected})
    job = _upload(owner, t, data).json()
    done = _commit(owner, t, job["id"])
    result = done["commit_result"]
    assert result["counts"]["photos_rejected"] == 1
    assert any(
        w["code"] == "photo_rejected" and "p3_sita.png" in w["message"].lower() for w in result["warnings"]
    )
    assert result["counts"]["photos_imported"] == 2
    assert result["counts"]["people_created"] == 3
    actions = [e["action"] for e in owner.get(f"/trees/{t}/audit?limit=200").json()["items"]]
    assert "document.malware_rejected" in actions


def test_a_non_image_is_rejected_and_a_pdf_is_not_filed_as_a_photo(owner, tree) -> None:
    from tests.doc_fixtures import image_pdf

    t = tree["id"]
    ged = "\n".join(
        [
            "0 HEAD",
            "1 GEDC",
            "2 VERS 5.5.1",
            "0 @I1@ INDI",
            "1 NAME Ravi /Iyer/",
            "1 OBJE",
            "2 FILE certificate.pdf",
            "1 OBJE",
            "2 FILE evil.jpg",
            "0 TRLR",
            "",
        ]
    )
    pdf = image_pdf(Image.new("RGB", (200, 100), (255, 255, 255)))
    data = _zip({"tree.ged": ged.encode(), "certificate.pdf": pdf, "evil.jpg": b"<script>alert(1)</script>"})
    job = _upload(owner, t, data).json()
    result = _commit(owner, t, job["id"])["commit_result"]
    assert result["counts"]["photos_rejected"] == 1  # the HTML pretending to be a JPEG
    docs = _photos_of(owner, t, _people(owner, t)["Ravi Iyer"])
    assert [(d["category"], d["mime_type"]) for d in docs] == [("other", "application/pdf")]


def test_existing_photo_is_linked_not_duplicated(owner, tree) -> None:
    t = tree["id"]
    r = owner.post(
        f"/trees/{t}/documents",
        data={"category": "photo", "title": "Already here"},
        files={"file": ("x.jpg", BLUE, "image/jpeg")},
    )
    assert r.status_code == 201, r.text
    existing = r.json()["id"]
    job = _upload(owner, t, _myheritage_zip()).json()
    _commit(owner, t, job["id"])
    people = _people(owner, t)
    assert existing in {d["id"] for d in _photos_of(owner, t, people["Ramesh Verma"])}
    assert existing in {d["id"] for d in _photos_of(owner, t, people["Arjun Verma"])}
    blues = [d for d in owner.get(f"/trees/{t}/documents?limit=100").json()["items"] if d["id"] == existing]
    assert len(blues) == 1 and blues[0]["title"] == "Already here"  # kept as it was


def test_attached_people_get_no_photos(owner, tree) -> None:
    t = tree["id"]
    arjun = create_person(owner, t, "Arjun", "Verma", status="living")
    job = _upload(owner, t, _myheritage_zip()).json()
    result = _commit(owner, t, job["id"], {"@I1@": {"attach": arjun["id"]}})["commit_result"]
    assert result["counts"]["photos_skipped_attached"] == 2
    assert _photos_of(owner, t, arjun["id"]) == []


def test_plain_ged_with_photos_explains_how_to_include_them(owner, tree) -> None:
    job = _upload(owner, tree["id"], MYHERITAGE_GED.encode(), "tree.ged").json()
    assert job["report"]["photos"]["package"] is False
    assert any(w["code"] == "photos_not_in_upload" for w in job["report"]["warnings"])
    result = _commit(owner, tree["id"], job["id"])["commit_result"]
    assert "photos_imported" not in result["counts"]


def test_package_safety(owner, tree) -> None:
    t = tree["id"]

    def code(data: bytes) -> str:
        r = _upload(owner, t, data)
        assert r.status_code == 422, r.text
        return str(r.json()["error"]["code"])

    ged = MYHERITAGE_GED.encode()
    assert code(_zip({"a.ged": ged, "b.ged": ged})) == "multiple_gedcom"
    assert code(_zip({"photo.jpg": RED})) == "no_gedcom_in_package"
    assert code(b"PK\x03\x04 this is not really a zip") == "bad_package"
    # a zip bomb: tiny compressed, huge uncompressed
    assert code(_zip({"tree.ged": ged, "bomb.jpg": b"\0" * 5_000_000})) == "package_rejected"
    # names that try to escape are only ever used for matching; nothing is written to disk
    traversal = _zip(
        {"tree.ged": ged, "../../../../tmp/P1_64_48.jpg": RED, "nested.zip": _zip({"x.jpg": RED})}
    )
    job = _upload(owner, t, traversal).json()
    assert job["status"] == "ready" and job["report"]["photos"]["ignored_entries"] == 1


def test_package_limits_are_enforced(owner, tree, monkeypatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "max_gedcom_package_bytes", 1_000)
    r = _upload(owner, tree["id"], _myheritage_zip())
    assert r.status_code in (413, 422)
    assert r.json()["error"]["code"] in ("file_too_large", "package_too_large")


def test_photo_import_is_tree_scoped_and_needs_import_rights(owner, tree, make_client) -> None:
    t = tree["id"]
    contributor = make_client()
    contributor.register()
    join_tree(owner, contributor, t, ["CONTRIBUTOR"])
    assert _upload(contributor, t, _myheritage_zip()).status_code == 403
    stranger = make_client()
    stranger.register()
    assert _upload(stranger, t, _myheritage_zip()).status_code == 404
