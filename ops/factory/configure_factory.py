#!/usr/bin/env python3
"""Write Vanshavali's local Infra Code Factory configuration (ADR-0029).

The factory (a standalone toolkit, kept OUTSIDE this repository) reads
``.infra-factory/config.json`` from the checkout. That file holds machine-specific absolute
paths (toolkit, Python, cache, TDD skill), so it is generated here and git-ignored; everything
that defines *what is verified* is in this script and is reviewed like any other code.

    python3 ops/factory/configure_factory.py --toolkit /path/to/infra-code-factory \\
        --tdd-skill /path/to/superpowers/skills/test-driven-development/SKILL.md          # preview
    python3 ops/factory/configure_factory.py ... --apply                                  # write

Run ``factory.py init --repo . --apply`` first (creates the ledger under .git/infra-factory/).
See docs/operations/code-factory.md for the whole procedure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUN_SUITE = REPO / "ops" / "factory" / "run_suite.py"
CONFIG = REPO / ".infra-factory" / "config.json"
TOOLKIT_VERSION = "0.3.1"
TOOLKIT_FILES = (
    "factory.py",
    "verification_policy.py",
    "cold_workspace.py",
    "test_report.py",
    "agent_bridge.py",
)

# Which repository roots belong to which layer. Paths outside every root (e2e/, renderer/, docs/,
# deploy/, ops/...) conservatively select the full stack. The generated API contract is "shared":
# touching it runs frontend + backend + contract suites.
PATH_DOMAINS = {
    "frontend": ["frontend"],
    "backend": ["backend"],
    "shared": ["frontend/openapi.json", "frontend/src/api"],
}
# Strengthen the toolkit minima (frontend: unit/component/visual/e2e; backend: unit/api/integration;
# shared: contract). Backend changes must also pass the migration suite, the API-contract check
# and the browser E2E suite: "a passing API test does not prove the browser workflow works".
REQUIRED = {"backend": ["migration", "contract", "e2e"]}
SUITES = [
    # id,                 domains,                   kind,          timeout (s)
    ("backend-unit", ["backend"], "unit", 1200),
    ("backend-api", ["backend"], "api", 3600),
    ("backend-integration", ["backend"], "integration", 1800),
    ("backend-migration", ["backend"], "migration", 1800),
    ("frontend-unit", ["frontend"], "unit", 900),
    ("frontend-component", ["frontend"], "component", 1200),
    ("frontend-visual", ["frontend"], "visual", 1200),
    ("frontend-e2e", ["frontend", "backend"], "e2e", 3600),
    ("shared-contract", ["shared", "backend"], "contract", 900),
]
# Builders may add tests but never change how work is verified. The toolkit already refuses edits to
# existing tests/snapshots, manifests, lockfiles, *.config.* and .gitignore; these are the
# project-specific runners and harnesses it cannot recognise by name.
PROTECTED_PATHS = [
    "ops/factory",
    "backend/tests/conftest.py",
    "backend/tests/helpers.py",
    "backend/alembic.ini",
    "e2e/scripts",
    "e2e/tests/helpers.ts",
    "frontend/src/test",
    "docs/architecture/adr/0029-agent-ticket-factory.md",
]


NETWORK_KEYS = (
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
)


def capture_network_env(path: Path) -> None:
    """Save this shell's proxy/CA settings for cold checkouts (values never enter config or logs)."""
    lines = [f"{k}={os.environ[k]}" for k in NETWORK_KEYS if os.environ.get(k)]
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("# proxy/CA settings for Vanshavali factory checks (ops/factory/run_suite.py)\n")
        f.write("\n".join(lines) + ("\n" if lines else ""))
    os.chmod(path, 0o600)
    print(f"saved {len(lines)} network setting(s) to {path}", file=sys.stderr)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_toolkit(toolkit: Path) -> None:
    missing = [f for f in TOOLKIT_FILES if not (toolkit / f).is_file()]
    if missing:
        sys.exit(f"--toolkit {toolkit} is not an Infra Code Factory directory (missing {', '.join(missing)})")
    sums = toolkit / "SHA256SUMS"
    if not sums.is_file():
        sys.exit("toolkit has no SHA256SUMS; re-extract the release archive")
    expected = {}
    for line in sums.read_text().splitlines():
        digest, _, name = line.partition("  ")
        expected[name.strip()] = digest.strip()
    for name in TOOLKIT_FILES:
        if expected.get(name) != sha256(toolkit / name):
            sys.exit(f"toolkit file {name} does not match SHA256SUMS: refusing a modified toolkit")
    changelog = (toolkit / "CHANGELOG.md").read_text() if (toolkit / "CHANGELOG.md").is_file() else ""
    if f"## {TOOLKIT_VERSION}" not in changelog:
        print(
            f"warning: toolkit is not version {TOOLKIT_VERSION}; re-check this integration", file=sys.stderr
        )


def suite_check(python: str, toolkit: Path, extra: list[str], sid: str, domains, kind, timeout):
    junit = f".factory-test-output/{sid}.xml"
    return {
        "id": sid,
        "domains": domains,
        "kind": kind,
        "argv": [
            python,
            "-I",
            str(toolkit / "test_report.py"),
            "--report",
            "{report}",
            "--junit",
            junit,
            "--timeout",
            str(timeout),
            "--",
            python,
            "-I",
            str(RUN_SUITE),
            sid,
            junit,
            *extra,
        ],
        "report": f"{sid}.json",
        "min_tests": 1,
    }


def agent(python: str, toolkit: Path, provider: str, mode: str, model: str, skill: Path | None):
    spec = {
        "argv": [
            python,
            str(toolkit / "agent_bridge.py"),
            "--provider",
            provider,
            "--mode",
            mode,
            "--model",
            "{model}",
            "--prompt-file",
            "{prompt_file}",
            "--result-file",
            "{result_file}",
        ],
        "stdin_prompt": False,
        "model": model,
    }
    if mode == "builder":
        spec["primary_skill"] = str(skill)
    return spec


def build(a: argparse.Namespace) -> dict:
    toolkit = a.toolkit.expanduser().resolve()
    check_toolkit(toolkit)
    skill = a.tdd_skill.expanduser().resolve()
    if not skill.is_file():
        sys.exit("--tdd-skill must point to the installed Superpowers test-driven-development/SKILL.md")
    cache = a.cache_dir.expanduser().resolve()
    python = a.python or sys.executable
    for tool in ("git", "uv", "npm", "npx", "node", "tesseract", "claude"):
        if not shutil.which(tool):
            print(f"warning: `{tool}` is not on PATH; the factory will block until it is", file=sys.stderr)
    if a.providers == "mixed" and not shutil.which("codex"):
        sys.exit("`codex` is not on PATH: install/authenticate it, or pass --providers claude")

    if a.providers == "mixed":
        codex_b = agent(python, toolkit, "codex", "builder", a.codex_model, skill)
        commands = {
            "backend": codex_b,
            "critical": codex_b,
            "frontend": agent(python, toolkit, "claude", "builder", a.claude_builder_model, skill),
            # two lenses on two providers: the reviewers do not share a model's blind spots
            "reviewer_standards": agent(python, toolkit, "codex", "reviewer", a.codex_model, None),
            "reviewer_spec": agent(python, toolkit, "claude", "reviewer", a.claude_review_model, None),
        }
    else:
        commands = {
            "backend": agent(python, toolkit, "claude", "builder", a.claude_builder_model, skill),
            "critical": agent(python, toolkit, "claude", "builder", a.claude_review_model, skill),
            "frontend": agent(python, toolkit, "claude", "builder", a.claude_builder_model, skill),
            "reviewer_standards": agent(python, toolkit, "claude", "reviewer", a.claude_review_model, None),
            "reviewer_spec": agent(python, toolkit, "claude", "reviewer", a.claude_review_model, None),
        }
    extra = ["--cache-dir", str(cache), "--pg-admin-url", a.pg_admin_url]
    if a.network_env:
        net = a.network_env.expanduser().resolve()
        if REPO in net.parents:
            sys.exit("--network-env must be outside the repository")
        if a.capture_network_env and a.apply:
            capture_network_env(net)
        elif not net.is_file():
            sys.exit(f"{net} does not exist: add --capture-network-env to create it from this shell")
        extra += ["--network-env", str(net)]
    static = lambda side: [python, "-I", str(RUN_SUITE), "--static", side, *extra]  # noqa: E731
    return {
        "version": 1,
        "base_ref": a.base_ref,
        "max_parallel": 2,
        "timeout_seconds": 3600,
        "checks": [static("backend"), static("frontend")],
        "protected_paths": PROTECTED_PATHS,
        "verification": {
            "path_domains": PATH_DOMAINS,
            "required": REQUIRED,
            "checks": [suite_check(python, toolkit, extra, *s) for s in SUITES],
        },
        "commands": commands,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--toolkit", required=True, type=Path, help="extracted infra-code-factory directory")
    p.add_argument(
        "--tdd-skill", required=True, type=Path, help="Superpowers test-driven-development/SKILL.md"
    )
    p.add_argument(
        "--providers",
        choices=("mixed", "claude"),
        default="mixed",
        help="mixed: Codex backend + standards review, Claude frontend + spec review (toolkit default); "
        "claude: Claude for every role",
    )
    p.add_argument("--codex-model", default="gpt-6.1-sol")
    p.add_argument("--claude-builder-model", default="sonnet")
    p.add_argument("--claude-review-model", default="opus")
    p.add_argument("--base-ref", default="main")
    p.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache" / "vanshavali-factory",
        help="download caches shared by cold checkouts (packages, browsers, ephemeris)",
    )
    p.add_argument(
        "--pg-admin-url",
        default="postgresql+psycopg://vanshavali:vanshavali@localhost:5432/postgres",
        help="LOCAL test PostgreSQL admin URL; suites create and drop their own databases",
    )
    p.add_argument(
        "--network-env",
        type=Path,
        help="private file of proxy/CA settings for checks behind a proxy, e.g. "
        "~/.config/vanshavali-factory/network.env (outside the repo)",
    )
    p.add_argument(
        "--capture-network-env",
        action="store_true",
        help="with --apply: write --network-env from this shell's proxy/CA variables",
    )
    p.add_argument("--python", help="interpreter for the toolkit (default: this one)")
    p.add_argument("--apply", action="store_true", help="write .infra-factory/config.json")
    a = p.parse_args(argv)
    if "localhost" not in a.pg_admin_url and "127.0.0.1" not in a.pg_admin_url:
        sys.exit("--pg-admin-url must be a local test server: suites DROP and CREATE databases on it")
    config = build(a)
    text = json.dumps(config, indent=2) + "\n"
    if not a.apply:
        print(text)
        print("(preview only; rerun with --apply to write .infra-factory/config.json)", file=sys.stderr)
        return 0
    if CONFIG.exists() and CONFIG.read_text() != text:
        backup = CONFIG.with_name("config.json.bak")
        backup.write_bytes(CONFIG.read_bytes())
        print(f"previous configuration saved to {backup.relative_to(REPO)}", file=sys.stderr)
    CONFIG.parent.mkdir(exist_ok=True)
    CONFIG.write_text(text)
    print(f"wrote {CONFIG.relative_to(REPO)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
