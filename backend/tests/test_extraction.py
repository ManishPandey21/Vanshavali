"""OCR + extraction proposals and their review (ADR-0009): proposals never change canonical data."""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.models import LandParcel, Property, Source
from app.modules.extraction.masking import mask_aadhaar
from tests.doc_fixtures import (
    BIRTH_CERTIFICATE_LINES,
    KUNDLI_LINES,
    LAND_LINES,
    image_pdf,
    png_bytes,
    requires_tesseract,
    text_image,
    text_pdf,
    upload,
)
from tests.helpers import create_person, exact

EXISTING_BIRTH = {
    "date": exact(1985, 3, 12),
    "time": {"value": "04:17", "precision": "exact", "source": "hospital_record"},
    "place_as_recorded": "Lucknow",
}


def _person(owner, t):  # type: ignore[no-untyped-def]
    return create_person(owner, t, "Aarav", "Sharma", status="living", sex="male", birth=EXISTING_BIRTH)


def _proposals(client, t, doc_id):  # type: ignore[no-untyped-def]
    r = client.get(f"/trees/{t}/documents/{doc_id}/proposals")
    assert r.status_code == 200, r.text
    return {p["field"]: p for p in r.json()}


def _review(client, t, pid, action="accept", **kw):  # type: ignore[no-untyped-def]
    return client.post(f"/trees/{t}/extraction-proposals/{pid}/review", json={"action": action, **kw})


def _births(client, t, person_id):  # type: ignore[no-untyped-def]
    return client.get(f"/trees/{t}/people/{person_id}/events", params={"type": "birth"}).json()


def _upload_certificate(owner, t, person_id, data, filename="bc.png", mime="image/png"):  # type: ignore[no-untyped-def]
    r = upload(
        owner,
        t,
        data,
        filename=filename,
        mime=mime,
        category="birth_certificate",
        title="Birth certificate of Aarav",
        link_target_type="person",
        link_target_id=person_id,
    )
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------- unit: masking
def test_aadhaar_masking_patterns():
    assert mask_aadhaar("Aadhaar: 2345 6789 0123") == "Aadhaar: XXXX XXXX XXXX"
    assert mask_aadhaar("UID 234567890123.") == "UID XXXX XXXX XXXX."
    assert mask_aadhaar("आधार: २३४५-६७८९-०१२३") == "आधार: XXXX XXXX XXXX"
    assert mask_aadhaar("Reg B-1985-00432, phone 9876543210") == "Reg B-1985-00432, phone 9876543210"
    assert mask_aadhaar("1234 5678 9012") == "1234 5678 9012"  # Aadhaar never starts with 0/1


# ---------------------------------------------------------------- birth certificate via OCR
@requires_tesseract
def test_birth_certificate_image_produces_masked_proposals(owner, tree):
    t = tree["id"]
    person = _person(owner, t)
    doc = _upload_certificate(owner, t, person["id"], png_bytes(text_image(BIRTH_CERTIFICATE_LINES)))
    assert doc["storage_class"] == "VAULT"
    assert doc["ocr_status"] == "completed", doc
    assert doc["extraction_status"] == "completed"
    assert doc["pending_proposals"] >= 8

    ocr = owner.get(f"/trees/{t}/documents/{doc['id']}/ocr-text").json()
    assert ocr["engine"].startswith("tesseract")
    assert "Aarav Sharma" in ocr["text"]
    assert "XXXX XXXX XXXX" in ocr["text"]
    assert "2345" not in ocr["text"] and "0123" not in ocr["text"]

    props = _proposals(owner, t, doc["id"])
    assert props["name"]["proposed_value"] == "Aarav Sharma"
    assert props["date_of_birth"]["proposed_value"]["day"] == 14
    assert props["time_of_birth"]["proposed_value"]["value"].startswith("04:17")
    assert props["time_of_birth"]["proposed_value"]["source"] == "birth_certificate"
    assert props["sex"]["proposed_value"] == "male"
    assert "Lucknow" in props["place_of_birth"]["proposed_value"]
    assert props["father_name"]["proposed_value"] == "Rakesh Sharma"
    assert props["mother_name"]["proposed_value"] == "Sunita Sharma"
    assert props["registration_number"]["proposed_value"] == "B-1985-00432"
    assert props["registration_date"]["proposed_value"]["day"] == 20
    for p in props.values():
        assert p["status"] == "pending" and p["value_label"] == "extracted"
        assert p["subject_person_id"] == person["id"]
        assert p["extractor"] == "birth_certificate_rules" and p["extractor_version"]
        assert p["source_location"]["page"] == 1 and p["source_location"]["line"] >= 1
        assert 0 < p["confidence"] <= 1
    assert "2345" not in json.dumps(list(props.values()))

    # nothing canonical changed by extraction alone
    births = _births(owner, t, person["id"])
    assert len(births) == 1 and births[0]["date"]["day"] == 12


@requires_tesseract
def test_scanned_pdf_uses_tesseract(owner, tree):
    t = tree["id"]
    person = _person(owner, t)
    pdf = image_pdf(text_image(BIRTH_CERTIFICATE_LINES))
    doc = _upload_certificate(owner, t, person["id"], pdf, filename="bc.pdf", mime="application/pdf")
    assert doc["ocr_status"] == "completed"
    assert doc["preview_status"] == "completed"
    props = _proposals(owner, t, doc["id"])
    assert props["father_name"]["proposed_value"] == "Rakesh Sharma"
    assert props["father_name"]["engine"].startswith("tesseract")


def test_text_layer_pdf_needs_no_ocr_engine(owner, tree):
    t = tree["id"]
    person = _person(owner, t)
    doc = _upload_certificate(
        owner, t, person["id"], text_pdf(BIRTH_CERTIFICATE_LINES), filename="bc.pdf", mime="application/pdf"
    )
    props = _proposals(owner, t, doc["id"])
    assert props["date_of_birth"]["engine"].startswith("pdf-text-layer")
    assert props["registration_number"]["proposed_value"] == "B-1985-00432"
    ocr = owner.get(f"/trees/{t}/documents/{doc['id']}/ocr-text").json()
    assert "XXXX XXXX XXXX" in ocr["text"] and "6789" not in ocr["text"]


# ---------------------------------------------------------------- review
def test_accept_creates_competing_birth_with_citation_and_provenance(owner, tree):
    t = tree["id"]
    person = _person(owner, t)
    original = _births(owner, t, person["id"])[0]
    doc = _upload_certificate(
        owner, t, person["id"], text_pdf(BIRTH_CERTIFICATE_LINES), filename="bc.pdf", mime="application/pdf"
    )
    props = _proposals(owner, t, doc["id"])

    r = _review(owner, t, props["date_of_birth"]["id"], note="matches the scan")
    assert r.status_code == 200, r.text
    reviewed = r.json()
    assert reviewed["status"] == "accepted" and reviewed["value_label"] == "user-confirmed"
    assert reviewed["applied_target_type"] == "event"
    assert reviewed["reviewed_by"] == owner.user["id"]
    event_id = reviewed["applied_target_id"]

    births = {e["id"]: e for e in _births(owner, t, person["id"])}
    assert len(births) == 2
    assert births[original["id"]]["is_preferred"] is True  # never overwritten
    assert births[original["id"]]["date"]["day"] == 12
    new = births[event_id]
    assert new["is_preferred"] is False
    assert new["date"]["day"] == 14
    assert new["evidence_status"] == "SOURCED"
    prov = new["provenance"]
    assert prov["origin"] == "ocr"
    assert prov["algorithm_or_model"] == "birth_certificate_rules"
    assert prov["source_document_id"] == doc["id"]
    assert prov["source_location"].startswith("page 1, line")
    assert prov["confirmed_by"] == owner.user["id"]
    assert prov["extracted_at"] and prov["confirmed_at"]

    cites = owner.get(f"/trees/{t}/citations", params={"target_type": "event", "target_id": event_id}).json()
    assert len(cites) == 1
    src = owner.get(f"/trees/{t}/sources/{cites[0]['source_id']}").json()
    assert src["document_id"] == doc["id"] and src["source_type"] == "certificate"

    # time and place join the same certificate event rather than creating more events
    assert _review(owner, t, props["time_of_birth"]["id"]).json()["applied_target_id"] == event_id
    assert _review(owner, t, props["place_of_birth"]["id"]).json()["applied_target_id"] == event_id
    births = {e["id"]: e for e in _births(owner, t, person["id"])}
    assert len(births) == 2
    assert births[event_id]["time"]["value"].startswith("04:17")
    assert births[event_id]["time"]["precision"] == "document_recorded"
    assert births[event_id]["place_as_recorded"] == "District Hospital, Lucknow"
    assert births[original["id"]]["place_as_recorded"] == "Lucknow"

    # re-reviewing is refused
    r = _review(owner, t, props["date_of_birth"]["id"], action="reject")
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_reviewed"

    # registration number goes to the document's source record
    r = _review(owner, t, props["registration_number"]["id"])
    assert r.json()["applied_target_type"] == "source"
    assert (
        owner.get(f"/trees/{t}/sources/{r.json()['applied_target_id']}").json()["record_number"]
        == "B-1985-00432"
    )

    # the conflict is surfaced, not resolved
    conflicts = owner.get(f"/trees/{t}/people/{person['id']}/birth-conflicts").json()
    assert conflicts["has_conflicts"] is True
    assert [c["field"] for c in conflicts["conflicts"]] == ["date"]


def test_name_and_parent_names_become_new_claims_only(owner, tree):
    t = tree["id"]
    person = _person(owner, t)
    doc = _upload_certificate(
        owner, t, person["id"], text_pdf(BIRTH_CERTIFICATE_LINES), filename="bc.pdf", mime="application/pdf"
    )
    props = _proposals(owner, t, doc["id"])
    r = _review(owner, t, props["name"]["id"])
    assert r.status_code == 200, r.text
    p = owner.get(f"/trees/{t}/people/{person['id']}").json()
    assert p["display_name"] == "Aarav Sharma"
    names = {n["id"]: n for n in p["names"]}
    new_name = names[r.json()["applied_target_id"]]
    assert new_name["full_name_as_recorded"] == "Aarav Sharma"
    assert new_name["is_preferred"] is False and new_name["type"] == "birth"
    assert new_name["evidence_status"] == "SOURCED" and new_name["provenance"]["origin"] == "ocr"

    # edit before accepting (OCR mistakes are corrected by the reviewer)
    r = _review(owner, t, props["mother_name"]["id"], action="edit", value="Sunita Devi Sharma")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "edited" and r.json()["final_value"] == "Sunita Devi Sharma"
    heritage = owner.get(f"/trees/{t}/people/{person['id']}/heritage").json()
    values = [
        a["value_text"]
        for attr in heritage["attributes"]
        if attr["attribute"] == "recorded_parent_name"
        for a in ([attr["preferred"]] if attr["preferred"] else []) + attr["alternatives"]
    ]
    assert values == ["Sunita Devi Sharma"]
    # parents are never auto-linked as people
    fam = owner.get(f"/trees/{t}/people/{person['id']}/family").json()
    assert fam["parents"] == []

    # reject leaves data untouched
    r = _review(owner, t, props["father_name"]["id"], action="reject", note="illegible")
    assert r.status_code == 200 and r.json()["status"] == "rejected" and r.json()["applied_target_id"] is None
    heritage2 = owner.get(f"/trees/{t}/people/{person['id']}/heritage").json()
    assert heritage2 == heritage

    # sex matches the existing value: accepted without change; a conflicting edit is refused
    assert _review(owner, t, props["sex"]["id"]).status_code == 200
    doc2 = _upload_certificate(
        owner,
        t,
        person["id"],
        text_pdf([*BIRTH_CERTIFICATE_LINES[:3], "Sex: Female"]),
        filename="bc2.pdf",
        mime="application/pdf",
    )
    r = _review(owner, t, _proposals(owner, t, doc2["id"])["sex"]["id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflicting_value"
    assert owner.get(f"/trees/{t}/people/{person['id']}").json()["sex_at_birth"] == "male"


def test_invalid_edit_value_rejected(owner, tree):
    t = tree["id"]
    person = _person(owner, t)
    doc = _upload_certificate(
        owner, t, person["id"], text_pdf(BIRTH_CERTIFICATE_LINES), filename="bc.pdf", mime="application/pdf"
    )
    props = _proposals(owner, t, doc["id"])
    r = _review(owner, t, props["date_of_birth"]["id"], action="edit", value="sometime in spring")
    assert r.status_code == 422
    r = _review(owner, t, props["date_of_birth"]["id"], action="edit", value="15/03/1985")
    assert r.status_code == 200 and r.json()["final_value"]["day"] == 15
    assert _review(owner, t, props["name"]["id"], action="edit").status_code == 422  # edit needs a value


def test_review_permissions(owner, tree, member_factory):
    t = tree["id"]
    person = _person(owner, t)
    doc = _upload_certificate(
        owner, t, person["id"], text_pdf(BIRTH_CERTIFICATE_LINES), filename="bc.pdf", mime="application/pdf"
    )
    pid = _proposals(owner, t, doc["id"])["date_of_birth"]["id"]
    viewer = member_factory(["VIEWER"])
    assert _review(viewer, t, pid).status_code == 403
    contributor = member_factory(["CONTRIBUTOR"])  # may review, but has no vault access
    assert _review(contributor, t, pid).status_code == 404
    owner.patch(f"/trees/{t}/documents/{doc['id']}", json={"privacy_level": "TREE_MEMBERS"})
    assert _review(contributor, t, pid).status_code == 403
    custodian = member_factory(["DOCUMENT_CUSTODIAN"])  # vault access, but no person write
    assert _review(custodian, t, pid).status_code == 403
    assert _review(owner, t, pid).status_code == 200
    assert _review(owner, t, str(uuid.uuid4())).status_code == 404


def test_proposal_without_linked_person_needs_target(owner, tree):
    t = tree["id"]
    person = _person(owner, t)
    r = upload(
        owner,
        t,
        text_pdf(BIRTH_CERTIFICATE_LINES),
        filename="bc.pdf",
        mime="application/pdf",
        category="birth_certificate",
    )
    doc = r.json()
    props = _proposals(owner, t, doc["id"])
    assert props["date_of_birth"]["subject_person_id"] is None
    r = _review(owner, t, props["date_of_birth"]["id"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "target_person_required"
    r = _review(owner, t, props["date_of_birth"]["id"], target_person_id=person["id"])
    assert r.status_code == 200, r.text
    # confirming a fact links the document to the person
    links = owner.get(f"/trees/{t}/documents/{doc['id']}").json()["links"]
    assert [ln["target_id"] for ln in links] == [person["id"]]


def test_reprocess_requires_manage_and_keeps_reviewed(owner, tree, member_factory):
    t = tree["id"]
    person = _person(owner, t)
    doc = _upload_certificate(
        owner, t, person["id"], text_pdf(BIRTH_CERTIFICATE_LINES), filename="bc.pdf", mime="application/pdf"
    )
    props = _proposals(owner, t, doc["id"])
    total = len(props)
    _review(owner, t, props["name"]["id"], action="reject")
    contributor = member_factory(["CONTRIBUTOR"])
    owner.patch(f"/trees/{t}/documents/{doc['id']}", json={"privacy_level": "TREE_MEMBERS"})
    assert contributor.post(f"/trees/{t}/documents/{doc['id']}/reprocess").status_code == 403
    r = owner.post(f"/trees/{t}/documents/{doc['id']}/reprocess")
    assert r.status_code == 200, r.text
    assert r.json()["ocr_status"] == "completed" and r.json()["pending_proposals"] == total - 1
    all_props = owner.get(f"/trees/{t}/documents/{doc['id']}/proposals").json()
    assert len(all_props) == total
    assert [p["status"] for p in all_props if p["field"] == "name"] == ["rejected"]


# ---------------------------------------------------------------- kundli
def test_kundli_extraction_creates_uploaded_chart_and_time_conflict(owner, tree):
    t = tree["id"]
    person = _person(owner, t)
    r = upload(
        owner,
        t,
        text_pdf(KUNDLI_LINES),
        filename="kundli.pdf",
        mime="application/pdf",
        category="kundli",
        title="Janma kundli",
        link_target_type="person",
        link_target_id=person["id"],
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["storage_class"] == "VAULT"
    props = _proposals(owner, t, doc["id"])
    assert props["nakshatra"]["proposed_value"] == "Rohini"
    assert props["nakshatra_pada"]["proposed_value"] == 2
    assert props["rashi"]["proposed_value"] == "Vrishabha"
    assert props["lagna"]["proposed_value"] == "Makara"
    assert props["tithi"]["proposed_value"] == "Ekadashi"
    assert props["paksha"]["proposed_value"] == "Shukla"
    assert props["ayanamsha"]["proposed_value"] == "Lahiri"
    assert props["chart_birth_time"]["proposed_value"]["source"] == "kundli"

    profile_ids = set()
    for field in (
        "chart_birth_date",
        "chart_birth_time",
        "chart_birth_place",
        "nakshatra",
        "nakshatra_pada",
        "rashi",
    ):
        r = _review(owner, t, props[field]["id"])
        assert r.status_code == 200, (field, r.text)
        assert r.json()["applied_target_type"] == "astrology_profile"
        profile_ids.add(r.json()["applied_target_id"])
    assert len(profile_ids) == 1
    profiles = owner.get(f"/trees/{t}/people/{person['id']}/astrology").json()
    assert len(profiles) == 1
    prof = profiles[0]
    assert prof["provenance_kind"] == "uploaded_chart" and prof["document_id"] == doc["id"]
    assert prof["nakshatra"] == "Rohini" and prof["nakshatra_pada"] == 2 and prof["rashi"] == "Vrishabha"
    assert prof["evidence_status"] == "SOURCED" and prof["provenance"]["origin"] == "ocr"
    assert prof["citation_count"] == 1

    conflicts = owner.get(f"/trees/{t}/people/{person['id']}/birth-conflicts").json()
    assert conflicts["has_conflicts"] is True
    by_field = {c["field"]: c for c in conflicts["conflicts"]}
    assert set(by_field) == {"time"}  # 04:17 (hospital) vs 04:45 (kundli); same date and city
    values = {v["claim_type"]: v["value"] for v in by_field["time"]["values"]}
    assert values["event"].startswith("04:17") and values["astrology_profile"].startswith("04:45")
    claims = {c["claim_type"]: c for c in conflicts["claims"]}
    assert claims["astrology_profile"]["sources"][0]["document_id"] == doc["id"]
    assert claims["event"]["is_preferred"] is True  # both retained; nothing changed
    assert len(_births(owner, t, person["id"])) == 1


# ---------------------------------------------------------------- land records
def _property(tree_id: str, owner_user_id: str) -> str:
    with get_sessionmaker()() as db:
        p = Property(
            tree_id=uuid.UUID(tree_id),
            property_type="agricultural_land",
            display_name="Rampur fields",
            created_by=uuid.UUID(owner_user_id),
        )
        db.add(p)
        db.commit()
        return str(p.id)


def test_land_record_extraction_fills_parcel(owner, tree, member_factory):
    t = tree["id"]
    prop_id = _property(t, owner.user["id"])
    r = upload(
        owner,
        t,
        text_pdf(LAND_LINES),
        filename="khatauni.pdf",
        mime="application/pdf",
        category="khatauni",
        title="Khatauni 2001",
        link_target_type="property",
        link_target_id=prop_id,
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    props = _proposals(owner, t, doc["id"])
    assert props["khasra_or_gata_number"]["proposed_value"] == "456/2"
    assert props["khata_number"]["proposed_value"] == "00123"
    assert props["village"]["proposed_value"] == "Rampur"
    assert props["area"]["proposed_value"]["unit"] == "hectare"
    assert props["holder_name"]["proposed_value"] == "Ram Prasad"
    assert props["holder_relative_name"]["proposed_value"] == "Shiv Prasad"
    assert props["mutation_number"]["proposed_value"] == "77"
    assert props["khasra_or_gata_number"]["subject_property_id"] == prop_id

    for f in (
        "khasra_or_gata_number",
        "khata_number",
        "village",
        "district",
        "area",
        "holder_name",
        "mutation_date",
    ):
        r = _review(owner, t, props[f]["id"])
        assert r.status_code == 200, (f, r.text)
        assert r.json()["applied_target_type"] == "land_parcel"
    with get_sessionmaker()() as db:
        parcels = list(db.scalars(select(LandParcel).where(LandParcel.property_id == uuid.UUID(prop_id))))
        assert len(parcels) == 1
        parcel = parcels[0]
        assert parcel.khasra_or_gata_number == "456/2" and parcel.khata_number == "00123"
        assert parcel.village == "Rampur" and parcel.district == "Gorakhpur"
        assert float(parcel.area) == 1.25 and parcel.area_unit == "hectare"
        assert parcel.extra_identifiers["recorded_holders"] == ["Ram Prasad"]
        assert parcel.extra_identifiers["mutation_date"]["year"] == 2001
        assert parcel.prov_origin == "ocr" and str(parcel.prov_source_document_id) == doc["id"]
        src = db.scalar(select(Source).where(Source.document_id == uuid.UUID(doc["id"])))
        assert src is not None and src.source_type == "land_record"

    # a contributor may read property records but not their vault content
    contributor = member_factory(["CONTRIBUTOR"])
    owner.patch(f"/trees/{t}/documents/{doc['id']}", json={"privacy_level": "TREE_MEMBERS"})
    assert _review(contributor, t, props["tehsil_taluk"]["id"]).status_code == 403
    # property custodians review land records (vault access limited to property categories)
    custodian = member_factory(["PROPERTY_CUSTODIAN"])
    assert _review(custodian, t, props["tehsil_taluk"]["id"]).status_code == 200
    assert "khatauni_number" not in props  # a heading is not an identifier
    # a different value for an already-filled column is never overwritten
    doc2 = upload(
        owner,
        t,
        text_pdf(["KHATAUNI", "Village: Sitapur"]),
        filename="k2.pdf",
        mime="application/pdf",
        category="khatauni",
        link_target_type="property",
        link_target_id=prop_id,
    ).json()
    r = _review(owner, t, _proposals(owner, t, doc2["id"])["village"]["id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflicting_value"


@pytest.mark.parametrize("category", ["photo", "letter"])
def test_non_extraction_categories_are_not_ocrd(owner, tree, category):
    doc = upload(
        owner, tree["id"], text_pdf(["Hello"]), filename="a.pdf", mime="application/pdf", category=category
    ).json()
    assert doc["ocr_status"] == "not_requested" and doc["extraction_status"] == "not_requested"
    assert owner.get(f"/trees/{tree['id']}/documents/{doc['id']}/proposals").json() == []


# ---------------------------------------------------------------- unit: extractors (no OCR engine)
def _ocr(lines: list[str]):  # type: ignore[no-untyped-def]
    from app.modules.extraction.ocr import OcrLine, OcrPage, OcrResult

    return OcrResult([OcrPage(1, [OcrLine(i + 1, ln, 0.9) for i, ln in enumerate(lines)])], "test", "0")


def test_hindi_labels_are_extracted():
    from app.modules.extraction.extractors import BIRTH_CERTIFICATE, KUNDLI, LAND_RECORD

    bc = {
        d.field: d.value
        for d in BIRTH_CERTIFICATE.extract(
            _ocr(
                [
                    "जन्म प्रमाण पत्र",
                    "बच्चे का नाम: आरव शर्मा",
                    "लिंग: पुरुष",
                    "जन्म तिथि: १४/०३/१९८५",
                    "जन्म का स्थान: लखनऊ",
                    "पिता का नाम: राकेश शर्मा",
                    "माता का नाम: सुनीता शर्मा",
                    "पंजीकरण संख्या: ५४३२/१९८५",
                    "आधार: २३४५ ६७८९ ०१२३",
                ]
            )
        )
    }
    assert bc["name"] == "आरव शर्मा"
    assert bc["sex"] == "male"
    assert (bc["date_of_birth"]["year"], bc["date_of_birth"]["month"], bc["date_of_birth"]["day"]) == (
        1985,
        3,
        14,
    )
    assert bc["place_of_birth"] == "लखनऊ"
    assert bc["father_name"] == "राकेश शर्मा" and bc["mother_name"] == "सुनीता शर्मा"
    assert bc["registration_number"] == "5432/1985"
    assert "२३४५" not in str(bc)

    k = {
        d.field: d.value
        for d in KUNDLI.extract(
            _ocr(
                [
                    "जन्म कुंडली",
                    "जन्म समय: 04:45 प्रातः",
                    "नक्षत्र: पूर्वाषाढ़ा चरण: 4",
                    "राशि: धनु   लग्न: मीन",
                    "तिथि: कृष्ण पक्ष अमावस्या",
                ]
            )
        )
    }
    assert k["nakshatra"] == "Purva Ashadha" and k["nakshatra_pada"] == 4
    assert k["rashi"] == "Dhanu" and k["lagna"] == "Meena"
    assert k["tithi"] == "Amavasya" and k["paksha"] == "Krishna"
    assert k["chart_birth_time"]["value"].startswith("04:45")

    land = {
        d.field: d.value
        for d in LAND_RECORD.extract(
            _ocr(
                [
                    "ग्राम: रामपुर   तहसील: सदर   जनपद: गोरखपुर",
                    "खाता संख्या: 00123   खसरा संख्या: 456/2",
                    "रकबा: 0.500 हेक्टेयर",
                    "खातेदार का नाम: राम प्रसाद   पिता का नाम: शिव प्रसाद",
                ]
            )
        )
    }
    assert land["village"] == "रामपुर" and land["district"] == "गोरखपुर"
    assert land["khata_number"] == "00123" and land["khasra_or_gata_number"] == "456/2"
    assert land["area"]["value"] == 0.5 and land["area"]["unit"] == "hectare"
    assert land["holder_name"] == "राम प्रसाद" and land["holder_relative_name"] == "शिव प्रसाद"


def test_no_label_no_proposal():
    from app.modules.extraction.extractors import BIRTH_CERTIFICATE

    drafts = BIRTH_CERTIFICATE.extract(
        _ocr(["Name of Hospital: City Care", "Sexton Road", "Some unrelated text"])
    )
    assert drafts == []
