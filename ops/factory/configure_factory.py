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
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUN_SUITE = REPO / "ops" / "factory" / "run_suite.py"
# Builders start through this controller-owned step, which installs dependencies from the committed
# lockfiles before the agent exists (builders themselves may never install packages).
BOOTSTRAP = REPO / "ops" / "factory" / "bootstrap_builder.py"
CONFIG = REPO / ".infra-factory" / "config.json"
TOOLKIT_VERSION = "0.3.4"
# SHA-256 of the toolkit's runtime files as reviewed for this integration (0.3.4). Pinned here, not
# read from the toolkit's own SHA256SUMS: that file ships next to the code it describes, so it proves
# nothing against a modified copy. 0.3.4 = the pinned 0.3.3 archive + the reviewed patch in
# ops/factory/toolkit/; `ops/factory/toolkit_release.py build` reproduces it and checks these hashes.
# Upgrading the toolkit = review its diff, then update these hashes in a reviewed PR.
TOOLKIT_SHA256 = {
    "factory.py": "dc40d73519fe93ae7da3abbe719527f92b536c3f7332e0fd3e5a9c7ba9e3edee",
    "verification_policy.py": "a984427a17e4e3636fe2a3bf054d9da7b226058d55e5d7f0bfbc2617fdabfcd6",
    "cold_workspace.py": "2f687c221d1b0226b5a9c3976967cba367bd7df2e2edb53fa80b31f1c3fa0faf",
    "test_report.py": "192b01fb39c01fda0a384d165df31c4a070a7d37347d2b4c9f2d50dabc9b67da",
    "agent_bridge.py": "b969e2076af0aba9e3f22b577bf89604f4d4183a2865e4b38693234212300722",
}
TOOLKIT_FILES = tuple(TOOLKIT_SHA256)

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
    for name, digest in TOOLKIT_SHA256.items():
        if sha256(toolkit / name) != digest:
            sys.exit(
                f"toolkit file {name} is not the reviewed Infra Code Factory {TOOLKIT_VERSION} "
                "(see TOOLKIT_SHA256 in ops/factory/configure_factory.py): refusing it"
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


EFFORTS = ("low", "medium", "high", "xhigh", "max")  # Claude Code CLI --effort levels
CODEX_EFFORTS = ("low", "medium", "high")
FULL_CLAUDE_ID = re.compile(r"claude-[a-z]+(-[0-9]+)+")
# Role -> (provider, model, effort): ADR-0030. Builders are chosen by ticket risk/complexity
# (role: critical, complexity: complex), not by frontend/backend; which suites run is still decided
# by the ticket's paths. Fable reviews critical tickets only, unless selected with --route.
ROUTES = {
    "builder_routine": ("claude", "claude-sonnet-5-5", "medium"),
    "builder_complex": ("claude", "claude-opus-5-5", "high"),
    "builder_critical": ("claude", "claude-opus-5-5", "high"),
    "reviewer_standards": ("claude", "claude-opus-5-5", "high"),
    "reviewer_spec": ("claude", "claude-opus-5-5", "high"),
    "reviewer_standards_critical": ("claude", "claude-opus-5-5", "high"),
    "reviewer_spec_critical": ("claude", "claude-fable-5-2", "high"),
}
# --providers mixed: the standards lens and routine builds on Codex, so the two reviewers never share
# one model's blind spots.
MIXED = {"builder_routine": "medium", "reviewer_standards": "high"}
# Tickets are still validated by role (frontend/backend/critical): those names stay as aliases.
LEGACY_ROLES = {"frontend": "builder_routine", "backend": "builder_routine", "critical": "builder_critical"}
NODE_MAJOR = 22  # .github/workflows/ci.yml
MIN_FREE_GB = 5.0
# One builder command covers install, agent, gate and repair rounds; reviewers get the same limit.
TIMEOUT_SECONDS = 5400
GATE = REPO / "ops" / "factory" / "changed_test_gate.py"


def parse_route(text: str) -> tuple[str, tuple[str, str, str]]:
    try:
        role, rest = text.split("=", 1)
        provider, model, effort = rest.split(":")
    except ValueError:
        raise argparse.ArgumentTypeError("--route takes ROLE=PROVIDER:MODEL:EFFORT") from None
    if role not in ROUTES:
        raise argparse.ArgumentTypeError(f"unknown role {role!r} (one of {', '.join(ROUTES)})")
    check_route(role, provider, model, effort)
    return role, (provider, model, effort)


def check_route(role: str, provider: str, model: str, effort: str) -> None:
    if provider not in ("claude", "codex"):
        raise argparse.ArgumentTypeError(f"{role}: provider must be claude or codex")
    if effort not in (CODEX_EFFORTS if provider == "codex" else EFFORTS):
        raise argparse.ArgumentTypeError(f"{role}: effort {effort!r} is not supported for {provider}")
    if provider == "claude" and not FULL_CLAUDE_ID.fullmatch(model):
        raise argparse.ArgumentTypeError(
            f"{role}: {model!r} is not a full Claude model id (aliases can be remapped)"
        )


def routes_for(a: argparse.Namespace) -> dict[str, tuple[str, str, str]]:
    routes = dict(ROUTES)
    if a.providers == "mixed":
        for role, effort in MIXED.items():
            routes[role] = ("codex", a.codex_model, effort)
    routes.update(dict(getattr(a, "route", None) or []))
    return routes


def agent(
    python: str,
    toolkit: Path,
    role: str,
    route: tuple[str, str, str],
    skill: Path | None,
    bootstrap: list[str] | None = None,
):
    provider, model, effort = route
    mode = "builder" if role.startswith("builder") else "reviewer"
    # Builders: [python -I bootstrap_builder.py <bootstrap args> --gate ... --] + the agent command.
    # Reviewers get no bootstrap: they read the candidate and the cold-check evidence only.
    prefix = [python, "-I", str(BOOTSTRAP), *(bootstrap or []), "--"] if mode == "builder" else []
    spec = {
        "argv": [
            *prefix,
            python,
            str(toolkit / "agent_bridge.py"),
            "--provider",
            provider,
            "--mode",
            mode,
            "--model",
            "{model}",
            "--effort",
            effort,
            "--strict-routing",
            "--prompt-file",
            "{prompt_file}",
            "--result-file",
            "{result_file}",
        ],
        "stdin_prompt": False,
        "provider": provider,
        "model": model,
        "effort": effort,
    }
    if mode == "builder":
        spec["primary_skill"] = str(skill)
    return spec


def probe_models(python: str, toolkit: Path, routes: dict[str, tuple[str, str, str]]) -> dict[str, dict]:
    """Run each distinct provider/model/effort once through the real bridge in strict mode: the
    model must answer and must be the one that served the run. Any failure stops the configuration."""
    results: dict[str, dict] = {}
    for provider, model, effort in sorted(set(routes.values())):
        key = f"{provider}:{model}:{effort}"
        with tempfile.TemporaryDirectory(prefix="vsh-model-probe-") as tmp:
            prompt = Path(tmp) / "prompt.txt"
            prompt.write_text("Reply with exactly: OK. Do not use any tools.")
            result = Path(tmp) / "probe-result.json"
            proc = subprocess.run(  # noqa: S603 (the pinned bridge, fixed argv)
                [python, str(toolkit / "agent_bridge.py"), "--provider", provider, "--mode", "builder",
                 "--model", model, "--effort", effort, "--strict-routing",
                 "--prompt-file", str(prompt), "--result-file", str(result)],
                cwd=tmp, capture_output=True, text=True, timeout=600,
            )  # fmt: skip
            evidence_file = result.with_name("probe-result.routing.json")
            evidence = json.loads(evidence_file.read_text()) if evidence_file.is_file() else {}
        if proc.returncode or evidence.get("outcome") != "ok":
            reason = evidence.get("error") or proc.stderr.strip()[-500:] or f"exit {proc.returncode}"
            sys.exit(
                f"model probe failed for {key}: {reason}\nNothing was written; fix access or choose another --route."
            )
        results[key] = {"served_models": sorted(evidence.get("served_models") or []), "at": time.time()}
        print(f"model probe ok: {key}", file=sys.stderr)
    return results


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
    routes = routes_for(a)
    for role, route in routes.items():
        try:
            check_route(role, *route)
        except argparse.ArgumentTypeError as exc:
            sys.exit(str(exc))
    if any(provider == "codex" for provider, _, _ in routes.values()) and not shutil.which("codex"):
        sys.exit("`codex` is not on PATH: install/authenticate it, or route every role to claude")
    extra = ["--cache-dir", str(cache), "--pg-admin-url", a.pg_admin_url]
    boot = ["--cache-dir", str(cache)]
    if a.network_env:
        net = a.network_env.expanduser().resolve()
        if REPO in net.parents:
            sys.exit("--network-env must be outside the repository")
        if a.capture_network_env and a.apply:
            capture_network_env(net)
        elif not net.is_file():
            sys.exit(f"{net} does not exist: add --capture-network-env to create it from this shell")
        extra += ["--network-env", str(net)]
        boot += ["--network-env", str(net)]
    boot += [
        "--gate",
        "--repair-rounds",
        str(getattr(a, "repair_rounds", 1)),
        "--pg-admin-url",
        a.pg_admin_url,
        "--min-free-gb",
        f"{MIN_FREE_GB:g}",
        "--node-major",
        str(NODE_MAJOR),
        # an argv path, so the factory hashes it with the other tools for the whole run
        "--gate-module",
        str(GATE),
        "--budget-seconds",
        str(TIMEOUT_SECONDS - 300),
    ]
    commands = {role: agent(python, toolkit, role, route, skill, boot) for role, route in routes.items()}
    for legacy, role in LEGACY_ROLES.items():
        commands[legacy] = commands[role]
    probe = None
    if getattr(a, "probe_models", False):
        probe = probe_models(python, toolkit, routes)
    static = lambda side: [python, "-I", str(RUN_SUITE), "--static", side, *extra]  # noqa: E731
    return {
        "version": 1,
        "base_ref": a.base_ref,
        "max_parallel": 2,
        "timeout_seconds": TIMEOUT_SECONDS,
        "checks": [static("backend"), static("frontend")],
        "protected_paths": PROTECTED_PATHS,
        "verification": {
            "path_domains": PATH_DOMAINS,
            "required": REQUIRED,
            "checks": [suite_check(python, toolkit, extra, *s) for s in SUITES],
        },
        "commands": commands,
        # For people and routing_report.py: the factory reads commands, not this section.
        "routing": {
            role: dict(zip(("provider", "model", "effort"), route, strict=True))
            for role, route in routes.items()
        },
        "model_probe": probe if probe is not None else "not run (preview, or --skip-model-probe)",
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
        help="mixed: Codex for routine builds and the standards lens, Claude for the rest; "
        "claude: Claude for every role (see ROUTES; override single roles with --route)",
    )
    p.add_argument("--codex-model", default="gpt-6.1-sol", help="Codex model for --providers mixed")
    p.add_argument(
        "--route",
        action="append",
        type=parse_route,
        default=[],
        metavar="ROLE=PROVIDER:MODEL:EFFORT",
        help="override one role (repeatable), e.g. builder_routine=claude:claude-opus-5-5:high; "
        "roles: " + ", ".join(ROUTES),
    )
    p.add_argument(
        "--repair-rounds",
        type=int,
        default=1,
        choices=range(3),
        help="times a failing changed-test gate is fed back to the builder within one attempt (default 1)",
    )
    p.add_argument(
        "--skip-model-probe",
        action="store_true",
        help="with --apply: do not check model availability now (the bridge still refuses a wrong model at run time)",
    )
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
    a.probe_models = a.apply and not a.skip_model_probe
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
