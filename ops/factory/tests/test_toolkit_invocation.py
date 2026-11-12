"""Regression test: the suite command must be able to start toolkit 0.5.0's test_report.py.

U02-VITALS-EDIT-C (12 Nov 2026) passed the changed-test gate, then every cold suite died before
running a test: ``ModuleNotFoundError: No module named 'path_safety'``. ``suite_check`` launched
``test_report.py`` with ``python3 -I``, which drops the script's own directory from ``sys.path``,
and 0.5.0's test_report.py imports ``path_safety`` from that directory. The fix keeps the
isolation that matters (``-s -E``: no user site, no PYTHON* variables; a script run never puts the
working directory, i.e. the cold checkout, on the path) and lets the toolkit import its own modules.
"""

# ruff: noqa: S603  (test code; same waiver as backend/tests in pyproject.toml)
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

FACTORY = Path(__file__).resolve().parent.parent


def load_configure():
    spec = importlib.util.spec_from_file_location(
        "configure_factory_invocation", FACTORY / "configure_factory.py"
    )
    if spec is None or spec.loader is None:
        raise ImportError("configure_factory.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ToolkitInvocationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="vsh-invocation-test-")
        self.tmp = Path(self._tmp)
        self.toolkit = self.tmp / "toolkit"
        self.toolkit.mkdir()
        # Shaped like 0.5.0: test_report.py imports a helper module that sits next to it.
        (self.toolkit / "path_safety.py").write_text('ORIGIN = "toolkit"\n')
        (self.toolkit / "test_report.py").write_text("from path_safety import ORIGIN\nprint(ORIGIN)\n")
        self.cold = self.tmp / "cold-checkout"  # the untrusted candidate checkout the suite runs in
        self.cold.mkdir()
        cf = load_configure()
        check = cf.suite_check(sys.executable, self.toolkit, [], "frontend-unit", ["frontend"], "unit", 60)
        argv = check["argv"]
        script = str(self.toolkit / "test_report.py")
        self.assertIn(script, argv)
        # The interpreter, its flags and the script, exactly as the factory will start them.
        self.launch = argv[: argv.index(script) + 1]

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def run_launch(self, **env: str) -> subprocess.CompletedProcess[str]:
        full = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
        full.update(env)
        return subprocess.run(
            self.launch, cwd=self.cold, env=full, capture_output=True, text=True, timeout=60
        )

    def test_test_report_can_import_its_own_modules(self) -> None:
        proc = self.run_launch()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "toolkit")

    def test_candidate_modules_cannot_shadow_the_toolkit(self) -> None:
        # A candidate controls the cold checkout: a module planted there (or named on PYTHONPATH)
        # must not replace the toolkit's own.
        (self.cold / "path_safety.py").write_text('ORIGIN = "planted"\n')
        proc = self.run_launch(PYTHONPATH=str(self.cold))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "toolkit")

    def test_user_site_and_python_variables_are_ignored(self) -> None:
        self.assertIn("-s", self.launch, "no user site-packages")
        self.assertIn("-E", self.launch, "no PYTHON* environment variables")
        self.assertNotIn("-I", self.launch, "-I hides the toolkit's own modules from test_report.py")


if __name__ == "__main__":
    unittest.main()
