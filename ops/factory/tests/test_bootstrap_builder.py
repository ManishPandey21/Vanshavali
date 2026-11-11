"""Regression tests for the orchestrator-owned builder dependency bootstrap (ADR-0029).

The first live ticket (U02-VITALS-EDIT-B) blocked because its builder worktree had no
``node_modules`` and builders may not install packages, so it never ran a test. The fix installs
dependencies *before* the builder starts, from the committed lockfiles, without giving the builder
any install permission. These tests drive ``bootstrap_builder.py`` against a real Git repository
laid out like a factory host (worktrees symlinked out of ``.git``) with fake ``npm``/``npx``/``uv``.

Run from the repository root: ``python3 -m unittest discover -s ops/factory/tests -v``
"""

# ruff: noqa: S101, S603, S607  (test code; same waiver as backend/tests in pyproject.toml)
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
FACTORY = HERE.parent
BOOTSTRAP = FACTORY / "bootstrap_builder.py"
CONFIGURE = FACTORY / "configure_factory.py"
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
}
PROXY_KEYS = {
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "NODE_EXTRA_CA_CERTS",
    "NPM_CONFIG_HTTPS_PROXY",
    "NPM_CONFIG_PROXY",
    "NPM_CONFIG_NOPROXY",
}
LOCKFILES = ("backend/uv.lock", "frontend/package-lock.json", "e2e/package-lock.json")

FAKE_TOOL = textwrap.dedent(
    """\
    #!/bin/sh
    # Records every call; FAKE_FAIL=<tool> fails it, FAKE_TOUCH=<path> edits a tracked file.
    echo "$(basename "$0") $* @ $(pwd)" >> "$FAKE_LOG"
    if [ -n "$FAKE_PROXY_LOG" ]; then echo "$HTTPS_PROXY" >> "$FAKE_PROXY_LOG"; fi
    if [ -n "$FAKE_ALLPROXY_LOG" ]; then echo "$HTTPS_PROXY|$https_proxy|$npm_config_https_proxy|$NODE_EXTRA_CA_CERTS" >> "$FAKE_ALLPROXY_LOG"; fi
    if [ "$FAKE_FAIL" = "$(basename "$0")" ]; then echo "fake failure" >&2; exit 7; fi
    if [ -n "$FAKE_TOUCH" ]; then echo changed >> "$FAKE_TOUCH"; fi
    if [ "$FAKE_HANG" = "$(basename "$0")" ]; then sleep 300 & echo $! > "$FAKE_PIDFILE"; wait; fi
    if [ "$(basename "$0")" = npm ]; then mkdir -p node_modules && touch node_modules/.installed; fi
    if [ "$(basename "$0")" = uv ]; then mkdir -p .venv; fi
    exit 0
    """
)
FAKE_AGENT = textwrap.dedent(
    """\
    import json, os, sys
    with open(os.environ["FAKE_AGENT_OUT"], "w") as f:
        json.dump({"argv": sys.argv[1:], "cwd": os.getcwd(),
                   "browsers": os.environ.get("PLAYWRIGHT_BROWSERS_PATH"),
                   "frontend_ready": os.path.isfile("frontend/node_modules/.installed"),
                   "e2e_ready": os.path.isfile("e2e/node_modules/.installed")}, f)
    """
)


def git(cwd: Path, *args: str) -> str:
    env = {**os.environ, **GIT_ENV}
    return subprocess.run(
        ["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True
    ).stdout.strip()


class Host:
    """A temporary factory host: main checkout, ledger dir, worktrees symlinked outside .git."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.repo = tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        for rel in LOCKFILES:
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / rel).write_text("{}\n")
        (self.repo / ".gitignore").write_text("node_modules/\n.venv/\n")
        (self.repo / "frontend" / "app.ts").write_text("export {};\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "base")
        self.outside = tmp / "worktrees-outside"
        self.outside.mkdir()
        (self.repo / ".git" / "infra-factory").mkdir()
        (self.repo / ".git" / "infra-factory" / "worktrees").symlink_to(self.outside)
        self.bin = tmp / "bin"
        self.bin.mkdir()
        for tool in ("npm", "npx", "uv"):
            path = self.bin / tool
            path.write_text(FAKE_TOOL)
            path.chmod(0o755)
        self.agent = tmp / "agent.py"
        self.agent.write_text(FAKE_AGENT)
        self.calls = tmp / "calls.log"
        self.agent_out = tmp / "agent.json"
        self.cache = tmp / "cache"

    def worktree(self, name: str = "T-1-1") -> Path:
        path = self.repo / ".git" / "infra-factory" / "worktrees" / name
        git(self.repo, "worktree", "add", "-q", "-b", "infra-factory/" + name, str(path), "main")
        return path

    def run(self, cwd: Path, *extra: str, **env: str) -> subprocess.CompletedProcess[str]:
        full_env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("FAKE_", "PLAYWRIGHT_"))
            and "proxy" not in k.lower()
            and k.upper() not in PROXY_KEYS
        }
        full_env.update(
            {
                "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
                "FAKE_LOG": str(self.calls),
                "FAKE_AGENT_OUT": str(self.agent_out),
                "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1",
                **GIT_ENV,
                **env,
            }
        )
        argv = [sys.executable, "-I", str(BOOTSTRAP), "--cache-dir", str(self.cache), *extra]
        argv += ["--", sys.executable, str(self.agent), "--mode", "builder"]
        return subprocess.run(argv, cwd=cwd, env=full_env, capture_output=True, text=True, timeout=120)

    def call_log(self) -> list[str]:
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def agent_started(self) -> bool:
        return self.agent_out.exists()


class BootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="vsh-bootstrap-test-")
        self.host = Host(Path(self._tmp).resolve())

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def assert_blocked(self, proc: subprocess.CompletedProcess[str], reason: str) -> None:
        self.assertNotEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("[bootstrap] FAILED", proc.stderr)
        self.assertIn(reason, proc.stderr)
        self.assertFalse(self.host.agent_started(), "builder must not start after a failed bootstrap")

    def test_clean_worktree_is_provisioned_then_builder_starts_without_install_rights(self) -> None:
        wt = self.host.worktree()
        proc = self.host.run(wt)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        real = wt.resolve()
        self.assertEqual(
            self.host.call_log(),
            [
                f"uv sync --frozen @ {real / 'backend'}",
                f"npm ci --no-audit --no-fund @ {real / 'frontend'}",
                f"npm ci --no-audit --no-fund @ {real / 'e2e'}",
                f"npx playwright install chromium @ {real / 'e2e'}",
            ],
        )
        started = json.loads(self.host.agent_out.read_text())
        # The builder is the unchanged agent command, in the provisioned worktree.
        self.assertEqual(started["argv"], ["--mode", "builder"])
        self.assertEqual(Path(started["cwd"]).resolve(), real)
        self.assertTrue(started["frontend_ready"] and started["e2e_ready"])
        self.assertEqual(started["browsers"], str(self.host.cache / "ms-playwright"))
        self.assertIn("[bootstrap] dependencies ready", proc.stderr)
        self.assertEqual(git(wt, "status", "--porcelain"), "", "installs must not dirty the candidate")

    def test_reused_worktree_is_reinstalled_from_lockfile_and_keeps_work_in_progress(self) -> None:
        wt = self.host.worktree()
        stale = wt / "frontend" / "node_modules"
        stale.mkdir(parents=True)
        (stale / "stale-package").write_text("from an earlier attempt\n")
        (wt / "frontend" / "app.ts").write_text("export const edited = 1;\n")
        (wt / "frontend" / "new.test.ts").write_text("// new test\n")
        before = git(wt, "status", "--porcelain")
        proc = self.host.run(wt)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        # npm ci (never "skip because node_modules exists") so a partial install is replaced.
        self.assertEqual(sum("npm ci" in c for c in self.host.call_log()), 2)
        self.assertEqual(git(wt, "status", "--porcelain"), before)
        self.assertTrue(self.host.agent_started())

    def test_install_failure_blocks_without_starting_builder_or_widening_the_install(self) -> None:
        wt = self.host.worktree()
        proc = self.host.run(wt, FAKE_FAIL="npm")
        self.assert_blocked(proc, "npm exited 7")
        calls = self.host.call_log()
        self.assertEqual(calls[-1].split(" @ ")[0], "npm ci --no-audit --no-fund")
        # No fallback such as `npm install`, no further steps after the failure.
        self.assertFalse(any(c.startswith("npm install") for c in calls))
        self.assertFalse(any(c.startswith("npx") for c in calls))

    def test_missing_lockfile_blocks_before_any_install(self) -> None:
        wt = self.host.worktree()
        git(wt, "rm", "-q", "e2e/package-lock.json")
        git(wt, "commit", "-q", "-m", "drop lockfile")
        proc = self.host.run(wt)
        self.assert_blocked(proc, "e2e/package-lock.json")
        self.assertEqual(self.host.call_log(), [])

    def test_uncommitted_lockfile_change_blocks(self) -> None:
        wt = self.host.worktree()
        (wt / "frontend" / "package-lock.json").write_text('{"tampered": true}\n')
        proc = self.host.run(wt)
        self.assert_blocked(proc, "frontend/package-lock.json differs from the committed lockfile")
        self.assertEqual(self.host.call_log(), [])

    def test_install_that_changes_tracked_files_blocks(self) -> None:
        wt = self.host.worktree()
        proc = self.host.run(wt, FAKE_TOUCH=str(wt / "frontend" / "package-lock.json"))
        self.assert_blocked(proc, "changed tracked files")

    def test_main_checkout_is_refused(self) -> None:
        proc = self.host.run(self.host.repo)
        self.assert_blocked(proc, "not a factory builder worktree")
        self.assertEqual(self.host.call_log(), [])

    def test_worktree_outside_the_factory_worktrees_directory_is_refused(self) -> None:
        stray = self.host.tmp / "stray"
        git(self.host.repo, "worktree", "add", "-q", "-b", "stray", str(stray), "main")
        proc = self.host.run(stray)
        self.assert_blocked(proc, "not a factory builder worktree")

    def test_subdirectory_of_a_worktree_is_refused(self) -> None:
        wt = self.host.worktree()
        proc = self.host.run(wt / "frontend")
        self.assert_blocked(proc, "not a factory builder worktree")

    def test_missing_agent_command_is_a_usage_error(self) -> None:
        wt = self.host.worktree()
        env = {**os.environ, "PATH": f"{self.host.bin}{os.pathsep}{os.environ['PATH']}"}
        env["FAKE_LOG"] = str(self.host.calls)
        proc = subprocess.run(
            [sys.executable, "-I", str(BOOTSTRAP), "--cache-dir", str(self.host.cache)],
            cwd=wt,
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(self.host.call_log(), [])

    def test_network_env_file_is_used_for_installs_and_must_be_private(self) -> None:
        wt = self.host.worktree()
        net = self.host.tmp / "network.env"
        net.write_text("HTTPS_PROXY=http://proxy.invalid:3128\n")
        net.chmod(0o644)
        proc = self.host.run(wt, "--network-env", str(net))
        self.assert_blocked(proc, "must be private")
        net.chmod(0o600)
        proc = self.host.run(wt, "--network-env", str(net))
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_live_proxy_setting_wins_over_a_stale_network_env_file(self) -> None:
        # The factory process passes its live environment to builders; a captured file can go
        # stale when a local proxy restarts on another port. The file only fills in what is missing.
        wt = self.host.worktree()
        net = self.host.tmp / "network.env"
        net.write_text("HTTPS_PROXY=http://stale.invalid:1\nNODE_EXTRA_CA_CERTS=/from/file.pem\n")
        net.chmod(0o600)
        seen = self.host.tmp / "proxy.log"
        proc = self.host.run(
            wt, "--network-env", str(net), HTTPS_PROXY="http://live.invalid:2", FAKE_PROXY_LOG=str(seen)
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(set(seen.read_text().split()), {"http://live.invalid:2"})
        seen.unlink()
        self.host.agent_out.unlink()
        proc = self.host.run(wt, "--network-env", str(net), FAKE_PROXY_LOG=str(seen))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(set(seen.read_text().split()), {"http://stale.invalid:1"})

    def test_live_no_proxy_alone_does_not_hide_the_saved_proxy(self) -> None:
        wt = self.host.worktree()
        net = self.host.tmp / "network.env"
        net.write_text("HTTPS_PROXY=http://saved.invalid:1\n")
        net.chmod(0o600)
        seen = self.host.tmp / "proxy.log"
        proc = self.host.run(wt, "--network-env", str(net), NO_PROXY="localhost", FAKE_PROXY_LOG=str(seen))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(set(seen.read_text().split()), {"http://saved.invalid:1"})

    def test_any_live_proxy_setting_drops_every_saved_proxy_key(self) -> None:
        # Review finding: per-key precedence let a stale lowercase / npm_config_ proxy from the
        # file sit beside a live HTTPS_PROXY, and npm and Playwright read those first.
        wt = self.host.worktree()
        net = self.host.tmp / "network.env"
        net.write_text(
            "HTTPS_PROXY=http://stale.invalid:1\nhttps_proxy=http://stale.invalid:1\n"
            "npm_config_https_proxy=http://stale.invalid:1\nNODE_EXTRA_CA_CERTS=/from/file.pem\n"
        )
        net.chmod(0o600)
        seen = self.host.tmp / "all-proxy.log"
        proc = self.host.run(
            wt, "--network-env", str(net), HTTPS_PROXY="http://live.invalid:2", FAKE_ALLPROXY_LOG=str(seen)
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        # CA settings are not proxy settings: the file still fills them in.
        self.assertEqual(set(seen.read_text().split()), {"http://live.invalid:2|||/from/file.pem"})

    def test_install_that_edits_an_already_modified_file_blocks(self) -> None:
        # Review finding: comparing `git status` text missed a second edit to a dirty file.
        wt = self.host.worktree()
        (wt / "frontend" / "app.ts").write_text("export const wip = 1;\n")
        proc = self.host.run(wt, FAKE_TOUCH=str(wt / "frontend" / "app.ts"))
        self.assert_blocked(proc, "changed tracked files")

    def test_lockfile_change_hidden_with_assume_unchanged_blocks(self) -> None:
        wt = self.host.worktree()
        git(wt, "update-index", "--assume-unchanged", "frontend/package-lock.json")
        (wt / "frontend" / "package-lock.json").write_text('{"tampered": true}\n')
        self.assertEqual(git(wt, "status", "--porcelain"), "", "precondition: git hides the change")
        proc = self.host.run(wt)
        self.assert_blocked(proc, "frontend/package-lock.json differs from the committed lockfile")
        self.assertEqual(self.host.call_log(), [])

    def test_uncommitted_install_configuration_blocks(self) -> None:
        wt = self.host.worktree()
        (wt / "frontend" / ".npmrc").write_text("registry=https://registry.invalid/\n")
        proc = self.host.run(wt)
        self.assert_blocked(proc, "frontend/.npmrc is not committed")
        self.assertEqual(self.host.call_log(), [])

    def test_agent_that_cannot_start_is_reported(self) -> None:
        wt = self.host.worktree()
        env = {k: v for k, v in os.environ.items() if not k.startswith(("FAKE_", "PLAYWRIGHT_"))}
        env.update(
            {"PATH": f"{self.host.bin}{os.pathsep}{os.environ['PATH']}", "FAKE_LOG": str(self.host.calls)}
        )
        proc = subprocess.run(
            [
                sys.executable,
                "-I",
                str(BOOTSTRAP),
                "--cache-dir",
                str(self.host.cache),
                "--",
                str(self.host.tmp / "no-such-agent"),
            ],
            cwd=wt,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertIn("[bootstrap] FAILED: cannot start the builder", proc.stderr)

    def _hanging_bootstrap(self, *extra: str) -> tuple[subprocess.Popen[str], Path]:
        """Start the bootstrap the way the factory does (own session) with `npm` hanging."""
        wt = self.host.worktree()
        pidfile = self.host.tmp / "grandchild.pid"
        env = {k: v for k, v in os.environ.items() if not k.startswith(("FAKE_", "PLAYWRIGHT_"))}
        env.update(
            {
                "PATH": f"{self.host.bin}{os.pathsep}{os.environ['PATH']}",
                "FAKE_LOG": str(self.host.calls),
                "FAKE_AGENT_OUT": str(self.host.agent_out),
                "FAKE_HANG": "npm",
                "FAKE_PIDFILE": str(pidfile),
            }
        )
        argv = [sys.executable, "-I", str(BOOTSTRAP), "--cache-dir", str(self.host.cache), *extra]
        argv += ["--", sys.executable, str(self.host.agent)]
        proc = subprocess.Popen(
            argv, cwd=wt, env=env, stderr=subprocess.PIPE, text=True, start_new_session=True
        )
        deadline = time.monotonic() + 60
        while not (pidfile.exists() and pidfile.read_text().strip()):
            self.assertLess(time.monotonic(), deadline, "fake npm never started")
            time.sleep(0.1)
        return proc, pidfile

    def assert_dead(self, pidfile: Path) -> None:
        pid = int(pidfile.read_text())
        deadline = time.monotonic() + 10
        while True:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            # a zombie reparented to init also counts as stopped
            stat = Path(f"/proc/{pid}/stat")
            if stat.exists() and stat.read_text().split(") ")[-1].startswith("Z"):
                return
            if time.monotonic() > deadline:
                os.kill(pid, signal.SIGKILL)
                self.fail("an install step's child process outlived the bootstrap")
            time.sleep(0.1)

    def test_factory_kill_of_the_builder_also_stops_running_installs(self) -> None:
        # Review finding: steps in their own session survived the factory's killpg(builder).
        proc, pidfile = self._hanging_bootstrap()
        os.killpg(proc.pid, signal.SIGKILL)  # what factory.py kill_tree does on timeout/SIGTERM
        proc.communicate(timeout=30)
        self.assert_dead(pidfile)
        self.assertFalse(self.host.agent_started())

    def test_step_timeout_stops_the_install_and_its_children(self) -> None:
        proc, pidfile = self._hanging_bootstrap("--step-timeout", "2")
        _, err = proc.communicate(timeout=60)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("[bootstrap] FAILED: npm timed out after 2s", err)
        self.assert_dead(pidfile)
        self.assertFalse(self.host.agent_started())


def load_configure():
    spec = importlib.util.spec_from_file_location("configure_factory_under_test", CONFIGURE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ConfigureTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="vsh-configure-test-")
        tmp = Path(self._tmp)
        self.toolkit = tmp / "toolkit"
        self.toolkit.mkdir()
        self.skill = tmp / "SKILL.md"
        self.skill.write_text("tdd\n")
        self.cf = load_configure()
        self.cf.check_toolkit = lambda toolkit: None  # the pinned hashes are tested by use, not here

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def build(self, providers: str, network_env: Path | None = None) -> dict:
        args = argparse.Namespace(
            toolkit=self.toolkit,
            tdd_skill=self.skill,
            providers=providers,
            codex_model="m-codex",
            claude_builder_model="m-build",
            claude_review_model="m-review",
            base_ref="main",
            cache_dir=Path(self._tmp) / "cache",
            pg_admin_url="postgresql+psycopg://u:p@localhost:5432/postgres",
            network_env=network_env,
            capture_network_env=False,
            python="/usr/bin/python3",
            apply=False,
        )
        return self.cf.build(args)

    def test_every_builder_command_runs_the_bootstrap_first_and_reviewers_do_not(self) -> None:
        for providers in ("claude", "mixed"):
            if providers == "mixed" and not shutil.which("codex"):
                self.cf.shutil = type("S", (), {"which": staticmethod(lambda t: "/bin/" + t)})
            commands = self.build(providers)["commands"]
            for role in ("frontend", "backend", "critical"):
                argv = commands[role]["argv"]
                self.assertEqual(argv[:3], ["/usr/bin/python3", "-I", str(BOOTSTRAP)], role)
                sep = argv.index("--")
                self.assertEqual(
                    argv[sep + 1 : sep + 3], ["/usr/bin/python3", str(self.toolkit / "agent_bridge.py")]
                )
                self.assertIn("builder", argv[sep:])
                self.assertIn("--cache-dir", argv[:sep])
            for role in ("reviewer_standards", "reviewer_spec"):
                argv = commands[role]["argv"]
                self.assertNotIn(str(BOOTSTRAP), argv, role)
                self.assertEqual(argv[1], str(self.toolkit / "agent_bridge.py"))

    def test_builder_bootstrap_gets_the_network_env(self) -> None:
        net = Path(self._tmp) / "network.env"
        net.write_text("")
        argv = self.build("claude", network_env=net)["commands"]["frontend"]["argv"]
        sep = argv.index("--")
        self.assertEqual(argv[argv.index("--network-env") + 1], str(net.resolve()))
        self.assertLess(argv.index("--network-env"), sep)


if __name__ == "__main__":
    unittest.main()
