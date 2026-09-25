"""Seed a demo account and family tree through the real service layer (authz + audit apply).

Usage: uv run python -m app.cli.seed_demo [--email demo@example.com] [--password ...]
All people are fictional.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from sqlalchemy import select

from app.authz.context import RequestInfo, load_tree_context
from app.core.db import get_sessionmaker
from app.core.security import hash_password
from app.models import Tree, TreeMembership, User
from app.models.enums import (
    AssertionSubject,
    DescentRule,
    EventType,
    HeritageAttribute,
    HouseholdRole,
    ProfileStatus,
    RelationshipType,
    SexAtBirth,
)
from app.modules.family import service as family
from app.modules.family.schemas import BranchIn, HouseholdIn, HouseholdMemberIn
from app.modules.genealogy import service as genealogy
from app.modules.genealogy.schemas import (
    EventIn,
    NameIn,
    ParticipantIn,
    PersonCreate,
    PlaceIn,
    RelationshipIn,
    VitalIn,
)
from app.modules.heritage import service as heritage
from app.modules.heritage.schemas import AssertionIn
from app.modules.trees import service as trees


def _d(y: int, m: int | None = None, d: int | None = None, precision: str | None = None) -> dict[str, Any]:
    if precision is None:
        precision = "exact" if d else ("day_unknown" if m else "year_only")
    out: dict[str, Any] = {"precision": precision, "year": y}
    if m:
        out["month"] = m
    if d:
        out["day"] = d
    return out


def seed(email: str, password: str) -> str:
    Session = get_sessionmaker()
    with Session() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, password_hash=hash_password(password), display_name="Demo Owner")
            db.add(user)
            db.flush()
        existing = db.scalar(
            select(Tree)
            .join(TreeMembership, TreeMembership.tree_id == Tree.id)
            .where(
                TreeMembership.user_id == user.id,
                Tree.name == "Iyer Family (demo)",
                Tree.deleted_at.is_(None),
            )
        )
        if existing:
            print(f"Demo tree already exists: {existing.id}")
            return str(existing.id)
        tree, _ = trees.create_tree(
            db,
            user,
            "Iyer Family (demo)",
            "Fictional demo family spanning four generations.",
            RequestInfo(ip="127.0.0.1", user_agent="seed"),
        )
        ctx = load_tree_context(db, tree.id, user, RequestInfo(ip="127.0.0.1", user_agent="seed"))

        kanchi = genealogy.create_place(
            ctx,
            PlaceIn(
                canonical_name="Kanchipuram",
                place_type="village",
                local_names=[{"name": "காஞ்சிபுரம்", "language": "ta", "script": "Taml"}],
                latitude=12.8342,
                longitude=79.7036,
            ),
        )
        chennai = genealogy.create_place(
            ctx, PlaceIn(canonical_name="Chennai", place_type="city", historical_names=[{"name": "Madras"}])
        )
        madurai = genealogy.create_place(ctx, PlaceIn(canonical_name="Madurai", place_type="city"))

        def person(
            given: str,
            surname: str,
            sex: SexAtBirth,
            status: ProfileStatus,
            birth: dict | None = None,
            death: dict | None = None,
            native: str | None = None,
            place_id=None,
            **kw: Any,
        ):  # type: ignore[no-untyped-def]
            names = [NameIn(given_name=given, surname=surname, is_preferred=True)]
            if native:
                names.append(NameIn(full_name_as_recorded=native, language="ta", type="birth"))
            return genealogy.create_person(
                ctx,
                PersonCreate(
                    profile_status=status,
                    sex_at_birth=sex,
                    names=names,
                    birth=VitalIn(date=birth, place_id=place_id) if birth else None,
                    death=VitalIn(date=death) if death else None,
                    **kw,
                ),
            )

        rama = person(
            "Ramaswamy",
            "Iyer",
            SexAtBirth.MALE,
            ProfileStatus.DECEASED,
            _d(1920, 3, 15),
            _d(1995, 11, 20),
            "ராமசாமி அய்யர்",
            kanchi.id,
            occupation="Vedic scholar",
        )
        lakshmi = person(
            "Lakshmi",
            "Iyer",
            SexAtBirth.FEMALE,
            ProfileStatus.DECEASED,
            _d(1925, precision="circa"),
            _d(2005, 4, 18),
            "லக்ஷ்மி",
        )
        krishnan = person(
            "Krishnan",
            "Iyer",
            SexAtBirth.MALE,
            ProfileStatus.DECEASED,
            _d(1945, 8, 22),
            _d(2019, 2, 2),
            place_id=kanchi.id,
        )
        meenakshi = person("Meenakshi", "Iyer", SexAtBirth.FEMALE, ProfileStatus.LIVING, _d(1950, 1, 9))
        subbu = person(
            "Subramanian",
            "Iyer",
            SexAtBirth.MALE,
            ProfileStatus.DECEASED,
            _d(1948, 5, 30),
            _d(2020, 6, 1),
            place_id=madurai.id,
        )
        anand = person(
            "Anand",
            "Iyer",
            SexAtBirth.MALE,
            ProfileStatus.LIVING,
            _d(1975, 12, 5),
            place_id=chennai.id,
            occupation="Engineer",
        )
        priya = person("Priya", "Iyer", SexAtBirth.FEMALE, ProfileStatus.LIVING, _d(1978, 7, 23))
        ravi = person("Ravi", "Iyer", SexAtBirth.MALE, ProfileStatus.LIVING, _d(1972, 3, 3))
        arjun = person("Arjun", "Iyer", SexAtBirth.MALE, ProfileStatus.LIVING, _d(2012, 10, 10))
        kavya = person("Kavya", "Iyer", SexAtBirth.FEMALE, ProfileStatus.LIVING, _d(2008, 4, 1))

        def rel(a, b, t: RelationshipType, **kw: Any):  # type: ignore[no-untyped-def]
            return genealogy.create_relationship(
                ctx, RelationshipIn(person_a_id=a.id, person_b_id=b.id, type=t, **kw)
            )

        u1 = rel(rama, lakshmi, RelationshipType.SPOUSE, start_date=_d(1943, precision="year_only"))
        for child in (krishnan, subbu):
            rel(rama, child, RelationshipType.BIOLOGICAL_PARENT, union_id=u1.id)
            rel(lakshmi, child, RelationshipType.BIOLOGICAL_PARENT, union_id=u1.id)
        u2 = rel(krishnan, meenakshi, RelationshipType.SPOUSE)
        for child in (anand, ravi):
            rel(krishnan, child, RelationshipType.BIOLOGICAL_PARENT, union_id=u2.id)
            rel(meenakshi, child, RelationshipType.BIOLOGICAL_PARENT, union_id=u2.id)
        u3 = rel(anand, priya, RelationshipType.SPOUSE)
        rel(anand, arjun, RelationshipType.BIOLOGICAL_PARENT, union_id=u3.id)
        rel(priya, arjun, RelationshipType.BIOLOGICAL_PARENT, union_id=u3.id)
        # Kavya: adopted by Ravi (legal lineage) — biological parents unknown
        rel(ravi, kavya, RelationshipType.ADOPTIVE_PARENT, subtype="dattak")

        genealogy.create_event(
            ctx,
            EventIn(
                type=EventType.MIGRATION,
                date=_d(1952, precision="year_only"),
                origin_place_id=kanchi.id,
                place_id=chennai.id,
                reason="Moved for temple service",
                participants=[ParticipantIn(person_id=rama.id)],
            ),
        )
        for p in (rama, krishnan, subbu):
            heritage.create_assertion(
                ctx,
                AssertionSubject.PERSON,
                p.id,
                AssertionIn(
                    attribute=HeritageAttribute.GOTRA,
                    value_text="Kashyapa",
                    evidence_status="FAMILY_RECOLLECTION",
                ),
            )
        heritage.create_assertion(
            ctx,
            AssertionSubject.PERSON,
            rama.id,
            AssertionIn(attribute=HeritageAttribute.KULADEVATA, value_text="Kamakshi Amman"),
        )
        heritage.create_assertion(
            ctx,
            AssertionSubject.PERSON,
            rama.id,
            AssertionIn(attribute=HeritageAttribute.ANCESTRAL_VILLAGE, place_id=kanchi.id),
        )
        branch = family.create_branch(
            ctx,
            BranchIn(
                name="Descendants of Ramaswamy", founder_person_id=rama.id, descent_rule=DescentRule.BILATERAL
            ),
        )
        family.derive_members(ctx, branch.id)
        home = family.create_household(
            ctx,
            HouseholdIn(
                name="Ancestral home",
                house_name="Gokulam",
                place_id=kanchi.id,
                branch_id=branch.id,
                start_date=_d(1943, precision="year_only"),
            ),
        )
        family.add_household_member(
            ctx, home.id, HouseholdMemberIn(person_id=rama.id, role=HouseholdRole.KARTA)
        )
        family.add_household_member(ctx, home.id, HouseholdMemberIn(person_id=lakshmi.id))
        family.add_household_member(
            ctx, home.id, HouseholdMemberIn(person_id=krishnan.id, end_date=_d(1970, precision="year_only"))
        )
        db.commit()
        print(f"Seeded demo tree {tree.id} for {email}")
        return str(tree.id)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", default="demo@example.com")
    ap.add_argument("--password", default="demo-password-123")
    args = ap.parse_args(argv)
    seed(args.email, args.password)
    return 0


if __name__ == "__main__":
    sys.exit(main())
