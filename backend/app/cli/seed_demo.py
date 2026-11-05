"""Seed the development/test accounts and demo family tree through the real service layer.

Usage (development or test only; refused when ``VSH_ENV`` is anything else):

    VSH_DEMO_PASSWORD=... VSH_SUPERADMIN_PASSWORD=... uv run python -m app.cli.seed_demo \\
        [--email demo@example.com] [--admin-email superadmin@example.com]

Creates, if missing:

* ``demo@example.com``: an ordinary verified user who owns the fictional "Iyer Family (demo)" tree.
* ``superadmin@example.com``: a verified platform system administrator (``is_system_admin``). Per
  ADR-0006 that grants platform endpoints only and **no tree access** (threat T12); the account is
  not added to any tree and must choose a new password at first sign-in.

Passwords are read only from the environment (never arguments or defaults), stored only as Argon2
hashes and never printed. The command is idempotent: existing accounts and the demo tree are left
as they are (passwords are not reset), and an existing non-admin account is never promoted.
All people are fictional.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from typing import Any

from sqlalchemy import select

from app.authz.context import RequestInfo, load_tree_context
from app.core import audit
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.security import hash_password, password_problems
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
from app.modules.consent import statements
from app.modules.consent.attestation import attest
from app.modules.consent.statements import StatementKind
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
from app.modules.identity.service import normalise_email
from app.modules.trees import service as trees

ALLOWED_ENVS = ("development", "test")
DEMO_EMAIL = "demo@example.com"
SUPERADMIN_EMAIL = "superadmin@example.com"
# Names of environment variables, not secrets.
DEMO_PASSWORD_ENV = "VSH_DEMO_PASSWORD"  # noqa: S105
SUPERADMIN_PASSWORD_ENV = "VSH_SUPERADMIN_PASSWORD"  # noqa: S105


class SeedRefused(RuntimeError):
    """Seeding is not allowed in this environment."""


def require_dev_env() -> None:
    env = get_settings().env
    if env not in ALLOWED_ENVS:
        raise SeedRefused(f"seeding is only allowed when VSH_ENV is development or test (it is {env})")


def _check_password(password: str, var: str) -> None:
    problems = password_problems(password)
    if problems:
        raise ValueError(f"{var}: " + "; ".join(problems))


def _d(y: int, m: int | None = None, d: int | None = None, precision: str | None = None) -> dict[str, Any]:
    if precision is None:
        precision = "exact" if d else ("day_unknown" if m else "year_only")
    out: dict[str, Any] = {"precision": precision, "year": y}
    if m:
        out["month"] = m
    if d:
        out["day"] = d
    return out


def seed_superadmin(email: str, password: str) -> str:
    """Create the platform system-admin account if missing; return its id. Never touches trees."""
    require_dev_env()
    email = normalise_email(email)
    with get_sessionmaker()() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is not None:
            if not user.is_system_admin:
                # An account someone registered must not silently gain admin rights.
                raise ValueError(f"{email} already exists and is not a system admin; refusing to promote it")
            print(f"System admin already exists: {email}")
            return str(user.id)
        _check_password(password, SUPERADMIN_PASSWORD_ENV)
        user = User(
            email=email,
            password_hash=hash_password(password),
            display_name="Super Admin (dev)",
            email_verified_at=dt.datetime.now(dt.UTC),
            is_system_admin=True,
            # the seed password is shared through the environment: replace it at first sign-in
            must_change_password=True,
        )
        db.add(user)
        db.flush()
        audit.record(
            db,
            action="user.system_admin_seeded",
            actor_user_id=None,
            target_type="user",
            target_id=user.id,
            details={"env": get_settings().env},
        )
        db.commit()
        print(f"Created system admin {email}; a new password is required at first sign-in")
        return str(user.id)


def seed(email: str, password: str) -> str:
    """Create the demo owner (if missing) and the demo tree (if missing); return the tree id."""
    require_dev_env()
    email = normalise_email(email)
    Session = get_sessionmaker()
    with Session() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is not None and user.is_system_admin:
            raise ValueError(f"{email} is a system admin; the demo tree owner must be an ordinary user")
        if user is None:
            _check_password(password, DEMO_PASSWORD_ENV)
            user = User(
                email=email,
                password_hash=hash_password(password),
                display_name="Demo Owner",
                email_verified_at=dt.datetime.now(dt.UTC),
            )
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
        # The demo owner confirms the family-data statement like a real user would (ADR-0011).
        stmt = statements.current(StatementKind.FAMILY_DATA, "en")
        attest(ctx, stmt.version, stmt.language)

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
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--email", default=DEMO_EMAIL, help="demo tree owner")
    ap.add_argument("--admin-email", default=SUPERADMIN_EMAIL, help="platform system admin")
    args = ap.parse_args(argv)
    try:
        require_dev_env()
        if normalise_email(args.email) == normalise_email(args.admin_email):
            print("--email and --admin-email must differ", file=sys.stderr)
            return 1
        missing = [v for v in (DEMO_PASSWORD_ENV, SUPERADMIN_PASSWORD_ENV) if not os.environ.get(v)]
        if missing:
            print(
                f"set {' and '.join(missing)} (passwords are read only from the environment)", file=sys.stderr
            )
            return 2
        # validate both before writing anything, so a bad run leaves the database untouched
        for var in (DEMO_PASSWORD_ENV, SUPERADMIN_PASSWORD_ENV):
            _check_password(os.environ[var], var)
        seed(args.email, os.environ[DEMO_PASSWORD_ENV])
        seed_superadmin(args.admin_email, os.environ[SUPERADMIN_PASSWORD_ENV])
    except SeedRefused as e:
        print(str(e), file=sys.stderr)
        return 2
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
