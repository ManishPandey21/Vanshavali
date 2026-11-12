"""Regression tests for the trusted changed-test gate (ADR-0030).

U02-VITALS-EDIT-B attempt 2 reached cold review with a new Playwright spec its builder never ran;
the spec looked for a "Vitals" region that the page calls "Life details" and failed in both cold
checkouts. The gate runs every new or changed test under the controller before the work is
accepted, feeds a failure back to the builder a bounded number of times, and blocks otherwise.

Real Git worktrees laid out like a factory host; fake npm/npx/uv/agent whose test runners write
real JUnit. A test file's content decides its outcome: PASS, FAIL, SKIP or NONE (no tests).
"""

# ruff: noqa: S603  (test code; same waiver as backend/tests in pyproject.toml)
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from test_bootstrap_builder import BOOTSTRAP, GIT_ENV, Host, git

GATE_MODULE = BOOTSTRAP.with_name("changed_test_gate.py")

FAKE_TOOL = textwrap.dedent(
    r"""
    import json, os, sys
    from pathlib import Path
    tool, args = Path(sys.argv[0]).name, sys.argv[1:]
    if args[:1] == ["--no-install"]:
        args = args[1:]
    knobs = json.loads(Path(KNOBS).read_text())
    with open(knobs["calls"], "a") as f:
        f.write(json.dumps({"tool": tool, "args": args, "cwd": os.getcwd(),
                            "planted": Path("node_modules/PLANTED").exists(),
                            "env": {k: os.environ.get(k) for k in ("VSH_E2E_API_PORT", "VSH_E2E_DB",
                                    "VSH_TEST_DB_NAME", "VSH_TEST_ADMIN_URL", "PLAYWRIGHT_BROWSERS_PATH")}}) + "\n")

    def junit(path, files):
        cases, failed = [], False
        for name in files:
            text = Path(name).read_text() if Path(name).is_file() else "MISSING"
            if "NONE" in text:
                continue
            body = ""
            if "FAIL" in text or "MISSING" in text:
                body, failed = '<failure message="locator not found">getByRole(region, Vitals)</failure>', True
                print("Error: expect(locator).toBeVisible() failed: getByRole(region, Vitals)")  # as the list reporter does
            elif "SKIP" in text:
                body = "<skipped/>"
            cases.append(f'<testcase classname="c" name="{name}">{body}</testcase>')
        xml = knobs.get("junit_prefix", "") + "<testsuites><testsuite>" + "".join(cases) + "</testsuite></testsuites>"
        Path(path).write_text(xml)
        print("ran", files, "failed" if failed else "ok")
        if knobs.get("mutate"):
            Path(knobs["mutate"]).write_text("changed by a test run\n")
        return 1 if failed else 0

    if tool == "npm":                                   # npm ci
        Path("node_modules").mkdir(exist_ok=True)
        sys.exit(0)
    if tool == "uv" and args[:1] == ["sync"]:
        Path(".venv").mkdir(exist_ok=True)
        sys.exit(0)
    if tool == "uv" and "fetch-ephemeris" in args:
        dest = Path(args[args.index("--dest") + 1]); dest.parent.mkdir(parents=True, exist_ok=True); dest.write_text("eph")
        sys.exit(0)
    if tool == "uv" and "pytest" in args:
        out = next(a.split("=", 1)[1] for a in args if a.startswith("--junitxml="))
        sys.exit(junit(out, [a for a in args if a.endswith(".py")]))
    if tool == "npx" and args[:2] == ["playwright", "install"]:
        sys.exit(0)
    if tool == "npx" and args[:2] == ["vitest", "run"]:
        out = next(a.split("=", 1)[1] for a in args if a.startswith("--outputFile.junit="))
        sys.exit(junit(out, [a for a in args if not a.startswith("-") and a not in ("vitest", "run")]))
    if tool == "npx" and args[:2] == ["playwright", "test"]:
        sys.exit(junit(os.environ["PLAYWRIGHT_JUNIT_OUTPUT_FILE"], [a for a in args if a.endswith(".spec.ts")]))
    print("unexpected call", tool, args); sys.exit(99)
    """
)

FAKE_AGENT = textwrap.dedent(
    r"""
    import json, os, sys
    from pathlib import Path
    knobs = json.loads(Path(KNOBS).read_text())
    prompt = Path(sys.argv[sys.argv.index("--prompt-file") + 1]).read_text()
    result = Path(sys.argv[sys.argv.index("--result-file") + 1])
    with open(knobs["prompts"], "a") as f:
        f.write(json.dumps({"prompt": prompt, "result": str(result), "e2e_port": os.environ.get("VSH_E2E_API_PORT")}) + "\n")
    repair = "CONTROLLER_TEST_GATE_RESULT" in prompt
    for rel, text in knobs.get("repair_writes" if repair else "writes", {}).items():
        path = Path(rel); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)
    result.write_text(json.dumps({"summary": "done"}))
    if "routing_outcome" in knobs:  # what toolkit 0.5.0's bridge records beside the result
        result.with_name(result.stem + ".routing.json").write_text(json.dumps({"outcome": knobs["routing_outcome"]}))
    sys.exit(knobs.get("agent_exit", 0))
    """
)


class GateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="vsh-gate-test-")
        self.host = Host(Path(self._tmp).resolve())
        tmp = self.host.tmp
        self.knobs_path = tmp / "knobs.json"
        for tool in ("npm", "npx", "uv"):
            f = self.host.bin / tool
            f.write_text(
                "#!" + sys.executable + "\n" + FAKE_TOOL.replace("KNOBS", repr(str(self.knobs_path)))
            )
            f.chmod(0o755)
        tesseract = self.host.bin / "tesseract"
        tesseract.write_text("#!/bin/sh\nexit 0\n")
        tesseract.chmod(0o755)
        self.agent = tmp / "gate_agent.py"
        self.agent.write_text(FAKE_AGENT.replace("KNOBS", repr(str(self.knobs_path))))
        self.logs = tmp / "logs"
        self.logs.mkdir()
        # a pre-existing test on the base branch: builders may never change it
        (self.host.repo / "frontend" / "src").mkdir(parents=True)
        (self.host.repo / "frontend" / "src" / "existing.test.ts").write_text("PASS\n")
        git(self.host.repo, "add", "-A")
        git(self.host.repo, "commit", "-q", "-m", "existing test")
        self.calls = tmp / "calls.jsonl"
        self.prompts = tmp / "prompts.jsonl"
        self.wt = self.host.worktree()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def ticket(self, paths: list[str]) -> dict:
        return {"id": "U02-TEST", "title": "t", "paths": paths, "acceptance": ["a"]}

    def run_gate(self, ticket: dict, *extra: str, **knobs) -> subprocess.CompletedProcess[str]:
        knobs.setdefault("calls", str(self.calls))
        knobs.setdefault("prompts", str(self.prompts))
        self.knobs_path.write_text(json.dumps(knobs))
        prompt = self.logs / "builder-prompt.txt"
        prompt.write_text(
            "Implement this ticket. Controller runs checks and commits.\n" + json.dumps(ticket, indent=2)
        )
        env = {k: v for k, v in os.environ.items() if not k.startswith(("FAKE_", "PLAYWRIGHT_", "VSH_"))}
        env.update(
            {
                "PATH": f"{self.host.bin}{os.pathsep}{os.environ['PATH']}",
                "FAKE_LOG": str(self.host.calls),
                **GIT_ENV,
            }
        )
        argv = [
            sys.executable,
            "-I",
            str(BOOTSTRAP),
            "--cache-dir",
            str(self.host.cache),
            "--gate",
            "--gate-module",
            str(GATE_MODULE),
            *extra,
            "--",
        ]
        argv += [
            sys.executable,
            str(self.agent),
            "--prompt-file",
            str(prompt),
            "--result-file",
            str(self.logs / "builder-result.json"),
        ]
        return subprocess.run(argv, cwd=self.wt, env=env, capture_output=True, text=True, timeout=120)

    def evidence(self) -> dict:
        return json.loads((self.logs / "changed-tests.json").read_text())

    def runs(self, tool: str, verb: str) -> list[dict]:
        if not self.calls.exists():
            return []
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        return [c for c in calls if c["tool"] == tool and verb in c["args"]]

    def prompts_seen(self) -> list[dict]:
        return [json.loads(line) for line in self.prompts.read_text().splitlines()]

    # ---------------------------------------------------------------- passing work
    def test_new_component_test_runs_under_the_controller_before_acceptance(self) -> None:
        t = self.ticket(["frontend/src/Overview.tsx", "frontend/src/Overview.test.tsx"])
        proc = self.run_gate(
            t, writes={"frontend/src/Overview.tsx": "ui", "frontend/src/Overview.test.tsx": "PASS"}
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        vitest = self.runs("npx", "vitest")
        self.assertEqual(len(vitest), 1)
        self.assertIn("src/Overview.test.tsx", vitest[0]["args"])
        self.assertTrue(vitest[0]["cwd"].endswith("/frontend"))
        ev = self.evidence()
        self.assertEqual(ev["outcome"], "passed")
        run = ev["rounds"][0]["runs"][0]
        self.assertEqual((run["runner"], run["counts"]["tests"], run["passed"]), ("vitest", 1, True))
        self.assertTrue(run["junit_sha256"] and run["log_sha256"])
        self.assertIn("Controller test gate", self.prompts_seen()[0]["prompt"])
        self.assertIn("npx playwright test", self.prompts_seen()[0]["prompt"])

    def test_no_changed_or_declared_tests_passes_and_says_so(self) -> None:
        proc = self.run_gate(
            self.ticket(["frontend/src/Overview.tsx"]), writes={"frontend/src/Overview.tsx": "ui"}
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("no changed or declared test files", proc.stderr)
        self.assertEqual(self.evidence()["rounds"][0]["runs"], [])

    def test_backend_test_runs_with_a_private_database_and_ephemeris(self) -> None:
        t = self.ticket(["backend/app/x.py", "backend/tests/test_x.py"])
        proc = self.run_gate(
            t,
            "--pg-admin-url",
            "postgresql+psycopg://u:p@localhost:5432/postgres",
            writes={"backend/app/x.py": "x", "backend/tests/test_x.py": "PASS"},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        pytest = self.runs("uv", "pytest")
        self.assertEqual(len(pytest), 1)
        self.assertIn("tests/test_x.py", pytest[0]["args"])
        self.assertTrue(pytest[0]["env"]["VSH_TEST_DB_NAME"].startswith("vsh_factory_"))
        self.assertEqual(
            pytest[0]["env"]["VSH_TEST_ADMIN_URL"], "postgresql+psycopg://u:p@localhost:5432/postgres"
        )
        self.assertEqual(len(self.runs("uv", "fetch-ephemeris")), 1)

    # ---------------------------------------------------------------- U02 regression
    def test_failing_new_playwright_spec_is_fed_back_once_then_accepted_when_fixed(self) -> None:
        spec = "e2e/tests/overview-vitals-edit.spec.ts"
        t = self.ticket(["frontend/src/Overview.tsx", spec])
        proc = self.run_gate(
            t,
            writes={"frontend/src/Overview.tsx": "ui", spec: "FAIL: region Vitals"},
            repair_writes={spec: "PASS: region Life details"},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        prompts = self.prompts_seen()
        self.assertEqual(len(prompts), 2)
        self.assertIn("CONTROLLER_TEST_GATE_RESULT", prompts[1]["prompt"])
        self.assertIn(
            "getByRole(region, Vitals)", prompts[1]["prompt"], "the builder sees the real failure output"
        )
        self.assertTrue(prompts[1]["result"].endswith("builder-result.repair-1.json"))
        ev = self.evidence()
        self.assertEqual([r["passed"] for r in ev["rounds"]], [False, True])
        self.assertEqual(ev["outcome"], "passed")
        pw = self.runs("npx", "test")
        self.assertEqual(len(pw), 2)
        self.assertIn("tests/overview-vitals-edit.spec.ts", pw[0]["args"])
        self.assertTrue(pw[0]["cwd"].endswith("/e2e"))
        port = int(pw[0]["env"]["VSH_E2E_API_PORT"])
        self.assertTrue(20000 <= port < 29000, "gate e2e runs get private ports")
        builder_port = int(prompts[0]["e2e_port"])
        self.assertTrue(20000 <= builder_port < 29000, "the builder's own e2e runs get private ports too")

    def test_failure_after_the_repair_rounds_blocks_the_attempt(self) -> None:
        spec = "e2e/tests/overview-vitals-edit.spec.ts"
        proc = self.run_gate(self.ticket([spec]), "--repair-rounds", "0", writes={spec: "FAIL"})
        self.assertEqual(proc.returncode, 4)
        self.assertIn("FAILED: new or changed tests did not pass", proc.stderr)
        self.assertEqual(len(self.prompts_seen()), 1, "no repair round when none are allowed")
        self.assertEqual(self.evidence()["outcome"], "failed")

    # ---------------------------------------------------------------- what counts as passing
    def test_skipped_new_test_fails_the_gate(self) -> None:
        t = "frontend/src/a.test.ts"
        proc = self.run_gate(self.ticket([t]), "--repair-rounds", "0", writes={t: "SKIP"})
        self.assertEqual(proc.returncode, 4)
        self.assertIn("1 skipped", self.evidence()["rounds"][0]["runs"][0]["reason"])

    def test_test_file_with_no_tests_fails_the_gate(self) -> None:
        t = "frontend/src/a.test.ts"
        proc = self.run_gate(self.ticket([t]), "--repair-rounds", "0", writes={t: "NONE"})
        self.assertEqual(proc.returncode, 4)
        self.assertIn("no tests ran", self.evidence()["rounds"][0]["runs"][0]["reason"])

    def test_declared_test_that_was_not_written_fails_the_gate(self) -> None:
        t = self.ticket(["frontend/src/Overview.tsx", "e2e/tests/overview.spec.ts"])
        proc = self.run_gate(t, "--repair-rounds", "0", writes={"frontend/src/Overview.tsx": "ui"})
        self.assertEqual(proc.returncode, 4)
        self.assertEqual(self.evidence()["rounds"][0]["declared_missing"], ["e2e/tests/overview.spec.ts"])

    def test_test_file_without_a_trusted_runner_fails_closed(self) -> None:
        t = "renderer/src/clip.test.ts"
        proc = self.run_gate(self.ticket([t]), "--repair-rounds", "0", writes={t: "PASS"})
        self.assertEqual(proc.returncode, 4)
        self.assertEqual(self.evidence()["rounds"][0]["runs"][0]["runner"], "unsupported")

    def test_junit_with_a_dtd_is_not_trusted(self) -> None:
        t = "frontend/src/a.test.ts"
        proc = self.run_gate(
            self.ticket([t]),
            "--repair-rounds",
            "0",
            writes={t: "PASS"},
            junit_prefix='<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]>',
        )
        self.assertEqual(proc.returncode, 4)
        self.assertIn("no JUnit report", self.evidence()["rounds"][0]["runs"][0]["reason"])

    # ---------------------------------------------------------------- integrity
    def test_a_gate_run_that_changes_the_candidate_is_refused(self) -> None:
        t = "frontend/src/a.test.ts"
        proc = self.run_gate(
            self.ticket([t]), writes={t: "PASS"}, mutate=str(self.wt / "frontend" / "app.ts")
        )
        self.assertEqual(proc.returncode, 4)
        self.assertIn("a test escaped its copy", proc.stderr)
        self.assertEqual(self.evidence()["outcome"], "work_rejected")

    def test_agent_failure_is_propagated_without_running_the_gate(self) -> None:
        proc = self.run_gate(
            self.ticket(["frontend/src/a.test.ts"]), writes={"frontend/src/a.test.ts": "PASS"}, agent_exit=5
        )
        self.assertEqual(proc.returncode, 5)
        self.assertEqual(self.runs("npx", "vitest"), [])
        self.assertEqual(self.evidence()["outcome"], "agent_failed")

    def test_stale_gate_evidence_is_refused(self) -> None:
        (self.logs / "changed-tests.json").write_text("{}")
        proc = self.run_gate(
            self.ticket(["frontend/src/a.test.ts"]), writes={"frontend/src/a.test.ts": "PASS"}
        )
        self.assertEqual(proc.returncode, 75, "a host/repository problem, not the work")
        self.assertIn("stale changed-tests.json", proc.stderr)
        self.assertFalse(self.prompts.exists(), "the builder must not start")

    def test_gate_needs_the_bridge_paths(self) -> None:
        env = {k: v for k, v in os.environ.items() if not k.startswith("FAKE_")}
        env.update({"PATH": f"{self.host.bin}{os.pathsep}{os.environ['PATH']}", **GIT_ENV})
        self.knobs_path.write_text(json.dumps({"calls": str(self.calls), "prompts": str(self.prompts)}))
        proc = subprocess.run(
            [
                sys.executable,
                "-I",
                str(BOOTSTRAP),
                "--cache-dir",
                str(self.host.cache),
                "--gate",
                "--gate-module",
                str(GATE_MODULE),
                "--",
                sys.executable,
                str(self.agent),
            ],
            cwd=self.wt,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 75)
        self.assertIn("--gate needs an agent command with --prompt-file", proc.stderr)

    # ---------------------------------------------------------------- review findings (H2, M1, M3)
    def test_gate_runs_in_a_fresh_copy_not_the_builders_tree(self) -> None:
        t = "frontend/src/a.test.ts"
        planted = "frontend/node_modules/PLANTED"  # ignored: invisible to git, visible to a runner
        proc = self.run_gate(self.ticket([t]), writes={t: "PASS", planted: "evil vitest"})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        run = self.runs("npx", "vitest")[0]
        self.assertFalse(run["planted"], "nothing the builder left in ignored files reaches the gate")
        self.assertNotEqual(Path(run["cwd"]).parent.resolve(), self.wt.resolve())
        self.assertIn("-gate-1", run["cwd"])
        self.assertFalse(Path(run["cwd"]).exists(), "the gate copy is removed afterwards")
        self.assertEqual(
            run["args"][:2], ["vitest", "run"], "runners never install (--no-install stripped above)"
        )

    def test_manifest_change_is_rejected_before_any_test_runs(self) -> None:
        t = "frontend/src/a.test.ts"
        proc = self.run_gate(self.ticket([t]), writes={t: "PASS", "frontend/package.json": "{}"})
        self.assertEqual(proc.returncode, 4)
        self.assertIn("frontend/package.json, a manifest", proc.stderr)
        self.assertEqual(self.runs("npx", "vitest"), [])
        self.assertEqual(self.evidence()["outcome"], "work_rejected")

    def test_changing_an_existing_test_is_rejected(self) -> None:
        t = "frontend/src/existing.test.ts"
        proc = self.run_gate(
            self.ticket(["frontend/src/a.ts"]), writes={"frontend/src/a.ts": "x", t: "PASS weakened"}
        )
        self.assertEqual(proc.returncode, 4)
        self.assertIn("an existing test", proc.stderr)

    def test_agent_configuration_written_by_the_builder_is_rejected(self) -> None:
        t = "frontend/src/a.test.ts"
        proc = self.run_gate(
            self.ticket([t]),
            writes={t: "FAIL", ".claude/settings.local.json": '{"permissions": {"allow": ["Bash(*)"]}}'},
        )
        self.assertEqual(proc.returncode, 4)
        self.assertIn(".claude/settings.local.json is agent configuration", proc.stderr)
        self.assertEqual(len(self.prompts_seen()), 1, "no repair round under a builder-written configuration")

    def test_each_file_must_run_its_own_tests(self) -> None:
        good, empty = "frontend/src/a.test.ts", "frontend/src/b.test.ts"
        proc = self.run_gate(
            self.ticket([good, empty]), "--repair-rounds", "0", writes={good: "PASS", empty: "NONE"}
        )
        self.assertEqual(proc.returncode, 4)
        runs = self.evidence()["rounds"][0]["runs"]
        self.assertEqual([(r["files"], r["passed"]) for r in runs], [([good], True), ([empty], False)])
        self.assertEqual(len(self.runs("npx", "vitest")), 2)

    def test_option_like_test_file_name_is_refused(self) -> None:
        t = "frontend/src/--config=x.test.ts"
        proc = self.run_gate(self.ticket([t]), "--repair-rounds", "0", writes={t: "PASS"})
        self.assertEqual(proc.returncode, 4)
        self.assertIn("unsafe test file name", self.evidence()["rounds"][0]["runs"][0]["reason"])
        self.assertEqual(self.runs("npx", "vitest"), [])

    def test_no_repair_round_without_time_left(self) -> None:
        t = "frontend/src/a.test.ts"
        proc = self.run_gate(
            self.ticket([t]), "--budget-seconds", "60", writes={t: "FAIL"}, repair_writes={t: "PASS"}
        )
        self.assertEqual(proc.returncode, 4)
        self.assertEqual(self.evidence()["outcome"], "failed_no_time_for_repair")
        self.assertEqual(len(self.prompts_seen()), 1)

    def test_pytest_runs_frozen_without_sync(self) -> None:
        t = "backend/tests/test_x.py"
        proc = self.run_gate(self.ticket([t]), writes={t: "PASS"})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.runs("uv", "pytest")[0]["args"][:4], ["run", "--frozen", "--no-sync", "pytest"])

    def test_gate_module_must_be_the_pinned_one(self) -> None:
        other = self.host.tmp / "changed_test_gate.py"
        other.write_text("# not the reviewed gate\n")
        proc = self.run_gate(self.ticket([]), "--gate-module", str(other))
        self.assertEqual(proc.returncode, 75)
        self.assertIn("--gate-module", proc.stderr)
        self.assertFalse(self.prompts.exists())

    def test_agent_cannot_fake_an_uncharged_infrastructure_refusal(self) -> None:
        proc = self.run_gate(self.ticket([]), agent_exit=75)
        self.assertEqual(proc.returncode, 1)

    def test_bridge_routing_refusal_is_reported_as_infrastructure(self) -> None:
        # toolkit 0.5.0's bridge exits 2 on a refused model/effort and records it in its evidence
        proc = self.run_gate(self.ticket([]), agent_exit=2, routing_outcome="routing_refused")
        self.assertEqual(proc.returncode, 75)
        self.assertEqual(self.evidence()["outcome"], "routing_refused")

    def test_agent_error_with_ordinary_routing_evidence_stays_an_agent_failure(self) -> None:
        proc = self.run_gate(self.ticket([]), agent_exit=2, routing_outcome="error")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(self.evidence()["outcome"], "agent_failed")


class HostCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="vsh-hostcheck-test-")
        self.host = Host(Path(self._tmp).resolve())
        self.wt = self.host.worktree()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_too_little_disk_blocks_before_any_install(self) -> None:
        proc = self.host.run(self.wt, "--min-free-gb", "1000000")
        self.assertEqual(proc.returncode, 3)
        self.assertIn("GiB free", proc.stderr)
        self.assertEqual(self.host.call_log(), [])
        self.assertFalse(self.host.agent_started())

    def test_wrong_node_major_blocks_with_the_version_found(self) -> None:
        node = self.host.bin / "node"
        node.write_text("#!/bin/sh\necho v18.19.0\n")
        node.chmod(0o755)
        proc = self.host.run(self.wt, "--node-major", "22")
        self.assertEqual(proc.returncode, 3)
        self.assertIn("Node.js v18.19.0 found; CI and the lockfiles use Node 22.x", proc.stderr)
        self.assertFalse(self.host.agent_started())

    def test_matching_node_major_proceeds(self) -> None:
        node = self.host.bin / "node"
        node.write_text("#!/bin/sh\necho v22.23.4\n")
        node.chmod(0o755)
        proc = self.host.run(self.wt, "--node-major", "22", "--min-free-gb", "0.001")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(self.host.agent_started())


if __name__ == "__main__":
    unittest.main()
