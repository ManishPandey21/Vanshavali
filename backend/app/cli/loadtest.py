"""HTTP-level load test against a real uvicorn server (PRS §49; docs/operations/performance.md).

Two steps, so the server under test never shares a process with the load generator:

    # 1. seed a synthetic tree (reuses benchmark.build) plus N contributor accounts
    VSH_DATABASE_URL=... uv run python -m app.cli.loadtest seed --people 10000 --users 50 --state lt.json

    # 2. start the server separately, e.g.
    VSH_DATABASE_URL=... VSH_LOGIN_RATE_LIMIT_PER_MINUTE=1000 \
        uv run uvicorn app.main:app --port 8200 --workers 4
    # then drive it
    uv run python -m app.cli.loadtest run --base-url http://127.0.0.1:8200 --state lt.json \
        --users 20 --duration 60

`ops/loadtest/run.sh` does all of it (database, migrate, seed, server, 20- and 50-user runs).

Each virtual user logs in with its own account (cookie session + CSRF double-submit header) and then
runs a closed loop over a weighted mix of reads and writes with an optional think time. Zero think time
(the default) makes each virtual user a saturating client, so N virtual users here correspond to many
more real, human-paced users. Latencies are wall-clock client-side (network loopback included).
Output: throughput, error rate and p50/p95/p99/max per endpoint; `--json` writes the raw summary.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import random
import statistics
import sys
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PASSWORD = "loadtest-password"  # noqa: S105 - synthetic accounts in a throwaway load-test database

GIVEN = ["Rama", "Krishna", "Lakshmi", "Sita", "Arjun", "Meena", "Ravi", "Anand", "Priya", "Kavya"]
SURNAMES = ["Iyer", "Sharma", "Patel", "Reddy", "Nair", "Das", "Singh", "Rao", "Menon", "Joshi"]

# (label, weight). Roughly 85% reads / 15% writes: browsing dominates genealogy use.
MIX: list[tuple[str, int]] = [
    ("people list", 18),
    ("person profile", 20),
    ("family view", 15),
    ("ancestors d10", 10),
    ("descendants d4", 4),
    ("search", 10),
    ("relationship path", 8),
    ("add person", 8),
    ("add relative", 7),
]
WRITE_LABELS = {"add person", "add relative"}


# ---------------------------------------------------------------- seed
def seed(people: int, users: int, state_path: Path) -> dict[str, Any]:
    from app.cli.benchmark import build
    from app.core.db import get_sessionmaker
    from app.core.security import hash_password
    from app.models import TreeMembership, User

    t0 = time.perf_counter()
    owner_email, tree_id, ids = build(people)
    built = time.perf_counter() - t0
    tag = uuid.uuid4().hex[:6]
    pw_hash = hash_password(PASSWORD)
    emails: list[str] = []
    with get_sessionmaker()() as db:
        for i in range(users):
            email = f"lt-{tag}-{i:03d}@example.com"
            u = User(email=email, password_hash=pw_hash, display_name=f"Load user {i}")
            if hasattr(User, "email_verified_at"):  # accounts must be verified to log in once that lands
                u.email_verified_at = dt.datetime.now(dt.UTC)
            db.add(u)
            db.flush()
            db.add(TreeMembership(tree_id=uuid.UUID(tree_id), user_id=u.id, roles=["CONTRIBUTOR"]))
            emails.append(email)
        db.commit()
    state = {
        "tree_id": tree_id,
        "owner_email": owner_email,
        "users": emails,
        "password": PASSWORD,
        "person_ids": [str(i) for i in ids],
        "people": len(ids),
        "build_seconds": round(built, 1),
    }
    state_path.write_text(json.dumps(state))
    print(f"seeded {len(ids)} people and {users} users in tree {tree_id} ({built:.1f}s) -> {state_path}")
    return state


# ---------------------------------------------------------------- run
@dataclass
class Stats:
    lat: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    errors: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    codes: dict[str, dict[int, int]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))
    samples: dict[str, str] = field(default_factory=dict)


def _pct(xs: list[float], p: float) -> float:
    if not xs:
        return float("nan")
    return xs[min(len(xs) - 1, round(p * (len(xs) - 1)))]


def _new_person(rng: random.Random) -> dict[str, Any]:
    given, sur = rng.choice(GIVEN), rng.choice(SURNAMES)
    return {
        "profile_status": "deceased",
        "sex_at_birth": rng.choice(["male", "female"]),
        "names": [{"given_name": given, "surname": sur, "is_preferred": True}],
        "birth": {"date": {"precision": "year_only", "year": rng.randint(1800, 1920)}},
    }


class VirtualUser:
    def __init__(
        self, idx: int, base: str, state: dict[str, Any], stats: Stats, think_ms: int, seed: int
    ) -> None:
        import httpx

        self.idx = idx
        self.email = state["users"][idx]
        self.password = state["password"]
        self.tree = f"/api/v1/trees/{state['tree_id']}"
        self.ids: list[str] = state["person_ids"]
        self.stats = stats
        self.think = think_ms / 1000
        self.rng = random.Random(seed * 1000 + idx)  # noqa: S311 - load-test randomness only
        self.client = httpx.AsyncClient(base_url=base, timeout=60.0)
        self.created: list[str] = []

    async def login(self) -> None:
        r = await self.client.post(
            "/api/v1/auth/login", json={"email": self.email, "password": self.password}
        )
        if r.status_code != 200:
            raise RuntimeError(f"login failed for {self.email}: {r.status_code} {r.text[:200]}")
        self.client.headers["X-CSRF-Token"] = self.client.cookies.get("vsh_csrf") or ""

    def _pick(self, lo: float = 0.0, hi: float = 1.0) -> str:
        n = len(self.ids)
        return self.ids[self.rng.randrange(int(lo * n), max(int(lo * n) + 1, int(hi * n)))]

    def _request(self, label: str) -> tuple[str, str, dict[str, Any] | None, int]:
        t, r = self.tree, self.rng
        if label == "people list":
            return "GET", f"{t}/people?limit=50", None, 200
        if label == "person profile":
            return "GET", f"{t}/people/{self._pick()}", None, 200
        if label == "family view":
            return "GET", f"{t}/people/{self._pick()}/family", None, 200
        if label == "ancestors d10":
            return "GET", f"{t}/people/{self._pick(0.6, 1.0)}/ancestors?depth=10", None, 200
        if label == "descendants d4":
            return "GET", f"{t}/people/{self._pick(0.0, 0.05)}/descendants?depth=4", None, 200
        if label == "search":
            q = f"{r.choice(GIVEN)} {r.choice(SURNAMES)}".lower().replace(" ", "%20")
            return "GET", f"{t}/search?q={q}&kinds=person", None, 200
        if label == "relationship path":
            return (
                "GET",
                f"{t}/relationship-path?from={self._pick(0.5, 1.0)}&to={self._pick(0.5, 1.0)}",
                None,
                200,
            )
        if label == "add person":
            return "POST", f"{t}/people", _new_person(r), 201
        if label == "add relative":
            anchor = self._pick(0.3, 1.0)
            body = {"relation": "child", "new_person": _new_person(r)}
            return "POST", f"{t}/people/{anchor}/relatives", body, 201
        raise ValueError(label)

    async def loop(self, labels: list[str], weights: list[int], until: float, record_from: float) -> None:
        while (now := time.perf_counter()) < until:
            label = self.rng.choices(labels, weights)[0]
            method, url, body, ok = self._request(label)
            t0 = time.perf_counter()
            try:
                resp = await self.client.request(method, url, json=body)
                code = resp.status_code
                text = resp.text[:200] if code != ok else ""
            except Exception as exc:  # timeouts / connection resets count as errors
                code, text = 0, repr(exc)[:200]
            dt = (time.perf_counter() - t0) * 1000
            if now >= record_from:
                self.stats.lat[label].append(dt)
                self.stats.codes[label][code] += 1
                if code != ok:
                    self.stats.errors[label] += 1
                    self.stats.samples.setdefault(label, f"{code} {text}")
            if self.think:
                await asyncio.sleep(self.rng.uniform(0.5, 1.5) * self.think)

    async def close(self) -> None:
        await self.client.aclose()


async def run(
    base: str,
    state: dict[str, Any],
    users: int,
    duration: float,
    warmup: float,
    think_ms: int,
    exclude: set[str] | None = None,
) -> dict[str, Any]:
    if users > len(state["users"]):
        raise SystemExit(f"state has only {len(state['users'])} accounts; re-seed with --users {users}")
    stats = Stats()
    vus = [VirtualUser(i, base, state, stats, think_ms, seed=users) for i in range(users)]
    t0 = time.perf_counter()
    await asyncio.gather(*(v.login() for v in vus))
    login_s = time.perf_counter() - t0
    mix = [m for m in MIX if m[0] not in (exclude or set())]
    labels, weights = [m[0] for m in mix], [m[1] for m in mix]
    load_before = os.getloadavg()
    start = time.perf_counter()
    record_from, until = start + warmup, start + warmup + duration
    await asyncio.gather(*(v.loop(labels, weights, until, record_from) for v in vus))
    elapsed = time.perf_counter() - record_from
    load_after = os.getloadavg()
    await asyncio.gather(*(v.close() for v in vus))

    rows = []
    total = errs = 0
    all_lat: list[float] = []
    for label, _ in mix:
        xs = sorted(stats.lat.get(label, []))
        total += len(xs)
        errs += stats.errors.get(label, 0)
        all_lat += xs
        rows.append(
            {
                "endpoint": label,
                "write": label in WRITE_LABELS,
                "count": len(xs),
                "rps": round(len(xs) / elapsed, 1),
                "errors": stats.errors.get(label, 0),
                "p50": round(statistics.median(xs), 1) if xs else None,
                "p95": round(_pct(xs, 0.95), 1) if xs else None,
                "p99": round(_pct(xs, 0.99), 1) if xs else None,
                "max": round(xs[-1], 1) if xs else None,
                "codes": dict(stats.codes.get(label, {})),
            }
        )
    all_lat.sort()
    return {
        "base_url": base,
        "people": state["people"],
        "users": users,
        "think_ms": think_ms,
        "excluded": sorted(exclude or []),
        "cpus": os.cpu_count(),
        "loadavg_1m_before_after": [round(load_before[0], 1), round(load_after[0], 1)],
        "duration_s": round(elapsed, 1),
        "login_s_all_users": round(login_s, 2),
        "requests": total,
        "throughput_rps": round(total / elapsed, 1),
        "errors": errs,
        "error_rate": round(errs / total, 4) if total else None,
        "overall": {
            "p50": round(statistics.median(all_lat), 1) if all_lat else None,
            "p95": round(_pct(all_lat, 0.95), 1),
            "p99": round(_pct(all_lat, 0.99), 1),
        },
        "endpoints": rows,
        "error_samples": stats.samples,
    }


def print_report(rep: dict[str, Any]) -> None:
    print(
        f"\n{rep['users']} virtual users, {rep['people']} people, think {rep['think_ms']} ms, "
        f"{rep['duration_s']} s measured, loadavg(1m) before/after {rep['loadavg_1m_before_after']} "
        f"on {rep['cpus']} CPUs" + (f", excluded {rep['excluded']}" if rep["excluded"] else "")
    )
    print(
        f"requests {rep['requests']}  throughput {rep['throughput_rps']} req/s  "
        f"errors {rep['errors']} ({(rep['error_rate'] or 0) * 100:.2f}%)  "
        f"overall p50/p95/p99 {rep['overall']['p50']}/{rep['overall']['p95']}/{rep['overall']['p99']} ms"
    )
    print(f"{'endpoint':20} {'n':>6} {'rps':>6} {'err':>4} {'p50':>7} {'p95':>7} {'p99':>7} {'max':>7}")
    for r in rep["endpoints"]:
        print(
            f"{r['endpoint']:20} {r['count']:6} {r['rps']:6} {r['errors']:4} "
            f"{r['p50'] or 0:7.1f} {r['p95'] or 0:7.1f} {r['p99'] or 0:7.1f} {r['max'] or 0:7.1f}"
        )
    for label, sample in rep["error_samples"].items():
        print(f"  first error [{label}]: {sample}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed", help="build the synthetic tree and load-test accounts")
    s.add_argument("--people", type=int, default=10000)
    s.add_argument("--users", type=int, default=50)
    s.add_argument("--state", type=Path, default=Path("loadtest-state.json"))
    r = sub.add_parser("run", help="drive a running server")
    r.add_argument("--base-url", default="http://127.0.0.1:8200")
    r.add_argument("--state", type=Path, default=Path("loadtest-state.json"))
    r.add_argument("--users", type=int, default=20)
    r.add_argument("--duration", type=float, default=60.0, help="measured seconds")
    r.add_argument("--warmup", type=float, default=5.0, help="unrecorded seconds before measuring")
    r.add_argument("--think-ms", type=int, default=0, help="mean think time between requests per user")
    r.add_argument("--exclude", default="", help="comma-separated endpoint labels to drop from the mix")
    r.add_argument("--json", type=Path, help="write the summary as JSON")
    args = ap.parse_args(argv)
    if args.cmd == "seed":
        seed(args.people, args.users, args.state)
        return 0
    state = json.loads(args.state.read_text())
    exclude = {x.strip() for x in args.exclude.split(",") if x.strip()}
    unknown = exclude - {m[0] for m in MIX}
    if unknown:
        ap.error(f"unknown endpoint labels: {sorted(unknown)}")
    rep = asyncio.run(
        run(args.base_url, state, args.users, args.duration, args.warmup, args.think_ms, exclude)
    )
    print_report(rep)
    if args.json:
        args.json.write_text(json.dumps(rep, indent=2))
    return 1 if (rep["error_rate"] or 0) > 0.01 else 0


if __name__ == "__main__":
    sys.exit(main())
