"""Regression tests for model/effort routing, the model probe, the reproducible toolkit release and
the routing report (ADR-0030). No model provider is called: the probe runs against a fake bridge.
"""

# ruff: noqa: S603, S607  (test code; same waiver as backend/tests in pyproject.toml)
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import shutil
import sqlite3
import subprocess
import tempfile
import textwrap
import unittest
import zipfile
from contextlib import redirect_stderr
from pathlib import Path

FACTORY = Path(__file__).resolve().parent.parent
BOOTSTRAP = FACTORY / "bootstrap_builder.py"


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", FACTORY / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RoutingConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="vsh-routing-test-")
        tmp = Path(self._tmp)
        self.toolkit = tmp / "toolkit"
        self.toolkit.mkdir()
        self.skill = tmp / "SKILL.md"
        self.skill.write_text("tdd\n")
        self.cf = load("configure_factory")
        self.cf.check_toolkit = lambda toolkit: None  # the pins are tested through toolkit_release below

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def args(self, providers: str = "claude", route: list | None = None, **extra) -> argparse.Namespace:
        ns = argparse.Namespace(
            toolkit=self.toolkit,
            tdd_skill=self.skill,
            providers=providers,
            codex_model="gpt-6.1-sol",
            route=route or [],
            repair_rounds=1,
            base_ref="main",
            cache_dir=Path(self._tmp) / "cache",
            pg_admin_url="postgresql+psycopg://u:p@localhost:5432/postgres",
            network_env=None,
            capture_network_env=False,
            python="/usr/bin/python3",
            apply=False,
            probe_models=False,
        )
        for key, value in extra.items():
            setattr(ns, key, value)
        return ns

    def build(self, **kw) -> dict:
        with redirect_stderr(io.StringIO()):
            return self.cf.build(self.args(**kw))

    def flag(self, argv: list[str], name: str) -> str:
        return argv[argv.index(name) + 1]

    def test_default_policy_pins_every_role_to_a_full_model_id_and_explicit_effort(self) -> None:
        commands = self.build()["commands"]
        expected = {
            "builder_routine": ("claude-sonnet-5-5", "medium"),
            "builder_complex": ("claude-opus-5-5", "high"),
            "builder_critical": ("claude-opus-5-5", "high"),
            "reviewer_standards": ("claude-opus-5-5", "high"),
            "reviewer_spec": ("claude-opus-5-5", "high"),
            "reviewer_standards_critical": ("claude-opus-5-5", "high"),
            "reviewer_spec_critical": ("claude-fable-5-2", "high"),
        }
        for role, (model, effort) in expected.items():
            argv = commands[role]["argv"]
            self.assertEqual((commands[role]["model"], commands[role]["effort"]), (model, effort), role)
            self.assertEqual(self.flag(argv, "--effort"), effort, role)
            self.assertIn("--strict-routing", argv, role)
            self.assertEqual(self.flag(argv, "--model"), "{model}", role)

    def test_fable_is_only_the_critical_escalation_unless_selected(self) -> None:
        commands = self.build()["commands"]
        fable = sorted(r for r, spec in commands.items() if "fable" in spec["model"])
        self.assertEqual(fable, ["reviewer_spec_critical"])
        commands = self.build(route=[("builder_complex", ("claude", "claude-fable-5-2", "high"))])["commands"]
        self.assertEqual(commands["builder_complex"]["model"], "claude-fable-5-2")

    def test_builders_run_the_bootstrap_with_the_gate_and_reviewers_do_not(self) -> None:
        commands = self.build()["commands"]
        for role in (
            "builder_routine",
            "builder_complex",
            "builder_critical",
            "frontend",
            "backend",
            "critical",
        ):
            argv = commands[role]["argv"]
            sep = argv.index("--")
            self.assertEqual(argv[:3], ["/usr/bin/python3", "-I", str(BOOTSTRAP)], role)
            for flag in ("--gate", "--node-major", "--min-free-gb", "--repair-rounds", "--pg-admin-url"):
                self.assertIn(flag, argv[:sep], role)
            self.assertEqual(argv[sep + 2], str(self.toolkit / "agent_bridge.py"), role)
        for role in ("reviewer_standards", "reviewer_spec", "reviewer_spec_critical"):
            self.assertNotIn(str(BOOTSTRAP), commands[role]["argv"], role)
            self.assertEqual(self.flag(commands[role]["argv"], "--mode"), "reviewer")

    def test_legacy_roles_alias_the_routing_tiers(self) -> None:
        commands = self.build()["commands"]
        self.assertEqual(commands["frontend"], commands["builder_routine"])
        self.assertEqual(commands["backend"], commands["builder_routine"])
        self.assertEqual(commands["critical"], commands["builder_critical"])

    def test_mixed_keeps_codex_for_routine_builds_and_the_standards_lens(self) -> None:
        self.cf.shutil = type("S", (), {"which": staticmethod(lambda t: "/bin/" + t)})
        commands = self.build(providers="mixed")["commands"]
        for role, effort in (("builder_routine", "medium"), ("reviewer_standards", "high")):
            self.assertEqual(self.flag(commands[role]["argv"], "--provider"), "codex", role)
            self.assertEqual(commands[role]["effort"], effort, role)
        self.assertEqual(self.flag(commands["reviewer_spec"]["argv"], "--provider"), "claude")

    def test_route_overrides_are_validated(self) -> None:
        parse = self.cf.parse_route
        self.assertEqual(
            parse("builder_routine=claude:claude-opus-5-5:low"),
            ("builder_routine", ("claude", "claude-opus-5-5", "low")),
        )
        for bad in (
            "builder_routine=claude:opus:high",  # alias
            "builder_routine=claude:claude-opus-5-5:ultra",  # effort the CLI would accept silently
            "builder_routine=codex:gpt-6.1-sol:xhigh",  # effort codex does not take here
            "coordinator=claude:claude-opus-5-5:medium",  # not a factory role
            "builder_routine=claude-opus-5-5",  # malformed
        ):
            with self.assertRaises(argparse.ArgumentTypeError, msg=bad):
                parse(bad)

    def test_config_records_the_routing_table(self) -> None:
        config = self.build()
        self.assertEqual(
            config["routing"]["builder_routine"],
            {"provider": "claude", "model": "claude-sonnet-5-5", "effort": "medium"},
        )
        self.assertIn("not run", config["model_probe"])


FAKE_BRIDGE = textwrap.dedent(
    r"""
    import json, sys
    from pathlib import Path
    a = sys.argv[1:]
    get = lambda f: a[a.index(f) + 1]
    model, effort = get("--model"), get("--effort")
    result = Path(get("--result-file"))
    served = {"claude-opus-5-5": "claude-sonnet-5-5"}.get(model, model)   # opus is "downgraded"
    ok = served == model and model != "claude-missing-1-0"
    ev = {"outcome": "ok" if ok else "routing_refused", "requested_model": model, "requested_effort": effort,
          "served_models": {served: {"outputTokens": 1}}, "error": None if ok else f"{model} did not serve this run"}
    result.with_name(result.stem + ".routing.json").write_text(json.dumps(ev))
    with open(LOG, "a") as f:
        f.write(json.dumps([model, effort, "--strict-routing" in a]) + "\n")
    sys.exit(0 if ok else 2)
    """
)


class ModelProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="vsh-probe-test-")
        self.toolkit = Path(self._tmp)
        self.log = self.toolkit / "calls.jsonl"
        (self.toolkit / "agent_bridge.py").write_text(FAKE_BRIDGE.replace("LOG", repr(str(self.log))))
        self.cf = load("configure_factory")

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def probe(self, routes: dict) -> dict:
        import sys

        with redirect_stderr(io.StringIO()):
            return self.cf.probe_models(sys.executable, self.toolkit, routes)

    def test_each_distinct_pair_is_probed_once_in_strict_mode(self) -> None:
        routes = {
            "a": ("claude", "claude-sonnet-5-5", "medium"),
            "b": ("claude", "claude-sonnet-5-5", "medium"),
            "c": ("claude", "claude-fable-5-2", "high"),
        }
        result = self.probe(routes)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual(
            sorted(calls), [["claude-fable-5-2", "high", True], ["claude-sonnet-5-5", "medium", True]]
        )
        self.assertEqual(result["claude:claude-fable-5-2:high"]["served_models"], ["claude-fable-5-2"])

    def test_unavailable_model_stops_the_configuration(self) -> None:
        with self.assertRaises(SystemExit) as stop:
            self.probe({"a": ("claude", "claude-missing-1-0", "low")})
        self.assertIn("model probe failed for claude:claude-missing-1-0:low", str(stop.exception))

    def test_downgraded_model_stops_the_configuration(self) -> None:
        with self.assertRaises(SystemExit) as stop:
            self.probe({"a": ("claude", "claude-opus-5-5", "high")})
        self.assertIn("did not serve this run", str(stop.exception))


class ToolkitReleaseTests(unittest.TestCase):
    """A release is the pinned base archive + a reviewed patch; anything else is refused."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="vsh-release-test-")
        self.tmp = Path(self._tmp)
        self.tr = load("toolkit_release")
        base = self.tmp / "src" / "infra-code-factory"
        base.mkdir(parents=True)
        for name in ("factory.py", "agent_bridge.py", "README.md"):
            (base / name).write_text(f"# {name} 0.3.3\n")
        self.sums(base)
        self.archive = self.tmp / "icf-0.3.3.zip"
        self.zip(base, self.archive)
        new = self.tmp / "new"
        shutil.copytree(base, new)
        (new / "factory.py").write_text("# factory.py 0.3.4\n")
        (new / "tests").mkdir()
        (new / "tests" / "test_new.py").write_text("ok\n")
        self.sums(new)
        diff = subprocess.run(
            ["git", "diff", "--no-index", "--binary", str(base), str(new)], capture_output=True, text=True
        ).stdout
        self.patch = self.tmp / "release.patch"
        self.patch.write_text(diff.replace(f"a{base}/", "a/").replace(f"b{new}/", "b/"))
        self.tr.BASE_ARCHIVE_SHA256 = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.tr.BASE_RUNTIME_SHA256 = {"factory.py": self.sha(base / "factory.py")}
        self.pins = {
            "factory.py": self.sha(new / "factory.py"),
            "agent_bridge.py": self.sha(new / "agent_bridge.py"),
        }

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    @staticmethod
    def sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def sums(self, root: Path) -> None:
        files = sorted(
            p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and p.name != "SHA256SUMS"
        )
        (root / "SHA256SUMS").write_text("".join(f"{self.sha(root / f)}  {f}\n" for f in files))

    @staticmethod
    def zip(root: Path, archive: Path) -> None:
        with zipfile.ZipFile(archive, "w") as zf:
            for p in sorted(root.rglob("*")):
                zf.write(p, Path("infra-code-factory") / p.relative_to(root))

    def build(self, out: str = "out") -> Path:
        return self.tr.build(self.archive, self.tmp / out, "0.3.4", self.pins, self.patch)

    def test_release_is_reproduced_from_archive_and_patch(self) -> None:
        out = self.build()
        self.assertEqual((out / "factory.py").read_text(), "# factory.py 0.3.4\n")
        self.tr.verify(out, self.pins)

    def test_other_archive_is_refused(self) -> None:
        self.tr.BASE_ARCHIVE_SHA256 = "0" * 64
        with self.assertRaisesRegex(self.tr.ReleaseError, "not the reviewed"):
            self.build()

    def test_patch_that_does_not_produce_the_pinned_files_is_refused(self) -> None:
        self.pins["factory.py"] = "0" * 64
        with self.assertRaisesRegex(self.tr.ReleaseError, "factory.py is not the reviewed file"):
            self.build()
        self.assertFalse((self.tmp / "out").exists())

    def test_existing_output_directory_is_never_overwritten(self) -> None:
        (self.tmp / "out").mkdir()
        with self.assertRaisesRegex(self.tr.ReleaseError, "already exists"):
            self.build()

    def test_verify_refuses_a_stale_manifest_like_0_3_3s(self) -> None:
        out = self.build()
        (out / "README.md").write_text("changed after the manifest\n")
        with self.assertRaisesRegex(self.tr.ReleaseError, "mismatch .*README.md"):
            self.tr.verify(out, self.pins)

    def test_verify_refuses_unlisted_and_missing_files(self) -> None:
        out = self.build()
        (out / "extra.py").write_text("planted\n")
        with self.assertRaisesRegex(self.tr.ReleaseError, "not in SHA256SUMS: extra.py"):
            self.tr.verify(out, self.pins)
        (out / "extra.py").unlink()
        (out / "tests" / "test_new.py").unlink()
        with self.assertRaisesRegex(self.tr.ReleaseError, "missing: tests/test_new.py"):
            self.tr.verify(out, self.pins)

    def test_archive_with_path_traversal_is_refused(self) -> None:
        evil = self.tmp / "evil.zip"
        with zipfile.ZipFile(evil, "w") as zf:
            zf.writestr("../escape.txt", "x")
        with tempfile.TemporaryDirectory() as td, self.assertRaisesRegex(self.tr.ReleaseError, "unsafe path"):
            self.tr.safe_extract(evil, Path(td))

    def test_committed_patch_matches_the_pins(self) -> None:
        """The reviewed patch in the repository yields exactly the pinned runtime hashes."""
        version, pins = self.tr.target()
        patch = self.tr.patch_path(version)
        self.assertTrue(patch.is_file(), patch)
        text = patch.read_text()
        for name in pins:
            if name in ("factory.py", "agent_bridge.py"):
                self.assertIn(f"diff --git a/{name} b/{name}", text, name)
        section = text.split("diff --git a/SHA256SUMS b/SHA256SUMS", 1)[1].split("\ndiff --git ", 1)[0]
        post_image = [
            line[1:] for line in section.splitlines() if line[:1] in ("+", " ") and not line.startswith("+++")
        ]
        listed = {line.split("  ", 1)[1]: line[:64] for line in post_image if len(line.split("  ")[0]) == 64}
        for name, digest in pins.items():
            self.assertEqual(listed.get(name), digest, f"patched SHA256SUMS entry for {name}")


class RoutingReportTests(unittest.TestCase):
    def test_attempts_join_ledger_routing_gate_and_cold_results(self) -> None:
        rr = load("routing_report")
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            home = repo / ".git" / "infra-factory"
            logs = home / "logs" / "T1-111"
            (logs / "cold-spec" / "reports").mkdir(parents=True)
            (logs / "cold-spec" / "frontend-unit.log").write_text("ok")
            (logs / "cold-spec" / "reports" / "frontend-unit.json").write_text(
                json.dumps({"status": "passed"})
            )
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
                    "CREATE TABLE events (sequence INTEGER PRIMARY KEY, ticket_id TEXT, state TEXT, at REAL, details TEXT)"
                )
                for state, details in (
                    ("PENDING", {}),
                    ("RUNNING", {"attempts": 1, "branch": "infra-factory/T1-111"}),
                    ("BLOCKED", {"error": "Command exited 2"}),
                ):
                    con.execute(
                        "INSERT INTO events(ticket_id,state,at,details) VALUES('T1',?,0,?)",
                        (state, json.dumps(details)),
                    )
            rows = rr.attempts(repo)
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(
                (row["outcome"], row["builder"]["model"], row["builder"]["tokens"]),
                ("BLOCKED", "claude-sonnet-5-5", 120),
            )
            self.assertEqual(row["gate"], {"outcome": "passed", "rounds": 2, "repairs_used": 1})
            self.assertEqual(row["cold_failed"], ["frontend-e2e"])
            text = rr.summary(rows)
            self.assertIn("| claude-sonnet-5-5 | medium | 1 | 0 | 0 | 1 | 1 | 0.50 | 120 |", text)


if __name__ == "__main__":
    unittest.main()
