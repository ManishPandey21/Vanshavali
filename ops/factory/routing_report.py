#!/usr/bin/env python3
"""Cost/quality report over completed factory attempts, per role, model and effort (ADR-0030).

Reads only local factory state: the ledger (``.git/infra-factory/ledger.sqlite3``) and each
attempt's log directory (``.git/infra-factory/logs/<ticket>-<stamp>/``): the bridge's routing
evidence (``*.routing.json``), the changed-test gate evidence (``changed-tests.json``), cold-check
reports and review results. Nothing is sent anywhere.

    python3 ops/factory/routing_report.py --repo .            # Markdown tables
    python3 ops/factory/routing_report.py --repo . --json     # one record per attempt

Attempts from before 0.3.4 have no routing evidence and are reported as ``unrecorded``.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def routing(path: Path) -> dict[str, Any]:
    data = load_json(path)
    if not isinstance(data, dict):
        return {"model": "unrecorded", "effort": "unrecorded"}
    served = data.get("served_models") or {}
    tokens = sum((u.get("inputTokens") or 0) + (u.get("outputTokens") or 0) for u in served.values())
    return {
        "provider": data.get("provider"),
        "model": data.get("requested_model"),
        "effort": data.get("requested_effort"),
        "served": sorted(served),
        "outcome": data.get("outcome"),
        "cost_usd": data.get("total_cost_usd"),
        "tokens": tokens,
        "duration_ms": data.get("duration_ms"),
        "turns": data.get("num_turns"),
    }


def builder_routing(logs: Path) -> dict[str, Any]:
    """The first builder turn's routing, with cost/tokens/duration summed over its repair rounds."""
    first = routing(logs / "builder-result.routing.json")
    repairs = [routing(p) for p in sorted(logs.glob("builder-result.repair-*.routing.json"))]
    for r in repairs:
        for key in ("cost_usd", "tokens", "duration_ms"):
            first[key] = (first.get(key) or 0) + (r.get(key) or 0)
    first["repair_turns"] = len(repairs)
    return first


def attempts(repo: Path) -> list[dict[str, Any]]:
    home = repo / ".git" / "infra-factory"
    ledger = home / "ledger.sqlite3"
    if not ledger.is_file():
        raise SystemExit(f"no factory ledger at {ledger}")
    con = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    events = [dict(r) for r in con.execute("SELECT ticket_id, state, details FROM events ORDER BY sequence")]
    con.close()
    out: list[dict[str, Any]] = []
    for i, ev in enumerate(events):
        details = json.loads(ev["details"]) if ev["details"] else {}
        if ev["state"] != "RUNNING" or "branch" not in details:
            continue
        stamp = details["branch"].rsplit("-", 1)[-1]
        logs = home / "logs" / f"{ev['ticket_id']}-{stamp}"
        end = next(
            (
                e
                for e in events[i + 1 :]
                if e["ticket_id"] == ev["ticket_id"] and e["state"] in ("BLOCKED", "READY", "MERGED")
            ),
            None,
        )
        end_details = json.loads(end["details"]) if end and end["details"] else {}
        gate = load_json(logs / "changed-tests.json") or {}
        cold: dict[str, dict[str, str]] = {}
        for lens in ("standards", "spec"):
            # A suite that ran has a log; only a passing suite gets a report (the toolkit writes
            # none for a failure), so a log without a passing report is a failure.
            lens_dir = logs / f"cold-{lens}"
            cold[lens] = {}
            for log in sorted(lens_dir.glob("*.log")):
                if log.stem.startswith("preflight"):
                    continue
                report = load_json(lens_dir / "reports" / f"{log.stem}.json") or {}
                cold[lens][log.stem] = report.get("status", "failed")
        reviews = {}
        for lens in ("standards", "spec"):
            result = load_json(logs / f"review-{lens}-result.json") or {}
            reviews[lens] = {
                "verdict": result.get("verdict", "not reached"),
                "findings": len(result.get("findings") or []),
                **{"routing": routing(logs / f"review-{lens}-result.routing.json")},
            }
        out.append(
            {
                "ticket": ev["ticket_id"],
                "attempt": details.get("attempts"),
                "logs": str(logs),
                "outcome": end["state"] if end else "IN FLIGHT",
                "error": (end_details.get("error") or "")[:300],
                "builder": builder_routing(logs),
                "gate": {
                    "outcome": gate.get("outcome", "not run"),
                    "rounds": len(gate.get("rounds") or []),
                    "repairs_used": max(0, len(gate.get("agent_runs") or []) - 1),
                },
                "cold_failed": sorted(
                    {k for lens in cold.values() for k, s in lens.items() if s != "passed"}
                ),
                "reviews": reviews,
            }
        )
    return out


def summary(rows: list[dict[str, Any]]) -> str:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["builder"]["model"]), str(row["builder"]["effort"]))].append(row)
    lines = [
        "## Builders by model and effort",
        "",
        "| Model | Effort | Attempts | READY/MERGED | Blocked at gate | Blocked in cold checks | Repairs used | Cost (USD) | Tokens |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for (model, effort), items in sorted(groups.items()):
        ok = sum(r["outcome"] in ("READY", "MERGED") for r in items)
        gate = sum(r["gate"]["outcome"] == "failed" for r in items)
        cold = sum(bool(r["cold_failed"]) for r in items)
        repairs = sum(r["gate"]["repairs_used"] for r in items)
        cost = sum(r["builder"].get("cost_usd") or 0 for r in items)
        tokens = sum(r["builder"].get("tokens") or 0 for r in items)
        lines.append(
            f"| {model} | {effort} | {len(items)} | {ok} | {gate} | {cold} | {repairs} | {cost:.2f} | {tokens} |"
        )
    lines += [
        "",
        "## Attempts",
        "",
        "| Ticket | Attempt | Outcome | Builder | Gate | Cold failures | Reviews |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        builder = f"{r['builder']['model']}/{r['builder']['effort']}"
        reviews = ", ".join(f"{lens}: {v['verdict']}" for lens, v in r["reviews"].items())
        lines.append(
            f"| {r['ticket']} | {r['attempt']} | {r['outcome']} | {builder} | {r['gate']['outcome']} | "
            f"{', '.join(r['cold_failed']) or '-'} | {reviews} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--repo", type=Path, default=Path("."))
    p.add_argument("--json", action="store_true", help="one JSON record per attempt")
    a = p.parse_args(argv)
    rows = attempts(a.repo.resolve())
    print(json.dumps(rows, indent=2) if a.json else summary(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
