#!/usr/bin/env python3
"""Write Vanshavali's local Infra Code Factory configuration (ADR-0029).

The factory (a standalone toolkit, kept OUTSIDE this repository) reads
``.infra-factory/config.json`` from the checkout. That file holds machine-specific absolute
paths (toolkit, Python, cache, TDD skill), so it is generated here and git-ignored; everything
that defines *what is verified* is in this script and is reviewed like any other code.

    python3 ops/factory/configure_factory.py --toolkit /path/to/infra-code-factory \\
        --tdd-skill /path/to/superpowers/skills/test-driven-development/SKILL.md \\
        --claude-builder-model CLAUDE_MODEL_ID --codex-model CODEX_MODEL_ID              # preview
    python3 ops/factory/configure_factory.py ... --apply                                  # write

Every agent runs with the toolkit's strict routing (pinned model id, explicit effort, no fallback,
served-model check). Specialist reviews and the independent risk gate come from REVIEW_POLICY.
Run ``factory.py init --repo . --apply`` first (creates the ledger under <git-common-dir>/infra-factory/).
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
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUN_SUITE = REPO / "ops" / "factory" / "run_suite.py"
# Builders start through this controller-owned step, which installs dependencies from the committed
# lockfiles before the agent exists (builders themselves may never install packages).
BOOTSTRAP = REPO / "ops" / "factory" / "bootstrap_builder.py"
CONFIG = REPO / ".infra-factory" / "config.json"
TOOLKIT_VERSION = "0.5.0 (+ local pilot hardening, code-factory a780fce)"
# SHA-256 of every toolkit file the controller loads, as reviewed for this integration. Pinned here,
# not read from the archive's own SHA256SUMS: that file is shipped next to the code it describes (so it
# proves nothing against a modified copy). 0.5.0 split the controller into several modules; all of
# them are pinned, plus the dashboard assets `factory.py dashboard` serves.
# Upgrading the toolkit = review its diff, then update these hashes in a reviewed PR.
TOOLKIT_SHA256 = {
    "factory.py": "705c5cf4d25733bb727501286edc3f192349434217fb9e10938321f2d712d9cd",
    "agent_bridge.py": "8147fa3421cb8c776133b143bf20a69b38d27aacfd4220da68705073ab0ef273",
    "cold_workspace.py": "845e48ecf5e075569014afa0e5fb2c0b67eb3d6362c941d5923a335a461787bd",
    "test_report.py": "cd7cce065433635ac7455ed93ce035d14bc166a14e5f740bee5f7aba89fa84c9",
    "verification_policy.py": "6de05ca2fc71b2ebc60b303f5e9a9e123fce1108a235a13dd84ae61cbe395997",
    "review_policy.py": "c9d52774d1a601349ef5ecb82b5f6eb6c543c1e4ca43c87fabec662490852e18",
    "repair.py": "c659988cc0c34985bd0121c6f0ac798127e2b0c8dd6deb6439f9dd3fc4387ec0",
    "path_safety.py": "c1466b8e0ad74467df0b148721e88270d6517e853e15780c9dcb98b0875069c6",
    "check_paths.py": "9f231a5107d4b3b22b17f3d4a3bab72d0ade6ca9da62d2245ecc94156b8a51a2",
    "runtime_requirements.py": "acea0519f05ee0896dc6737a5cb00a4cf8722fa2d3c224eb5f9fa4c7f82eaa8d",
    "ticket_controls.py": "96a784dc705082baf27296d807ff79dd94397f13730ba825700e590d6802bdb3",
    "skill_inventory.py": "d9216614549aeda97a3bc9448374de8bce08cfa1dc0933d75d40f54de983b2f3",
    "egm.py": "5ebf14133f43a22a410440f614cc6a097ca75ef93e538f0336e4294b901f9cd6",
    "ledger_view.py": "732f459c20580f8575c43c855015ec8042b0966dfacbdb7b3fc8a67ef32db754",
    "web/index.html": "e21ea5f741c9b6002a562ec3fe5ab473bbe8182745f5139a966f40e873960ef3",
    "web/app.js": "1b22b7b5bd8170ea3b6620693d91f0cad11e9d9c7821ed3aa57fffd91bde1445",
    "web/style.css": "810d1ed8c02efc8ff6e097a79c03e77896bc1a327b9c585aa084f179e399ef39",
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


# Diff-selected specialist lenses and the independent risk gate (toolkit 0.5.0 `review_policy`).
# Standards and spec reviews stay mandatory for every ticket. Globs are Python fnmatch on the changed
# paths (deleted ones included): `*` crosses `/`. Each specialist runs in its own cold checkout with
# its own fresh reviewer, so keep the list short: at most eight are allowed.
REVIEW_POLICY = {
    "specialists": {
        "security": {
            "paths": [
                "backend/app/authz/*",
                "backend/app/api/*",
                "backend/app/core/security.py",
                "backend/app/core/storage.py",
                "backend/app/core/scanner.py",
                "backend/app/core/filetypes.py",
                "backend/app/core/ratelimit.py",
                "backend/app/core/totp.py",
                "backend/app/modules/identity/*",
                "backend/app/modules/consent/*",
                "backend/app/modules/public/*",
                "backend/app/modules/sharing/*",
                "backend/app/modules/takedown/*",
                "backend/app/modules/ownership/*",
                "backend/app/modules/documents/*",
                "backend/app/modules/archive/*",
                "backend/app/modules/gedcom/*",
                "backend/app/modules/property/*",
                "deploy/*",
                "docs/security/*",
            ],
            "focus": "CLAUDE.md rule 5: authorisation on every handler with backend/app/authz as the only "
            "authority; IDOR/BOLA, cross-tree access, privilege escalation, living-person and child-data "
            "leakage, public trees, share links and signed-URL abuse, uploads and downloads, exports, "
            "secrets. Require the negative tests and the threat-model/privacy-model updates.",
        },
        "data": {
            "paths": [
                "backend/alembic/*",
                "backend/app/models/*",
                "backend/app/core/db.py",
                "docs/architecture/domain-model.md",
            ],
            "focus": "CLAUDE.md rules 3-4: the relational schema is canonical; every change is an Alembic "
            "migration with a working downgrade and a single head; data integrity, compatibility with "
            "existing rows, and docs/architecture/domain-model.md kept in sync.",
        },
        "provenance": {
            "paths": [
                "backend/app/modules/documents/*",
                "backend/app/modules/evidence/*",
                "backend/app/modules/extraction/*",
                "backend/app/modules/smartadd/*",
                "backend/app/modules/review/*",
                "backend/app/modules/merge/*",
            ],
            "focus": "CLAUDE.md rule 7: original -> validate -> malware scan -> immutable storage -> OCR -> "
            "extraction -> proposed data -> human review -> confirmed fact with citation. OCR/AI or merge "
            "output must never overwrite canonical data directly.",
        },
        "frontend": {
            "paths": ["frontend/src/*", "frontend/index.html"],
            "focus": "CLAUDE.md rule 9: accessible, responsive, mobile-first UI that handles Indic scripts; "
            "en/hi locale parity; loading, empty, error and 403 states; suggestion lists only from the "
            "master-data service (ADR-0026); relationship words only from the server's kinship packs; "
            "API types only from the generated client.",
        },
    },
    "risk": {
        "minimum_level": "low",
        # High and critical candidates stop at AWAITING_HUMAN until a person attests (factory.py approve).
        "human_review_levels": ["high", "critical"],
        "path_levels": [
            {
                "paths": [
                    "backend/app/authz/*",
                    "backend/app/modules/identity/*",
                    "backend/app/modules/consent/*",
                    "backend/app/modules/public/*",
                    "backend/app/modules/sharing/*",
                    "backend/app/modules/property/*",
                    "backend/app/core/security.py",
                    "backend/app/core/storage.py",
                    "backend/alembic/*",
                    "deploy/*",
                    ".github/*",
                ],
                "level": "high",
            },
            {"paths": ["backend/*", "e2e/*"], "level": "medium"},
        ],
    },
}
REPAIR_REPOSITORY = "ManishPandey21/Vanshavali"
# Changed-test gate (ADR-0030): after the agent, bootstrap_builder.py runs every test file the builder
# added or changed in a fresh controller-provisioned worktree and feeds failures back to it, inside
# the same builder command and attempt. The host checks match CI (.github/workflows/ci.yml).
GATE = REPO / "ops" / "factory" / "changed_test_gate.py"
NODE_MAJOR = 22
MIN_FREE_GB = 5.0
# One builder command covers install, agent, gate and repair rounds; reviewers get the same limit.
TIMEOUT_SECONDS = 5400

# Strict routing (agent_bridge.py --strict-routing): model ids must be pinned, full ids; aliases such
# as "opus" are refused because another variable could remap them. Same pattern as the toolkit's.
FULL_CLAUDE_ID = re.compile(r"claude-(?:[a-z]+(?:-[0-9]+)+|[0-9]+(?:-[0-9]+)*-[a-z]+-[0-9]{8})")
CLAUDE_EFFORTS = ("low", "medium", "high", "xhigh", "max")
CODEX_EFFORTS = ("low", "medium", "high")
# Effort per kind of role, per provider (Codex tops out at "high").
EFFORT = {
    "claude": {
        "builder": "medium",
        "builder_critical": "xhigh",
        "reviewer": "high",
        "reviewer_critical": "max",
        "specialist": "high",
        "risk": "high",
    },
    "codex": {
        "builder": "medium",
        "builder_critical": "high",
        "reviewer": "high",
        "reviewer_critical": "high",
        "specialist": "high",
        "risk": "high",
    },
}


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


def check_model(provider: str, model: str) -> str:
    if provider == "claude" and not FULL_CLAUDE_ID.fullmatch(model):
        sys.exit(f"{model!r} is not a pinned Claude model id (strict routing refuses aliases)")
    if not model.strip() or any(c.isspace() for c in model) or model.startswith("-"):
        sys.exit(f"{model!r} is not an explicit model id")
    return model


def parse_route(text: str) -> tuple[str, tuple[str, str, str]]:
    try:
        role, rest = text.split("=", 1)
        provider, model, effort = rest.split(":")
    except ValueError:
        raise argparse.ArgumentTypeError("--route takes ROLE=PROVIDER:MODEL:EFFORT") from None
    if provider not in ("claude", "codex"):
        raise argparse.ArgumentTypeError("provider must be claude or codex")
    if effort not in (CLAUDE_EFFORTS if provider == "claude" else CODEX_EFFORTS):
        raise argparse.ArgumentTypeError(f"effort {effort!r} is not supported for {provider}")
    return role, (provider, model, effort)


def agent(
    python: str,
    toolkit: Path,
    route: tuple[str, str, str],
    mode: str,
    skill: Path | None = None,
    bootstrap: list[str] | None = None,
    support: dict | None = None,
):
    provider, model, effort = route
    check_model(provider, model)
    # Builders: [python -I bootstrap_builder.py <bootstrap args> --] + the unchanged agent command.
    # Reviewers and the risk assessor get no bootstrap: they read the candidate and cold evidence only.
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
        "model": model,
        "effort": effort,
        "provider": provider,
    }
    if mode == "builder":
        spec["primary_skill"] = str(skill)
        if support:
            spec["support_skills"] = dict(support)
    return spec


def routes(a: argparse.Namespace) -> dict[str, tuple[str, str, str]]:
    """Provider/model/effort for every role. Builders route by the ticket's ``role`` (layer), as before:
    the toolkit falls back to commands[role] because no builder_routine/complex/critical tier is defined."""
    if not a.claude_builder_model:
        sys.exit("--claude-builder-model is required (a pinned Claude model id; no default is assumed)")
    cb = ("claude", a.claude_builder_model)
    cr = ("claude", a.claude_review_model or a.claude_builder_model)
    if a.providers == "mixed":
        if not a.codex_model:
            sys.exit("--codex-model is required with --providers mixed (or pass --providers claude)")
        cx = ("codex", a.codex_model)
        # two lenses on two providers: the reviewers do not share a model's blind spots
        base = {
            "backend": (cx, "builder"),
            "frontend": (cb, "builder"),
            "critical": (cx, "builder_critical"),
            "reviewer_standards": (cx, "reviewer"),
            "reviewer_spec": (cr, "reviewer"),
            "reviewer_standards_critical": (cx, "reviewer_critical"),
            "reviewer_spec_critical": (cr, "reviewer_critical"),
            "risk_assessor": (cx, "risk"),
        }
    else:
        base = {
            "backend": (cb, "builder"),
            "frontend": (cb, "builder"),
            "critical": (cr, "builder_critical"),
            "reviewer_standards": (cr, "reviewer"),
            "reviewer_spec": (cr, "reviewer"),
            "reviewer_standards_critical": (cr, "reviewer_critical"),
            "reviewer_spec_critical": (cr, "reviewer_critical"),
            "risk_assessor": (cr, "risk"),
        }
    for name in REVIEW_POLICY["specialists"]:
        base["reviewer_" + name] = (cr, "specialist")
    out = {role: (pm[0], pm[1], EFFORT[pm[0]][kind]) for role, (pm, kind) in base.items()}
    for role, route in a.route:
        if role not in out:
            sys.exit(f"--route: unknown role {role!r} (one of {', '.join(sorted(out))})")
        out[role] = route
    return out


def builder_skills(a: argparse.Namespace, toolkit: Path) -> tuple[Path, dict, dict | None]:
    """Primary TDD skill (+ optional helper skills from a verified inventory, toolkit 0.4.1)."""
    if bool(a.tdd_skill) == bool(a.skills_inventory):
        sys.exit("give exactly one of --tdd-skill or --skills-inventory")
    if a.tdd_skill:
        skill = a.tdd_skill.expanduser().resolve()
        if not skill.is_file():
            sys.exit("--tdd-skill must point to the installed Superpowers test-driven-development/SKILL.md")
        return skill, {}, None
    sys.path.insert(0, str(toolkit))  # hash-checked above
    from skill_inventory import builder_skills as toolkit_builder_skills

    try:
        inventory = json.loads(a.skills_inventory.expanduser().read_text(encoding="utf-8"))
        skill, helpers = toolkit_builder_skills(inventory)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        sys.exit(f"--skills-inventory: {exc}")
    return Path(skill), dict(helpers), inventory


def state_dir_problems(repo: Path = REPO) -> list[str]:
    """The toolkit keeps builder worktrees in <git-common-dir>/infra-factory/worktrees.

    Claude Code refuses to edit files under a `.git` directory, and since 0.5.0 the toolkit refuses
    any symlink on the path of a cold checkout, so the old "symlink worktrees out of .git" layout
    blocks every ticket. The supported layout is a factory clone with a separate Git directory.
    """
    try:
        out = subprocess.run(  # noqa: S603
            ["git", "-C", str(repo), "rev-parse", "--path-format=absolute", "--git-common-dir"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ["cannot find the Git directory of this checkout"]
    common = Path(out)
    worktrees = common / "infra-factory" / "worktrees"
    problems = []
    if worktrees.is_symlink():
        problems.append(
            f"{worktrees} is a symlink: toolkit 0.5.0 refuses symlinks on cold-checkout paths. "
            "Move to a clone with a separate Git directory (runbook setup step 3)"
        )
    if ".git" in common.resolve().parts:
        problems.append(
            f"the factory state directory {common.resolve()}/infra-factory is inside a `.git` directory, "
            "where Claude builders cannot edit files. Use a clone made with --separate-git-dir "
            "(runbook setup step 3)"
        )
    return problems


def build(a: argparse.Namespace) -> dict:
    toolkit = a.toolkit.expanduser().resolve()
    check_toolkit(toolkit)
    skill, support, inventory = builder_skills(a, toolkit)
    cache = a.cache_dir.expanduser().resolve()
    python = a.python or sys.executable
    for tool in ("git", "uv", "npm", "npx", "node", "tesseract", "claude"):
        if not shutil.which(tool):
            print(f"warning: `{tool}` is not on PATH; the factory will block until it is", file=sys.stderr)
    role_routes = routes(a)
    if any(r[0] == "codex" for r in role_routes.values()) and not shutil.which("codex"):
        sys.exit("`codex` is not on PATH: install/authenticate it, or pass --providers claude")
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
        str(a.repair_rounds),
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

    commands = {}
    for role, route in role_routes.items():
        if role in ("backend", "frontend", "critical"):
            commands[role] = agent(python, toolkit, route, "builder", skill, boot, support)
        else:
            commands[role] = agent(python, toolkit, route, "reviewer")
    # The preflight side is named by a token that is not a repository path: since 0.5.0 the toolkit
    # protects every in-repo path named in a check argv, and a bare "backend" would freeze backend/.
    static = lambda side: [python, "-I", str(RUN_SUITE), "--static", f"{side}-preflight", *extra]  # noqa: E731
    config = {
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
        "review_policy": REVIEW_POLICY,
        "repair_policy": {"max_repairs": 2},
        "commands": commands,
    }
    if any(i <= 0 for i in a.ci_workflow_id):
        sys.exit("--ci-workflow-id must be a positive GitHub Actions workflow id")
    if a.ci_workflow_id:
        config["repair_policy"]["github"] = {
            "repository": REPAIR_REPOSITORY,
            "workflow_ids": a.ci_workflow_id,
        }
    if a.egm:
        config["workflow"] = "egm"
    if inventory is not None:
        config["skill_inventory"] = inventory
    return config


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--toolkit", required=True, type=Path, help="extracted infra-code-factory directory")
    p.add_argument("--tdd-skill", type=Path, help="Superpowers test-driven-development/SKILL.md")
    p.add_argument(
        "--skills-inventory",
        type=Path,
        help="instead of --tdd-skill: a verified Matt/Superpowers skill inventory (toolkit 0.4.1)",
    )
    p.add_argument(
        "--providers",
        choices=("mixed", "claude"),
        default="mixed",
        help="mixed: Codex backend + standards review, Claude frontend + spec review (toolkit default); "
        "claude: Claude for every role",
    )
    p.add_argument("--codex-model", help="pinned Codex model id (required with --providers mixed)")
    p.add_argument("--claude-builder-model", help="pinned Claude model id for builders (required)")
    p.add_argument(
        "--claude-review-model", help="pinned Claude model id for reviewers (default: the builder model)"
    )
    p.add_argument(
        "--route",
        action="append",
        type=parse_route,
        default=[],
        help="override one role, e.g. reviewer_security=claude:MODEL_ID:max (repeatable)",
    )
    p.add_argument(
        "--ci-workflow-id",
        action="append",
        type=int,
        default=[],
        help="numeric id of a GitHub Actions workflow whose failed run may seed `factory.py repair "
        "--source github` (repeatable; e.g. the CI workflow)",
    )
    p.add_argument(
        "--repair-rounds",
        type=int,
        default=1,
        choices=range(3),
        help="times a failing changed-test gate is fed back to the builder within one attempt (default 1)",
    )
    p.add_argument("--egm", action="store_true", help="require approved EGM design handoffs on every ticket")
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
    return p


def main(argv: list[str] | None = None) -> int:
    a = parser().parse_args(argv)
    if "localhost" not in a.pg_admin_url and "127.0.0.1" not in a.pg_admin_url:
        sys.exit("--pg-admin-url must be a local test server: suites DROP and CREATE databases on it")
    problems = state_dir_problems()
    if problems and a.apply:
        sys.exit("refusing to configure this checkout:\n- " + "\n- ".join(problems))
    for problem in problems:
        print(f"warning: {problem}", file=sys.stderr)
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
