"""Synthetic large-tree benchmark (PRS §49: p95 < 500 ms at 10k people).

Usage: VSH_DATABASE_URL=... uv run python -m app.cli.benchmark --people 10000
Creates a throwaway tree with a multi-generation synthetic family (bulk inserts, fictional names),
then times key API calls in-process and prints p50/p95 per endpoint.
"""

from __future__ import annotations

import argparse
import random
import statistics
import time
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import insert

from app.core.dates import GenealogicalDate, date_to_json
from app.core.db import get_sessionmaker
from app.core.ids import uuid7
from app.core.security import hash_password
from app.core.textnorm import phonetic_key, search_key
from app.main import create_app
from app.models import Event, EventParticipant, NameRecord, Person, Relationship, Tree, TreeMembership, User
from app.models.enums import EventType, ParticipantRole, ProfileStatus, RelationshipType, SexAtBirth

GIVEN = [
    "Rama",
    "Krishna",
    "Lakshmi",
    "Sita",
    "Arjun",
    "Meena",
    "Ravi",
    "Anand",
    "Priya",
    "Kavya",
    "Suresh",
    "Gita",
    "Mohan",
    "Radha",
    "Vijay",
    "Asha",
    "Deepak",
    "Usha",
    "Kiran",
    "Lata",
]
SURNAMES = ["Iyer", "Sharma", "Patel", "Reddy", "Nair", "Das", "Singh", "Rao", "Menon", "Joshi"]


def build(people: int, seed: int = 7) -> tuple[str, str, list[uuid.UUID]]:
    rng = random.Random(seed)
    email = f"bench-{uuid.uuid4().hex[:8]}@example.com"
    with get_sessionmaker()() as db:
        user = User(email=email, password_hash=hash_password("benchmark-password"), display_name="Bench")
        db.add(user)
        db.flush()
        tree = Tree(name="Benchmark tree", slug=f"bench-{uuid.uuid4().hex[:8]}", created_by=user.id)
        db.add(tree)
        db.flush()
        db.add(TreeMembership(tree_id=tree.id, user_id=user.id, roles=["OWNER"]))
        ids: list[uuid.UUID] = []
        persons, names, events, parts, rels = [], [], [], [], []
        generation: list[tuple[uuid.UUID, SexAtBirth, int]] = []
        year = 1800
        while len(ids) < people:
            nxt: list[tuple[uuid.UUID, SexAtBirth, int]] = []
            Parent = tuple[uuid.UUID, SexAtBirth, int] | None
            couples: list[tuple[Parent, Parent]] = [
                (generation[i], generation[i + 1]) for i in range(0, len(generation) - 1, 2)
            ] or [(None, None)]
            for pa, pb in couples:
                for _ in range(rng.randint(2, 4)):
                    if len(ids) >= people:
                        break
                    pid, sex = uuid7(), rng.choice([SexAtBirth.MALE, SexAtBirth.FEMALE])
                    by = year + rng.randint(0, 5)
                    given, sur = rng.choice(GIVEN), rng.choice(SURNAMES)
                    status = ProfileStatus.DECEASED if by < 1930 else ProfileStatus.LIVING
                    persons.append(
                        dict(
                            id=pid,
                            tree_id=tree.id,
                            preferred_display_name=f"{given} {sur}",
                            profile_status=status,
                            sex_at_birth=sex,
                        )
                    )
                    names.append(
                        dict(
                            id=uuid7(),
                            tree_id=tree.id,
                            person_id=pid,
                            given_name=given,
                            surname=sur,
                            is_preferred=True,
                            search_text=search_key(given, sur),
                            search_phonetic=phonetic_key(f"{given} {sur}"),
                        )
                    )
                    d = GenealogicalDate(precision="year_only", year=by)  # type: ignore[arg-type]
                    eid = uuid7()
                    lo, hi = d.sort_range()
                    events.append(
                        dict(
                            id=eid,
                            tree_id=tree.id,
                            type=EventType.BIRTH,
                            date=date_to_json(d),
                            date_sort_from=lo,
                            date_sort_to=hi,
                            is_preferred=True,
                        )
                    )
                    parts.append(
                        dict(
                            id=uuid7(),
                            tree_id=tree.id,
                            event_id=eid,
                            person_id=pid,
                            role=ParticipantRole.PRINCIPAL,
                        )
                    )
                    for parent in (pa, pb):
                        if parent is not None:
                            rels.append(
                                dict(
                                    id=uuid7(),
                                    tree_id=tree.id,
                                    person_a_id=parent[0],
                                    person_b_id=pid,
                                    type=RelationshipType.BIOLOGICAL_PARENT,
                                )
                            )
                    ids.append(pid)
                    nxt.append((pid, sex, by))
            generation = nxt
            year += 25
        for model, rows in (
            (Person, persons),
            (NameRecord, names),
            (Event, events),
            (EventParticipant, parts),
            (Relationship, rels),
        ):
            for i in range(0, len(rows), 2000):
                db.execute(insert(model), rows[i : i + 2000])
        db.commit()
    # refresh planner statistics after the bulk load (autovacuum would do this for organically grown data)
    from app.core.db import get_engine

    with get_engine().connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT").exec_driver_sql("ANALYZE")
    return email, str(tree.id), ids


def timed(client: TestClient, url: str, runs: int) -> list[float]:
    out = []
    for _ in range(runs):
        t0 = time.perf_counter()
        r = client.get(url)
        out.append((time.perf_counter() - t0) * 1000)
        assert r.status_code == 200, (url, r.status_code, r.text[:200])
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--people", type=int, default=10000)
    ap.add_argument("--runs", type=int, default=20)
    args = ap.parse_args(argv)
    t0 = time.perf_counter()
    email, tree_id, ids = build(args.people)
    print(f"built {len(ids)} people in {time.perf_counter() - t0:.1f}s")
    client = TestClient(create_app())
    assert (
        client.post("/api/v1/auth/login", json={"email": email, "password": "benchmark-password"}).status_code
        == 200
    )
    csrf = client.cookies.get("vsh_csrf")
    client.headers["X-CSRF-Token"] = csrf or ""
    base = f"/api/v1/trees/{tree_id}"
    leaf, root, mid = ids[-1], ids[0], ids[len(ids) // 2]
    cases = {
        "people list (page 1)": f"{base}/people?limit=50",
        "person profile": f"{base}/people/{mid}",
        "family view": f"{base}/people/{mid}/family",
        "ancestors depth 10": f"{base}/people/{leaf}/ancestors?depth=10",
        "descendants depth 4": f"{base}/people/{root}/descendants?depth=4",
        "search 'krishna iyer'": f"{base}/search?q=krishna%20iyer&kinds=person",
        "relationship path": f"{base}/relationship-path?from={leaf}&to={mid}",
        "duplicates": f"{base}/duplicates?limit=20",
    }
    print(f"{'endpoint':28} {'p50 ms':>8} {'p95 ms':>8}")
    for label, url in cases.items():
        runs = max(3, args.runs // 4) if label == "duplicates" else args.runs
        xs = sorted(timed(client, url, runs))
        p95 = xs[min(len(xs) - 1, int(round(0.95 * (len(xs) - 1))))]
        print(f"{label:28} {statistics.median(xs):8.1f} {p95:8.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
