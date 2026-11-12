#!/usr/bin/env python3
"""Trusted changed-test execution gate for factory builders (ADR-0030).

A builder's statement that its tests pass is not evidence. After the builder exits, and before the
controller commits its work, the controller itself runs every test file the builder created or
changed, plus every test file the ticket declares, in the builder's own worktree:

    frontend/**/*.test.ts(x)       npx --no-install vitest run <file>           (frontend/)
    e2e/tests/**/*.spec.ts         npx --no-install playwright test <file>      (e2e/, real backend + SPA)
    e2e/visual/**/*.spec.ts        the same with --config=playwright.visual.config.ts
    backend/tests/**/test_*.py     uv run --frozen --no-sync pytest <file>      (backend/, private database)

It runs in a fresh copy of the builder's changes that the controller provisioned itself (see
``bootstrap_builder.py``), one file per run, so each file must yield its own JUnit with at least one
test, exit code 0 and no failure, error or skip (the cold-check rule). Runners never install or
download anything. A declared test file that does not exist, or a changed test file with no
trusted runner, fails the gate. The gate must not change the candidate: tracked and untracked
files are compared by content before and after. Evidence (commands, exit codes, counts, log and
JUnit hashes) is written beside the builder result. Cold verification is unchanged and still runs
every selected suite twice afterwards; this gate only stops untested work from reaching it.

Imported by ``bootstrap_builder.py``; this file lives under ``ops/factory/`` (a protected path).
"""

# ruff: noqa: S607  (runs fixed, trusted argv by design)
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

TEST_NAME = re.compile(r"(.+\.(test|spec)\.[cm]?[jt]sx?|test_.+\.py|.+_test\.py)")
SCHEMA = 1


class GateError(RuntimeError):
    pass


def is_test_file(path: str) -> bool:
    return bool(TEST_NAME.fullmatch(PurePosixPath(path).name))


def runner_for(path: str) -> str:
    """The trusted runner for one test file, or 'unsupported'."""
    p = PurePosixPath(path)
    name = p.name
    if p.parts[:1] == ("frontend",) and re.fullmatch(r".+\.test\.tsx?", name):
        return "vitest"
    if p.parts[:2] == ("e2e", "tests") and name.endswith(".spec.ts"):
        return "playwright"
    if p.parts[:2] == ("e2e", "visual") and name.endswith(".spec.ts"):
        return "playwright-visual"
    if p.parts[:2] == ("backend", "tests") and re.fullmatch(r"test_.+\.py|.+_test\.py", name):
        return "pytest"
    return "unsupported"


def ticket_from_prompt(text: str) -> dict[str, Any]:
    """The factory appends the ticket JSON to the builder prompt; read it back."""
    try:
        ticket, _ = json.JSONDecoder().raw_decode(text[text.index("{") :])
    except ValueError:
        raise GateError("cannot find the ticket JSON in the builder prompt") from None
    if not isinstance(ticket, dict) or not isinstance(ticket.get("paths"), list):
        raise GateError("the builder prompt does not carry a ticket with paths")
    return ticket


def changed_files(root: Path) -> list[str]:
    """Added, modified or untracked paths in the worktree (deletions excluded)."""
    out = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames"],
        cwd=root,
        capture_output=True,
    )
    if out.returncode:
        raise GateError("git status failed in the builder worktree")
    files = []
    for entry in out.stdout.split(b"\0"):
        if entry and "D" not in entry[:2].decode():
            files.append(entry[3:].decode("utf-8", "surrogateescape"))
    return sorted(files)


SAFE_PATH = re.compile(r"[A-Za-z0-9._/@+-]+")


def safe_path(path: str) -> bool:
    """A test path that cannot be read as a runner option or split by a shell."""
    return bool(SAFE_PATH.fullmatch(path)) and not any(
        part.startswith("-") for part in PurePosixPath(path).parts
    )


def plan(root: Path, ticket: dict[str, Any]) -> tuple[dict[str, list[str]], list[str]]:
    """{runner: [files]} to execute, and declared test files that are missing."""
    declared = [p for p in ticket["paths"] if isinstance(p, str) and is_test_file(p)]
    missing = sorted(p for p in declared if not (root / p).is_file())
    wanted = {p for p in changed_files(root) if is_test_file(p)} | {
        p for p in declared if (root / p).is_file()
    }
    groups: dict[str, list[str]] = {}
    for path in sorted(wanted):
        groups.setdefault(runner_for(path), []).append(path)
    return groups, missing


def junit_counts(path: Path) -> dict[str, int] | None:
    if path.is_symlink() or not path.is_file():
        return None
    raw = path.read_bytes()
    # Written by test code the builder authored: refuse DTDs/entities outright (fail closed) rather
    # than rely on the parser's expansion limits. ElementTree never fetches external entities.
    if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
        return None
    try:
        root = ET.fromstring(raw)  # noqa: S314 (DTD/entities refused above)
    except ET.ParseError:
        return None
    counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for case in root.iter("testcase"):
        counts["tests"] += 1
        for kind, key in (("failure", "failures"), ("error", "errors"), ("skipped", "skipped")):
            if case.find(kind) is not None:
                counts[key] += 1
    return counts


def sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def namespace(root: Path) -> str:
    return hashlib.sha256(("gate:" + str(root)).encode()).hexdigest()[:10]


def command(
    runner: str, files: list[str], root: Path, junit: Path, ctx: Any
) -> tuple[list[str], Path, dict[str, str]]:
    """(argv, cwd, extra env) for one runner over its files."""
    ns = namespace(root)
    if runner == "vitest":
        rel = [str(PurePosixPath(f).relative_to("frontend")) for f in files]
        argv = [
            "npx",
            "--no-install",
            "vitest",
            "run",
            "--reporter=default",
            "--reporter=junit",
            f"--outputFile.junit={junit}",
            *rel,
        ]
        return argv, root / "frontend", {}
    if runner in ("playwright", "playwright-visual"):
        rel = [str(PurePosixPath(f).relative_to("e2e")) for f in files]
        port = 20000 + (int(ns[:6], 16) % 4500) * 2  # API port; the SPA uses port + 1 (as run_suite.py)
        env = {
            "VSH_E2E_ADMIN_URL": ctx.pg_admin_url,
            "VSH_E2E_DB": f"vsh_factory_{ns}_gate_{runner.replace('-', '_')}",
            "VSH_E2E_API_PORT": str(port),
            "VSH_E2E_WEB_PORT": str(port + 1),
            "PLAYWRIGHT_JUNIT_OUTPUT_FILE": str(junit),
        }
        argv = ["npx", "--no-install", "playwright", "test", "--reporter=list,junit", "--trace=off"]
        if runner == "playwright-visual":
            argv.append("--config=playwright.visual.config.ts")
        return argv + rel, root / "e2e", env
    if runner == "pytest":
        rel = [str(PurePosixPath(f).relative_to("backend")) for f in files]
        env = {
            "VSH_TEST_ADMIN_URL": ctx.pg_admin_url,
            "VSH_TEST_DB_NAME": f"vsh_factory_{ns}_gate_pytest",
            "VSH_REQUIRE_EPHEMERIS": "1",
        }
        argv = [
            "uv",
            "run",
            "--frozen",
            "--no-sync",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            f"--junitxml={junit}",
            *rel,
        ]
        return argv, root / "backend", env
    raise GateError(f"no trusted runner for {runner}")


Runner = Callable[[list[str], Path, dict[str, str], Path], int]


def run_gate(
    root: Path,
    ticket: dict[str, Any],
    ctx: Any,
    out_dir: Path,
    label: str,
    execute: Runner,
    prepare: Callable[[str], None],
) -> dict[str, Any]:
    """Run every changed/declared test once. ``execute(argv, cwd, env, log)`` returns the exit code;
    ``prepare(runner)`` installs what a runner needs (ephemeris, tools) and may raise."""
    groups, missing = plan(root, ticket)
    result: dict[str, Any] = {
        "label": label,
        "started_at": time.time(),
        "declared_missing": missing,
        "runs": [],
    }
    n = 0
    for runner, files in groups.items():
        for path in files:  # one run per file: each file must produce its own tests
            n += 1
            run: dict[str, Any] = {"runner": runner, "files": [path]}
            result["runs"].append(run)
            if runner == "unsupported":
                run.update(passed=False, reason="no trusted runner for this test file")
                continue
            if not safe_path(path):
                run.update(passed=False, reason="unsafe test file name (could be read as a runner option)")
                continue
            junit = out_dir / f"{label}-{n}-{runner}.junit.xml"
            log = out_dir / f"{label}-{n}-{runner}.log"
            for stale in (junit, log):
                if stale.exists() or stale.is_symlink():
                    raise GateError(f"stale gate output {stale.name}; refusing to reuse evidence")
            try:
                prepare(runner)
                argv, cwd, extra = command(runner, [path], root, junit, ctx)
                env = dict(ctx.env)
                env.update(extra)
                run["argv"] = argv
                run["exit_code"] = execute(argv, cwd, env, log)
            except GateError as exc:
                run.update(passed=False, reason=str(exc))
                continue
            counts = junit_counts(junit)
            run.update(
                counts=counts,
                log=str(log),
                log_sha256=sha256(log),
                junit=str(junit),
                junit_sha256=sha256(junit),
            )
            reasons = []
            if run["exit_code"] != 0:
                reasons.append(f"exit code {run['exit_code']}")
            if counts is None:
                reasons.append("no JUnit report")
            else:
                if counts["tests"] < 1:
                    reasons.append("no tests ran from this file")
                for key in ("failures", "errors", "skipped"):
                    if counts[key]:
                        reasons.append(f"{counts[key]} {key}")
            run["passed"] = not reasons
            if reasons:
                run["reason"] = ", ".join(reasons)
    result["finished_at"] = time.time()
    result["passed"] = not missing and all(r["passed"] for r in result["runs"])
    result["tested_files"] = sorted(f for r in result["runs"] for f in r["files"])
    # Zero changed or declared tests passes (cold verification still runs every suite); it is
    # recorded so routing_report and reviewers can see a ticket that added no tests.
    result["no_tests"] = not result["runs"] and not missing
    return result


def failure_report(result: dict[str, Any], max_lines: int = 120) -> str:
    """What a builder needs to fix its work: which runs failed and the end of their output."""
    parts = []
    for path in result["declared_missing"]:
        parts.append(f"- Declared test file {path} does not exist; the ticket requires it.")
    for run in result["runs"]:
        if run["passed"]:
            continue
        parts.append(f"- {run['runner']} over {', '.join(run['files'])}: {run.get('reason', 'failed')}")
        log = Path(run["log"]) if run.get("log") else None
        if log and log.is_file():
            tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]
            parts.append("  Last lines of its output:\n" + "\n".join("    " + line for line in tail))
    return "\n".join(parts)
