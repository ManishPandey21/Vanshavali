#!/usr/bin/env python3
"""Trusted test-suite wrapper for the Infra Code Factory (ADR-0029).

The factory's controller runs every required test category in a *cold* checkout: a fresh Git
repository holding only the candidate commit, with a scrubbed environment (PATH plus a private
HOME/TMPDIR and ``FACTORY_NAMESPACE``). Nothing is installed there and no database exists. This
wrapper makes Vanshavali's real suites runnable in that state and writes native JUnit XML, which
the toolkit's ``test_report.py`` turns into evidence (it rejects empty, skipped or failing runs).

    python3 -I ops/factory/run_suite.py SUITE JUNIT_PATH [--cache-dir DIR] [--pg-admin-url URL]
    python3 -I ops/factory/run_suite.py --static backend|frontend [--cache-dir DIR]

Suites (each maps to one verification-policy check kind):

    backend-unit / backend-api / backend-integration / backend-migration
        pytest, partitioned by ``pytest_kinds.py`` (every collected test lands in exactly one).
    frontend-unit       vitest, ``*.test.ts`` (logic, hooks, i18n, API client)
    frontend-component  vitest, ``*.test.tsx`` (rendered React components)
    frontend-visual     Playwright screenshot comparison, ``e2e/visual`` (playwright.visual.config.ts)
    frontend-e2e        Playwright end-to-end + accessibility, ``e2e/tests``
    shared-contract     backend OpenAPI == frontend/openapi.json, and schema.d.ts == generated types

``--static`` runs the exit-code-only preflight (ruff/format/mypy, or eslint/tsc/vite build).

Everything this file needs from the host is explicit: ``uv``, ``node``/``npm``, ``tesseract`` and a
reachable PostgreSQL 16 admin URL (dev default below; never a production URL). Each suite gets its
own database and ports derived from ``FACTORY_NAMESPACE`` so concurrent runs and a developer's own
stack are not touched. Downloads are cached in ``--cache-dir`` (package caches, Playwright
browsers, the checksum-verified ephemeris); installed trees (``.venv``, ``node_modules``) are always
built fresh inside the cold checkout, never reused from a builder.

This file lives under ``ops/factory/`` which the factory config lists in ``protected_paths``:
a builder cannot change how its own work is verified.
"""

# ruff: noqa: S603, S607  (a test runner: it runs fixed, trusted argv by design)
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

DEFAULT_PG_ADMIN_URL = "postgresql+psycopg://vanshavali:vanshavali@localhost:5432/postgres"
BACKEND_KINDS = ("unit", "api", "integration", "migration")
SUITES = (
    *(f"backend-{k}" for k in BACKEND_KINDS),
    "frontend-unit",
    "frontend-component",
    "frontend-visual",
    "frontend-e2e",
    "shared-contract",
)
# A real Remotion render needs the renderer bundle + ffmpeg; CI's `renderer` job runs it
# (VSH_TEST_REMOTION=1). Deselected here rather than skipped, so it never counts as a pass.
DESELECT = ("tests/test_render_jobs.py::test_real_remotion_render_end_to_end",)
HERE = Path(__file__).resolve().parent
# Host network settings a cold checkout may need to download packages (corporate proxy / private
# CA). The factory scrubs the environment, so they come from a 0600 file *outside* the repository
# (written by configure_factory.py --capture-network-env); only these names are ever read from it.
NETWORK_KEYS = frozenset(
    {
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "NO_PROXY",
        "ALL_PROXY",
        "https_proxy",
        "http_proxy",
        "no_proxy",
        "all_proxy",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "NODE_EXTRA_CA_CERTS",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "PIP_CERT",
        "UV_NATIVE_TLS",
        "UV_SYSTEM_CERTS",
        "npm_config_https_proxy",
        "npm_config_proxy",
        "npm_config_noproxy",
        "npm_config_cafile",
    }
)


class SuiteError(RuntimeError):
    pass


def log(msg: str) -> None:
    print(f"[run_suite] {msg}", file=sys.stderr, flush=True)


def namespace() -> str:
    return os.environ.get("FACTORY_NAMESPACE") or f"manual-{os.getpid()}-{time.time_ns()}"


def ns_hash(n: int = 10) -> str:
    return hashlib.sha256(namespace().encode()).hexdigest()[:n]


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise SuiteError(
            f"`{name}` is not on PATH; install it on the factory host (see docs/operations/code-factory.md)"
        )
    return path


def read_network_env(path: Path) -> dict[str, str]:
    """KEY=VALUE lines; unknown keys are an error (this file must never smuggle in app config)."""
    if path.is_symlink() or not path.is_file():
        raise SuiteError(f"network env file {path} is missing or a symlink")
    if os.name == "posix" and path.stat().st_mode & 0o077:
        raise SuiteError(f"network env file {path} must be private (chmod 600)")
    values: dict[str, str] = {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or key not in NETWORK_KEYS:
            raise SuiteError(
                f"{path}:{n}: only network settings are allowed ({', '.join(sorted(NETWORK_KEYS))})"
            )
        values[key] = value
    return values


def run(argv: list[str], cwd: Path, env: dict[str, str]) -> None:
    log(f"$ (cd {cwd.name}) {' '.join(argv)}")
    proc = subprocess.run(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL)
    if proc.returncode:
        raise SuiteError(f"{argv[0]} exited {proc.returncode}")


class Context:
    def __init__(self, root: Path, cache: Path, pg_admin_url: str, network_env: Path | None = None) -> None:
        self.root = root
        self.backend = root / "backend"
        self.frontend = root / "frontend"
        self.e2e = root / "e2e"
        self.cache = cache
        self.pg_admin_url = pg_admin_url
        for d in ("backend", "frontend", "e2e"):
            if not (root / d).is_dir():
                raise SuiteError(f"run from the repository root (missing {d}/)")
        cache.mkdir(parents=True, exist_ok=True)
        self.env = dict(os.environ)
        self.env.update(
            {
                # same interpreter as CI (.github/workflows/ci.yml); uv installs it into the cache if absent
                "UV_PYTHON": "3.11",
                "UV_CACHE_DIR": str(cache / "uv"),
                "UV_PYTHON_INSTALL_DIR": str(cache / "uv-python"),
                "UV_LINK_MODE": "copy",
                "npm_config_cache": str(cache / "npm"),
                "npm_config_update_notifier": "false",
                "npm_config_fund": "false",
                "npm_config_audit": "false",
                "PLAYWRIGHT_BROWSERS_PATH": str(cache / "ms-playwright"),
                "PYTHONDONTWRITEBYTECODE": "1",
                "VSH_EPHEMERIS_PATH": str(cache / "ephemeris" / "de440s.bsp"),
            }
        )
        # Never let a test run see a production-looking configuration.
        for key in list(self.env):
            if key.startswith("VSH_") and key != "VSH_EPHEMERIS_PATH":
                del self.env[key]
        # cold checkouts live under .git/infra-factory/: see the note in frontend/vite.config.ts
        self.env["VSH_FACTORY_COLD"] = "1"
        if network_env is not None:
            self.env.update(read_network_env(network_env))

    # ---------------------------------------------------------------- installs (fresh, cached downloads)
    def backend_deps(self) -> None:
        if not (self.backend / ".venv").is_dir():
            require_tool("uv")
            run(["uv", "sync", "--frozen"], self.backend, self.env)

    def frontend_deps(self) -> None:
        if not (self.frontend / "node_modules").is_dir():
            require_tool("npm")
            run(["npm", "ci", "--no-audit", "--no-fund"], self.frontend, self.env)

    def e2e_deps(self) -> None:
        self.backend_deps()
        self.frontend_deps()
        if not (self.e2e / "node_modules").is_dir():
            run(["npm", "ci", "--no-audit", "--no-fund"], self.e2e, self.env)
        # Version-matched browser for the pinned @playwright/test; downloaded once into the cache.
        run(["npx", "playwright", "install", "chromium"], self.e2e, self.env)

    def ephemeris(self) -> None:
        path = Path(self.env["VSH_EPHEMERIS_PATH"])
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            # fetch() verifies the pinned checksum (ADR-0022) before the file is used.
            run(
                ["uv", "run", "python", "-m", "app.cli.calendar", "fetch-ephemeris", "--dest", str(path)],
                self.backend,
                self.env,
            )

    # ---------------------------------------------------------------- suites
    def pytest_suite(self, kind: str, junit: Path) -> None:
        require_tool("tesseract")  # OCR tests must run, never skip
        self.backend_deps()
        self.ephemeris()
        env = dict(self.env)
        env.update(
            {
                "VSH_TEST_ADMIN_URL": self.pg_admin_url,
                "VSH_TEST_DB_NAME": f"vsh_factory_{ns_hash()}_{kind}",
                "VSH_REQUIRE_EPHEMERIS": "1",
                "PYTHONPATH": str(HERE),
            }
        )
        argv = [
            "uv",
            "run",
            "pytest",
            "-q",
            "-p",
            "pytest_kinds",
            f"--factory-kind={kind}",
            f"--junitxml={junit}",
        ]
        argv += [f"--deselect={d}" for d in DESELECT]
        run(argv, self.backend, env)

    def vitest_suite(self, kind: str, junit: Path) -> None:
        self.frontend_deps()
        argv = [
            "npx",
            "vitest",
            "run",
            "--reporter=default",
            "--reporter=junit",
            f"--outputFile.junit={junit}",
        ]
        if kind == "unit":
            argv += ["--exclude=**/node_modules/**", "--exclude=**/*.test.tsx"]
        else:
            argv += [".test.tsx"]  # vitest filters are path substrings: only component tests match
        run(argv, self.frontend, self.env)

    def playwright_suite(self, kind: str, junit: Path) -> None:
        self.e2e_deps()
        base = 20000 + (int(ns_hash(6), 16) % 4500) * 2  # API port; the SPA uses base + 1
        env = dict(self.env)
        env.update(
            {
                "VSH_E2E_ADMIN_URL": self.pg_admin_url,
                "VSH_E2E_DB": f"vsh_factory_{ns_hash()}_{kind}",
                "VSH_E2E_API_PORT": str(base),
                "VSH_E2E_WEB_PORT": str(base + 1),
                "PLAYWRIGHT_JUNIT_OUTPUT_FILE": str(junit),
            }
        )
        argv = ["npx", "playwright", "test", "--reporter=list,junit", "--trace=off"]
        if kind == "visual":
            argv += ["--config=playwright.visual.config.ts"]
        run(argv, self.e2e, env)

    def contract_suite(self, junit: Path) -> None:
        """The generated API contract the SPA compiles against must match the server's."""
        self.backend_deps()
        self.frontend_deps()
        cases: list[tuple[str, str | None]] = []
        tmp = Path(tempfile.mkdtemp(prefix="vsh-contract-"))

        # 1. backend OpenAPI == committed frontend/openapi.json (exactly what `npm run gen:api` writes)
        script = "import json; from app.main import app; print(json.dumps(app.openapi(), indent=1))"
        proc = subprocess.run(
            ["uv", "run", "python", "-c", script],
            cwd=self.backend,
            env=self.env,
            capture_output=True,
            text=True,
        )
        if proc.returncode:
            cases.append(
                (
                    "openapi_document_matches_backend",
                    f"backend failed to build OpenAPI:\n{proc.stderr[-4000:]}",
                )
            )
        else:
            committed = (self.frontend / "openapi.json").read_text(encoding="utf-8")
            ok = proc.stdout == committed
            cases.append(
                (
                    "openapi_document_matches_backend",
                    None if ok else "frontend/openapi.json is stale: run `npm run gen:api` in frontend/",
                )
            )

        # 2. committed schema.d.ts == openapi-typescript output for the committed document
        out = tmp / "schema.d.ts"
        proc = subprocess.run(
            ["npx", "openapi-typescript", "openapi.json", "-o", str(out), "--default-non-nullable", "false"],
            cwd=self.frontend,
            env=self.env,
            capture_output=True,
            text=True,
        )
        if proc.returncode or not out.is_file():
            cases.append(
                ("typescript_types_match_openapi", f"openapi-typescript failed:\n{proc.stderr[-4000:]}")
            )
        else:
            same = out.read_bytes() == (self.frontend / "src/api/schema.d.ts").read_bytes()
            cases.append(
                (
                    "typescript_types_match_openapi",
                    None
                    if same
                    else "frontend/src/api/schema.d.ts is stale: run `npm run gen:api` in frontend/",
                )
            )
        shutil.rmtree(tmp, ignore_errors=True)
        write_junit(junit, "shared-contract", cases)
        failed = [name for name, err in cases if err]
        if failed:
            raise SuiteError("contract mismatch: " + ", ".join(failed))

    # ---------------------------------------------------------------- exit-code preflight
    def static(self, side: str) -> None:
        if side == "backend":
            self.backend_deps()
            run(["uv", "run", "ruff", "check", "app", "tests"], self.backend, self.env)
            run(["uv", "run", "ruff", "format", "--check", "app", "tests"], self.backend, self.env)
            run(["uv", "run", "mypy", "app"], self.backend, self.env)
        else:
            self.frontend_deps()
            run(["npm", "run", "lint"], self.frontend, self.env)
            run(["npm", "run", "typecheck"], self.frontend, self.env)
            run(["npm", "run", "build"], self.frontend, self.env)


def write_junit(path: Path, suite: str, cases: list[tuple[str, str | None]]) -> None:
    failures = sum(1 for _, err in cases if err)
    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<testsuites><testsuite name={quoteattr(suite)} tests="{len(cases)}" failures="{failures}" errors="0" skipped="0">',
    ]
    for name, err in cases:
        parts.append(f"<testcase classname={quoteattr(suite)} name={quoteattr(name)}>")
        if err:
            parts.append(f"<failure message={quoteattr(err.splitlines()[0])}>{escape(err)}</failure>")
        parts.append("</testcase>")
    parts.append("</testsuite></testsuites>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("suite", nargs="?", choices=SUITES)
    p.add_argument(
        "junit", nargs="?", help="relative path for the native JUnit XML (e.g. .factory-test-output/x.xml)"
    )
    p.add_argument("--static", choices=("backend", "frontend"))
    p.add_argument("--cache-dir", default=str(Path.home() / ".cache" / "vanshavali-factory"))
    p.add_argument("--pg-admin-url", default=DEFAULT_PG_ADMIN_URL)
    p.add_argument("--network-env", help="private KEY=VALUE file of proxy/CA settings (outside the repo)")
    p.add_argument("--repo", default=".", help="checkout root (default: current directory)")
    a = p.parse_args(argv)
    if bool(a.static) == bool(a.suite):
        p.error("give exactly one of SUITE JUNIT or --static SIDE")
    if a.suite and not a.junit:
        p.error("SUITE needs a JUNIT output path")
    try:
        net = Path(a.network_env).expanduser() if a.network_env else None
        ctx = Context(Path(a.repo).resolve(), Path(a.cache_dir).expanduser().resolve(), a.pg_admin_url, net)
        if a.static:
            ctx.static(a.static)
            return 0
        junit = (ctx.root / a.junit).resolve()
        if ctx.root not in junit.parents:
            p.error("JUNIT must be inside the checkout")
        side, kind = a.suite.split("-", 1)
        if side == "backend":
            ctx.pytest_suite(kind, junit)
        elif side == "frontend" and kind in ("unit", "component"):
            ctx.vitest_suite(kind, junit)
        elif side == "frontend":
            ctx.playwright_suite(kind, junit)
        else:
            ctx.contract_suite(junit)
        if not junit.is_file():
            raise SuiteError(f"{a.suite} produced no JUnit report at {a.junit}")
        log(f"{a.suite}: JUnit written to {a.junit}")
        return 0
    except SuiteError as exc:
        log(f"FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
