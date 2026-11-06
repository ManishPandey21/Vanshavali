"""Geography reference data (ADR-0019, increment 1): staging and validation, the database-enforced
hierarchy, four-eyes activation, cascade and search in any script, many-to-many PIN codes, retired
and historical codes, diff and rollback, and the boundary with tree data and ordinary users."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.cli import geo as geo_cli
from app.core.config import get_settings
from app.core.ids import uuid7
from app.models import AuditEvent, GeoSnapshot, GeoUnit
from app.models.enums import GeoSnapshotStatus, GeoSource
from app.models.geo import GEO_UNIT_PARENT_SQL, PARENT_LEVELS
from app.modules.geo import importer
from app.modules.geo.importer import GeoImportError, stage
from tests.conftest import owner_session
from tests.test_masterdata_admin import _make_system_admin

FIX = Path(__file__).parent / "fixtures" / "geo"
ADMIN = "/admin/master-data/geo/snapshots"
LICENCE = "Synthetic test data"
ATTRIBUTION = "Vanshavali test fixtures (not official)"


def _stage(source: GeoSource, label: str, path: Path) -> GeoSnapshot:
    with owner_session() as db:
        return stage(
            db,
            source=source,
            label=label,
            path=path,
            licence=LICENCE,
            attribution=ATTRIBUTION,
            staged_by="pytest",
        )


@pytest.fixture
def admins(make_client: Any) -> tuple[Any, Any]:
    return _make_system_admin(make_client()), _make_system_admin(make_client())


def _go_live(admins: tuple[Any, Any], snap: GeoSnapshot) -> None:
    a, b = admins
    r = a.post(f"{ADMIN}/{snap.id}/approve", json={"reason": "Counts and diff checked"})
    assert r.status_code == 200, r.text
    r = b.post(f"{ADMIN}/{snap.id}/activate", json={"reason": "Second review done"})
    assert r.status_code == 200, r.text


@pytest.fixture
def live(admins: tuple[Any, Any]) -> dict[str, GeoSnapshot]:
    lgd = _stage(GeoSource.LGD, "v1", FIX / "lgd_v1.csv")
    _go_live(admins, lgd)
    post = _stage(GeoSource.INDIA_POST, "v1", FIX / "post_v1.csv")
    _go_live(admins, post)
    return {"lgd": lgd, "post": post}


def _codes(resp: Any) -> list[str]:
    assert resp.status_code == 200, resp.text
    return [u["code"] for u in resp.json()["items"]]


# ---------------------------------------------------------------- the hierarchy
def test_parent_table_and_database_trigger_agree():
    sql = {
        m[0]: tuple(re.findall(r"'(\w+)'", m[1]))
        for m in re.findall(r"WHEN '(\w+)' THEN ARRAY\[([^\]]*)\]", GEO_UNIT_PARENT_SQL)
    }
    assert sql == PARENT_LEVELS


def test_the_database_refuses_an_invalid_hierarchy():
    with owner_session() as db:
        s1 = GeoSnapshot(source=GeoSource.LGD, label="a", licence="x", attribution="x")
        s2 = GeoSnapshot(source=GeoSource.LGD, label="b", licence="x", attribution="x")
        db.add_all([s1, s2])
        db.flush()
        india = GeoUnit(id=uuid7(), snapshot_id=s1.id, level="country", code="IN", name_en="India")
        state = GeoUnit(
            id=uuid7(), snapshot_id=s1.id, level="state", code="909", name_en="UP", parent_id=india.id
        )
        db.add(india)
        db.flush()
        db.add(state)
        db.commit()
        bad = [
            {
                "snapshot_id": s1.id,
                "level": "village",
                "code": "1",
                "name_en": "Under a state",
                "parent_id": state.id,
            },
            {
                "snapshot_id": s1.id,
                "level": "district",
                "code": "2",
                "name_en": "No parent",
                "parent_id": None,
            },
            {
                "snapshot_id": s2.id,
                "level": "district",
                "code": "3",
                "name_en": "Other snapshot",
                "parent_id": state.id,
            },
            {
                "snapshot_id": s1.id,
                "level": "country",
                "code": "NP",
                "name_en": "Country under a state",
                "parent_id": state.id,
            },
        ]
        for row in bad:
            db.add(GeoUnit(id=uuid7(), **row))
            with pytest.raises(IntegrityError, match="geo_unit"):
                db.flush()
            db.rollback()


# ---------------------------------------------------------------- staging
def test_staging_validates_counts_and_hides_rows_until_activation(client, owner):
    snap = _stage(GeoSource.LGD, "v1", FIX / "lgd_v1.csv")
    assert snap.status == GeoSnapshotStatus.VALIDATED
    assert snap.report["error_count"] == 0
    assert snap.report["counts"] == {
        "country": 1,
        "state": 2,
        "district": 2,
        "subdistrict": 3,
        "village": 5,
        "town": 1,
    }
    assert snap.report["diff"] == {"previous": None, "added": snap.report["counts"]}
    assert len(snap.files[0]["sha256"]) == 64 and snap.files[0]["rows"] == 14
    # nothing is visible before approval and activation
    r = owner.get("/geo/units")
    assert r.status_code == 200 and r.json() == {"items": [], "next_cursor": None, "snapshot": None}
    assert client.get("/geo/units").status_code == 401


def _write(tmp_path: Path, text: str, name: str = "units.csv") -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


HEADER = ",".join(importer.LGD_HEADER)
BASE = f"{HEADER}\ncountry,IN,,,India,,,,,,,,,\nstate,909,country,IN,Uttar Pradesh,,,,,,,,,\n"


@pytest.mark.parametrize(
    "rows, message",
    [
        ("village,1,state,909,Wrong parent,,,,,,,,,", "needs a parent of level subdistrict"),
        ("district,5,state,999,Orphan,,,,,,,,,", "parent state 999 is not in the file"),
        ("state,909,country,IN,Twice,,,,,,,,,", "duplicate state code 909"),
        ("district,ABC,state,909,Letters,,,,,,,,,", "bad district code"),
        ("district,5,state,909,,,,,,,,,,", "name_en is required"),
        ("district,5,state,909,Bad date,,,,,,,2026-13-01,,", "valid_from must be a date"),
        ("district,5,state,909,Script,,deva,,,,,,,", "ISO 15924"),
        ("district,5,state,909,Too,many,columns,,,,,,,,,,,", "expected 14 columns"),
        ("planet,5,state,909,Mars,,,,,,,,,", "unknown level"),
        ("district,5,state,909,\x07bell,,,,,,,,,", "control characters"),
    ],
)
def test_bad_rows_fail_the_snapshot_and_insert_nothing(tmp_path, rows, message):
    snap = _stage(GeoSource.LGD, "bad", _write(tmp_path, BASE + rows + "\n"))
    assert snap.status == GeoSnapshotStatus.FAILED
    assert any(message in e for e in snap.report["errors"]), snap.report["errors"]
    assert snap.report["diff"] is None
    with owner_session() as db:
        assert db.scalar(select(GeoUnit.id).where(GeoUnit.snapshot_id == snap.id)) is None


def test_a_file_without_a_country_fails(tmp_path):
    snap = _stage(
        GeoSource.LGD, "nocountry", _write(tmp_path, f"{HEADER}\nstate,909,country,IN,UP,,,,,,,,,\n")
    )
    assert snap.status == GeoSnapshotStatus.FAILED
    assert any("no country row" in e for e in snap.report["errors"])


@pytest.mark.parametrize(
    "content, message",
    [
        (b"", "empty"),
        (b"level,code\nstate,1\n", "header must be exactly"),
        (b"\xff\xfe not utf-8", "not valid UTF-8"),
        (HEADER.encode() + b"\n\x00\x01", "binary content"),
    ],
)
def test_unusable_files_are_refused_outright(tmp_path, content, message):
    p = tmp_path / "f.csv"
    p.write_bytes(content)
    with pytest.raises(GeoImportError, match=message):
        _stage(GeoSource.LGD, "x", p)
    with owner_session() as db:
        assert db.scalar(select(GeoSnapshot.id)) is None


def test_size_label_and_source_link_limits(tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "MAX_BYTES", 100)
    with pytest.raises(GeoImportError, match="byte limit"):
        _stage(GeoSource.LGD, "big", FIX / "lgd_v1.csv")
    monkeypatch.undo()
    with owner_session() as db:
        for kw, message in (
            ({"label": "bad label!"}, "label"),
            ({"label": "ok", "source_url": "javascript:alert(1)"}, "source_url"),
        ):
            with pytest.raises(GeoImportError, match=message):
                stage(db, source=GeoSource.LGD, path=FIX / "lgd_v1.csv", licence="x", attribution="x", **kw)
    _stage(GeoSource.LGD, "v1", FIX / "lgd_v1.csv")
    with pytest.raises(GeoImportError, match="already exists"):
        _stage(GeoSource.LGD, "v1", FIX / "lgd_v1.csv")


def test_bad_post_rows(tmp_path):
    header = ",".join(importer.POST_HEADER)
    rows = [
        ("021006,X,,,,,", "bad PIN"),
        ("221006,X,Main,,,,", "office_type"),
        ("221006,X,,Sometimes,,,", "delivery"),
        ("221006,X,,,,,village", "must look like village:123456"),
    ]
    for row, message in rows:
        snap = _stage(
            GeoSource.INDIA_POST,
            f"p{abs(hash(row)) % 10_000}",
            _write(tmp_path, f"{header}\n{row}\n", "p.csv"),
        )
        assert snap.status == GeoSnapshotStatus.FAILED
        assert any(message in e for e in snap.report["errors"]), (row, snap.report["errors"])


# ---------------------------------------------------------------- activation
def test_activation_needs_a_second_admin_and_approval_first(admins, owner, make_client):
    a, b = admins
    snap = _stage(GeoSource.LGD, "v1", FIX / "lgd_v1.csv")
    r = a.post(f"{ADMIN}/{snap.id}/activate", json={"reason": "skip approval"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "snapshot_not_approved"
    assert a.post(f"{ADMIN}/{snap.id}/approve", json={"reason": "Looks right"}).json()["status"] == "approved"
    r = a.post(f"{ADMIN}/{snap.id}/activate", json={"reason": "mine"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "second_admin_required"
    listed = {s["id"]: s for s in b.get(ADMIN).json()}
    assert listed[str(snap.id)]["approved_by_name"] == "Platform Admin"
    r = b.post(f"{ADMIN}/{snap.id}/activate", json={"reason": "Reviewed the report"})
    assert r.status_code == 200 and r.json()["status"] == "active"
    assert _codes(owner.get("/geo/units")) == ["927", "909"]  # Maharashtra, Uttar Pradesh (by name)
    with owner_session() as db:
        actions = [e.action for e in db.scalars(select(AuditEvent).where(AuditEvent.action.like("geo.%")))]
        assert actions == ["geo.snapshot_approved", "geo.snapshot_activated"]
    # failed snapshots cannot be approved
    bad = _stage(GeoSource.INDIA_POST, "bad", FIX / "post_v1.csv")  # valid rows…
    with owner_session() as db:
        db.get(GeoSnapshot, bad.id).status = GeoSnapshotStatus.FAILED  # …but pretend validation failed
        db.commit()
    r = a.post(f"{ADMIN}/{bad.id}/approve", json={"reason": "please"})
    assert r.status_code == 409


ENDPOINTS = [
    ("GET", ADMIN, None),
    ("GET", f"{ADMIN}/0190a1a2-0000-7000-8000-000000000000", None),
    ("POST", f"{ADMIN}/0190a1a2-0000-7000-8000-000000000000/approve", {"reason": "abc"}),
    ("POST", f"{ADMIN}/0190a1a2-0000-7000-8000-000000000000/activate", {"reason": "abc"}),
    ("POST", f"{ADMIN}/0190a1a2-0000-7000-8000-000000000000/rollback", {"reason": "abc"}),
    ("POST", f"{ADMIN}/0190a1a2-0000-7000-8000-000000000000/discard", {"reason": "abc"}),
]


@pytest.mark.parametrize("method, path, body", ENDPOINTS)
def test_ordinary_users_cannot_manage_snapshots(client, owner, tree, make_client, method, path, body):
    assert client.request(method, path, json=body).status_code == 401
    assert owner.request(method, path, json=body).status_code == 404
    no_mfa = _make_system_admin(make_client(), mfa=False)
    r = no_mfa.request(method, path, json=body)
    assert r.status_code == 403 and r.json()["error"]["code"] == "admin_mfa_required"


def test_operator_activation_needs_an_approved_snapshot(admins, capsys):
    a, _ = admins
    snap = _stage(GeoSource.LGD, "v1", FIX / "lgd_v1.csv")
    args = ["activate", "--snapshot", str(snap.id), "--reason", "pilot go-live", "--operator", "Ops on call"]
    assert geo_cli.main(args) == 1
    a.post(f"{ADMIN}/{snap.id}/approve", json={"reason": "Reviewed"})
    assert geo_cli.main(args) == 0
    with owner_session() as db:
        ev = db.scalar(select(AuditEvent).where(AuditEvent.action == "geo.snapshot_activated_by_operator"))
        assert ev is not None and ev.actor_user_id is None and ev.details["operator"] == "Ops on call"
        assert db.get(GeoSnapshot, snap.id).status == GeoSnapshotStatus.ACTIVE


# ---------------------------------------------------------------- lookups
def test_cascade_state_district_subdistrict_village(owner, live):
    assert _codes(owner.get("/geo/units", params={"parent_level": "country", "parent_code": "IN"})) == [
        "927",
        "909",
    ]
    up = owner.get("/geo/units", params={"parent_level": "state", "parent_code": "909"}).json()
    assert [u["name_en"] for u in up["items"]] == ["Varanasi"]
    assert up["snapshot"] == {"source": "lgd", "label": "v1", "licence": LICENCE, "attribution": ATTRIBUTION}
    tehsils = owner.get("/geo/units", params={"parent_level": "district", "parent_code": "90187"}).json()[
        "items"
    ]
    # a town can sit directly under a district; the sub-districts carry the state's local term
    assert [(u["level"], u["name_en"]) for u in tehsils] == [
        ("subdistrict", "Pindra"),
        ("town", "Varanasi"),
        ("subdistrict", "Varanasi Sadar"),
    ]
    assert tehsils[0]["local_term"] == "Tehsil"
    only = owner.get(
        "/geo/units", params={"parent_level": "district", "parent_code": "90187", "level": "subdistrict"}
    )
    assert _codes(only) == ["90901", "90902"]
    villages = owner.get("/geo/units", params={"parent_level": "subdistrict", "parent_code": "90901"}).json()[
        "items"
    ]
    assert [v["name_en"] for v in villages] == ["Babatpur", "Phulpur"]
    assert [p["name_en"] for p in villages[0]["path"]] == ["Uttar Pradesh", "Varanasi", "Pindra"]
    taluka = owner.get("/geo/units", params={"parent_level": "district", "parent_code": "90520"}).json()[
        "items"
    ]
    assert taluka[0]["local_term"] == "Taluka"
    # a parent that does not exist, or half a parent
    assert owner.get("/geo/units", params={"parent_level": "district", "parent_code": "1"}).status_code == 404
    assert owner.get("/geo/units", params={"parent_level": "district"}).status_code == 422
    # listing every village in India is refused; a search is fine
    r = owner.get("/geo/units", params={"level": "village"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "search_too_broad"
    assert _codes(owner.get("/geo/units", params={"level": "village", "q": "babat"})) == ["9100001"]


@pytest.mark.parametrize(
    "q, expected",
    [
        # a word prefix: Varanasi Sadar matches too
        ("वाराणसी", {("district", "90187"), ("town", "9300001"), ("subdistrict", "90902")}),
        ("banaras", {("district", "90187")}),
        ("Benares", {("district", "90187")}),
        ("kashi", {("district", "90187")}),
        ("poona", {("district", "90520")}),
        ("United Prov", {("state", "909")}),
        ("sheopur", {("village", "9100003")}),
        # शिवपुर romanises with its inherent vowel ("shivapura"), so both Shivpur and Shivapur match
        ("shivapur", {("village", "9200001"), ("village", "9100003")}),
        ("खेड", {("village", "9200001")}),
        ("%", set()),
        ("zzzz", set()),
    ],
)
def test_search_in_any_script_spelling_alias_or_former_name(owner, live, q, expected):
    r = owner.get("/geo/units", params={"q": q})
    assert r.status_code == 200, r.text
    assert {(u["level"], u["code"]) for u in r.json()["items"]} == expected


def test_pincode_maps_to_many_offices_and_places(owner, live):
    r = owner.get("/geo/pincodes/221006")
    assert r.status_code == 200
    body = r.json()
    assert [o["office_name"] for o in body["offices"]] == ["Babatpur B.O", "Phulpur S.O"]
    assert [u["name_en"] for u in body["offices"][0]["units"]] == ["Babatpur", "Phulpur"]
    # the same village is served by both offices; a PIN is not a village
    assert [u["code"] for u in body["offices"][1]["units"]] == ["9100002"]
    assert body["offices"][0]["units"][0]["path"][-1]["name_en"] == "Pindra"
    shivpur = owner.get("/geo/pincodes/221003").json()["offices"][0]
    assert {u["level"] for u in shivpur["units"]} == {"village", "town"}
    # a unit the LGD snapshot does not know is left out (and was reported as a warning when staged)
    khed = owner.get("/geo/pincodes/412205").json()["offices"][0]
    assert khed["delivery"] is False and [u["code"] for u in khed["units"]] == ["9200001"]
    assert any("9999999" in w for w in live["post"].report["warnings"])
    assert owner.get("/geo/pincodes/000001").status_code == 422
    assert owner.get("/geo/pincodes/110001").json()["offices"] == []


def test_historical_units_resolve_but_are_not_offered(owner, live):
    sadar = owner.get("/geo/units", params={"parent_level": "subdistrict", "parent_code": "90902"})
    assert _codes(sadar) == ["9100003"]
    with_old = owner.get(
        "/geo/units",
        params={"parent_level": "subdistrict", "parent_code": "90902", "include_historical": "true"},
    ).json()["items"]
    old = next(u for u in with_old if u["code"] == "9100004")
    assert old["status"] == "historical" and old["successor_codes"] == ["9100003"]
    one = owner.get("/geo/units/village/9100004").json()
    assert one["status"] == "historical" and one["valid_to"] == "1991-03-31"
    assert owner.get("/geo/units/village/1").status_code == 404
    assert owner.get("/geo/units/village/<script>").status_code in (404, 422)


def test_a_new_snapshot_reports_its_diff_retires_codes_and_can_be_rolled_back(admins, owner, live):
    a, b = admins
    v2 = _stage(GeoSource.LGD, "v2", FIX / "lgd_v2.csv")
    diff = v2.report["diff"]
    assert diff["previous"] == "v1"
    assert diff["added"] == {"village": 1}
    assert diff["retired"] == {"village": 2}
    assert diff["moved"] == {"village": 1}
    assert diff["renamed"] == {"village": 1}
    assert "village 9100002 Phulpur" in diff["samples"]["retired"]
    _go_live(admins, v2)
    # a code dropped by the new snapshot still resolves, marked retired
    gone = owner.get("/geo/units/village/9100002").json()
    assert gone["status"] == "retired" and gone["name_en"] == "Phulpur"
    assert [p["name_en"] for p in gone["path"]] == ["Uttar Pradesh", "Varanasi", "Pindra"]
    assert "9100002" not in _codes(
        owner.get("/geo/units", params={"parent_level": "subdistrict", "parent_code": "90901"})
    )
    moved = owner.get("/geo/units/village/9100003").json()
    assert moved["path"][-1]["code"] == "90901"
    # the former name still finds the renamed village
    assert _codes(owner.get("/geo/units", params={"q": "Khed Shivapur"})) == ["9200001"]
    # the old snapshot is kept; it can be restored by one admin, never discarded
    listed = {s["label"]: s for s in a.get(ADMIN).json() if s["source"] == "lgd"}
    assert listed["v1"]["status"] == "superseded" and listed["v2"]["status"] == "active"
    r = a.post(f"{ADMIN}/{listed['v1']['id']}/discard", json={"reason": "tidy up"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "snapshot_kept"
    r = a.post(f"{ADMIN}/{listed['v1']['id']}/rollback", json={"reason": "v2 broke a district"})
    assert r.status_code == 200 and r.json()["status"] == "active"
    assert owner.get("/geo/units/village/9100002").json()["status"] == "current"
    assert b.get(f"{ADMIN}/{listed['v2']['id']}").json()["status"] == "superseded"
    assert (
        b.post(f"{ADMIN}/{listed['v2']['id']}/rollback", json={"reason": "again"}).json()["status"]
        == "active"
    )


def test_unused_snapshots_can_be_discarded(admins, tmp_path):
    a, _ = admins
    failed = _stage(GeoSource.LGD, "bad", _write(tmp_path, BASE + "village,1,state,909,x,,,,,,,,,\n"))
    ok = _stage(GeoSource.LGD, "ok", FIX / "lgd_v1.csv")
    for snap in (failed, ok):
        r = a.post(f"{ADMIN}/{snap.id}/discard", json={"reason": "Wrong file"})
        assert r.status_code == 204
    with owner_session() as db:
        assert db.scalar(select(GeoSnapshot.id)) is None and db.scalar(select(GeoUnit.id)) is None
    assert a.post(f"{ADMIN}/{ok.id}/discard", json={"reason": "again"}).status_code == 404
    assert a.post(f"{ADMIN}/{ok.id}/approve", json={"reason": "x"}).status_code == 422  # reason too short


# ---------------------------------------------------------------- the boundary with family data
def test_a_family_place_names_a_unit_by_level_and_code(owner, tree, live, admins):
    t = tree["id"]
    body = {
        "canonical_name": "Babatpur",
        "place_type": "village",
        "lgd_level": "village",
        "lgd_code": "9100001",
        "district": "Varanasi",
        "state": "Uttar Pradesh",
        "country": "India",
    }
    r = owner.post(f"/trees/{t}/places", json=body)
    assert r.status_code == 201, r.text
    place = r.json()
    assert (place["lgd_level"], place["lgd_code"]) == ("village", "9100001")
    assert (
        owner.post(f"/trees/{t}/places", json={"canonical_name": "X", "lgd_level": "village"}).status_code
        == 422
    )
    assert (
        owner.post(
            f"/trees/{t}/places", json={"canonical_name": "X", "lgd_level": "galaxy", "lgd_code": "1"}
        ).status_code
        == 422
    )
    # a historical, unlisted or foreign place stays free text
    free = owner.post(
        f"/trees/{t}/places", json={"canonical_name": "Lyallpur (pre-1947)", "place_type": "town"}
    )
    assert free.status_code == 201 and free.json()["lgd_level"] is None
    # system admins manage the snapshots but still cannot see any family's places
    a, _ = admins
    assert a.get(f"/trees/{t}/places").status_code == 404
    # and the snapshot list carries reference data only: no tree, place or person fields
    assert all(not k.startswith(("tree", "place", "person")) for snap in a.get(ADMIN).json() for k in snap)


def test_rate_limit_and_feature_flag(owner, live, monkeypatch):
    monkeypatch.setattr(get_settings(), "geo_rate_limit_per_minute", 3)
    for _ in range(3):
        assert owner.get("/geo/units").status_code == 200
    assert owner.get("/geo/units").status_code == 429
    monkeypatch.setattr(get_settings(), "geo_rate_limit_per_minute", 1000)
    monkeypatch.setattr(get_settings(), "geo_enabled", False)
    assert owner.get("/geo/units").status_code == 404
    assert owner.get("/geo/pincodes/221006").status_code == 404


def test_synthetic_generator_produces_a_valid_snapshot(tmp_path, capsys):
    out, post = tmp_path / "u.csv", tmp_path / "p.csv"
    assert geo_cli.main(["synth", "--villages", "500", "--out", str(out), "--offices-out", str(post)]) == 0
    rc = geo_cli.main(
        [
            "stage",
            "--source",
            "lgd",
            "--label",
            "synth",
            "--file",
            str(out),
            "--licence",
            "x",
            "--attribution",
            "x",
        ]
    )
    assert rc == 0, capsys.readouterr()
    rc = geo_cli.main(
        [
            "stage",
            "--source",
            "india_post",
            "--label",
            "synth",
            "--file",
            str(post),
            "--licence",
            "x",
            "--attribution",
            "x",
        ]
    )
    assert rc == 0, capsys.readouterr()
    assert "validated" in capsys.readouterr().out
