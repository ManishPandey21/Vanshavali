"""Pipeline benchmarks over real HTTP: GEDCOM imports, document uploads, property history.

    cd backend && SMOKE_PASSWORD=... uv run python ../ops/loadtest/pipeline_bench.py \
        --base-url https://pilot.test --email smoke@... [--ca-file root.crt] [--json out.json]

Complements app.cli.loadtest (browsing and editing mix). Uses a verified account and creates its own
synthetic tree ("Pipeline bench"), which it deletes at the end. Measures:
- import:   synthetic GEDCOM (1,000 and 10,000 people): upload->report latency, commit latency
- upload:   N photos (≈1 MB JPEG) uploaded C at a time: upload latency, and time until the worker
            reports scan clean + previews done (the scan/preview/OCR pipeline, via the job queue)
- property: a property with 40 dated events and a 6-generation parcel subdivision chain, then
            sequential reads of the full record and the leaf parcel's lineage (p50/p95/p99)
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import random
import statistics
import time
from typing import Any

import httpx
from PIL import Image

API = "/api/v1"


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, round(p / 100 * (len(xs) - 1)))], 1)


def summary(xs: list[float]) -> dict[str, float]:
    return {
        "n": len(xs),
        "p50": pct(xs, 50),
        "p95": pct(xs, 95),
        "p99": pct(xs, 99),
        "max": round(max(xs), 1),
        "mean": round(statistics.fmean(xs), 1),
    }


def gedcom(n: int, seed: int = 11) -> bytes:
    """n people in 4-generation-deep families of 2 parents + 2 children, linked across generations."""
    rng = random.Random(seed)  # noqa: S311 - synthetic test data, not security
    given = ["Rama", "Sita", "Arjun", "Meena", "Ravi", "Kavya", "Suresh", "Anita", "Mohan", "Lata"]
    lines = ["0 HEAD", "1 GEDC", "2 VERS 5.5.1", "1 CHAR UTF-8"]
    for i in range(1, n + 1):
        lines += [
            f"0 @I{i}@ INDI",
            f"1 NAME {rng.choice(given)} /Bench{i % 97}/",
            f"1 SEX {'M' if i % 2 else 'F'}",
            "1 BIRT",
            f"2 DATE {rng.randint(1850, 1950)}",
            "1 DEAT Y",
        ]
    for fam, i in enumerate(range(1, n - 3, 4), 1):  # family: i, i+1 parents of i+2, i+3
        lines += [
            f"0 @F{fam}@ FAM",
            f"1 HUSB @I{i}@",
            f"1 WIFE @I{i + 1}@",
            f"1 CHIL @I{i + 2}@",
            f"1 CHIL @I{i + 3}@",
        ]
    lines.append("0 TRLR")
    return ("\n".join(lines) + "\n").encode()


def jpeg(seed: int) -> bytes:
    rng = random.Random(seed)  # noqa: S311 - synthetic test data, not security
    im = Image.effect_noise((1600, 1200), 40).convert("RGB")
    im.paste((rng.randint(0, 255), rng.randint(0, 255), 80), (100, 100, 700, 500))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


class Bench:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.c = client

    def csrf(self) -> dict[str, str]:
        tok = self.c.cookies.get("vsh_csrf")
        return {"X-CSRF-Token": tok} if tok else {}

    async def req(self, method: str, url: str, expect: int = 200, **kw: Any) -> Any:
        r = await self.c.request(method, url, headers=self.csrf(), **kw)
        if r.status_code != expect:
            raise RuntimeError(f"{method} {url} -> {r.status_code}: {r.text[:300]}")
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else r.content

    async def login(self, email: str, password: str) -> None:
        await self.req("POST", f"{API}/auth/login", json={"email": email, "password": password})

    async def new_tree(self) -> str:
        t = await self.req("POST", f"{API}/trees", 201, json={"name": "Pipeline bench"})
        stmt = await self.req("GET", f"{API}/consent-statements/family_data?lang=en")
        await self.req(
            "POST",
            f"{API}/trees/{t['id']}/attestation",
            201,
            json={"statement_version": stmt["version"], "language": "en"},
        )
        return str(t["id"])

    async def imports(self, t: str, sizes: list[int]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for n in sizes:
            data = gedcom(n)
            t0 = time.perf_counter()
            job = await self.req(
                "POST",
                f"{API}/trees/{t}/imports",
                201,
                files={"file": (f"bench-{n}.ged", data, "application/octet-stream")},
            )
            staged = (time.perf_counter() - t0) * 1000
            if job["status"] != "ready":
                raise RuntimeError(f"import of {n} people: status {job['status']}")
            t1 = time.perf_counter()
            done = await self.req(
                "POST", f"{API}/trees/{t}/imports/{job['id']}/commit", json={"decisions": {}}
            )
            committed = (time.perf_counter() - t1) * 1000
            out[f"{n}_people"] = {
                "bytes": len(data),
                "upload_and_report_ms": round(staged),
                "commit_ms": round(committed),
                "status": done["status"],
                "created": (done.get("commit_result") or {}).get("created"),
            }
            print(
                f"import {n:>6} people ({len(data) // 1024} KiB): report {staged:,.0f} ms, commit {committed:,.0f} ms"
            )
        return out

    async def uploads(self, t: str, n: int, concurrency: int, timeout: float) -> dict[str, Any]:
        photos = [jpeg(i) for i in range(n)]
        sem = asyncio.Semaphore(concurrency)
        up_ms: list[float] = []
        ready_ms: list[float] = []
        start = time.perf_counter()

        async def one(i: int) -> None:
            async with sem:
                t0 = time.perf_counter()
                doc = await self.req(
                    "POST",
                    f"{API}/trees/{t}/documents",
                    201,
                    data={"category": "photo", "title": f"bench {i}"},
                    files={"file": (f"b{i}.jpg", photos[i], "image/jpeg")},
                )
                up_ms.append((time.perf_counter() - t0) * 1000)
            while True:  # outside the semaphore: the pipeline runs in the worker
                d = await self.req("GET", f"{API}/trees/{t}/documents/{doc['id']}")
                if d["scan_status"] == "clean" and d["preview_status"] in ("completed", "skipped", "failed"):
                    ready_ms.append((time.perf_counter() - t0) * 1000)
                    return
                if time.perf_counter() - t0 > timeout:
                    raise RuntimeError(
                        f"document {doc['id']} not processed in {timeout}s: {d['scan_status']}"
                    )
                await asyncio.sleep(0.5)

        await asyncio.gather(*(one(i) for i in range(n)))
        wall = time.perf_counter() - start
        res = {
            "documents": n,
            "concurrency": concurrency,
            "avg_bytes": sum(map(len, photos)) // n,
            "upload_ms": summary(up_ms),
            "upload_to_processed_ms": summary(ready_ms),
            "wall_s": round(wall, 1),
            "processed_per_min": round(n / wall * 60, 1),
        }
        print(
            f"uploads {n} at {concurrency}: upload p95 {res['upload_ms']['p95']} ms, "
            f"to processed p50 {res['upload_to_processed_ms']['p50']} / p95 {res['upload_to_processed_ms']['p95']} ms, "
            f"{res['processed_per_min']}/min"
        )
        return res

    async def property_history(self, t: str, reads: int) -> dict[str, Any]:
        prop = await self.req(
            "POST",
            f"{API}/trees/{t}/properties",
            201,
            json={
                "property_type": "agricultural_land",
                "classification": "ancestral",
                "display_name": "Bench khet",
            },
        )
        pid = prop["id"]
        for i in range(40):
            await self.req(
                "POST",
                f"{API}/trees/{t}/properties/{pid}/events",
                201,
                json={
                    "type": ["purchase", "inheritance", "partition", "family_settlement"][i % 4],
                    "date": {"precision": "year_only", "year": 1850 + i * 4},
                },
            )
        parent = None
        for depth in range(6):
            body: dict[str, Any] = {"survey_number": f"77/{depth}", "village": "Rampur"}
            if parent:
                body["parent_parcel_id"] = parent
            parent = (await self.req("POST", f"{API}/trees/{t}/properties/{pid}/parcels", 201, json=body))[
                "id"
            ]
        detail: list[float] = []
        lineage: list[float] = []
        for _ in range(reads):
            t0 = time.perf_counter()
            await self.req("GET", f"{API}/trees/{t}/properties/{pid}")
            detail.append((time.perf_counter() - t0) * 1000)
            t0 = time.perf_counter()
            await self.req("GET", f"{API}/trees/{t}/properties/{pid}/parcels/{parent}/lineage")
            lineage.append((time.perf_counter() - t0) * 1000)
        res = {
            "events": 40,
            "parcel_depth": 6,
            "property_detail_ms": summary(detail),
            "leaf_lineage_ms": summary(lineage),
        }
        print(
            f"property history: detail p95 {res['property_detail_ms']['p95']} ms, lineage p95 {res['leaf_lineage_ms']['p95']} ms"
        )
        return res


async def main_async(args: argparse.Namespace) -> dict[str, Any]:
    verify: Any = args.ca_file or True
    async with httpx.AsyncClient(base_url=args.base_url, verify=verify, timeout=600, trust_env=False) as c:
        b = Bench(c)
        await b.login(args.email, os.environ["SMOKE_PASSWORD"])
        t = await b.new_tree()
        out: dict[str, Any] = {"base_url": args.base_url}
        try:
            out["property_history"] = await b.property_history(t, args.reads)
            out["uploads"] = await b.uploads(t, args.uploads, args.concurrency, args.timeout)
            out["imports"] = await b.imports(t, [int(x) for x in args.import_sizes.split(",")])
        finally:
            await b.req("DELETE", f"{API}/trees/{t}")
        return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--email", required=True)
    ap.add_argument("--ca-file")
    ap.add_argument("--uploads", type=int, default=20)
    ap.add_argument("--concurrency", type=int, default=5)
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--reads", type=int, default=100)
    ap.add_argument("--import-sizes", default="1000,10000")
    ap.add_argument("--json")
    args = ap.parse_args()
    out = asyncio.run(main_async(args))
    if args.json:
        with open(args.json, "w") as f:
            json.dump(out, f, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
