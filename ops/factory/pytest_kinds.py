"""pytest plugin: partition the backend suite into the factory's test kinds (ADR-0029).

Loaded only by ``ops/factory/run_suite.py`` (``-p pytest_kinds --factory-kind=KIND``); the
normal ``uv run pytest`` and CI are unaffected. Every collected test is assigned exactly one kind,
from what the test actually touches, so new test files are classified automatically:

    migration    the test drives Alembic itself (``command.upgrade``/``downgrade``, drift checks)
    api          the test requests the ``app`` fixture, i.e. goes through the HTTP API
                 (``client``, ``owner``, ``tree``, ``member_factory``... all depend on it)
    integration  otherwise touches the database directly (owner sessions, engines, raw SQL)
    unit         everything else: pure functions and in-memory logic

The four partitions are disjoint and together cover the whole suite, so running all four runs
every test once. Tests of other kinds are *deselected* (absent from the JUnit report), never
skipped. Classification is a trusted project input, not proof of what a test asserts.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

KINDS = ("unit", "api", "integration", "migration")
MIGRATION_MARKERS = ("command.upgrade", "command.downgrade", "compare_metadata", "alembic")
DB_MARKERS = (
    "owner_session",
    "get_engine",
    "create_engine",
    "sessionmaker",
    "Session(",
    "_owner_engine",
    "text(",
    "SessionLocal",
)


def pytest_addoption(parser: Any) -> None:
    parser.addoption("--factory-kind", choices=KINDS, help="run only tests of this factory kind")


def _source(obj: Any) -> str:
    try:
        return inspect.getsource(obj)
    except (OSError, TypeError):
        return ""


def kind_of(item: Any) -> str:
    module = getattr(item, "module", None)
    sources = [_source(getattr(item, "obj", None))]
    if any(marker in sources[0] for marker in MIGRATION_MARKERS):
        return "migration"
    if "app" in getattr(item, "fixturenames", ()):
        return "api"
    # fixtures defined next to the test (not the shared conftest harness) count as part of it
    for name in getattr(item, "fixturenames", ()):
        for fixturedef in item._fixtureinfo.name2fixturedefs.get(name, ()):
            func = getattr(fixturedef, "func", None)
            if func is not None and getattr(func, "__module__", "") == getattr(module, "__name__", None):
                sources.append(_source(func))
    if any(marker in src for src in sources for marker in DB_MARKERS):
        return "integration"
    return "unit"


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    wanted = config.getoption("--factory-kind")
    if not wanted:
        return
    keep, drop = [], []
    counts = dict.fromkeys(KINDS, 0)
    for item in items:
        kind = kind_of(item)
        counts[kind] += 1
        (keep if kind == wanted else drop).append(item)
    if drop:
        config.hook.pytest_deselected(items=drop)
        items[:] = keep
    summary = ", ".join(f"{k}={v}" for k, v in counts.items())
    config.stash[_SUMMARY] = f"factory kinds: {summary}; running {wanted}"


_SUMMARY = pytest.StashKey[str]()


def pytest_report_collectionfinish(config: Any) -> str | None:
    return config.stash.get(_SUMMARY, None)
