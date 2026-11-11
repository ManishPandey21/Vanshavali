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

Any failure stops here with a ``[bootstrap] FAILED`` line and a non-zero exit, so the builder never
starts and the factory blocks the ticket. There is no fallback: nothing retries with ``npm
install``, skips a component, or grants the agent anything. Output goes to the builder log.

This file lives under ``ops/factory/`` (a protected path): a builder cannot change it.
"""

# ruff: noqa: S603, S606, S607  (runs fixed, trusted argv by design)
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
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


def check_lockfiles(root: Path) -> None:
    for component, lockfile, _ in COMPONENTS:
        rel = f"{component}/{lockfile}"
        path = root / rel
        if path.is_symlink() or not path.is_file():
            raise BootstrapError(f"{rel} is missing: dependencies install only from a committed lockfile")
        if subprocess.run(
            ["git", "ls-files", "--error-unmatch", rel], cwd=root, capture_output=True
        ).returncode:
            raise BootstrapError(f"{rel} is not committed")
        if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", rel], cwd=root).returncode:
            raise BootstrapError(f"{rel} differs from the committed lockfile")


def tracked_state(root: Path) -> str:
    return git(root, "status", "--porcelain=v1", "--untracked-files=all")


def install_env(cache: Path, network_env: Path | None) -> dict[str, str]:
    env = dict(os.environ)
    if network_env is not None:
        rs = _load_run_suite()
        try:
            saved = rs.read_network_env(network_env)
        except rs.SuiteError as exc:
            raise BootstrapError(str(exc)) from None
        # Unlike a cold check, a builder inherits the factory's live environment; a captured file
        # can be stale (a local proxy restarted on another port), so it only fills in what is unset.
        for key, value in saved.items():
            env.setdefault(key, value)
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


def step(argv: list[str], cwd: Path, env: dict[str, str], root: Path) -> None:
    if not shutil.which(argv[0], path=env.get("PATH")):
        raise BootstrapError(f"`{argv[0]}` is not on PATH (see docs/operations/code-factory.md)")
    log(f"$ (cd {cwd.relative_to(root)}) {' '.join(argv)}")
    started = time.monotonic()
    try:
        proc = subprocess.run(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, timeout=STEP_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise BootstrapError(f"{argv[0]} timed out after {STEP_TIMEOUT}s") from None
    if proc.returncode:
        raise BootstrapError(f"{argv[0]} exited {proc.returncode}")
    log(f"  ok in {time.monotonic() - started:.0f}s")


def provision(root: Path, cache: Path, network_env: Path | None) -> dict[str, str]:
    check_worktree(root)
    check_lockfiles(root)
    cache.mkdir(parents=True, exist_ok=True)
    env = install_env(cache, network_env)
    before = tracked_state(root)
    started = time.monotonic()
    for component, _, argv in COMPONENTS:
        step(argv, root / component, env, root)
    # Version-matched browser for the pinned @playwright/test (cached; no download when present).
    step(["npx", "playwright", "install", "chromium"], root / "e2e", env, root)
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
    p.add_argument("--network-env", help="private KEY=VALUE file of proxy/CA settings (outside the repo)")
    a = p.parse_args(argv[:sep])
    agent = argv[sep + 1 :]
    try:
        net = Path(a.network_env).expanduser() if a.network_env else None
        env = provision(Path.cwd().resolve(), Path(a.cache_dir).expanduser().resolve(), net)
    except BootstrapError as exc:
        log(f"FAILED: {exc}")
        log("the builder was not started; fix the host or repository, then `retry` the ticket")
        return 3
    sys.stderr.flush()
    os.execvpe(agent[0], agent, env)
    return 0  # unreachable


if __name__ == "__main__":
    sys.exit(main())
