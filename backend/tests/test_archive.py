"""Full archive export (PRS §43): contents, checksums, privacy view, vault opt-in."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

from tests.doc_fixtures import png_bytes, text_image, upload
from tests.helpers import create_person, exact


def _zip(resp) -> zipfile.ZipFile:  # type: ignore[no-untyped-def]
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/zip"
    return zipfile.ZipFile(io.BytesIO(resp.content))


def test_archive_contents_checksums_and_privacy(owner, tree, member_factory):
    t = tree["id"]
    create_person(owner, t, "Ancestor", birth={"date": exact(1900, 1, 1)})
    create_person(owner, t, "LivingPriya", status="living", birth={"date": exact(1990, 5, 5)})
    photo = png_bytes(text_image(["Family photo"]))
    cert = png_bytes(text_image(["Birth certificate", "Name: Test"]))
    assert upload(owner, t, photo, filename="photo.png", category="photo", title="Photo").status_code == 201
    assert (
        upload(owner, t, cert, filename="cert.png", category="birth_certificate", title="Cert").status_code
        == 201
    )

    z = _zip(owner.get(f"/trees/{t}/exports/archive"))
    names = z.namelist()
    for required in (
        "manifest.json",
        "genealogy/tree.ged",
        "genealogy/canonical-data.json",
        "documents/index.json",
        "source-index.csv",
        "checksums.sha256",
        "README.txt",
        "property/properties.json",
    ):
        assert f"family-export/{required}" in names
    manifest = json.loads(z.read("family-export/manifest.json"))
    for f in manifest["files"]:
        assert hashlib.sha256(z.read(f"family-export/{f['path']}")).hexdigest() == f["sha256"]
    canonical = z.read("family-export/genealogy/canonical-data.json").decode()
    assert "Ancestor" in canonical and "LivingPriya" not in canonical  # living excluded by default
    index = json.loads(z.read("family-export/documents/index.json"))
    by_cat = {d["category"]: d for d in index}
    assert by_cat["photo"]["included"] is True
    assert by_cat["birth_certificate"]["included"] is False  # vault needs explicit opt-in

    z2 = _zip(
        owner.get(
            f"/trees/{t}/exports/archive", params={"include_vault_documents": True, "exclude_living": False}
        )
    )
    index2 = {d["category"]: d for d in json.loads(z2.read("family-export/documents/index.json"))}
    assert index2["birth_certificate"]["included"] is True
    assert z2.read(f"family-export/{index2['birth_certificate']['path']}") == cert
    assert "LivingPriya" in z2.read("family-export/genealogy/canonical-data.json").decode()

    contributor = member_factory(["CONTRIBUTOR"])
    assert (
        contributor.get(f"/trees/{t}/exports/archive", params={"include_vault_documents": True}).status_code
        == 403
    )
    zc = _zip(contributor.get(f"/trees/{t}/exports/archive"))
    assert all(
        d["category"] != "birth_certificate" or not d["included"]
        for d in json.loads(zc.read("family-export/documents/index.json"))
    )
    assert "family-export/property/properties.json" in zc.namelist()  # contributors have property.read
    viewer = member_factory(["VIEWER"])
    assert viewer.get(f"/trees/{t}/exports/archive").status_code == 403
    events = owner.get(f"/trees/{t}/audit", params={"action": "archive."}).json()["items"]
    assert len(events) == 3  # two owner exports + one contributor export; refused ones are not logged
