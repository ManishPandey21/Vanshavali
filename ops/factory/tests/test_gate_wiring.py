"""Regression tests for wiring the changed-test gate into toolkit 0.5.0's builder commands, and for the
routing report over 0.5.0's ledger and logs (ADR-0030). No model provider, network or database.

Run from the repository root: ``python3 -m unittest discover -s ops/factory/tests -v``
"""

# ruff: noqa: S603, S607  (test code; same waiver as backend/tests in pyproject.toml)
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_configure_factory import Base

FACTORY = Path(__file__).resolve().parent.parent
BOOTSTRAP = FACTORY / "bootstrap_builder.py"
BUILDERS = ("backend", "frontend", "critical")


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", FACTORY / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GateWiring(Base):
    def test_every_builder_runs_the_gate_and_no_reviewer_does(self):
        for providers in ("claude", "mixed"):
            commands = self.build("--providers", providers)["commands"]
            for role in BUILDERS:
                argv = commands[role]["argv"]
                sep = argv.index("--")
                self.assertEqual(argv[2], str(BOOTSTRAP), role)
                for flag in ("--gate", "--repair-rounds", "--node-major", "--min-free-gb", "--pg-admin-url"):
                    self.assertIn(flag, argv[:sep], role)
                self.assertEqual(argv[argv.index("--gate-module") + 1], str(FACTORY / "changed_test_gate.py"))
            for role, spec in commands.items():
                if role not in BUILDERS:
                    self.assertNotIn("--gate", spec["argv"], role)

    def test_one_builder_command_has_time_for_a_repair_round(self):
        config = self.build()
        argv = config["commands"]["frontend"]["argv"]
        self.assertEqual(config["timeout_seconds"], 5400)
        self.assertLess(float(argv[argv.index("--budget-seconds") + 1]), config["timeout_seconds"])

    def test_repair_rounds_are_bounded(self):
        argv = self.build("--repair-rounds", "0")["commands"]["backend"]["argv"]
        self.assertEqual(argv[argv.index("--repair-rounds") + 1], "0")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.args("--repair-rounds", "3")


def write_attempt(home: Path) -> None:
    logs = home / "logs" / "T1-111"
    (logs / "cold-spec" / "reports").mkdir(parents=True)
    (logs / "cold-spec" / "frontend-unit.log").write_text("ok")
    (logs / "cold-spec" / "reports" / "frontend-unit.json").write_text(json.dumps({"status": "passed"}))
    (logs / "cold-spec" / "frontend-e2e.log").write_text("failed")  # no report: failed
    (logs / "builder-result.routing.json").write_text(
        json.dumps(
            {
                "provider": "claude",
                "requested_model": "claude-sonnet-5-5",
                "requested_effort": "medium",
                "outcome": "ok",
                "served_models": {"claude-sonnet-5-5": {"inputTokens": 100, "outputTokens": 20}},
                "total_cost_usd": 0.5,
            }
        )
    )
    (logs / "changed-tests.json").write_text(
        json.dumps({"outcome": "passed", "rounds": [{}, {}], "agent_runs": [{}, {}]})
    )
    with sqlite3.connect(home / "ledger.sqlite3") as con:
        con.execute(
            "CREATE TABLE events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id TEXT, state TEXT, "
            "at REAL, details TEXT)"
        )
        for state, details in (
            ("PENDING", {}),
            ("RUNNING", {"attempts": 1, "branch": "infra-factory/T1-111"}),
            ("AWAITING_HUMAN", {"error": None}),
        ):
            con.execute(
                "INSERT INTO events(ticket_id,state,at,details) VALUES('T1',?,0,?)",
                (state, json.dumps(details)),
            )
    con.close()


class RoutingReport(unittest.TestCase):
    def setUp(self):
        self.rr = load("routing_report")
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def check(self, repo: Path) -> None:
        rows = self.rr.attempts(repo)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        # 0.5.0 ends a high-risk attempt that passed review in AWAITING_HUMAN
        self.assertEqual(
            (row["outcome"], row["builder"]["model"], row["builder"]["tokens"]),
            ("AWAITING_HUMAN", "claude-sonnet-5-5", 120),
        )
        self.assertEqual(row["gate"], {"outcome": "passed", "rounds": 2, "repairs_used": 1})
        self.assertEqual(row["builder"]["repair_turns"], 0)
        self.assertEqual(row["cold_failed"], ["frontend-e2e"])
        self.assertIn(
            "| claude-sonnet-5-5 | medium | 1 | 1 | 0 | 1 | 1 | 0.50 | 120 |", self.rr.summary(rows)
        )

    def test_attempts_join_ledger_routing_gate_and_cold_results(self):
        repo = self.tmp / "repo"
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        write_attempt(repo / ".git" / "infra-factory")
        self.check(repo)

    def test_state_is_found_in_a_separate_git_dir(self):
        # the runbook's factory clone: `git clone --separate-git-dir`, so `.git` is a file
        repo, gitdir = self.tmp / "checkout", self.tmp / "gitdir"
        subprocess.run(["git", "init", "-q", "--separate-git-dir", str(gitdir), str(repo)], check=True)
        self.assertTrue((repo / ".git").is_file())
        write_attempt(gitdir / "infra-factory")
        self.check(repo)


if __name__ == "__main__":
    unittest.main()
