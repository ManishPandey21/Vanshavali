"""Astrology profiles (PRS §11): validation, provenance, privacy, branch scope and birth conflicts."""

from __future__ import annotations

from tests.helpers import create_person, exact

CERT_BIRTH = {
    "date": exact(1990, 8, 5),
    "time": {"value": "10:05", "precision": "document_recorded", "source": "birth_certificate"},
    "place_as_recorded": "Pune",
}


def _profile(client, t, pid, **body):  # type: ignore[no-untyped-def]
    return client.post(f"/trees/{t}/people/{pid}/astrology", json=body)


def test_create_list_update_delete_with_vocabulary(owner, tree):
    t = tree["id"]
    p = create_person(owner, t, "Meera", status="living")
    r = _profile(
        owner,
        t,
        p["id"],
        nakshatra="रोहिणी",
        nakshatra_pada=3,
        rashi="Taurus",
        lagna="Kark",
        tithi="Ekadasi",
        paksha="Sukla",
        ayanamsha="Lahiri",
    )
    assert r.status_code == 201, r.text
    prof = r.json()
    assert (prof["nakshatra"], prof["rashi"], prof["lagna"], prof["tithi"], prof["paksha"]) == (
        "Rohini",
        "Vrishabha",
        "Karka",
        "Ekadashi",
        "Shukla",
    )
    assert prof["provenance_kind"] == "entered" and prof["is_preferred"] is True
    assert prof["privacy_level"] == "PRIVATE_TREE_ADMINS"
    assert prof["provenance"]["origin"] == "manual"

    assert _profile(owner, t, p["id"], nakshatra="Pluto").status_code == 422
    assert _profile(owner, t, p["id"], rashi="Ophiuchus").status_code == 422
    assert _profile(owner, t, p["id"], nakshatra="Rohini", nakshatra_pada=5).status_code == 422
    assert _profile(owner, t, p["id"], paksha="full moon").status_code == 422
    assert _profile(owner, t, p["id"], timezone_id="Mars/Olympus").status_code == 422

    # a second chart is kept alongside the first; it becomes preferred only when asked
    r = _profile(owner, t, p["id"], nakshatra="Mrigashira", provenance_kind="imported")
    assert r.status_code == 201 and r.json()["is_preferred"] is False
    second = r.json()["id"]
    assert len(owner.get(f"/trees/{t}/people/{p['id']}/astrology").json()) == 2

    r = owner.patch(f"/trees/{t}/astrology/{second}", json={"is_preferred": True, "rashi": "मिथुन"})
    assert r.status_code == 200 and r.json()["rashi"] == "Mithuna"
    profiles = {x["id"]: x for x in owner.get(f"/trees/{t}/people/{p['id']}/astrology").json()}
    assert profiles[second]["is_preferred"] is True and profiles[prof["id"]]["is_preferred"] is False
    assert owner.patch(f"/trees/{t}/astrology/{second}", json={"nakshatra_pada": 0}).status_code == 422

    assert owner.delete(f"/trees/{t}/astrology/{second}").status_code == 200
    assert owner.get(f"/trees/{t}/astrology/{second}").status_code == 404


def test_calculated_provenance_requires_system_and_ephemeris(owner, tree):
    t = tree["id"]
    p = create_person(owner, t, "Ravi")
    r = _profile(owner, t, p["id"], provenance_kind="calculated", nakshatra="Hasta")
    assert r.status_code == 422
    r = _profile(
        owner,
        t,
        p["id"],
        provenance_kind="calculated",
        nakshatra="Hasta",
        calculation_system="Jagannatha Hora 8.0 (external)",
        ephemeris_version="Swiss Ephemeris 2.10",
        ayanamsha="Chitrapaksha",
        calculation_timestamp="2026-09-01T10:00:00Z",
    )
    assert r.status_code == 201, r.text
    assert r.json()["ayanamsha"] == "Lahiri"
    pid = r.json()["id"]
    r = owner.patch(f"/trees/{t}/astrology/{pid}", json={"ephemeris_version": None})
    assert r.status_code == 422


def test_astrology_privacy_for_viewer(owner, tree, member_factory):
    t = tree["id"]
    living = create_person(owner, t, "Priya", status="living")
    prof = _profile(
        owner,
        t,
        living["id"],
        nakshatra="Swati",
        chart_birth_time={"value": "05:30", "precision": "document_recorded", "source": "kundli"},
    ).json()
    viewer = member_factory(["VIEWER"])
    assert viewer.get(f"/trees/{t}/people/{living['id']}/astrology").json() == []
    assert viewer.get(f"/trees/{t}/astrology/{prof['id']}").status_code == 404
    assert "Swati" not in viewer.get(f"/trees/{t}/people/{living['id']}/birth-conflicts").text
    assert _profile(viewer, t, living["id"], nakshatra="Swati").status_code == 403

    # opening the profile's own level is not enough while the person's astrology group is restricted
    owner.patch(f"/trees/{t}/astrology/{prof['id']}", json={"privacy_level": "TREE_MEMBERS"})
    assert viewer.get(f"/trees/{t}/people/{living['id']}/astrology").json() == []
    owner.put(
        f"/trees/{t}/people/{living['id']}/privacy", json={"field_privacy": {"astrology": "TREE_MEMBERS"}}
    )
    shown = viewer.get(f"/trees/{t}/people/{living['id']}/astrology").json()
    assert [x["nakshatra"] for x in shown] == ["Swati"]
    # birth time stays protected in the conflict view even though astrology is shared
    bc = viewer.get(f"/trees/{t}/people/{living['id']}/birth-conflicts").json()
    assert "05:30" not in str(bc) and "birth_time" in bc["withheld_fields"]

    researcher = member_factory(["RESEARCHER"])
    r = researcher.get(f"/trees/{t}/people/{living['id']}/astrology")
    assert r.status_code == 404 or r.json() == []  # the person (TREE_MEMBERS) is hidden from researchers

    # deceased people inherit the person's level
    dead = create_person(owner, t, "Dada", status="deceased", privacy_level="TREE_MEMBERS")
    _profile(owner, t, dead["id"], rashi="Simha", privacy_level="TREE_MEMBERS")
    assert [x["rashi"] for x in viewer.get(f"/trees/{t}/people/{dead['id']}/astrology").json()] == ["Simha"]


def test_branch_admin_writes_only_inside_branch(owner, tree, member_factory):
    t = tree["id"]
    branch = owner.post(f"/trees/{t}/branches", json={"name": "Pune branch"}).json()
    inside = create_person(owner, t, "Inside", branch_ids=[branch["id"]])
    outside = create_person(owner, t, "Outside")
    admin = member_factory(["BRANCH_ADMIN"], branch_id=branch["id"])
    assert _profile(admin, t, inside["id"], rashi="Tula").status_code == 201
    assert _profile(admin, t, outside["id"], rashi="Tula").status_code == 403
    prof = _profile(owner, t, outside["id"], rashi="Tula", privacy_level="TREE_MEMBERS").json()
    assert admin.delete(f"/trees/{t}/astrology/{prof['id']}").status_code in (403, 404)


def test_birth_conflicts_certificate_vs_kundli(owner, tree):
    t = tree["id"]
    p = create_person(owner, t, "Anil", status="deceased", birth=CERT_BIRTH)
    none = owner.get(f"/trees/{t}/people/{p['id']}/birth-conflicts").json()
    assert none["has_conflicts"] is False and len(none["claims"]) == 1

    # a Kundli that agrees within tolerance raises no alert
    _profile(
        owner,
        t,
        p["id"],
        provenance_kind="uploaded_chart",
        chart_birth_date=exact(1990, 8, 5),
        chart_birth_time={"value": "10:12", "precision": "document_recorded", "source": "kundli"},
        chart_birth_place="Pune, Maharashtra",
    )
    ok = owner.get(f"/trees/{t}/people/{p['id']}/birth-conflicts").json()
    assert ok["has_conflicts"] is False and len(ok["claims"]) == 2

    # a Kundli with a different time and a different day: retain both and alert
    _profile(
        owner,
        t,
        p["id"],
        provenance_kind="uploaded_chart",
        chart_birth_date=exact(1990, 8, 6),
        chart_birth_time={"value": "11:40", "precision": "document_recorded", "source": "kundli"},
        chart_birth_place="Nashik",
        evidence_status="FAMILY_RECOLLECTION",
    )
    out = owner.get(f"/trees/{t}/people/{p['id']}/birth-conflicts").json()
    assert out["has_conflicts"] is True
    fields = {c["field"]: c for c in out["conflicts"]}
    assert set(fields) == {"date", "time", "place"}
    assert len(fields["time"]["values"]) == 3
    kinds = sorted(c["claim_type"] for c in out["claims"])
    assert kinds == ["astrology_profile", "astrology_profile", "event"]
    for c in out["claims"]:
        assert c["provenance"]["origin"] == "manual"
        assert c["evidence_status"]
    # the civil record is still the preferred birth
    events = owner.get(f"/trees/{t}/people/{p['id']}/events", params={"type": "birth"}).json()
    assert len(events) == 1 and events[0]["is_preferred"] is True
