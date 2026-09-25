"""Ancestral property module (PRS §17, §37; ADR-0010)."""

from __future__ import annotations

import uuid
from fractions import Fraction
from typing import Any

from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.models import AuditEvent, Document, DocumentLink
from app.modules.property.schemas import LEGAL_NOTICE
from app.modules.property.shares import find_violations
from tests.conftest import new_tree
from tests.helpers import create_person

YEAR = {"precision": "year_only"}


def year(y: int) -> dict[str, Any]:
    return {**YEAR, "year": y}


def make_property(client: Any, t: str, **kw: Any) -> dict[str, Any]:
    body = {
        "property_type": "agricultural_land",
        "classification": "ancestral",
        "display_name": "Khet at Rampur",
    }
    body.update(kw)
    r = client.post(f"/trees/{t}/properties", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def add_parcel(client: Any, t: str, pid: str, **kw: Any) -> dict[str, Any]:
    r = client.post(f"/trees/{t}/properties/{pid}/parcels", json=kw)
    assert r.status_code == 201, r.text
    return r.json()


def add_interest(client: Any, t: str, pid: str, **kw: Any) -> Any:
    return client.post(f"/trees/{t}/properties/{pid}/interests", json=kw)


def make_branch(client: Any, t: str, name: str) -> str:
    r = client.post(f"/trees/{t}/branches", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def insert_document(
    t: str,
    title: str,
    *,
    category: str = "partition_deed",
    privacy: str = "TREE_MEMBERS",
    link_to: tuple | None = None,
) -> str:
    """The documents API is built separately; simulate an uploaded deed directly."""
    with get_sessionmaker()() as db:
        doc = Document(
            tree_id=uuid.UUID(t),
            category=category,
            storage_class="STANDARD",
            title=title,
            original_filename="deed.pdf",
            mime_type="application/pdf",
            size_bytes=1024,
            checksum_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            storage_key=f"test/{uuid.uuid4()}",
            encryption_key_id="test-key",
            privacy_level=privacy,
            scan_status="clean",
        )
        db.add(doc)
        db.flush()
        if link_to:
            db.add(
                DocumentLink(
                    tree_id=uuid.UUID(t),
                    document_id=doc.id,
                    target_type=link_to[0],
                    target_id=uuid.UUID(link_to[1]),
                )
            )
        db.commit()
        return str(doc.id)


def audit_actions(t: str) -> list[str]:
    with get_sessionmaker()() as db:
        return list(
            db.scalars(
                select(AuditEvent.action).where(
                    AuditEvent.tree_id == uuid.UUID(t), AuditEvent.action.like("property.%")
                )
            )
        )


# ---------------------------------------------------------------- full flow
def test_full_flow_partition_timeline_lineage(owner, tree):
    t = tree["id"]
    # 1. create property
    prop = make_property(owner, t)
    pid = prop["id"]
    assert prop["legal_notice"] == LEGAL_NOTICE
    assert prop["privacy_level"] == "PRIVATE_TREE_ADMINS"
    # 2. add parcel with Indian identifiers and a regionally variable unit
    parcel = add_parcel(
        owner,
        t,
        pid,
        state_or_ut="Uttar Pradesh",
        district="Varanasi",
        village="Rampur",
        khasra_or_gata_number="123",
        khatauni_number="45",
        area="12.5",
        area_unit="bigha",
        extra_identifiers={"fasli_year": "1383", "gata_serial": 7},
    )
    assert parcel["label"] == "Khasra/Gata 123 (Rampur)"
    assert parcel["area"] == "12.5000" or float(parcel["area"]) == 12.5
    assert parcel["area_sq_m"] is None and "Regionally variable" in parcel["area_conversion_note"]
    assert parcel["extra_identifiers"]["gata_serial"] == 7
    # 3. link a deceased ancestor as documented owner from 1930
    anc = create_person(
        owner,
        t,
        "Ramdhan",
        "Mishra",
        status="deceased",
        death={"date": {"precision": "exact", "year": 1975, "month": 3, "day": 2}},
    )
    death_event = anc["death"]["event_id"]
    r = add_interest(
        owner,
        t,
        pid,
        holder_type="person",
        holder_person_id=anc["id"],
        interest_type="owner",
        share_numerator=1,
        share_denominator=1,
        valid_from=year(1930),
        status="documented",
    )
    assert r.status_code == 201, r.text
    anc_interest = r.json()
    assert anc_interest["share"] == "1/1" and anc_interest["counts_toward_whole"] is True
    assert anc_interest["holder"]["display_name"] == "Ramdhan Mishra"
    # 4. a partition deed exists as a document (inserted directly), also linked to the property
    deed = insert_document(t, "Batwara deed 1976", link_to=("property", pid))
    # 5. partition among three branches, 1/3 each, after the ancestor's death
    branches = [make_branch(owner, t, n) for n in ("Elder branch", "Middle branch", "Younger branch")]
    r = owner.post(
        f"/trees/{t}/properties/{pid}/partition",
        json={
            "date": year(1976),
            "description": "Family partition after the death of Ramdhan",
            "related_event_id": death_event,
            "document_ids": [deed],
            "allocations": [
                {
                    "holder_type": "family_branch",
                    "holder_branch_id": b,
                    "share_numerator": 1,
                    "share_denominator": 3,
                }
                for b in branches
            ],
        },
    )
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["type"] == "partition" and ev["legal_notice"] == LEGAL_NOTICE
    assert [i["id"] for i in ev["interests_ended"]] == [anc_interest["id"]]
    assert ev["interests_ended"][0]["status"] == "transferred"
    assert ev["interests_ended"][0]["valid_to"]["year"] == 1976
    assert sorted(i["share"] for i in ev["interests_created"]) == ["1/3"] * 3
    assert {i["interest_type"] for i in ev["interests_created"]} == {"co_owner"}
    assert ev["related_event"]["type"] == "death" and ev["related_event"]["principal"]["id"] == anc["id"]
    assert [d["id"] for d in ev["documents"]] == [deed]
    assert "storage_key" not in r.text and "checksum" not in r.text
    # 6. timeline
    tl = owner.get(f"/trees/{t}/properties/{pid}/timeline").json()
    assert tl["legal_notice"] == LEGAL_NOTICE
    assert [e["type"] for e in tl["events"]] == ["partition"]
    assert {d["id"] for d in tl["documents"]} == {deed}  # property-level link
    assert sorted(i["holder"]["display_name"] for i in tl["current_interests"]) == [
        "Elder branch",
        "Middle branch",
        "Younger branch",
    ]
    # holders_at: before and after the partition
    before = owner.get(f"/trees/{t}/properties/{pid}/timeline", params={"at": "1950-06-01"}).json()[
        "holders_at"
    ]
    assert [i["id"] for i in before["interests"]] == [anc_interest["id"]]
    assert before["documented_share_total"] == "1/1"
    after = owner.get(f"/trees/{t}/properties/{pid}/timeline", params={"at": "1980-01-01"}).json()[
        "holders_at"
    ]
    assert len(after["interests"]) == 3 and after["documented_share_total"] == "1/1"
    assert after["has_overlapping_claims"] is False
    assert owner.get(f"/trees/{t}/properties/{pid}/timeline", params={"at": "not-a-date"}).status_code == 422
    # 7. lineage: each branch traces back through the partition to the first acquirer
    lin = owner.get(f"/trees/{t}/properties/{pid}/lineage").json()
    assert lin["legal_notice"] == LEGAL_NOTICE
    assert len(lin["chains"]) == 3
    for chain in lin["chains"]:
        assert [s["type"] for s in chain["steps"]] == ["partition"]
        assert [o["id"] for o in chain["origin_interests"]] == [anc_interest["id"]]
        assert chain["first_acquirers"][0]["person_id"] == anc["id"]
    assert [h["person_id"] for h in lin["first_acquirers"]] == [anc["id"]]
    assert [p["id"] for p in lin["partitions"]] == [ev["id"]]
    assert lin["partitions"][0]["documents"][0]["title"] == "Batwara deed 1976"
    # 8. detail counts and person's interests
    detail = owner.get(f"/trees/{t}/properties/{pid}").json()
    assert detail["counts"]["events"] == 1 and detail["counts"]["interests"] == 4
    assert detail["counts"]["documents"] == 1 and detail["documented_share_total"] == "1/1"
    mine = owner.get(f"/trees/{t}/people/{anc['id']}/property-interests").json()
    assert mine["legal_notice"] == LEGAL_NOTICE
    assert [(i["property"]["id"], i["interest"]["status"]) for i in mine["items"]] == [(pid, "transferred")]
    # 9. audit trail, no sensitive values
    actions = audit_actions(t)
    for a in (
        "property.created",
        "property.parcel_added",
        "property.interest_changed",
        "property.event_recorded",
        "property.partition_recorded",
    ):
        assert a in actions
    with get_sessionmaker()() as db:
        details = [
            e.details for e in db.scalars(select(AuditEvent).where(AuditEvent.action.like("property.%")))
        ]
    assert "Ramdhan" not in str(details) and "1/3" not in str(details) and "123" not in str(details)


# ---------------------------------------------------------------- shares
def test_fraction_exactness():
    from types import SimpleNamespace

    from app.models.enums import InterestStatus, InterestType

    assert Fraction(1, 3) + Fraction(1, 3) + Fraction(1, 3) == 1
    assert 0.1 + 0.2 != 0.3  # why shares are never floats

    def mk(n: int, d: int, parcel: Any = None) -> Any:
        return SimpleNamespace(
            id=uuid.uuid4(),
            parcel_id=parcel,
            interest_type=InterestType.CO_OWNER,
            status=InterestStatus.DOCUMENTED,
            share_numerator=n,
            share_denominator=d,
            valid_from_sort=None,
            valid_to_sort=None,
        )

    assert find_violations([mk(1, 3), mk(1, 3), mk(1, 3)]) == []
    assert find_violations([mk(1, 7), mk(2, 7), mk(4, 7)]) == []
    assert find_violations([mk(333333, 1000000)] * 3 + [mk(1, 1000000)]) == []
    v = find_violations([mk(1, 3), mk(1, 3), mk(1, 3), mk(1, 10**12)])
    assert len(v) == 1 and v[0].total == Fraction(1, 1) + Fraction(1, 10**12)
    parcel = uuid.uuid4()
    v = find_violations([mk(1, 2), mk(2, 3, parcel)])
    assert v[0].scope == "parcel" and v[0].parcel_id == parcel


def test_shares_exceed_whole_rejected_but_disputes_overlap(owner, tree):
    t = tree["id"]
    pid = make_property(owner, t)["id"]
    a = create_person(owner, t, "Hari")
    b = create_person(owner, t, "Shyam")
    c = create_person(owner, t, "Mohan")

    def interest(person: str, n: int, d: int, status: str = "documented", **kw: Any) -> Any:
        return add_interest(
            owner,
            t,
            pid,
            holder_type="person",
            holder_person_id=person,
            interest_type="co_owner",
            share_numerator=n,
            share_denominator=d,
            status=status,
            valid_from=year(1990),
            **kw,
        )

    for person in (a, b, c):
        assert interest(person["id"], 1, 3).status_code == 201
    extra = create_person(owner, t, "Claimant")
    r = interest(extra["id"], 1, 1_000_000)
    assert r.status_code == 422 and r.json()["error"]["code"] == "shares_exceed_whole"
    viol = r.json()["error"]["details"]["violations"][0]
    assert viol["total"] == "1000001/1000000" and viol["scope"] == "property"
    # a disputed (or asserted) claim may overlap — that is how disputes appear
    r = interest(extra["id"], 1, 2, status="disputed")
    assert r.status_code == 201, r.text
    assert r.json()["counts_toward_whole"] is False
    assert interest(extra["id"], 1, 4, status="asserted").status_code == 201
    detail = owner.get(f"/trees/{t}/properties/{pid}").json()
    assert detail["has_overlapping_claims"] is True and detail["documented_share_total"] == "1/1"
    # promoting the disputed claim to documented breaks the invariant
    disputed_id = next(i for i in detail["current_interests"] if i["status"] == "disputed")["id"]
    r = owner.patch(f"/trees/{t}/properties/{pid}/interests/{disputed_id}", json={"status": "documented"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "shares_exceed_whole"
    # an event creating a documented interest that overflows is rejected atomically
    r = owner.post(
        f"/trees/{t}/properties/{pid}/events",
        json={
            "type": "purchase",
            "date": year(2000),
            "creates_interests": [
                {
                    "holder_type": "entity",
                    "holder_name": "Co-op Society",
                    "share_numerator": 1,
                    "share_denominator": 2,
                }
            ],
        },
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "shares_exceed_whole"
    assert owner.get(f"/trees/{t}/properties/{pid}").json()["counts"]["events"] == 0
    # ...but a sale that ends a share and creates an equal one is fine
    ids = [i["id"] for i in detail["current_interests"] if i["holder"]["person_id"] == a["id"]]
    r = owner.post(
        f"/trees/{t}/properties/{pid}/events",
        json={
            "type": "sale",
            "date": year(2000),
            "ends_interest_ids": ids,
            "creates_interests": [
                {
                    "holder_type": "entity",
                    "holder_name": "Co-op Society",
                    "interest_type": "co_owner",
                    "share_numerator": 2,
                    "share_denominator": 6,
                }
            ],
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["interests_created"][0]["share"] == "1/3"
    # parcel-scoped: property-wide shares also cover each parcel
    parcel = add_parcel(owner, t, pid, survey_number="77")
    r = add_interest(
        owner,
        t,
        pid,
        holder_type="unknown",
        share_numerator=1,
        share_denominator=5,
        status="documented",
        parcel_id=parcel["id"],
        valid_from=year(2005),
    )
    assert r.status_code == 422
    assert r.json()["error"]["details"]["violations"][0]["scope"] == "parcel"


def test_event_validation(owner, tree, make_client):
    t = tree["id"]
    pid = make_property(owner, t)["id"]
    p = create_person(owner, t, "Dinesh")
    i = add_interest(
        owner,
        t,
        pid,
        holder_type="person",
        holder_person_id=p["id"],
        status="documented",
        valid_from=year(1950),
    ).json()
    # changing interests needs a dated event
    r = owner.post(
        f"/trees/{t}/properties/{pid}/events", json={"type": "gift", "ends_interest_ids": [i["id"]]}
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "event_date_required"
    # related genealogy event must exist in this tree
    r = owner.post(
        f"/trees/{t}/properties/{pid}/events",
        json={"type": "succession", "related_event_id": str(uuid.uuid4())},
    )
    assert r.status_code == 404
    # relinquishment defaults the ended status to relinquished
    r = owner.post(
        f"/trees/{t}/properties/{pid}/events",
        json={"type": "relinquishment", "date": year(1960), "ends_interest_ids": [i["id"]]},
    )
    assert r.status_code == 201, r.text
    assert r.json()["interests_ended"][0]["status"] == "relinquished"
    # cannot end twice
    r = owner.post(
        f"/trees/{t}/properties/{pid}/events",
        json={"type": "sale", "date": year(1961), "ends_interest_ids": [i["id"]]},
    )
    assert r.status_code == 409
    lin = owner.get(f"/trees/{t}/properties/{pid}/lineage").json()
    assert lin["transfers_out"][0]["from_holders"][0]["person_id"] == p["id"]
    # descriptive patch on an event
    ev_id = lin["transfers_out"][0]["event"]["id"]
    r = owner.patch(
        f"/trees/{t}/properties/{pid}/events/{ev_id}", json={"registration_number": "REG-12/1960"}
    )
    assert r.status_code == 200 and r.json()["registration_number"] == "REG-12/1960"
    # holder must exist in the same tree
    r = add_interest(owner, t, pid, holder_type="person", holder_person_id=str(uuid.uuid4()))
    assert r.status_code == 404
    r = add_interest(owner, t, pid, holder_type="family_branch", holder_branch_id=str(uuid.uuid4()))
    assert r.status_code == 404
    r = add_interest(owner, t, pid, holder_type="person")
    assert r.status_code == 422
    r = add_interest(owner, t, pid, holder_type="unknown", share_numerator=3, share_denominator=2)
    assert r.status_code == 422


def test_partition_balance_rule(owner, tree):
    t = tree["id"]
    pid = make_property(owner, t)["id"]
    anc = create_person(owner, t, "Balram")
    add_interest(
        owner,
        t,
        pid,
        holder_type="person",
        holder_person_id=anc["id"],
        status="documented",
        valid_from=year(1900),
    )
    kids = [create_person(owner, t, n) for n in ("K1", "K2")]
    alloc = [
        {"holder_type": "person", "holder_person_id": k["id"], "share_numerator": 1, "share_denominator": 3}
        for k in kids
    ]
    r = owner.post(f"/trees/{t}/properties/{pid}/partition", json={"date": year(1950), "allocations": alloc})
    assert r.status_code == 422 and r.json()["error"]["code"] == "allocation_mismatch"
    assert r.json()["error"]["details"]["mismatches"][0] == {
        "parcel_id": None,
        "allocated": "2/3",
        "ended": "1/1",
    }
    r = owner.post(
        f"/trees/{t}/properties/{pid}/partition",
        json={"date": year(1950), "allocations": alloc, "allow_partial": True},
    )
    assert r.status_code == 201, r.text
    assert len(r.json()["interests_created"]) == 2
    # partition by parcels: each parcel's allocation must equal the property-wide share ended
    pid2 = make_property(owner, t, display_name="Bagicha")["id"]
    p1 = add_parcel(owner, t, pid2, plot_number="1")
    p2 = add_parcel(owner, t, pid2, plot_number="2")
    add_interest(
        owner,
        t,
        pid2,
        holder_type="person",
        holder_person_id=anc["id"],
        status="documented",
        valid_from=year(1900),
    )
    by_parcel = [
        {
            "holder_type": "person",
            "holder_person_id": kids[0]["id"],
            "share_numerator": 1,
            "share_denominator": 1,
            "parcel_id": p1["id"],
        },
    ]
    r = owner.post(
        f"/trees/{t}/properties/{pid2}/partition", json={"date": year(1950), "allocations": by_parcel}
    )
    assert r.status_code == 422  # plot 2 left unallocated
    by_parcel.append({**by_parcel[0], "holder_person_id": kids[1]["id"], "parcel_id": p2["id"]})
    r = owner.post(
        f"/trees/{t}/properties/{pid2}/partition", json={"date": year(1950), "allocations": by_parcel}
    )
    assert r.status_code == 201, r.text
    assert {i["interest_type"] for i in r.json()["interests_created"]} == {"owner"}
    assert {p["id"] for p in r.json()["parcels"]} == {p1["id"], p2["id"]}


# ---------------------------------------------------------------- authorisation
def test_visibility_rules(owner, tree, member_factory):
    t = tree["id"]
    prop = make_property(owner, t)
    pid = prop["id"]
    add_parcel(owner, t, pid, khasra_or_gata_number="998")
    contributor = member_factory(["CONTRIBUTOR"], name="Contrib")
    viewer = member_factory(["VIEWER"], name="Viewer")
    researcher = member_factory(["RESEARCHER"], name="Researcher")
    # default PRIVATE_TREE_ADMINS: hidden from everyone but admins/custodians
    for c in (contributor, viewer, researcher):
        assert c.get(f"/trees/{t}/properties").json() == []
        assert c.get(f"/trees/{t}/properties/{pid}").status_code == 404
        assert c.get(f"/trees/{t}/properties/{pid}/timeline").status_code == 404
        assert c.post(f"/trees/{t}/properties/{pid}/parcels", json={"plot_number": "1"}).status_code == 404
        hits = c.get(f"/trees/{t}/search", params={"q": "998"}).json()["hits"]
        assert not [h for h in hits if h["kind"] == "property"]
    hits = owner.get(f"/trees/{t}/search", params={"q": "998", "kinds": "property"}).json()["hits"]
    assert hits[0]["id"] == pid and "khasra" in hits[0]["match_reason"]
    # shared with tree members: contributors read (not write); viewers/researchers still not
    assert (
        owner.patch(f"/trees/{t}/properties/{pid}", json={"privacy_level": "TREE_MEMBERS"}).status_code == 200
    )
    assert [p["id"] for p in contributor.get(f"/trees/{t}/properties").json()] == [pid]
    got = contributor.get(f"/trees/{t}/properties/{pid}").json()
    assert got["can_edit"] is False and got["legal_notice"] == LEGAL_NOTICE
    assert contributor.patch(f"/trees/{t}/properties/{pid}", json={"display_name": "X"}).status_code == 403
    assert (
        contributor.post(
            f"/trees/{t}/properties", json={"property_type": "house", "display_name": "H"}
        ).status_code
        == 403
    )
    assert viewer.get(f"/trees/{t}/properties/{pid}").status_code == 404
    # even at INVITED_RESEARCHER, researchers need an explicit grant (no property.read)
    owner.patch(f"/trees/{t}/properties/{pid}", json={"privacy_level": "INVITED_RESEARCHER"})
    assert researcher.get(f"/trees/{t}/properties/{pid}").status_code == 404
    # explicit grant: viewer sees it, cannot write (403)
    owner.patch(f"/trees/{t}/properties/{pid}", json={"privacy_level": "PRIVATE_TREE_ADMINS"})
    r = owner.post(
        f"/trees/{t}/grants",
        json={
            "user_id": viewer.user["id"],
            "resource_type": "property",
            "resource_id": pid,
            "permission": "view",
        },
    )
    assert r.status_code == 201, r.text
    assert viewer.get(f"/trees/{t}/properties/{pid}").status_code == 200
    assert [p["id"] for p in viewer.get(f"/trees/{t}/properties").json()] == [pid]
    assert viewer.post(f"/trees/{t}/properties/{pid}/parcels", json={"plot_number": "1"}).status_code == 403
    assert researcher.get(f"/trees/{t}/properties/{pid}").status_code == 404
    # contributor cannot see linked private documents' metadata on a shared property
    owner.patch(f"/trees/{t}/properties/{pid}", json={"privacy_level": "TREE_MEMBERS"})
    insert_document(t, "Admin-only deed", privacy="PRIVATE_TREE_ADMINS", link_to=("property", pid))
    insert_document(
        t, "Shared khatauni", category="khatauni", privacy="TREE_MEMBERS", link_to=("property", pid)
    )
    tl = contributor.get(f"/trees/{t}/properties/{pid}/timeline").json()
    assert [d["title"] for d in tl["documents"]] == ["Shared khatauni"] and tl["hidden_document_count"] == 1
    assert len(owner.get(f"/trees/{t}/properties/{pid}/timeline").json()["documents"]) == 2


def test_hidden_holders_and_person_interests(owner, tree, member_factory):
    t = tree["id"]
    pid = make_property(owner, t, privacy_level="TREE_MEMBERS")["id"]
    secret = create_person(owner, t, "Private", privacy_level="PRIVATE_TREE_ADMINS")
    add_interest(owner, t, pid, holder_type="person", holder_person_id=secret["id"], status="documented")
    contributor = member_factory(["CONTRIBUTOR"])
    detail = contributor.get(f"/trees/{t}/properties/{pid}").json()
    holder = detail["current_interests"][0]["holder"]
    assert holder["hidden"] is True and holder["person_id"] is None and holder["person"] is None
    assert secret["id"] not in str(detail)
    assert contributor.get(f"/trees/{t}/people/{secret['id']}/property-interests").status_code == 404
    # contributors cannot record a holder they cannot see (and cannot write anyway)
    public_person = create_person(owner, t, "Visible", privacy_level="TREE_MEMBERS")
    other = make_property(owner, t, display_name="Private plot")  # PRIVATE_TREE_ADMINS
    add_interest(owner, t, other["id"], holder_type="person", holder_person_id=public_person["id"])
    add_interest(owner, t, pid, holder_type="person", holder_person_id=public_person["id"], status="asserted")
    mine = contributor.get(f"/trees/{t}/people/{public_person['id']}/property-interests").json()
    assert [i["property"]["id"] for i in mine["items"]] == [pid]  # the private property is filtered out
    assert len(owner.get(f"/trees/{t}/people/{public_person['id']}/property-interests").json()["items"]) == 2


def test_property_custodian_can_write(owner, tree, member_factory):
    t = tree["id"]
    custodian = member_factory(["PROPERTY_CUSTODIAN"], name="Custodian")
    owners_prop = make_property(owner, t, display_name="Haveli", property_type="ancestral_home")
    assert custodian.get(f"/trees/{t}/properties/{owners_prop['id']}").status_code == 200
    prop = make_property(custodian, t, display_name="Custodian's record")
    assert prop["can_edit"] is True
    parcel = add_parcel(custodian, t, prop["id"], survey_number="12/3", area="1.5", area_unit="acre")
    assert parcel["area_sq_m"] == "6070.28"
    branch = make_branch(owner, t, "Main line")
    r = add_interest(
        custodian, t, prop["id"], holder_type="family_branch", holder_branch_id=branch, status="documented"
    )
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    r = custodian.post(
        f"/trees/{t}/properties/{prop['id']}/interests/{iid}/end",
        json={"valid_to": year(2001), "status": "relinquished"},
    )
    assert r.status_code == 200 and r.json()["status"] == "relinquished" and r.json()["is_current"] is False
    # PRIVATE_SELF stays with the tree owner
    r = custodian.patch(f"/trees/{t}/properties/{prop['id']}", json={"privacy_level": "PRIVATE_SELF"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "privacy_would_hide"
    assert "property.interest_changed" in audit_actions(t)


def test_cross_tree_isolation(owner, tree, make_client):
    t = tree["id"]
    pid = make_property(owner, t)["id"]
    other = make_client()
    other.register(name="Other owner")
    t2 = new_tree(other, "Other family")["id"]
    pid2 = make_property(other, t2)["id"]
    # non-member of tree A
    assert other.get(f"/trees/{t}/properties/{pid}").status_code == 404
    assert other.get(f"/trees/{t}/properties").status_code == 404
    # tree B's property through tree B's URL but A's id, and vice versa
    assert other.get(f"/trees/{t2}/properties/{pid}").status_code == 404
    assert owner.get(f"/trees/{t}/properties/{pid2}").status_code == 404
    assert other.post(f"/trees/{t2}/properties/{pid}/parcels", json={"plot_number": "1"}).status_code == 404
    # a holder from another tree is rejected
    stranger = create_person(other, t2, "Stranger")
    r = add_interest(owner, t, pid, holder_type="person", holder_person_id=stranger["id"])
    assert r.status_code == 404
    # a document from another tree cannot be linked
    doc = insert_document(t2, "Foreign deed")
    r = owner.post(f"/trees/{t}/properties/{pid}/events", json={"type": "other", "document_ids": [doc]})
    assert r.status_code == 404


# ---------------------------------------------------------------- parcels
def test_ulpin_validation(owner, tree):
    t = tree["id"]
    pid = make_property(owner, t)["id"]
    for bad in ("ABC123", "AB12CD34EF56GH7", "AB12-CD34EF56G", "अ" * 14):
        r = owner.post(f"/trees/{t}/properties/{pid}/parcels", json={"ulpin": bad})
        assert r.status_code == 422, bad
    parcel = add_parcel(owner, t, pid, ulpin=" ab12cd34ef56gh ")
    assert parcel["ulpin"] == "AB12CD34EF56GH"
    r = owner.patch(f"/trees/{t}/properties/{pid}/parcels/{parcel['id']}", json={"ulpin": "short"})
    assert r.status_code == 422
    # area rules: unit required, unit must be known, recorded precision limited to 4 places
    assert owner.post(f"/trees/{t}/properties/{pid}/parcels", json={"area": "2"}).status_code == 422
    assert (
        owner.post(
            f"/trees/{t}/properties/{pid}/parcels", json={"area": "2", "area_unit": "furlong"}
        ).status_code
        == 422
    )
    assert (
        owner.post(
            f"/trees/{t}/properties/{pid}/parcels", json={"area": "2.12345", "area_unit": "acre"}
        ).status_code
        == 422
    )
    hits = owner.get(f"/trees/{t}/search", params={"q": "AB12CD34EF56GH", "kinds": "property"}).json()["hits"]
    assert hits and hits[0]["match_tier"] == "exact"


def test_subdivision_lineage(owner, tree):
    t = tree["id"]
    pid = make_property(owner, t)["id"]
    parent = add_parcel(
        owner, t, pid, village="Sonpur", district="Patna", survey_number="45", area="2", area_unit="hectare"
    )
    assert parent["area_sq_m"] == "20000.00"
    r = owner.post(
        f"/trees/{t}/properties/{pid}/parcels/{parent['id']}/subdivide",
        json={
            "date": year(1985),
            "description": "Survey 45 split into 45/1 and 45/2",
            "children": [
                {"subdivision_number": "1", "area": "1.2", "area_unit": "hectare"},
                {"subdivision_number": "2", "area": "1", "area_unit": "hectare"},
            ],
        },
    )
    assert r.status_code == 201, r.text
    out = r.json()
    kids = out["children"]
    assert [k["label"] for k in kids] == ["Survey 45/1 (Sonpur)", "Survey 45/2 (Sonpur)"]
    assert all(k["parent_parcel_id"] == parent["id"] and k["district"] == "Patna" for k in kids)
    assert out["event"]["type"] == "subdivision" and len(out["event"]["parcels"]) == 3
    assert out["warnings"]  # 2.2 ha recorded against a 2 ha parent
    grand = add_parcel(
        owner, t, pid, parent_parcel_id=kids[0]["id"], survey_number="45", subdivision_number="1A"
    )
    lin = owner.get(f"/trees/{t}/properties/{pid}/parcels/{kids[0]['id']}/lineage").json()
    assert [a["id"] for a in lin["ancestors"]] == [parent["id"]]
    assert [s["id"] for s in lin["siblings"]] == [kids[1]["id"]]
    assert [(d["parcel"]["id"], d["depth"]) for d in lin["descendants"]] == [(grand["id"], 1)]
    root = owner.get(f"/trees/{t}/properties/{pid}/parcels/{parent['id']}/lineage").json()
    assert [(d["parcel"]["id"], d["depth"]) for d in root["descendants"]] == [
        (kids[0]["id"], 1),
        (grand["id"], 2),
        (kids[1]["id"], 1),
    ]
    assert root["parcel"]["child_count"] == 2
    groups = owner.get(f"/trees/{t}/properties/{pid}/lineage").json()["parcel_groups"]
    assert {g["parent"]["id"]: len(g["children"]) for g in groups} == {parent["id"]: 2, kids[0]["id"]: 1}
    # cycles are refused
    r = owner.patch(
        f"/trees/{t}/properties/{pid}/parcels/{parent['id']}", json={"parent_parcel_id": grand["id"]}
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "parcel_cycle"
    # parcels with history cannot be deleted; a fresh one can
    assert owner.delete(f"/trees/{t}/properties/{pid}/parcels/{parent['id']}").status_code == 409
    assert owner.delete(f"/trees/{t}/properties/{pid}/parcels/{grand['id']}").status_code == 200


def test_property_crud_and_delete_policy(owner, tree):
    t = tree["id"]
    empty = make_property(
        owner, t, display_name="Empty", property_type="house", classification="self_acquired"
    )
    kept = make_property(owner, t, display_name="Kept")
    add_interest(owner, t, kept["id"], holder_type="unknown")
    listed = owner.get(f"/trees/{t}/properties", params={"type": "house"}).json()
    assert [p["id"] for p in listed] == [empty["id"]]
    assert [p["id"] for p in owner.get(f"/trees/{t}/properties", params={"q": "kep"}).json()] == [kept["id"]]
    r = owner.patch(
        f"/trees/{t}/properties/{empty['id']}", json={"current_status": "sold", "display_name": "Old house"}
    )
    assert r.status_code == 200 and r.json()["display_name"] == "Old house"
    assert owner.patch(f"/trees/{t}/properties/{empty['id']}", json={"display_name": None}).status_code == 422
    r = owner.delete(f"/trees/{t}/properties/{kept['id']}")
    assert r.status_code == 409 and r.json()["error"]["code"] == "property_has_history"
    add_parcel(owner, t, empty["id"], plot_number="9")
    assert owner.delete(f"/trees/{t}/properties/{empty['id']}").status_code == 200
    assert owner.get(f"/trees/{t}/properties/{empty['id']}").status_code == 404
    assert "property.deleted" in audit_actions(t)
