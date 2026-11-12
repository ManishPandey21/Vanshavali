"""Regression tests for the factory config generator (ADR-0029, toolkit 0.5.0 upgrade).

They build the configuration against a stand-in toolkit directory (the real toolkit lives outside the
repository and is pinned by hash), so they need no network, model provider or database.

Run from the repository root: ``python3 -m unittest discover -s ops/factory/tests -v``
"""

# ruff: noqa: S603, S607  (test code; same waiver as backend/tests in pyproject.toml)
from __future__ import annotations

import contextlib
import fnmatch
import hashlib
import importlib.util
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
FACTORY = HERE.parent
REPO = FACTORY.parents[1]
GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
}
CLAUDE_ID = "claude-testmodel-1-0"
CODEX_ID = "codex-test-model"


def load():
    spec = importlib.util.spec_from_file_location("configure_factory", FACTORY / "configure_factory.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cf = load()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(self.tmp)], check=False))
        self.toolkit = self.tmp / "toolkit"
        hashes = {}
        for name in cf.TOOLKIT_SHA256:
            path = self.toolkit / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# stand-in for {name}\n")
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.skill = self.tmp / "SKILL.md"
        self.skill.write_text("# tdd\n")
        patcher = mock.patch.object(cf, "TOOLKIT_SHA256", hashes)
        patcher.start()
        self.addCleanup(patcher.stop)
        which = mock.patch.object(cf.shutil, "which", return_value="/usr/bin/true")
        which.start()
        self.addCleanup(which.stop)

    def args(self, *extra: str):
        return cf.parser().parse_args(
            [
                "--toolkit",
                str(self.toolkit),
                "--tdd-skill",
                str(self.skill),
                "--claude-builder-model",
                CLAUDE_ID,
                "--codex-model",
                CODEX_ID,
                "--cache-dir",
                str(self.tmp / "cache"),
                *extra,
            ]
        )

    def build(self, *extra: str) -> dict:
        with contextlib.redirect_stderr(io.StringIO()):
            return cf.build(self.args(*extra))

    def refused(self, *extra: str) -> str:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ctx:
            cf.build(self.args(*extra))
        return str(ctx.exception.code)


class ToolkitPinning(Base):
    def test_modified_toolkit_file_is_refused(self):
        (self.toolkit / "review_policy.py").write_text("# tampered\n")
        self.assertIn("review_policy.py", self.refused())

    def test_every_module_the_controller_imports_is_pinned(self):
        # 0.5.0 split the controller; an unpinned module would be loaded without review.
        for name in (
            "factory.py",
            "review_policy.py",
            "repair.py",
            "check_paths.py",
            "path_safety.py",
            "runtime_requirements.py",
            "ticket_controls.py",
            "skill_inventory.py",
            "egm.py",
            "verification_policy.py",
            "cold_workspace.py",
            "test_report.py",
            "agent_bridge.py",
            "ledger_view.py",
        ):
            self.assertIn(name, cf.TOOLKIT_SHA256)


class StrictRouting(Base):
    def test_every_agent_is_strictly_routed_with_pinned_model_and_effort(self):
        for role, spec in self.build()["commands"].items():
            argv = spec["argv"]
            self.assertIn("--strict-routing", argv, role)
            effort = argv[argv.index("--effort") + 1]
            self.assertEqual(effort, spec["effort"], role)
            allowed = cf.CLAUDE_EFFORTS if spec["provider"] == "claude" else cf.CODEX_EFFORTS
            self.assertIn(effort, allowed, role)
            self.assertEqual(argv[argv.index("--provider") + 1], spec["provider"], role)
            self.assertIn(spec["model"], (CLAUDE_ID, CODEX_ID), role)

    def test_only_builders_start_through_the_bootstrap(self):
        for role, spec in self.build()["commands"].items():
            boots = str(cf.BOOTSTRAP) in spec["argv"]
            self.assertEqual(boots, role in ("backend", "frontend", "critical"), role)
            self.assertEqual("primary_skill" in spec, boots, role)

    def test_mixed_providers_keep_the_two_lenses_on_different_providers(self):
        c = self.build()["commands"]
        self.assertEqual(c["backend"]["provider"], "codex")
        self.assertEqual(c["frontend"]["provider"], "claude")
        self.assertNotEqual(c["reviewer_standards"]["provider"], c["reviewer_spec"]["provider"])
        self.assertNotEqual(
            c["reviewer_standards_critical"]["provider"], c["reviewer_spec_critical"]["provider"]
        )

    def test_claude_only(self):
        c = self.build("--providers", "claude")["commands"]
        self.assertEqual({s["provider"] for s in c.values()}, {"claude"})
        self.assertEqual(c["critical"]["effort"], "xhigh")
        self.assertEqual(c["reviewer_spec_critical"]["effort"], "max")

    def test_builders_route_by_layer_not_by_complexity_tier(self):
        # The toolkit routes to builder_routine/complex/critical when they exist; Vanshavali keeps the
        # layer -> provider mapping, so those tiers must stay undefined.
        c = self.build()["commands"]
        self.assertFalse({"builder_routine", "builder_complex", "builder_critical"} & set(c))

    def test_model_aliases_are_refused(self):
        self.assertIn("pinned", self.refused("--claude-builder-model", "opus"))

    def test_models_are_never_assumed(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cf.build(cf.parser().parse_args(["--toolkit", str(self.toolkit), "--tdd-skill", str(self.skill)]))
        a = cf.parser().parse_args(
            [
                "--toolkit",
                str(self.toolkit),
                "--tdd-skill",
                str(self.skill),
                "--claude-builder-model",
                CLAUDE_ID,
            ]
        )
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ctx:
            cf.build(a)
        self.assertIn("--codex-model", str(ctx.exception.code))

    def test_route_override_and_unknown_role(self):
        c = self.build("--route", f"reviewer_security=claude:{CLAUDE_ID}:max")["commands"]
        self.assertEqual(c["reviewer_security"]["effort"], "max")
        self.assertIn("unknown role", self.refused("--route", f"reviewer_typo=claude:{CLAUDE_ID}:high"))

    def test_codex_effort_above_high_is_refused(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.args("--route", f"backend=codex:{CODEX_ID}:max")


class ReviewPolicy(Base):
    def test_every_selected_lens_and_the_risk_assessor_has_a_command(self):
        c = self.build()
        policy = c["review_policy"]
        for name in policy["specialists"]:
            self.assertIn("reviewer_" + name, c["commands"])
        self.assertIn("risk_assessor", c["commands"])

    def test_policy_satisfies_the_toolkit_contract(self):
        policy = cf.REVIEW_POLICY
        self.assertLessEqual(len(policy["specialists"]), 8)
        for name, rule in policy["specialists"].items():
            self.assertRegex(name, r"^[a-z][a-z0-9_]{0,31}$")
            self.assertNotIn(name, {"standards", "spec", "risk"})
            self.assertEqual(set(rule), {"paths", "focus"})
            self.assertTrue(rule["focus"].strip())
        levels = ("low", "medium", "high", "critical")
        risk = policy["risk"]
        self.assertIn(risk["minimum_level"], levels)
        first = min(levels.index(x) for x in risk["human_review_levels"])
        self.assertEqual(set(risk["human_review_levels"]), set(levels[first:]))
        globs = [g for r in policy["specialists"].values() for g in r["paths"]]
        globs += [g for r in risk["path_levels"] for g in r["paths"]]
        for glob in globs:
            self.assertFalse(glob.startswith("/") or "\\" in glob or ".." in glob.split("/"), glob)

    def test_specialists_are_selected_by_real_repository_paths(self):
        def lenses(path):
            return {
                n
                for n, r in cf.REVIEW_POLICY["specialists"].items()
                if any(fnmatch.fnmatchcase(path, g) for g in r["paths"])
            }

        self.assertIn("security", lenses("backend/app/authz/permissions.py"))
        self.assertIn("security", lenses("backend/app/modules/identity/service.py"))
        self.assertIn("data", lenses("backend/alembic/versions/0001_x.py"))
        self.assertIn("provenance", lenses("backend/app/modules/extraction/service.py"))
        self.assertIn("frontend", lenses("frontend/src/pages/Tree.tsx"))
        self.assertEqual(lenses("backend/app/modules/kinship/service.py"), set())
        # Every glob must still match something in the repository (catches renamed modules).
        tracked = subprocess.run(
            ["git", "-C", str(REPO), "ls-files"], capture_output=True, text=True, check=True
        ).stdout.split()
        rules = list(cf.REVIEW_POLICY["specialists"].values()) + cf.REVIEW_POLICY["risk"]["path_levels"]
        for glob in {g for r in rules for g in r["paths"]}:
            self.assertTrue(any(fnmatch.fnmatchcase(p, glob) for p in tracked), glob)

    def test_security_paths_require_a_human(self):
        risk = cf.REVIEW_POLICY["risk"]
        high = [r for r in risk["path_levels"] if r["level"] in risk["human_review_levels"]]
        for path in ("backend/app/authz/privacy.py", "backend/alembic/env.py", "deploy/pilot/x.sh"):
            self.assertTrue(any(fnmatch.fnmatchcase(path, g) for r in high for g in r["paths"]), path)


class RepairAndWorkflow(Base):
    def test_repair_budget_matches_three_attempts(self):
        self.assertEqual(self.build()["repair_policy"], {"max_repairs": 2})

    def test_github_repair_allowlist(self):
        c = self.build("--ci-workflow-id", "4242")
        self.assertEqual(
            c["repair_policy"]["github"], {"repository": cf.REPAIR_REPOSITORY, "workflow_ids": [4242]}
        )
        self.assertIn("positive", self.refused("--ci-workflow-id", "0"))

    def test_egm_is_opt_in(self):
        self.assertNotIn("workflow", self.build())
        self.assertEqual(self.build("--egm")["workflow"], "egm")


class CheckArgvDoesNotFreezeTheRepository(Base):
    """Toolkit >= 0.5.0 protects every in-repository path named in a check argv (check_paths.py).

    A bare ``backend`` in the preflight argv used to name a directory: every backend ticket would then
    be refused as a "configured check input". Only the trusted wrapper itself may be named.
    """

    def referenced(self, config) -> set[str]:
        tracked = set(
            subprocess.run(
                ["git", "-C", str(REPO), "ls-files"], capture_output=True, text=True, check=True
            ).stdout.split()
        )
        known = set(tracked)
        for name in tracked:
            known.update(p.as_posix() for p in Path(name).parents if p.as_posix() != ".")
        known.add(".")
        found = set()
        argvs = list(config["checks"]) + [c["argv"] for c in config["verification"]["checks"]]
        for argv in argvs:
            for arg in argv:
                value = arg.split("=", 1)[1] if arg.startswith("-") and "=" in arg else arg
                value = value.split("::", 1)[0]
                if not value or value.startswith("-") or "{" in value:
                    continue
                candidate = Path(os.path.abspath(REPO / value))
                if candidate.is_relative_to(REPO):
                    rel = candidate.relative_to(REPO).as_posix()
                    if rel in known:
                        found.add(rel)
        return found

    def test_only_the_suite_wrapper_is_referenced(self):
        self.assertEqual(self.referenced(self.build()), {"ops/factory/run_suite.py"})

    def test_run_suite_accepts_the_preflight_tokens(self):
        spec = importlib.util.spec_from_file_location("run_suite", FACTORY / "run_suite.py")
        run_suite = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(run_suite)
        calls = []
        with (
            mock.patch.object(run_suite.Context, "__init__", return_value=None),
            mock.patch.object(run_suite.Context, "static", lambda self, side: calls.append(side)),
        ):
            self.assertEqual(run_suite.main(["--static", "backend-preflight"]), 0)
            self.assertEqual(run_suite.main(["--static", "frontend"]), 0)
        self.assertEqual(calls, ["backend", "frontend"])


class StateDirectory(unittest.TestCase):
    """Builder worktrees must be outside any `.git` directory and reached without symlinks."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(self.tmp)], check=False))

    def git(self, *args):
        subprocess.run(["git", *args], check=True, capture_output=True, env=GIT_ENV)

    def test_default_clone_is_refused(self):
        repo = self.tmp / "repo"
        self.git("init", "-q", str(repo))
        problems = cf.state_dir_problems(repo)
        self.assertTrue(any("inside a `.git` directory" in p for p in problems), problems)

    def test_symlinked_worktrees_are_refused(self):
        repo, outside = self.tmp / "repo", self.tmp / "outside"
        self.git("init", "-q", str(repo))
        outside.mkdir()
        (repo / ".git" / "infra-factory").mkdir()
        (repo / ".git" / "infra-factory" / "worktrees").symlink_to(outside)
        self.assertTrue(any("symlink" in p for p in cf.state_dir_problems(repo)))

    def test_separate_git_dir_is_accepted(self):
        repo = self.tmp / "vsh-factory"
        self.git("init", "-q", "--separate-git-dir", str(self.tmp / "vsh-factory-gitdir"), str(repo))
        self.assertEqual(cf.state_dir_problems(repo), [])

    def test_apply_refuses_a_bad_layout(self):
        with (
            mock.patch.object(cf, "state_dir_problems", return_value=["bad layout"]),
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as ctx,
        ):
            cf.main(["--toolkit", "/nonexistent", "--tdd-skill", "/nonexistent", "--apply"])
        self.assertIn("bad layout", str(ctx.exception.code))


@unittest.skipUnless(os.environ.get("VSH_FACTORY_TOOLKIT"), "set VSH_FACTORY_TOOLKIT to the reviewed toolkit")
class RealToolkit(unittest.TestCase):
    """Optional: validate the generated config with the pinned toolkit's own loaders."""

    def test_toolkit_accepts_the_generated_configuration(self):
        toolkit = Path(os.environ["VSH_FACTORY_TOOLKIT"]).resolve()
        skill = Path(tempfile.mkdtemp()) / "SKILL.md"
        skill.write_text("# tdd\n")
        with (
            mock.patch.object(cf.shutil, "which", return_value="/usr/bin/true"),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            config = cf.build(
                cf.parser().parse_args(
                    [
                        "--toolkit",
                        str(toolkit),
                        "--tdd-skill",
                        str(skill),
                        "--claude-builder-model",
                        CLAUDE_ID,
                        "--codex-model",
                        CODEX_ID,
                        "--ci-workflow-id",
                        "1",
                    ]
                )
            )
        sys.path.insert(0, str(toolkit))
        import repair
        import review_policy

        review_policy.validate(config["review_policy"])
        repair.validate_policy(config["repair_policy"])
        for role in review_policy.required_commands(config["review_policy"]):
            self.assertIn(role, config["commands"])
        bridge = (toolkit / "agent_bridge.py").read_text(encoding="utf-8")
        pattern = re.search(r"FULL_CLAUDE_ID = re\.compile\(r'(.+)'\)", bridge).group(1)
        self.assertEqual(pattern, cf.FULL_CLAUDE_ID.pattern)


if __name__ == "__main__":
    unittest.main()
