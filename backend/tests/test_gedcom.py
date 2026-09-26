"""GEDCOM 5.5.1 / 7.0 import, export and round-trip (PRS §22; ADR-0008)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.storage import get_store
from app.models import (
    Assertion,
    AstrologyProfile,
    AuditEvent,
    Citation,
    Event,
    EventParticipant,
    GedcomExtension,
    ImportJob,
    NameRecord,
    Person,
    Relationship,
)
from app.modules.gedcom import mapping, parser
from app.modules.gedcom.gdate import format_date, parse_date
from tests.conftest import new_tree, owner_session
from tests.helpers import create_person, exact

BASE = "https://vanshavali.app/gedcom/ext/v1/"

G7 = f"""0 HEAD
1 GEDC
2 VERS 7.0
1 SCHMA
2 TAG _IND_GOTRA {BASE}gotra
2 TAG _CLAN {BASE}kuladevata
2 TAG _XYZ https://example.org/xyz
1 SOUR TestApp
0 @I1@ INDI
1 NAME Ramesh /Sharma/
2 GIVN Ramesh
2 SURN Sharma
2 TRAN रमेश /शर्मा/
3 LANG hi-Deva
2 TRAN ரமேஷ் /சர்மா/
3 LANG ta
1 SEX M
1 BIRT
2 DATE ABT 1890
2 PLAC Varanasi, Uttar Pradesh, India
2 SOUR @S1@
3 PAGE p. 12
1 DEAT
2 DATE BET 1950 AND 1955
1 _IND_GOTRA Kashyapa
1 _CLAN Vindhyavasini
1 _IND_NAKSHATRA Rohini
1 _IND_NAKSHATRA_PADA 2
1 _XYZ custom value
2 _XYZ_DETAIL nested
1 FAMS @F1@
0 @I2@ INDI
1 NAME Sita /Sharma/
1 SEX F
1 BIRT
2 DATE 12 MAR 1895
3 TIME 06:30
2 _IND_BIRTH_TIME_CONF approximate kundli
1 DEAT Y
1 FAMS @F1@
0 @I3@ INDI
1 NAME Mohan /Sharma/
1 SEX M
1 BIRT
2 DATE BET 1920 AND 1922
1 DEAT
2 DATE BEF 1990
1 NOTE Adopted from his maternal uncle's family.
2 CONT Recorded by the Panda at Haridwar.
1 FAMC @F1@
2 PEDI ADOPTED
0 @I4@ INDI
1 NAME Gita /Sharma/
1 SEX F
1 BIRT
2 DATE 5 JAN 1925
1 BURI
2 PLAC Manikarnika Ghat
1 FAMC @F1@
2 PEDI BIRTH
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
1 CHIL @I4@
1 MARR
2 DATE 1915
0 @S1@ SOUR
1 TITL Varanasi Panda Bahi
0 TRLR
"""

G551 = (
    b"0 HEAD\r\n1 SOUR PAF\r\n1 GEDC\r\n2 VERS 5.5.1\r\n2 FORM LINEAGE-LINKED\r\n1 CHAR ANSI\r\n"
    b"0 @I1@ INDI\r\n1 NAME Jos\xe9 /Fern\xe1ndez/\r\n1 SEX M\r\n1 BIRT\r\n"
    b"2 DATE @#DJULIAN@ 12 JAN 1700\r\n1 NOTE This is a long note that is spl\r\n2 CONC it across lines.\r\n"
    b"2 CONT Second line.\r\n1 FAMC @F1@\r\n2 PEDI adopted\r\n"
    b"0 @I2@ INDI\r\n1 NAME Maria /Fern\xe1ndez/\r\n1 SEX F\r\n1 FAMS @F1@\r\n"
    b"0 @F1@ FAM\r\n1 WIFE @I2@\r\n1 CHIL @I1@\r\n0 TRLR\r\n"
)


def _db():  # type: ignore[no-untyped-def]
    return owner_session()


def _upload(client: Any, tree_id: str, content: bytes | str, name: str = "family.ged") -> Any:
    data = content.encode("utf-8") if isinstance(content, str) else content
    return client.post(f"/trees/{tree_id}/imports", files={"file": (name, data, "application/octet-stream")})


def _import(client: Any, tree_id: str, content: bytes | str, decisions: dict | None = None) -> dict:
    r = _upload(client, tree_id, content)
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["status"] == "ready", job
    c = client.post(f"/trees/{tree_id}/imports/{job['id']}/commit", json={"decisions": decisions or {}})
    assert c.status_code == 200, c.text
    return c.json()


def _people(tree_id: str) -> dict[str, Person]:
    with _db() as db:
        return {
            p.preferred_display_name: p
            for p in db.scalars(
                select(Person).where(Person.tree_id == uuid.UUID(tree_id), Person.deleted_at.is_(None))
            )
        }


def _export(client: Any, tree_id: str, **params: Any) -> Any:
    q = "&".join(f"{k}={str(v).lower()}" for k, v in params.items())
    return client.get(f"/trees/{tree_id}/exports/gedcom" + (f"?{q}" if q else ""))


# ------------------------------------------------------------------------------ parser
def test_parse_gedcom7_sample() -> None:
    result = parser.parse(G7.encode("utf-8"))
    assert result.version == "7.0" and result.encoding == "UTF-8"
    assert result.errors == []
    staged, report = mapping.stage(result)
    assert report["counts"]["people"] == 4
    assert report["counts"]["families"] == 1
    assert report["counts"]["sources"] == 1 and report["counts"]["citations"] == 1
    assert report["unknown_extension_tags"] == {"_XYZ": 1}
    # _CLAN is ours by SCHMA URI, not by tag name
    assert report["extension_tags"]["_IND_KULADEVATA"] == 1
    ramesh = staged["individuals"][0]
    by_script = {n["script"]: n for n in ramesh["names"]}
    assert by_script["Deva"]["given"] == "रमेश" and by_script["Deva"]["language"] == "hi"
    assert by_script["Taml"]["surname"] == "சர்மா" and by_script["Taml"]["language"] == "ta"
    assert [n["is_preferred"] for n in ramesh["names"]] == [True, False, False]
    birth, death = ramesh["events"]
    assert birth["date"]["precision"] == "circa" and birth["date"]["year"] == 1890
    assert birth["date"].get("month") is None  # never invented
    assert death["date"]["precision"] == "range" and death["date"]["end_year"] == 1955
    assert {h["attribute"]: h["value"] for h in ramesh["heritage"]} == {
        "gotra": "Kashyapa",
        "kuladevata": "Vindhyavasini",
    }
    assert ramesh["astrology"] == {"nakshatra": "Rohini", "nakshatra_pada": 2}
    assert ramesh["preserved"][0]["tag"] == "_XYZ"
    assert "1 _XYZ_DETAIL nested" in ramesh["preserved"][0]["payload"]
    sita = staged["individuals"][1]
    assert sita["events"][0]["time"]["precision"] == "approximate"
    assert sita["events"][0]["time"]["source"] == "kundli"
    mohan = staged["individuals"][2]
    assert mohan["famc"][0]["pedi"] == "ADOPTED"
    assert mohan["notes"] == ["Adopted from his maternal uncle's family.\nRecorded by the Panda at Haridwar."]
    assert staged["individuals"][3]["profile_status"] == "deceased"  # burial is death evidence


def test_parse_gedcom551_ansi_and_conc() -> None:
    result = parser.parse(G551)
    assert result.version == "5.5.1"
    assert result.encoding == "CP1252"
    assert any(i.code == "encoding_legacy" for i in result.issues)
    staged, report = mapping.stage(result)
    jose = staged["individuals"][0]
    assert jose["display_name"] == "José Fernández"
    assert jose["notes"] == ["This is a long note that is split across lines.\nSecond line."]
    assert jose["events"][0]["date"]["calendar"] == "julian"
    assert jose["famc"][0]["pedi"] == "ADOPTED"
    assert staged["families"][0]["wife"] == "@I2@"
    assert any(w["code"] == "encoding_legacy" for w in report["warnings"])


def test_parser_reports_errors_with_line_numbers_without_crashing() -> None:
    bad = b"0 HEAD\n1 GEDC\n2 VERS 7.0\n0 @I1@ INDI\n1 NAME A /B/\nthis is not gedcom\n3 DATE 1900\n0 TRLR\n"
    result = parser.parse(bad)
    codes = {(i.code, i.line) for i in result.errors}
    assert ("syntax", 6) in codes and ("level_jump", 7) in codes
    _staged, report = mapping.stage(result)
    assert report["counts"]["people"] == 1 and len(report["errors"]) == 2


def test_record_cap_and_ansel() -> None:
    many = "0 HEAD\n1 GEDC\n2 VERS 7.0\n" + "".join(f"0 @I{i}@ INDI\n" for i in range(10)) + "0 TRLR\n"
    result = parser.parse(many.encode(), max_records=5)
    assert result.truncated and any(i.code == "too_many_records" for i in result.errors)
    text, bad = parser.decode_ansel(b"Jos\xe2e M\xe8uller \xa5lfred")
    assert text == "José Müller Ælfred" and bad == 0
    ansel = parser.parse(
        b"0 HEAD\n1 GEDC\n2 VERS 5.5\n1 CHAR ANSEL\n0 @I1@ INDI\n1 NAME Jos\xe2e /X/\n0 TRLR\n"
    )
    assert ansel.encoding == "ANSEL"
    staged, _ = mapping.stage(ansel)
    assert staged["individuals"][0]["display_name"] == "José X"


def test_date_grammar_round_trip() -> None:
    for payload in ("ABT 1890", "EST 1890", "BEF 3 MAR 1901", "AFT 1920", "BET 1920 AND 1922",
                    "FROM 1901 TO 1905", "JULIAN 12 JAN 1700", "12 MAR 1895", "MAR 1895"):  # fmt: skip
        d, warns = parse_date(payload)
        assert d is not None and warns == []
        assert format_date(d) == (payload, None), payload
    d, _ = parse_date("31 FEB 1900")
    assert d is not None and d["precision"] == "day_unknown" and "day" not in d
    vs = {"calendar": "vikram_samvat", "precision": "year_only", "year": 2045, "original_text": "Samvat 2045"}
    assert format_date(vs) == ("", "Samvat 2045")
    d, _ = parse_date("", "Samvat 2045")
    assert d == {"precision": "unknown", "calendar": "gregorian", "original_text": "Samvat 2045"}


# ------------------------------------------------------------------------------ import API
def test_upload_stores_original_and_reports(owner, tree) -> None:
    t = tree["id"]
    r = _upload(owner, t, G7)
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["status"] == "ready"
    assert job["detected_version"] == "7.0" and job["detected_encoding"] == "UTF-8"
    assert job["counts"]["people"] == 4
    assert job["report"]["unknown_extension_tags"] == {"_XYZ": 1}
    assert job["preview_total"] == 4 and job["preview"][0]["xref"] == "@I1@"
    assert job["preview"][0]["heritage"] == ["gotra", "kuladevata"]
    with _db() as db:
        row = db.get(ImportJob, uuid.UUID(job["id"]))
        assert row is not None and row.original_storage_key == f"SYSTEM/{t}/imports/{job['id']}/original.ged"
        assert get_store().get(row.original_storage_key) == G7.encode("utf-8")
    listed = owner.get(f"/trees/{t}/imports").json()
    assert [j["id"] for j in listed] == [job["id"]]


def test_upload_validation(owner, tree, member_factory, monkeypatch) -> None:
    t = tree["id"]
    assert _upload(owner, t, b"\x89PNG\r\n\x1a\n...").status_code == 422
    contributor = member_factory(["CONTRIBUTOR"])
    assert _upload(contributor, t, G7).status_code == 403  # GEDCOM_IMPORT is admin-only
    assert contributor.get(f"/trees/{t}/imports").status_code == 403
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 100)
    r = _upload(owner, t, G7)
    assert r.status_code == 413 and r.json()["error"]["code"] == "file_too_large"


def test_duplicate_detection_finds_existing_person(owner, tree) -> None:
    t = tree["id"]
    existing = create_person(
        owner, t, "Ramesh", "Sharma", sex="male", birth={"date": {"precision": "year_only", "year": 1891}}
    )
    create_person(owner, t, "Unrelated", "Person")
    job = _upload(owner, t, G7).json()
    ramesh = next(p for p in job["preview"] if p["xref"] == "@I1@")
    assert [d["person"]["id"] for d in ramesh["duplicates"]] == [existing["id"]]
    reasons = " ".join(ramesh["duplicates"][0]["reasons"])
    assert "similarity" in reasons and "birth years" in reasons
    gita = next(p for p in job["preview"] if p["xref"] == "@I4@")
    assert gita["duplicates"] == []


def test_commit_decisions_create_skip_attach(owner, tree) -> None:
    t = tree["id"]
    existing = create_person(
        owner,
        t,
        "Ramesh",
        "Sharma",
        sex="male",
        birth={"date": exact(1890, 2, 1), "place_as_recorded": "Kashi"},
    )
    before = owner.get(f"/trees/{t}/people/{existing['id']}").json()
    job = _upload(owner, t, G7).json()
    result = owner.post(
        f"/trees/{t}/imports/{job['id']}/commit",
        json={"decisions": {"@I1@": {"attach": existing["id"]}, "@I4@": "skip"}},
    )
    assert result.status_code == 200, result.text
    counts = result.json()["commit_result"]["counts"]
    assert counts["people_created"] == 2 and counts["people_attached"] == 1 and counts["people_skipped"] == 1
    people = _people(t)
    assert set(people) == {"Ramesh Sharma", "Sita Sharma", "Mohan Sharma"}  # Gita skipped
    after = owner.get(f"/trees/{t}/people/{existing['id']}").json()
    # existing person unchanged: same display name, sex, status, preferred name and preferred birth
    for field in ("display_name", "sex_at_birth", "profile_status", "privacy_level"):
        assert after[field] == before[field]
    assert after["birth"]["date"] == before["birth"]["date"]
    pid = uuid.UUID(existing["id"])
    with _db() as db:
        names = db.scalars(select(NameRecord).where(NameRecord.person_id == pid)).all()
        preferred = [n for n in names if n.is_preferred]
        assert len(preferred) == 1 and preferred[0].prov_origin.value == "manual"
        imported = [n for n in names if n.prov_origin.value == "gedcom"]
        assert {n.script for n in imported} == {"Latn", "Deva", "Taml"}
        assert not any(n.is_preferred for n in imported)
        births = db.scalars(
            select(Event)
            .join(EventParticipant, EventParticipant.event_id == Event.id)
            .where(EventParticipant.person_id == pid, Event.type == "birth")
        ).all()
        assert len(births) == 2
        assert [e.is_preferred for e in births if e.prov_origin.value == "gedcom"] == [False]
        assert [e.is_preferred for e in births if e.prov_origin.value == "manual"] == [True]
        # heritage / astrology from the file are NOT applied to an attached person
        assert db.scalars(select(Assertion).where(Assertion.person_id == pid)).all() == []
        assert db.scalars(select(AstrologyProfile).where(AstrologyProfile.person_id == pid)).all() == []
        # relationships link the attached person to the imported family; adoption typed by PEDI
        mohan = people["Mohan Sharma"].id
        sita = people["Sita Sharma"].id
        rels = db.scalars(select(Relationship).where(Relationship.tree_id == uuid.UUID(t))).all()
        union = next(r for r in rels if r.type.value == "spouse")
        assert {union.person_a_id, union.person_b_id} == {pid, sita}
        adoptive = [r for r in rels if r.type.value == "adoptive_parent"]
        assert {(r.person_a_id, r.person_b_id) for r in adoptive} == {(pid, mohan), (sita, mohan)}
        assert all(r.union_id == union.id and r.lineage.value == "legal" for r in adoptive)
        assert all(
            r.prov_origin.value == "gedcom" and r.evidence_status.value == "USER_ASSERTION" for r in rels
        )


def test_commit_creates_everything_with_provenance(owner, tree) -> None:
    t = tree["id"]
    body = _import(owner, t, G7)
    assert body["status"] == "committed"
    people = _people(t)
    assert len(people) == 4
    ramesh, sita, gita = people["Ramesh Sharma"], people["Sita Sharma"], people["Gita Sharma"]
    assert ramesh.profile_status.value == "deceased" and ramesh.sex_at_birth.value == "male"
    assert sorted(ramesh.scripts_used) == ["Deva", "Latn", "Taml"]
    with _db() as db:
        gotra = db.scalars(select(Assertion).where(Assertion.person_id == ramesh.id)).all()
        assert {(a.attribute, a.value_text) for a in gotra} == {
            ("gotra", "Kashyapa"),
            ("kuladevata", "Vindhyavasini"),
        }
        assert all(
            a.prov_origin.value == "gedcom" and a.evidence_status.value == "USER_ASSERTION" and a.is_preferred
            for a in gotra
        )
        astro = db.scalars(select(AstrologyProfile).where(AstrologyProfile.person_id == ramesh.id)).one()
        assert (
            astro.provenance_kind.value == "imported"
            and astro.nakshatra == "Rohini"
            and astro.nakshatra_pada == 2
        )
        assert astro.prov_origin.value == "gedcom"
        ext = db.scalars(select(GedcomExtension).where(GedcomExtension.person_id == ramesh.id)).one()
        assert ext.tag == "_XYZ" and ext.uri == "https://example.org/xyz" and "_XYZ_DETAIL" in ext.payload
        cit = db.scalars(select(Citation).where(Citation.tree_id == uuid.UUID(t))).one()
        assert cit.page_or_image == "p. 12" and cit.target_type.value == "event"
        birth = db.scalars(
            select(Event)
            .join(EventParticipant, EventParticipant.event_id == Event.id)
            .where(EventParticipant.person_id == sita.id, Event.type == "birth")
        ).one()
        assert birth.time["value"] == "06:30:00" and birth.time["precision"] == "approximate"
        bio = db.scalars(
            select(Relationship).where(
                Relationship.person_b_id == gita.id, Relationship.type == "biological_parent"
            )
        ).all()
        assert len(bio) == 2 and all(r.union_id is not None for r in bio)
        marriage = db.scalars(
            select(Event).where(Event.tree_id == uuid.UUID(t), Event.type == "marriage")
        ).one()
        parts = db.scalars(
            select(EventParticipant.person_id).where(EventParticipant.event_id == marriage.id)
        ).all()
        assert set(parts) == {ramesh.id, sita.id}
        audit_rows = db.scalars(select(AuditEvent).where(AuditEvent.action.like("gedcom.%"))).all()
        imported = next(a for a in audit_rows if a.action == "gedcom.imported")
        assert imported.details["counts"]["people_created"] == 4
        assert "Ramesh" not in str(imported.details) and "Kashyapa" not in str(imported.details)
        assert {a.action for a in audit_rows} == {"gedcom.uploaded", "gedcom.imported"}
    # the person API sees the imported data through the normal privacy rules
    p = owner.get(f"/trees/{t}/people/{ramesh.id}").json()
    assert p["birth"]["date"]["precision"] == "circa"
    assert p["birth"]["place_name"] == "Varanasi, Uttar Pradesh, India"


def test_living_people_from_file_are_protected(owner, tree) -> None:
    t = tree["id"]
    g = "0 HEAD\n1 GEDC\n2 VERS 7.0\n0 @I1@ INDI\n1 NAME Arjun /Rao/\n1 BIRT\n2 DATE 1990\n0 @I2@ INDI\n1 NAME Old /Rao/\n1 BIRT\n2 DATE 1850\n0 @I3@ INDI\n1 NAME Nodates /Rao/\n0 @I4@ INDI\n1 NAME Secret /Rao/\n1 RESN CONFIDENTIAL\n0 TRLR\n"
    _import(owner, t, g)
    people = _people(t)
    assert people["Arjun Rao"].profile_status.value == "living"
    assert people["Old Rao"].profile_status.value == "unknown"
    assert people["Nodates Rao"].profile_status.value == "unknown"
    assert people["Arjun Rao"].privacy_level.value == tree.get("default_person_privacy", "TREE_MEMBERS")
    assert people["Secret Rao"].privacy_level.value == "PRIVATE_TREE_ADMINS"


def test_commit_twice_conflicts_and_cancel(owner, tree) -> None:
    t = tree["id"]
    job = _upload(owner, t, G7).json()
    url = f"/trees/{t}/imports/{job['id']}"
    assert owner.post(f"{url}/commit", json={"decisions": {}}).status_code == 200
    again = owner.post(f"{url}/commit", json={"decisions": {}})
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_committed"
    assert len(_people(t)) == 4
    assert owner.post(f"{url}/cancel").status_code == 409
    job2 = _upload(owner, t, G7).json()
    url2 = f"/trees/{t}/imports/{job2['id']}"
    bad = owner.post(f"{url2}/commit", json={"decisions": {"@I99@": "create"}})
    assert bad.status_code == 422
    c = owner.post(f"{url2}/cancel")
    assert c.status_code == 200 and c.json()["status"] == "cancelled"
    assert owner.post(f"{url2}/commit", json={"decisions": {}}).status_code == 409
    assert len(_people(t)) == 4


def test_imports_are_tree_scoped(owner, tree, make_client) -> None:
    t = tree["id"]
    job = _upload(owner, t, G7).json()
    other = make_client()
    other.register()
    other_tree = new_tree(other, "Other")
    # the other tree's admin cannot reach this job, neither via their tree nor ours
    assert other.get(f"/trees/{other_tree['id']}/imports/{job['id']}").status_code == 404
    assert other.post(f"/trees/{other_tree['id']}/imports/{job['id']}/commit", json={}).status_code == 404
    assert other.get(f"/trees/{t}/imports/{job['id']}").status_code == 404
    assert other.get(f"/trees/{t}/exports/gedcom").status_code == 404
    # attaching to a person from another tree is refused
    foreign = create_person(other, other_tree["id"], "Ramesh", "Sharma")
    r = owner.post(
        f"/trees/{t}/imports/{job['id']}/commit", json={"decisions": {"@I1@": {"attach": foreign["id"]}}}
    )
    assert r.status_code == 422
    assert _people(t) == {}


# ------------------------------------------------------------------------------ export
@pytest.fixture
def family_tree(owner, tree) -> dict[str, Any]:
    t = tree["id"]
    grandpa = create_person(owner, t, "Venkat", "Iyer", sex="male", birth={"date": exact(1901, 4, 3)})
    grandma = create_person(
        owner, t, "Kamala", "Iyer", sex="female", birth={"date": {"precision": "circa", "year": 1905}}
    )
    living = create_person(
        owner, t, "Priya", "Iyer", status="living", sex="female", birth={"date": exact(1990, 6, 1)}
    )
    hidden = create_person(owner, t, "Secret", "Iyer", sex="male", privacy_level="PRIVATE_TREE_ADMINS")
    adopted = create_person(
        owner,
        t,
        "Ravi",
        "Iyer",
        sex="male",
        birth={"date": {"precision": "range", "year": 1930, "end_year": 1932}},
    )
    union = owner.post(
        f"/trees/{t}/relationships",
        json={"person_a_id": grandpa["id"], "person_b_id": grandma["id"], "type": "spouse"},
    ).json()
    for parent in (grandpa, grandma):
        r = owner.post(
            f"/trees/{t}/relationships",
            json={
                "person_a_id": parent["id"],
                "person_b_id": adopted["id"],
                "type": "adoptive_parent",
                "union_id": union["id"],
            },
        )
        assert r.status_code == 201, r.text
    owner.post(
        f"/trees/{t}/relationships",
        json={"person_a_id": adopted["id"], "person_b_id": living["id"], "type": "biological_parent"},
    )
    owner.post(
        f"/trees/{t}/people/{grandpa['id']}/heritage", json={"attribute": "gotra", "value_text": "Kaundinya"}
    )
    owner.post(
        f"/trees/{t}/people/{grandpa['id']}/names",
        json={"given_name": "वेंकट", "surname": "अय्यर", "language": "sa"},
    )
    owner.post(
        f"/trees/{t}/people/{grandpa['id']}/names",
        json={"given_name": "வெங்கட்", "surname": "ஐயர்"},
    )
    return {"grandpa": grandpa, "grandma": grandma, "living": living, "hidden": hidden, "adopted": adopted}


def test_export_privacy_for_contributor(owner, tree, family_tree, member_factory) -> None:
    t = tree["id"]
    contributor = member_factory(["CONTRIBUTOR"])
    r = _export(contributor, t)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/octet-stream"
    assert 'filename="tree.ged"' in r.headers["content-disposition"]
    text = r.content.decode("utf-8")
    assert text.startswith("0 HEAD\n1 GEDC\n2 VERS 7.0\n") and text.rstrip().endswith("0 TRLR")
    assert "Venkat /Iyer/" in text and "Ravi /Iyer/" in text
    assert "Priya" not in text  # living: excluded by default
    assert "Secret" not in text  # admin-only person invisible to a contributor
    assert "1 NAME Living" not in text
    # living people included on request, but reduced to placeholders for a non-admin
    text2 = _export(contributor, t, exclude_living=False).content.decode()
    assert "Priya" not in text2 and "1 NAME Living" in text2 and "1990" not in text2
    assert "Secret" not in text2
    # include_sensitive needs PRIVACY_MANAGE
    assert _export(contributor, t, include_sensitive=True).status_code == 403
    viewer = member_factory(["VIEWER"])
    assert _export(viewer, t).status_code == 403
    # admin sees admin-only people; with exclude_living=false the living person's details too
    admin_text = _export(owner, t, exclude_living=False).content.decode()
    assert "Secret /Iyer/" in admin_text and "Priya /Iyer/" in admin_text and "1 JUN 1990" in admin_text
    assert "1 RESN CONFIDENTIAL" in admin_text


def test_export_structure_and_schema(owner, tree, family_tree) -> None:
    t = tree["id"]
    text = _export(owner, t).content.decode()
    lines = text.splitlines()
    assert f"2 TAG _IND_GOTRA {BASE}gotra" in lines
    assert not any("_IND_RASHI" in ln for ln in lines)  # only tags actually used are declared
    assert "1 _IND_GOTRA Kaundinya" in lines
    assert "2 DATE 3 APR 1901" in lines and "2 DATE ABT 1905" in lines and "2 DATE BET 1930 AND 1932" in lines
    assert "2 TRAN वेंकट /अय्यर/" in lines and "3 LANG sa-Deva" in lines
    assert "2 TRAN வெங்கட் /ஐயர்/" in lines and "3 LANG und-Taml" in lines
    assert "2 PEDI ADOPTED" in lines
    fam_start = lines.index(next(ln for ln in lines if ln.endswith(" FAM")))
    fam_block = lines[fam_start : fam_start + 4]
    assert fam_block[1].startswith("1 HUSB @I") and fam_block[2].startswith("1 WIFE @I")
    with _db() as db:
        ev = db.scalars(select(AuditEvent).where(AuditEvent.action == "gedcom.exported")).one()
        assert ev.details["exclude_living"] is True and ev.details["include_sensitive"] is False
        assert ev.details["counts"]["people"] == 4


def test_sensitive_export_is_admin_only_and_audited(owner, tree, family_tree) -> None:
    t = tree["id"]
    r = _export(owner, t, include_sensitive=True, exclude_living=False)
    assert r.status_code == 200
    with _db() as db:
        ev = db.scalars(select(AuditEvent).where(AuditEvent.action == "gedcom.exported")).one()
        assert ev.details["include_sensitive"] is True and ev.details["exclude_living"] is False
        assert ev.summary and "sensitive" in ev.summary


# ------------------------------------------------------------------------------ round trip
def test_round_trip_export_then_import(owner, tree) -> None:
    t = tree["id"]
    _import(owner, t, G7)
    exported = _export(owner, t, exclude_living=False, include_sensitive=True)
    assert exported.status_code == 200
    text = exported.content.decode()
    assert "2 TAG _XYZ https://example.org/xyz" in text and "1 _XYZ custom value" in text
    assert "2 _XYZ_DETAIL nested" in text
    copy_tree = new_tree(owner, "Copy")["id"]
    _import(owner, copy_tree, exported.content)

    def snapshot(tree_id: str) -> dict[str, Any]:
        tid = uuid.UUID(tree_id)
        with _db() as db:
            people = {p.id: p for p in db.scalars(select(Person).where(Person.tree_id == tid))}
            label = {pid: p.preferred_display_name for pid, p in people.items()}
            names = {
                label[n.person_id]: sorted(
                    (n.given_name or "", n.surname or "", n.script or "", n.is_preferred)
                    for n in db.scalars(select(NameRecord).where(NameRecord.person_id == n.person_id))
                )
                for n in db.scalars(select(NameRecord).where(NameRecord.tree_id == tid))
            }
            rels = sorted(
                (label[r.person_a_id], label[r.person_b_id], r.type.value, r.union_id is not None)
                for r in db.scalars(select(Relationship).where(Relationship.tree_id == tid))
            )
            events = sorted(
                (
                    label[pid],
                    e.type.value,
                    {k: v for k, v in (e.date or {}).items() if k != "original_text"}.__repr__(),
                    (e.time or {}).get("value"),
                    (e.time or {}).get("precision"),
                    e.place_as_recorded or "",
                )
                for e, pid in db.execute(
                    select(Event, EventParticipant.person_id)
                    .join(EventParticipant, EventParticipant.event_id == Event.id)
                    .where(Event.tree_id == tid)
                )
            )
            heritage = sorted(
                (label[a.person_id], a.attribute, a.value_text)
                for a in db.scalars(select(Assertion).where(Assertion.tree_id == tid))
            )
            astro = sorted(
                (label[a.person_id], a.nakshatra, a.nakshatra_pada)
                for a in db.scalars(select(AstrologyProfile).where(AstrologyProfile.tree_id == tid))
            )
            exts = sorted(
                (label.get(e.person_id, ""), e.tag, e.uri, e.payload)
                for e in db.scalars(select(GedcomExtension).where(GedcomExtension.tree_id == tid))
            )
            statuses = sorted(
                (label[p.id], p.profile_status.value, str(p.sex_at_birth)) for p in people.values()
            )
        return {
            "names": names, "rels": rels, "events": events, "heritage": heritage, "astro": astro,
            "exts": exts, "statuses": statuses,
        }  # fmt: skip

    a, b = snapshot(t), snapshot(copy_tree)
    for key in a:
        assert a[key] == b[key], key
    assert ("Ramesh Sharma", "gotra", "Kashyapa") in b["heritage"]
    assert any(r[2] == "adoptive_parent" for r in b["rels"])
    assert any("ரமேஷ்" in n[0] for n in b["names"]["Ramesh Sharma"])


# ------------------------------------------------------------------------------ MyHeritage exports
# Fictional family, with the quirks of a MyHeritage Family Tree Builder 5.5.1 export: UTF-8 BOM,
# CRLF line ends, a malformed "0  _PUBLISH" record, _UID/_UPD everywhere, photos with local paths,
# an "Unassociated photos" pseudo-person, a wife recorded without a name, RELI/NATI facts, a birth
# with a place but no date, and "1 DEAT Y".
MYHERITAGE = "\ufeff" + "\r\n".join(
    [
        "0 HEAD",
        "1 GEDC",
        "2 VERS 5.5.1",
        "2 FORM LINEAGE-LINKED",
        "1 CHAR UTF-8",
        "1 SOUR MYHERITAGE",
        "2 NAME MyHeritage Family Tree Builder",
        "0  _PUBLISH",
        "1 _SITENAME Example Web Site",
        "0 @I1@ INDI",
        "1 _UID 11111111111111111111111111111111",
        "1 _UPD 12 DEC 2024 00:50:52 GMT+5.5",
        "1 NAME Arjun /Verma/",
        "2 GIVN Arjun",
        "2 SURN Verma",
        "1 SEX M",
        "1 BIRT",
        "2 DATE 3 MAR 1980",
        "2 PLAC Lucknow",
        "1 RELI Hindu",
        "2 _UID 22222222222222222222222222222222",
        "1 NATI Indian",
        "1 FAMC @F1@",
        "1 OBJE",
        "2 FORM jpg",
        "2 FILE C:\\Users\\someone\\Photos\\P1.jpg",
        "0 @I2@ INDI",
        "1 NAME Ramesh /Verma/",
        "1 SEX M",
        "1 BIRT",
        "2 _UID 33333333333333333333333333333333",
        "2 PLAC India",
        "1 DEAT Y",
        "1 FAMS @F1@",
        "0 @I3@ INDI",
        "1 _UID 44444444444444444444444444444444",
        "1 SEX F",
        "1 FAMS @F1@",
        "0 @I88888888@ INDI",
        "1 RIN MH:I88888888",
        "1 _UID Unassociated photos",
        "1 _UPD 25 SEP 2026 01:27:49 GMT+5.5",
        "1 SEX U",
        "1 OBJE",
        "2 FORM jpg",
        "2 TITL WhatsApp Image",
        "2 FILE C:\\Users\\someone\\Photos\\P17.jpg",
        "1 OBJE",
        "2 FORM jpg",
        "2 FILE C:\\Users\\someone\\Photos\\P18.jpg",
        "0 @F1@ FAM",
        "1 HUSB @I2@",
        "1 WIFE @I3@",
        "1 CHIL @I1@",
        "0 TRLR",
        "",
    ]
)


def test_myheritage_photo_container_is_not_a_person(owner, tree) -> None:
    t = tree["id"]
    r = _upload(owner, t, MYHERITAGE.encode("utf-8"))
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["status"] == "ready"
    report = job["report"]
    # three real people (including the wife recorded without a name); the photo album is skipped
    assert report["counts"]["people"] == 3
    assert report["counts"]["media_refs"] == 3  # its photos are still counted as media references
    codes = [w["code"] for w in report["warnings"]]
    assert codes.count("photo_container_skipped") == 1
    assert codes.count("no_name") == 1  # the wife: a real person, kept as "Unnamed"
    assert [p["xref"] for p in job["preview"]] == ["@I1@", "@I2@", "@I3@"]
    result = owner.post(f"/trees/{t}/imports/{job['id']}/commit", json={"decisions": {}}).json()
    assert result["commit_result"]["counts"]["people_created"] == 3
    names = sorted(p["display_name"] for p in owner.get(f"/trees/{t}/people").json()["items"])
    assert names == ["Arjun Verma", "Ramesh Verma", "Unnamed"]


def test_photo_container_rule_keeps_real_people() -> None:
    def indi(*lines: str) -> Any:
        return parser.parse(
            ("0 HEAD\n1 GEDC\n2 VERS 5.5.1\n0 @I1@ INDI\n" + "\n".join(lines) + "\n0 TRLR\n").encode()
        ).records[1]

    # only photos (no MyHeritage marker needed)
    assert mapping._is_photo_container(indi("1 SEX U", "1 OBJE", "2 FILE a.jpg"))
    # an unnamed person with a family link, an event, or a known sex is a person, not an album
    assert not mapping._is_photo_container(indi("1 OBJE", "2 FILE a.jpg", "1 FAMS @F1@"))
    assert not mapping._is_photo_container(indi("1 OBJE", "2 FILE a.jpg", "1 BIRT", "2 DATE 1900"))
    assert not mapping._is_photo_container(indi("1 SEX F", "1 OBJE", "2 FILE a.jpg"))
    # a named person with the MyHeritage marker (never produced, but never skipped either)
    assert not mapping._is_photo_container(indi("1 NAME A /B/", "1 _UID Unassociated photos", "1 OBJE"))
    # no photos at all: never a container
    assert not mapping._is_photo_container(indi("1 SEX U"))


def _religion(client: Any, tree_id: str, person_id: str) -> list[dict[str, Any]]:
    """Every religion assertion (preferred first) on a person's heritage profile, as the caller sees it."""
    profile = client.get(f"/trees/{tree_id}/people/{person_id}/heritage").json()
    views = [v for v in profile["attributes"] if v["attribute"] == "religion"]
    return [a for v in views for a in ([v["preferred"]] if v["preferred"] else []) + v["alternatives"]]


def test_reli_becomes_religion_and_is_only_exported_as_sensitive(owner, tree, member_factory) -> None:
    t = tree["id"]
    _import(owner, t, MYHERITAGE.encode("utf-8"))
    arjun = next(
        p for p in owner.get(f"/trees/{t}/people").json()["items"] if p["display_name"] == "Arjun Verma"
    )
    religion = _religion(owner, t, arjun["id"])
    assert [a["value_text"] for a in religion] == ["Hindu"]
    assert religion[0]["evidence_status"] == "USER_ASSERTION"  # recorded in the file, never inferred
    # NATI has no home in the model: kept verbatim, not mapped
    with owner_session() as db:
        tags = {
            e.tag
            for e in db.scalars(
                select(GedcomExtension).where(GedcomExtension.person_id == uuid.UUID(arjun["id"]))
            )
        }
    assert "NATI" in tags and "RELI" not in tags
    # religion is sensitive: never in ordinary exports, only in an admin's sensitive export
    assert "1 RELI" not in _export(owner, t, exclude_living=False).text
    contrib = member_factory(["CONTRIBUTOR"])
    assert "1 RELI" not in _export(contrib, t, exclude_living=False).text
    sensitive = _export(owner, t, exclude_living=False, include_sensitive=True).text
    assert "1 RELI Hindu" in sensitive
    # and it survives a round trip without duplication
    t2 = new_tree(owner, "Round trip")["id"]
    _import(owner, t2, sensitive)
    arjun2 = next(
        p for p in owner.get(f"/trees/{t2}/people").json()["items"] if p["display_name"] == "Arjun Verma"
    )
    assert [a["value_text"] for a in _religion(owner, t2, arjun2["id"])] == ["Hindu"]


def test_reli_religion_is_hidden_by_field_privacy(owner, tree, member_factory) -> None:
    t = tree["id"]
    _import(owner, t, MYHERITAGE.encode("utf-8"))
    arjun = next(
        p for p in owner.get(f"/trees/{t}/people").json()["items"] if p["display_name"] == "Arjun Verma"
    )
    r = owner.put(
        f"/trees/{t}/people/{arjun['id']}/privacy",
        json={"field_privacy": {"religion": "PRIVATE_TREE_ADMINS"}},
    )
    assert r.status_code == 200, r.text
    viewer = member_factory(["VIEWER"])
    heritage = viewer.get(f"/trees/{t}/people/{arjun['id']}/heritage")
    assert heritage.status_code == 200 and "Hindu" not in heritage.text
    assert "religion" in heritage.json()["withheld_attributes"]
    assert [a["value_text"] for a in _religion(owner, t, arjun["id"])] == ["Hindu"]


def test_preview_reports_undated_events_without_inventing_a_date(owner, tree) -> None:
    job = _upload(owner, tree["id"], MYHERITAGE.encode("utf-8")).json()
    by_xref = {p["xref"]: p for p in job["preview"]}
    ramesh = by_xref["@I2@"]
    assert ramesh["birth"] is None and ramesh["birth_recorded"] is True and ramesh["birth_place"] == "India"
    assert ramesh["death"] is None and ramesh["death_recorded"] is True and ramesh["death_place"] is None
    arjun = by_xref["@I1@"]
    assert arjun["birth"] and "1980" in arjun["birth"] and arjun["birth_place"] == "Lucknow"
    assert arjun["death"] is None and arjun["death_recorded"] is False
    assert "yes" not in str(job["preview"])
