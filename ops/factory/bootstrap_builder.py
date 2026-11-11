#!/usr/bin/env python3
"""Orchestrator-owned dependency bootstrap for factory builders (ADR-0029).

Builders run as headless coding agents that may run tests but may **not** install packages. A
fresh builder worktree has no ``node_modules`` or ``.venv``, so without this step a builder cannot
run a single test (the first live ticket, U02-VITALS-EDIT-B, blocked exactly that way). The
factory therefore launches every builder through this wrapper, which the *controller* runs before
the agent exists:

    python3 -I ops/factory/bootstrap_builder.py --cache-dir DIR [--network-env FILE] -- AGENT_ARGV...

1. Refuses to run anywhere but the top level of a factory builder worktree (a linked Git worktree
   under ``<git-common-dir>/infra-factory/worktrees``, following the symlink the runbook asks for).
2. Checks every lockfile it installs from is committed and unmodified.
3. Installs from those lockfiles only: ``uv sync --frozen`` (backend), ``npm ci`` (frontend, e2e)
   and the Playwright Chromium matching the pinned ``@playwright/test``. ``npm ci`` always replaces
   ``node_modules``, so a reused worktree with a stale or partial install is handled the same way
   as a new one.
4. Checks the installs changed no tracked file (``node_modules``/``.venv`` are git-ignored).
5. Replaces itself with AGENT_ARGV (``exec``): the agent command and its permissions are unchanged.

With ``--gate`` (what ``configure_factory.py`` writes, ADR-0030) step 5 instead runs the agent as a
child, then runs the trusted changed-test gate (``changed_test_gate.py``) in the same worktree:
every test file the builder created or changed, and every test file the ticket declares, must run
and pass under the controller before the factory commits the work and starts cold review. A failing
gate gives the builder the controller's own failure output for at most ``--repair-rounds`` more
turns (same attempt, same model and effort), then blocks the ticket. ``--min-free-gb`` and
``--node-major`` refuse a host that cannot run the suites.

Any failure stops here with a ``[bootstrap] FAILED`` line and a non-zero exit, so the builder never
starts and the factory blocks the ticket. There is no fallback: nothing retries with ``npm
install``, skips a component, or grants the agent anything. Output goes to the builder log.

This file lives under ``ops/factory/`` (a protected path): a builder cannot change it.
"""

# ruff: noqa: S603, S606, S607  (runs fixed, trusted argv by design)
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEP_TIMEOUT = 1200  # seconds per install step; the factory's builder timeout bounds the whole call
NPM_CI = ["npm", "ci", "--no-audit", "--no-fund"]
# (component dir, lockfile, install argv) - every install reads only the committed lockfile.
COMPONENTS = (
    ("backend", "uv.lock", ["uv", "sync", "--frozen"]),
    ("frontend", "package-lock.json", NPM_CI),
    ("e2e", "package-lock.json", NPM_CI),
)
# Files that steer those installs (registry, scripts, interpreter). If present they must be committed
# and unmodified, like the lockfiles; an untracked one could point an install anywhere.
INSTALL_CONFIG = (
    ".npmrc",
    "frontend/.npmrc",
    "e2e/.npmrc",
    "uv.toml",
    "backend/uv.toml",
    "backend/.python-version",
)


class BootstrapError(RuntimeError):
    pass


def log(msg: str) -> None:
    print(f"[bootstrap] {msg}", file=sys.stderr, flush=True)


def _load_run_suite():
    # -I drops the script directory from sys.path; load the sibling module explicitly.
    spec = importlib.util.spec_from_file_location("vsh_factory_run_suite", HERE / "run_suite.py")
    if spec is None or spec.loader is None:
        raise BootstrapError("cannot load ops/factory/run_suite.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if proc.returncode:
        raise BootstrapError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def check_worktree(root: Path) -> None:
    """Only the top level of a linked worktree inside the factory's worktrees directory."""
    reason = "not a factory builder worktree"
    try:
        top = Path(git(root, "rev-parse", "--show-toplevel")).resolve()
        git_dir = Path(git(root, "rev-parse", "--path-format=absolute", "--git-dir")).resolve()
        common = Path(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
    except BootstrapError as exc:
        raise BootstrapError(f"{root}: {reason} ({exc})") from None
    if top != root:
        raise BootstrapError(f"{root}: {reason} (run from the worktree root {top})")
    if git_dir == common:
        raise BootstrapError(f"{root}: {reason} (this is the main checkout)")
    allowed = (common / "infra-factory" / "worktrees").resolve()
    if allowed == root or allowed not in root.parents:
        raise BootstrapError(f"{root}: {reason} (expected under {allowed})")


def check_committed(root: Path, rel: str, what: str) -> None:
    """``rel`` must equal its blob in HEAD byte for byte.

    Compares content hashes rather than asking ``git diff``/``git status``, which honour the
    ``--assume-unchanged`` and ``--skip-worktree`` index flags and would hide a modified file.
    """
    path = root / rel
    if path.is_symlink() or not path.is_file():
        raise BootstrapError(f"{rel} is not a regular file")
    committed = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"HEAD:{rel}"], cwd=root, capture_output=True, text=True
    )
    if committed.returncode:
        raise BootstrapError(f"{rel} is not committed")
    if git(root, "hash-object", "--no-filters", "--", rel) != committed.stdout.strip():
        raise BootstrapError(f"{rel} differs from the committed {what}")


def check_lockfiles(root: Path) -> None:
    for component, lockfile, _ in COMPONENTS:
        rel = f"{component}/{lockfile}"
        if not (root / rel).exists() and not (root / rel).is_symlink():
            raise BootstrapError(f"{rel} is missing: dependencies install only from a committed lockfile")
        check_committed(root, rel, "lockfile")
    for rel in INSTALL_CONFIG:
        if (root / rel).exists() or (root / rel).is_symlink():
            check_committed(root, rel, "install configuration")


def tracked_state(root: Path) -> dict[str, str]:
    """Every changed or untracked path with a hash of its content (ignored files excluded)."""
    out = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames"],
        cwd=root,
        capture_output=True,
    )
    if out.returncode:
        raise BootstrapError(f"git status failed: {out.stderr.decode(errors='replace').strip()}")
    state: dict[str, str] = {}
    for entry in out.stdout.split(b"\0"):
        if not entry:
            continue
        rel = entry[3:].decode("utf-8", "surrogateescape")
        path = root / rel
        if path.is_symlink():
            digest = "link:" + os.readlink(path)
        elif path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            digest = "absent"
        state[rel] = entry[:2].decode() + ":" + digest
    return state


def proxy_key(name: str) -> bool:
    return "proxy" in name.lower()


def no_proxy_key(name: str) -> bool:
    # NO_PROXY / npm_config_noproxy list exceptions; on their own they name no proxy.
    return name.lower().replace("_", "").endswith("noproxy")


def merge_network(env: dict[str, str], network_env: Path | None) -> None:
    """Fill ``env`` from the saved network file, never mixing a stale saved proxy with a live one."""
    if network_env is not None:
        rs = _load_run_suite()
        try:
            saved = rs.read_network_env(network_env)
        except rs.SuiteError as exc:
            raise BootstrapError(str(exc)) from None
        # Unlike a cold check, a builder inherits the factory's live environment, and a captured
        # file can be stale (a local proxy restarted on another port). Proxy settings are taken as a
        # set: if the live environment has any, none come from the file (npm and Playwright read
        # npm_config_*/lowercase names first, so mixing would pick the stale one). Other settings
        # (CA bundles) only fill in what is unset.
        proxies = {k for k in rs.NETWORK_KEYS if proxy_key(k) and not no_proxy_key(k)}
        live_proxy = any(env.get(k) for k in proxies)
        for key, value in saved.items():
            if proxy_key(key) and live_proxy:
                continue
            env.setdefault(key, value)


def install_env(cache: Path, network_env: Path | None) -> dict[str, str]:
    env = dict(os.environ)
    merge_network(env, network_env)
    env.pop("PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD", None)
    # Same caches as the cold checks (run_suite.py), so downloads are shared and offline-friendly.
    env.update(
        {
            "UV_PYTHON": "3.11",
            "UV_CACHE_DIR": str(cache / "uv"),
            "UV_PYTHON_INSTALL_DIR": str(cache / "uv-python"),
            "UV_LINK_MODE": "copy",
            "npm_config_cache": str(cache / "npm"),
            "npm_config_update_notifier": "false",
            "npm_config_fund": "false",
            "npm_config_audit": "false",
            "PLAYWRIGHT_BROWSERS_PATH": str(cache / "ms-playwright"),
        }
    )
    return env


def run_bounded(
    argv: list[str], cwd: Path, env: dict[str, str], timeout: int, output: Path | None = None
) -> int:
    """Run one trusted command; its exit code. A timeout kills it (and, under the factory, us)."""
    if not shutil.which(argv[0], path=env.get("PATH")):
        raise BootstrapError(f"`{argv[0]}` is not on PATH (see docs/operations/code-factory.md)")
    # Steps stay in the bootstrap's process group: the factory stops a builder by killing that
    # group (SIGKILL, uncatchable), which must take running installs and their scripts with it.
    sink = open(output, "xb") if output is not None else None  # noqa: SIM115 (closed below)
    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=sink,
            stderr=subprocess.STDOUT if sink else None,
        )
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            log(f"FAILED: {argv[0]} timed out after {timeout}s; stopping it and its child processes")
            log("the builder was not started or its work was not accepted; fix the cause, then `retry`")
            sys.stderr.flush()
            if os.getpgrp() == os.getpid():
                # Started by the factory, we lead our own group: kill it whole (this process too),
                # so scripts the tool spawned cannot outlive the step.
                os.killpg(os.getpgrp(), signal.SIGKILL)
            proc.kill()  # run by hand inside someone else's group: stop only the step itself
            proc.wait()
            raise BootstrapError(f"{argv[0]} timed out after {timeout}s") from None
        return proc.returncode
    finally:
        if sink is not None:
            sink.close()


def step(argv: list[str], cwd: Path, env: dict[str, str], root: Path, timeout: int) -> None:
    log(f"$ (cd {cwd.relative_to(root)}) {' '.join(argv)}")
    started = time.monotonic()
    code = run_bounded(argv, cwd, env, timeout)
    if code:
        raise BootstrapError(f"{argv[0]} exited {code}")
    log(f"  ok in {time.monotonic() - started:.0f}s")


def provision(
    root: Path, cache: Path, network_env: Path | None, timeout: int = STEP_TIMEOUT
) -> dict[str, str]:
    check_worktree(root)
    check_lockfiles(root)
    cache.mkdir(parents=True, exist_ok=True)
    env = install_env(cache, network_env)
    before = tracked_state(root)
    started = time.monotonic()
    for component, _, argv in COMPONENTS:
        step(argv, root / component, env, root, timeout)
    # Version-matched browser for the pinned @playwright/test (cached; no download when present).
    step(["npx", "playwright", "install", "chromium"], root / "e2e", env, root, timeout)
    if tracked_state(root) != before:
        raise BootstrapError("dependency installation changed tracked files in the worktree")
    log(
        f"dependencies ready ({', '.join(c for c, _, _ in COMPONENTS)}) in "
        f"{time.monotonic() - started:.0f}s; starting builder"
    )
    # The builder sees the browsers it was given; nothing else about its environment changes.
    builder_env = dict(os.environ)
    builder_env["PLAYWRIGHT_BROWSERS_PATH"] = env["PLAYWRIGHT_BROWSERS_PATH"]
    return builder_env


def host_checks(root: Path, cache: Path, min_free_gb: float, node_major: int | None) -> None:
    """Refuse a host that cannot run the suites, with a message saying what to fix."""
    cache.mkdir(parents=True, exist_ok=True)
    for where in (root, cache):
        free = shutil.disk_usage(where).free / 2**30
        if free < min_free_gb:
            raise BootstrapError(
                f"only {free:.1f} GiB free at {where}; the suites need {min_free_gb:g} GiB "
                "(remove finished factory worktrees with `git worktree remove`, or old caches)"
            )
    if node_major is not None:
        node = shutil.which("node")
        if not node:
            raise BootstrapError("`node` is not on PATH (Node.js 22 is required)")
        version = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()
        try:
            major = int(version.lstrip("v").split(".")[0])
        except ValueError:
            raise BootstrapError(f"cannot read the Node.js version ({version!r})") from None
        if major != node_major:
            raise BootstrapError(f"Node.js {version} found; CI and the lockfiles use Node {node_major}.x")


GATE_NOTICE = """

Controller test gate (trusted; read before you finish): when you stop, the factory controller itself
runs, in this worktree, every test file you created or changed and every test file the ticket
declares: frontend *.test.ts(x) with `cd frontend && npx vitest run <file>`, e2e/tests/*.spec.ts with
`cd e2e && npx playwright test <file>` (it starts its own backend, database and SPA; nothing to set
up), backend tests with `cd backend && uv run pytest <file>`. A failure, a skipped test or a missing
declared test blocks this attempt before review. Run those commands yourself first: see each new test
fail before your change and pass after it. Take every locator and label from the rendered page or the
component source, never from the ticket's wording. Dependencies are installed; you cannot and need not
install packages. If the skill file named above cannot be read, use the
superpowers:test-driven-development skill through the Skill tool.
"""


def _flag_value(agent: list[str], flag: str) -> Path:
    if flag not in agent or agent.index(flag) == len(agent) - 1:
        raise BootstrapError(f"--gate needs an agent command with {flag} (the factory's bridge has it)")
    return Path(agent[agent.index(flag) + 1])


def _with(agent: list[str], flag: str, value: Path) -> list[str]:
    out = list(agent)
    out[out.index(flag) + 1] = str(value)
    return out


def gated_build(
    root: Path,
    agent: list[str],
    builder_env: dict[str, str],
    cache: Path,
    network_env: Path | None,
    pg_admin_url: str,
    repair_rounds: int,
    timeout: int,
) -> int:
    """Run the agent, then the changed-test gate; give it the gate's failure at most repair_rounds times."""
    gate = _load("changed_test_gate")
    prompt_file = _flag_value(agent, "--prompt-file")
    result_file = _flag_value(agent, "--result-file")
    logs = result_file.parent
    evidence_path = logs / "changed-tests.json"
    if evidence_path.exists() or evidence_path.is_symlink():
        raise BootstrapError(f"stale {evidence_path.name}; refusing to reuse gate evidence")
    ticket = gate.ticket_from_prompt(prompt_file.read_text(encoding="utf-8"))
    rs = _load_run_suite()
    ctx = rs.Context(root, cache, pg_admin_url, None)
    merge_network(ctx.env, network_env)
    evidence: dict = {
        "schema": gate.SCHEMA,
        "ticket": ticket.get("id"),
        "worktree": str(root),
        "repair_rounds_allowed": repair_rounds,
        "agent_runs": [],
        "rounds": [],
        "outcome": "error",
    }

    def prepare(runner: str) -> None:
        if runner == "pytest":
            if not shutil.which("tesseract", path=ctx.env.get("PATH")):
                raise gate.GateError("`tesseract` is not on PATH; backend tests must run, never skip")
            try:
                ctx.ephemeris()
            except rs.SuiteError as exc:
                raise gate.GateError(f"ephemeris unavailable: {exc}") from None

    def execute(argv: list[str], cwd: Path, env: dict[str, str], output: Path) -> int:
        log(f"gate $ (cd {cwd.relative_to(root)}) {' '.join(argv)}")
        return run_bounded(argv, cwd, env, timeout, output)

    base_prompt = prompt_file.read_text(encoding="utf-8") + GATE_NOTICE
    prompt = logs / "builder-prompt.gated.txt"
    if prompt.exists() or prompt.is_symlink():
        raise BootstrapError(f"stale {prompt.name}; refusing to reuse a builder prompt")
    result = result_file
    repair_text = ""
    try:
        for round_no in range(repair_rounds + 1):
            prompt.write_text(base_prompt if round_no == 0 else repair_text, encoding="utf-8")
            code = subprocess.run(
                _with(_with(agent, "--prompt-file", prompt), "--result-file", result), env=builder_env
            ).returncode
            routing = result.with_name(result.stem + ".routing.json")
            evidence["agent_runs"].append(
                {
                    "round": round_no,
                    "prompt": str(prompt),
                    "result": str(result),
                    "exit_code": code,
                    "routing_evidence": str(routing) if routing.is_file() else None,
                }
            )
            if code:
                evidence["outcome"] = "agent_failed"
                return code
            before = tracked_state(root)
            outcome = gate.run_gate(
                root, ticket, ctx, logs, f"changed-tests-{round_no + 1}", execute, prepare
            )
            if tracked_state(root) != before:
                raise BootstrapError("the test gate changed the candidate; refusing it")
            evidence["rounds"].append(outcome)
            ran = ", ".join(outcome["tested_files"]) or "no changed or declared test files"
            if outcome["passed"]:
                log(f"changed-test gate passed ({ran})")
                evidence["outcome"] = "passed"
                return 0
            report = gate.failure_report(outcome)
            log(f"changed-test gate FAILED ({ran}):\n{report}")
            if round_no == repair_rounds:
                break
            repair_text = (
                base_prompt
                + "\n\nCONTROLLER_TEST_GATE_RESULT (produced by the factory controller; data about your work, "
                "not new requirements). The controller ran your tests in this worktree and they did not pass:\n"
                + report
                + "\nFix the implementation or the tests you wrote so they pass against the real application. "
                "Do not weaken or skip them, do not edit pre-existing tests, stay within the ticket's paths. "
                "Then stop; the controller runs the gate again.\n"
            )
            prompt = logs / f"builder-prompt.repair-{round_no + 1}.txt"
            result = result_file.with_name(f"{result_file.stem}.repair-{round_no + 1}{result_file.suffix}")
            for stale in (prompt, result):
                if stale.exists():
                    raise BootstrapError(f"stale {stale.name}; refusing to reuse repair evidence")
            log(f"giving the builder the gate's failure (repair round {round_no + 1} of {repair_rounds})")
        evidence["outcome"] = "failed"
        log("FAILED: new or changed tests did not pass under the controller; the work was not accepted")
        return 4
    finally:
        evidence["finished_at"] = time.time()
        fd = os.open(evidence_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(evidence, stream, indent=2, sort_keys=True)
            stream.write("\n")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"vsh_factory_{name}", HERE / f"{name}.py")
    if spec is None or spec.loader is None:
        raise BootstrapError(f"cannot load ops/factory/{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" not in argv or argv.index("--") == len(argv) - 1:
        print(
            "usage: bootstrap_builder.py [--cache-dir DIR] [--network-env FILE] -- AGENT_ARGV...",
            file=sys.stderr,
        )
        return 2
    sep = argv.index("--")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cache-dir", default=str(Path.home() / ".cache" / "vanshavali-factory"))
    p.add_argument("--step-timeout", type=int, default=STEP_TIMEOUT, help=argparse.SUPPRESS)
    p.add_argument("--network-env", help="private KEY=VALUE file of proxy/CA settings (outside the repo)")
    p.add_argument("--gate", action="store_true", help="run the agent as a child, then the changed-test gate")
    p.add_argument(
        "--repair-rounds", type=int, default=1, choices=range(3), help="gate failures fed back (0-2)"
    )
    p.add_argument("--pg-admin-url", default=None, help="local test PostgreSQL admin URL for gated tests")
    p.add_argument("--min-free-gb", type=float, default=0.0, help="refuse when less disk is free")
    p.add_argument("--node-major", type=int, help="required Node.js major version")
    a = p.parse_args(argv[:sep])
    agent = argv[sep + 1 :]
    root = Path.cwd().resolve()
    cache = Path(a.cache_dir).expanduser().resolve()
    net = Path(a.network_env).expanduser() if a.network_env else None
    try:
        host_checks(root, cache, a.min_free_gb, a.node_major)
        env = provision(root, cache, net, a.step_timeout)
        if a.gate:
            ns = _load("changed_test_gate").namespace(root)
            port = 20000 + (int(ns[:6], 16) % 4500) * 2
            # The builder's own Playwright runs get private ports and a private database too.
            env.update(
                {
                    "VSH_E2E_API_PORT": str(port),
                    "VSH_E2E_WEB_PORT": str(port + 1),
                    "VSH_E2E_DB": f"vsh_factory_{ns}_builder",
                }
            )
    except BootstrapError as exc:
        log(f"FAILED: {exc}")
        log("the builder was not started; fix the host or repository, then `retry` the ticket")
        return 3
    if a.gate:
        rs = _load_run_suite()
        try:
            return gated_build(
                root,
                agent,
                env,
                cache,
                net,
                a.pg_admin_url or rs.DEFAULT_PG_ADMIN_URL,
                a.repair_rounds,
                a.step_timeout,
            )
        except (BootstrapError, OSError, ValueError, RuntimeError) as exc:
            log(f"FAILED: {exc}")
            return 3
    sys.stderr.flush()
    try:
        os.execvpe(agent[0], agent, env)
    except OSError as exc:
        log(f"FAILED: cannot start the builder {agent[0]!r}: {exc}")
        return 3
    return 0  # unreachable


if __name__ == "__main__":
    sys.exit(main())
