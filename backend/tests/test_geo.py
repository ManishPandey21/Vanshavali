"""Indian geography reference data (ADR-0019): importer, snapshots, API, and linked tree places.

Uses the committed SYNTHETIC fixture (tests/fixtures/geo): snapshot 2026-02, then 2026-05 with
district 9901 renamed Allahabad -> Prayagraj, village 9900003 split into 9900007 and 9900008, and a
PIN office whose district (Kaushambi) is not in the data.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.core.db import get_engine
from app.models import AuditEvent, GeoSnapshot, GeoUnit, GeoUnitAlias, PincodeOffice
from app.models.enums import GeoLevel, GeoSnapshotStatus
from app.models.rls import GRANT_APP_ROLE_SQL, READ_ONLY_TABLES
from app.modules.geo import fixture, importer
from app.modules.geo.importer import ImportRefused
from tests.conftest import ApiClient, owner_session

FX = fixture.FIXTURE_DIR


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def f(p: Path) -> tuple[Path, str]:
    return p, sha(p)


def load(until: str = "2026-05") -> None:
    with owner_session() as db:
        fixture.load(db, until=until)
        db.commit()


def stage1(snapshot: str, d: Path, db: Any, **kw: Any) -> importer.ImportResult:
    files = [f(d / n) for n in ("states.csv", "districts.csv", "subdistricts.csv")]
    return importer.import_files(db, stage=1, snapshot=snapshot, files=files, **kw)


def write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


STATES_HEADER = "S.No.,State Code,State Version,State Name (In English),State Name (In Local language)\n"


# ------------------------------------------------------------------ importer
def test_fixture_loads_into_an_active_snapshot_with_its_provenance() -> None:
    load("2026-02")
    with owner_session() as db:
        snap = db.get(GeoSnapshot, "2026-02")
        assert snap is not None and snap.status == GeoSnapshotStatus.ACTIVE
        assert {imp["stage"] for imp in snap.imports} == {1, 2, 3}
        first = snap.imports[0]
        assert first["licence"].startswith("Government Open Data Licence")
        assert all(re.fullmatch(r"[0-9a-f]{64}", fi["sha256"]) for fi in first["files"])
        counts = dict(db.execute(select(GeoUnit.level, func.count()).group_by(GeoUnit.level)).all())
        assert counts == {
            GeoLevel.STATE: 2,
            GeoLevel.DISTRICT: 2,
            GeoLevel.SUB_DISTRICT: 3,
            GeoLevel.VILLAGE: 6,
            GeoLevel.URBAN_BODY: 1,
        }
        rampur = db.scalars(select(GeoUnit).where(GeoUnit.lgd_code == "9900001")).one()
        assert (rampur.state_code, rampur.district_code, rampur.sub_district_code) == ("9", "9901", "99001")
        assert rampur.name_local == "रामपुर" and rampur.local_script == "Deva"
        ulb = db.scalars(select(GeoUnit).where(GeoUnit.level == GeoLevel.URBAN_BODY)).one()
        assert ulb.category == "Nagar Panchayat" and ulb.parent_level == GeoLevel.DISTRICT
        # India Post office coordinates are never imported (§1)
        assert not hasattr(PincodeOffice, "latitude")
        assert db.scalar(select(func.count()).select_from(PincodeOffice)) == 5
        unmatched = db.scalars(select(PincodeOffice).where(PincodeOffice.district_code.is_(None))).one()
        assert unmatched.district_name == "KAUSHAMBI"


def test_checksum_mismatch_is_refused_and_writes_nothing() -> None:
    with owner_session() as db:
        p = FX / "2026-02" / "states.csv"
        with pytest.raises(ImportRefused, match="checksum mismatch"):
            importer.import_files(db, stage=1, snapshot="2026-02", files=[(p, "0" * 64)])
        db.rollback()
        assert db.scalar(select(func.count()).select_from(GeoSnapshot)) == 0


def test_unrecognised_files_are_refused_not_guessed(tmp_path: Path) -> None:
    p = write(tmp_path, "x.csv", "name,code\nRampur,1\n")
    with (
        owner_session() as db,
        pytest.raises(ImportRefused, match="not a recognised LGD or India Post layout"),
    ):
        importer.import_files(db, stage=1, snapshot="2026-02", files=[f(p)])
    # the right layout in the wrong stage is refused too
    v = FX / "2026-02" / "villages_9.csv"
    with owner_session() as db, pytest.raises(ImportRefused, match="stage 1 takes"):
        importer.import_files(db, stage=1, snapshot="2026-02", files=[f(v)])


def test_headers_are_matched_tolerantly(tmp_path: Path) -> None:
    p = write(
        tmp_path, "s.csv", "Downloaded from LGD\n\nstate code,STATE NAME(in english)\n9,Uttar  Pradesh\n"
    )
    with owner_session() as db:
        importer.import_files(db, stage=1, snapshot="2026-02", files=[f(p)])
        u = db.scalars(select(GeoUnit)).one()
        assert (u.lgd_code, u.name_en) == ("9", "Uttar Pradesh")  # whitespace collapsed


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("Ram\x00pur", "control character"),
        ("Ram‮pur", "control character"),  # bidi override
        ("R" * 201, "longer than 200"),
    ],
)
def test_names_are_validated_as_plain_text(tmp_path: Path, name: str, reason: str) -> None:
    p = write(tmp_path, "s.csv", STATES_HEADER + f'1,9,1,"{name}",\n')
    with owner_session() as db, pytest.raises(ImportRefused) as exc:
        importer.import_files(db, stage=1, snapshot="2026-02", files=[f(p)])
    assert any(reason in msg and line == 2 for line, msg in exc.value.problems)


def test_names_are_nfc_normalised_and_joiners_kept(tmp_path: Path) -> None:
    decomposed = "क़"  # क + nukta, NFC is क़
    p = write(tmp_path, "s.csv", STATES_HEADER + f"1,9,1,Test,{decomposed}र‍ी\n")
    with owner_session() as db:
        importer.import_files(db, stage=1, snapshot="2026-02", files=[f(p)])
        u = db.scalars(select(GeoUnit)).one()
        assert u.name_local == "क़र‍ी"


def test_unknown_parents_and_repeated_codes_are_refused(tmp_path: Path) -> None:
    p = write(
        tmp_path,
        "d.csv",
        "State Code,District Code,District Name (In English)\n9,9901,A\n9,9901,B\n77,9903,C\n",
    )
    s = write(tmp_path, "s.csv", STATES_HEADER + "1,9,1,UP,\n")
    with owner_session() as db, pytest.raises(ImportRefused) as exc:
        importer.import_files(db, stage=1, snapshot="2026-02", files=[f(s), f(p)])
    msgs = [m for _, m in exc.value.problems]
    assert any("repeats line 2" in m for m in msgs)
    assert any("unknown parent state 77" in m for m in msgs)


def test_a_state_scoped_import_refuses_other_states(tmp_path: Path) -> None:
    load("2026-02")
    v = (FX / "2026-02" / "villages_9.csv").read_text(encoding="utf-8")
    p = write(tmp_path, "v.csv", v)
    with owner_session() as db, pytest.raises(ImportRefused, match="not in state 10"):
        importer.import_files(db, stage=2, snapshot="2026-05", state="10", files=[f(p)])


def test_snapshot_order_and_scopes_are_enforced() -> None:
    load("2026-02")
    d5 = FX / "2026-05"
    with owner_session() as db:
        with pytest.raises(ImportRefused, match="is active: import into a new snapshot"):
            stage1("2026-02", d5, db)
        db.rollback()
        with pytest.raises(ImportRefused, match="older than the newest"):
            stage1("2025-11", d5, db)
        db.rollback()
        with pytest.raises(ImportRefused, match="YYYY-MM"):
            stage1("2026-13", d5, db)
        db.rollback()
        stage1("2026-05", d5, db)
        db.commit()
        with pytest.raises(ImportRefused, match="already has an import covering state"):
            stage1("2026-05", d5, db)
        db.rollback()
        with pytest.raises(ImportRefused, match="2026-05 is staged: activate or discard it"):
            stage1("2026-08", d5, db)


def test_a_new_snapshot_records_renames_splits_and_needs_review_for_large_changes(tmp_path: Path) -> None:
    load("2026-02")
    d5 = FX / "2026-05"
    with owner_session() as db:
        r1 = stage1("2026-05", d5, db, report_dir=tmp_path)
        assert r1.summary["district"]["renamed"] == 1
        r2 = importer.import_files(
            db,
            stage=2,
            snapshot="2026-05",
            state="9",
            files=[f(d5 / "villages_9.csv")],
            successors_file=f(d5 / "successors.csv"),
            report_dir=tmp_path,
        )
        assert r2.summary["village"] | {} == {
            "before": 6,
            "after": 7,
            "new": 2,
            "renamed": 0,
            "moved": 0,
            "changed": 0,
            "retired": 1,
            "merged": 0,
            "split": 1,
            "unchanged": 5,
        }
        db.commit()
        report = (tmp_path / "geo-changes-2026-05-stage2-state9.csv").read_text(encoding="utf-8")
        assert "split,village,9900003,Bhagwatpur,,99001,,9900007;9900008," in report
        stage1_report = (tmp_path / "geo-changes-2026-05-stage1.csv").read_text(encoding="utf-8")
        assert "renamed,district,9901,Prayagraj,Allahabad" in stage1_report

        # the rename keeps the old name as a historical alias
        alias = db.scalars(select(GeoUnitAlias).where(GeoUnitAlias.lgd_code == "9901")).one()
        assert (alias.name, alias.kind.value) == ("Allahabad", "historical")
        # versioned rows: the old district row is closed at 2026-02, the new one starts at 2026-05
        rows = db.scalars(
            select(GeoUnit).where(GeoUnit.lgd_code == "9901").order_by(GeoUnit.first_snapshot)
        ).all()
        assert [(r.name_en, r.first_snapshot, r.last_snapshot) for r in rows] == [
            ("Allahabad", "2026-02", "2026-02"),
            ("Prayagraj", "2026-05", None),
        ]
        # unchanged units keep one row across snapshots
        assert db.scalar(select(func.count()).select_from(GeoUnit).where(GeoUnit.lgd_code == "9900001")) == 1

        # 1 of 6 villages retired is more than 5%: activation needs the explicit flag
        with pytest.raises(ImportRefused, match="village \\(state 9\\): 1 of 6 retired"):
            importer.activate(db, "2026-05", operator="op")
        db.rollback()
        assert importer.activate(db, "2026-05", operator="op", accept_large_change=True).startswith(
            "snapshot 2026-05 is active"
        )
        db.commit()
        ev = db.scalars(select(AuditEvent).where(AuditEvent.action == "geo.snapshot.activated")).all()
        assert ev[-1].details["snapshot"] == "2026-05" and ev[-1].details["accept_large_change"] is True


def test_successors_must_name_retired_codes(tmp_path: Path) -> None:
    load("2026-02")
    d5 = FX / "2026-05"
    bad = write(tmp_path, "succ.csv", "level,lgd_code,successor_codes\nvillage,9900001,9900007\n")
    with owner_session() as db, pytest.raises(ImportRefused, match="does not retire: village 9900001"):
        importer.import_files(
            db,
            stage=2,
            snapshot="2026-05",
            state="9",
            files=[f(d5 / "villages_9.csv")],
            successors_file=f(bad),
        )


def test_rollback_and_discard_restore_the_previous_state(owner: ApiClient) -> None:
    load("2026-05")
    with owner_session() as db:
        # rollback: activate the previous snapshot; the API reads it again
        importer.activate(db, "2026-02", operator="op")
        db.commit()
    r = owner.get("/geo/units", params={"level": "district", "parent": "9"})
    assert [u["name_en"] for u in r.json()["items"]] == ["Allahabad", "Pratapgarh"]
    assert r.json()["snapshot"]["id"] == "2026-02"
    with owner_session() as db:
        with pytest.raises(ImportRefused, match="only the newest"):
            importer.discard(db, "2026-02", operator="op")
        db.rollback()
        before = db.scalar(select(func.count()).select_from(GeoUnit))
        importer.discard(db, "2026-05", operator="op")
        db.commit()
        units = db.scalars(select(GeoUnit)).all()
        assert len(units) == 14 < before
        assert all(u.last_snapshot is None and u.first_snapshot == "2026-02" for u in units)
        assert all(u.successor_codes == [] for u in units)
        assert db.scalar(select(func.count()).select_from(GeoUnitAlias)) == 0
        assert (
            db.scalar(
                select(func.count()).select_from(PincodeOffice).where(PincodeOffice.last_snapshot.is_(None))
            )
            == 5
        )


def test_an_active_snapshot_cannot_be_discarded() -> None:
    load("2026-02")
    with owner_session() as db, pytest.raises(ImportRefused, match="is active"):
        importer.discard(db, "2026-02", operator="op")


def test_the_synthetic_fixture_is_refused_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "env", "production")
    with owner_session() as db, pytest.raises(ImportRefused, match="never loaded in production"):
        fixture.load(db)


def test_the_application_role_can_only_read_reference_tables() -> None:
    assert "ARRAY[" + ", ".join(f"'{t}'" for t in READ_ONLY_TABLES) + "]" in GRANT_APP_ROLE_SQL
    load("2026-02")
    with get_engine().connect() as c:  # the application's own (non-owner) role
        assert c.execute(text("SELECT count(*) FROM geo_unit")).scalar() == 14
        for stmt in (
            "INSERT INTO geo_snapshot (id) VALUES ('2030-01')",
            "UPDATE geo_unit SET name_en = 'x'",
            "DELETE FROM geo_unit_alias",
            "DELETE FROM pincode_office",
        ):
            with pytest.raises(Exception, match="permission denied"):
                c.execute(text(stmt))
            c.rollback()


# ------------------------------------------------------------------ API
def names(r: Any) -> list[str]:
    assert r.status_code == 200, r.text
    return [u["name_en"] for u in r.json()["items"]]


def test_geo_endpoints_need_a_signed_in_user(client: ApiClient) -> None:
    load("2026-02")
    for path in ("/geo/units?level=state", "/geo/units/9?level=state", "/geo/pincodes/212402"):
        assert client.get(path).status_code == 401


def test_switched_off_or_unloaded_answers_404(owner: ApiClient, monkeypatch: pytest.MonkeyPatch) -> None:
    assert owner.get("/geo/units", params={"level": "state"}).status_code == 404  # nothing loaded
    load("2026-02")
    assert owner.get("/geo/units", params={"level": "state"}).status_code == 200
    monkeypatch.setattr(get_settings(), "geo_enabled", False)
    for path in ("/geo/units?level=state", "/geo/units/9?level=state", "/geo/pincodes/212402"):
        assert owner.get(path).status_code == 404


def test_the_cascade_lists_children_level_by_level(owner: ApiClient) -> None:
    load("2026-02")
    states = owner.get("/geo/units", params={"level": "state"}).json()
    assert [s["name_en"] for s in states["items"]] == ["Bihar", "Uttar Pradesh"]
    up = states["items"][1]
    assert up["name_local"] == "उत्तर प्रदेश" and up["sub_district_label"] == "tehsil"
    assert states["snapshot"]["attribution"].startswith("Source: Local Government Directory")
    assert names(owner.get("/geo/units", params={"level": "district", "parent": "9"})) == [
        "Allahabad",
        "Pratapgarh",
    ]
    assert names(owner.get("/geo/units", params={"level": "sub_district", "parent": "9901"})) == [
        "Phulpur",
        "Soraon",
    ]
    v = owner.get("/geo/units", params={"level": "village", "parent": "99001"}).json()["items"]
    assert [u["name_en"] for u in v] == ["Bhagwatpur", "Rampur", "Rampura"]
    assert [a["name_en"] for a in v[1]["ancestors"]] == ["Uttar Pradesh", "Allahabad", "Phulpur"]
    assert names(owner.get("/geo/units", params={"level": "urban_body", "parent": "9901"})) == ["Phulpur"]
    # pagination
    p1 = owner.get("/geo/units", params={"level": "village", "parent": "99001", "limit": 2}).json()
    p2 = owner.get(
        "/geo/units", params={"level": "village", "parent": "99001", "limit": 2, "cursor": p1["next_cursor"]}
    ).json()
    assert [u["name_en"] for u in p1["items"] + p2["items"]] == ["Bhagwatpur", "Rampur", "Rampura"]
    assert p2["next_cursor"] is None
    # a level below the state needs a parent
    assert owner.get("/geo/units", params={"level": "village"}).status_code == 422


def test_search_meets_english_local_script_and_variant_spellings(owner: ApiClient) -> None:
    load("2026-02")

    def search(q: str, **kw: Any) -> list[dict[str, Any]]:
        r = owner.get("/geo/units", params={"q": q, **kw})
        assert r.status_code == 200, r.text
        return r.json()["items"]

    rampur = search("Rampur")
    assert [(u["lgd_code"], u["match"]["reason"]) for u in rampur[:2]] == [
        ("9900001", "name"),
        ("9900005", "name"),
    ]
    assert rampur[2]["name_en"] == "Rampura"  # exact before prefix
    assert {u["lgd_code"] for u in search("रामपुर")[:2]} == {"9900001", "9900005"}
    assert search("Raampur")[0]["name_en"] == "Rampur"
    # scoped by an ancestor
    assert [u["lgd_code"] for u in search("Rampur", parent="9902", parent_level="district")] == ["9900005"]
    # trigram: a misspelling still finds the village
    assert "Sikandra" in [u["name_en"] for u in search("Sikandara")]
    # two letters only within a scope; one letter never
    assert search("Ra") == []
    assert search("Ra", parent="99001", parent_level="sub_district")
    assert owner.get("/geo/units", params={"q": "R"}).status_code == 422


def test_search_finds_former_names_through_aliases(owner: ApiClient) -> None:
    load("2026-05")
    hits = owner.get("/geo/units", params={"q": "Allahabad", "level": "district"}).json()["items"]
    assert hits[0]["name_en"] == "Prayagraj"
    assert hits[0]["match"] == {"reason": "alias", "text": "Allahabad"}


def test_unit_detail_shows_ancestors_and_successors(owner: ApiClient) -> None:
    load("2026-05")
    r = owner.get("/geo/units/9900003", params={"level": "village"}).json()
    assert r["unit"]["status"] == "retired"
    assert sorted(s["name_en"] for s in r["unit"]["successors"]) == [
        "Bhagwatpur Dakshini",
        "Bhagwatpur Uttari",
    ]
    d = owner.get("/geo/units/9901", params={"level": "district"}).json()["unit"]
    assert d["status"] == "current" and d["aliases"] == [
        {"name": "Allahabad", "kind": "historical", "script": "Latn"}
    ]
    assert owner.get("/geo/units/123", params={"level": "village"}).status_code == 404
    assert owner.get("/geo/units/9901").status_code == 422  # the level is required


def test_a_pin_code_suggests_upper_levels_never_a_village(owner: ApiClient) -> None:
    load("2026-05")
    r = owner.get("/geo/pincodes/212402").json()
    assert sorted(o["office_name"] for o in r["offices"]) == ["Phulpur S.O", "Rampur B.O"]
    assert [d["name_en"] for d in r["districts"]] == ["Prayagraj"]
    assert [s["name_en"] for s in r["states"]] == ["Uttar Pradesh"]
    assert "villages" not in r
    unmatched = owner.get("/geo/pincodes/212207").json()
    assert unmatched["districts"] == [] and unmatched["offices"][0]["district_name"] == "KAUSHAMBI"
    assert owner.get("/geo/pincodes/999999").status_code == 404
    assert owner.get("/geo/pincodes/012345").status_code == 422


def test_responses_carry_an_etag_for_the_active_snapshot(owner: ApiClient) -> None:
    load("2026-02")
    r = owner.get("/geo/units", params={"level": "state"})
    tag = r.headers["etag"]
    assert (
        owner.get("/geo/units", params={"level": "state"}, headers={"If-None-Match": tag}).status_code == 304
    )
    with owner_session() as db:
        stage1("2026-05", FX / "2026-05", db)
        importer.activate(db, "2026-05", operator="op")
        db.commit()
    again = owner.get("/geo/units", params={"level": "state"}, headers={"If-None-Match": tag})
    assert again.status_code == 200 and again.headers["etag"] != tag


def test_geo_requests_are_rate_limited_per_user(owner: ApiClient, make_client: Any) -> None:
    load("2026-02")
    from app.modules.geo.router import RATE_LIMIT_PER_MINUTE

    for _ in range(RATE_LIMIT_PER_MINUTE):
        assert owner.get("/geo/units", params={"level": "state"}).status_code == 200
    assert owner.get("/geo/units", params={"level": "state"}).status_code == 429
    other = make_client()
    other.register()
    assert other.get("/geo/units", params={"level": "state"}).status_code == 200


def test_queries_are_not_logged(owner: ApiClient, caplog: pytest.LogCaptureFixture) -> None:
    load("2026-02")
    with caplog.at_level("DEBUG"):
        owner.get("/geo/units", params={"q": "Bhagwatpur"})
    # the server logs request paths only (the test client's own httpx logger is not the server)
    server = [r.getMessage() for r in caplog.records if not r.name.startswith(("httpx", "httpcore"))]
    assert server and not any("Bhagwatpur" in m for m in server)


# ------------------------------------------------------------------ tree places (§4)
def place(owner: ApiClient, tree_id: str, **body: Any) -> Any:
    return owner.post(f"/trees/{tree_id}/places", json=body)


def test_a_picked_unit_is_checked_and_stamped_with_the_snapshot(
    owner: ApiClient, tree: dict[str, Any]
) -> None:
    load("2026-02")
    tid = tree["id"]
    r = place(
        owner,
        tid,
        canonical_name="Rampur",
        place_type="village",
        lgd_code="9900001",
        lgd_level="village",
        district="Allahabad",
        state="Uttar Pradesh",
        country="India",
    )
    assert r.status_code == 201, r.text
    assert (r.json()["lgd_level"], r.json()["lgd_snapshot_id"], r.json()["lgd_note"]) == (
        "village",
        "2026-02",
        None,
    )
    # the client cannot choose the snapshot, and an unknown code is refused
    assert place(owner, tid, canonical_name="X", lgd_code="123", lgd_level="village").status_code == 422
    assert place(owner, tid, canonical_name="X", lgd_level="village").status_code == 422
    # a code typed by hand stays free text, as before
    free = place(owner, tid, canonical_name="Old village", lgd_code="LGD-77").json()
    assert (free["lgd_level"], free["lgd_snapshot_id"]) == (None, None)


def test_an_lgd_update_never_rewrites_a_place_and_only_adds_a_note(
    owner: ApiClient, tree: dict[str, Any]
) -> None:
    load("2026-02")
    tid = tree["id"]
    village = place(
        owner,
        tid,
        canonical_name="Rampur (Allahabad)",
        place_type="village",
        lgd_code="9900001",
        lgd_level="village",
        district="Allahabad",
        state="Uttar Pradesh",
    ).json()
    district = place(
        owner, tid, canonical_name="Allahabad", place_type="district", lgd_code="9901", lgd_level="district"
    ).json()
    split = place(
        owner, tid, canonical_name="Bhagwatpur", place_type="village", lgd_code="9900003", lgd_level="village"
    ).json()
    with owner_session() as db:
        d5 = FX / "2026-05"
        stage1("2026-05", d5, db)
        importer.import_files(
            db,
            stage=2,
            snapshot="2026-05",
            state="9",
            files=[f(d5 / "villages_9.csv")],
            successors_file=f(d5 / "successors.csv"),
        )
        importer.activate(db, "2026-05", operator="op", accept_large_change=True)
        db.commit()

    v = owner.get(f"/trees/{tid}/places/{village['id']}").json()
    assert (v["canonical_name"], v["district"], v["lgd_snapshot_id"]) == (
        "Rampur (Allahabad)",
        "Allahabad",
        "2026-02",
    )
    assert v["lgd_note"]["kind"] == "ancestor_renamed" and v["lgd_note"]["since"] == "2026-05"
    assert [a["name_en"] for a in v["lgd_note"]["unit"]["ancestors"]] == [
        "Uttar Pradesh",
        "Prayagraj",
        "Phulpur",
    ]
    dn = owner.get(f"/trees/{tid}/places/{district['id']}").json()["lgd_note"]
    assert (dn["kind"], dn["previous_name"], dn["unit"]["name_en"]) == ("renamed", "Allahabad", "Prayagraj")
    sn = owner.get(f"/trees/{tid}/places/{split['id']}").json()["lgd_note"]
    assert sn["kind"] == "retired" and sorted(s["lgd_code"] for s in sn["successors"]) == [
        "9900007",
        "9900008",
    ]

    # re-saving the same pick keeps the old link (and the note); accepting re-links on purpose
    same = owner.patch(
        f"/trees/{tid}/places/{district['id']}", json={"lgd_code": "9901", "lgd_level": "district"}
    ).json()
    assert same["lgd_snapshot_id"] == "2026-02" and same["lgd_note"] is not None
    acc = owner.patch(
        f"/trees/{tid}/places/{district['id']}",
        json={"lgd_accept_current": True, "canonical_name": "Prayagraj"},
    ).json()
    assert (acc["lgd_snapshot_id"], acc["lgd_note"], acc["canonical_name"]) == ("2026-05", None, "Prayagraj")
    assert any(h["name"] == "Allahabad" for h in acc["historical_names"])  # the family's old name is kept
    # a retired code cannot be linked again, a successor can
    assert (
        owner.patch(f"/trees/{tid}/places/{split['id']}", json={"lgd_accept_current": True}).status_code
        == 422
    )
    ok = owner.patch(
        f"/trees/{tid}/places/{split['id']}", json={"lgd_code": "9900007", "lgd_level": "village"}
    ).json()
    assert (ok["lgd_snapshot_id"], ok["lgd_note"]) == ("2026-05", None)
    # typing a code by hand unlinks
    un = owner.patch(f"/trees/{tid}/places/{village['id']}", json={"lgd_code": "LGD 1"}).json()
    assert (un["lgd_level"], un["lgd_snapshot_id"], un["lgd_note"]) == (None, None, None)
    # and a snapshot that places were linked under cannot be discarded
    with owner_session() as db:
        importer.activate(db, "2026-02", operator="op")
        with pytest.raises(ImportRefused, match="place\\(s\\) were linked while 2026-05 was active"):
            importer.discard(db, "2026-05", operator="op")
