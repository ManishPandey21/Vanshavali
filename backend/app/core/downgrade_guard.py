"""Refuse an Alembic downgrade that would widen or discard access (ADR-0027, recovery runbook D4).

Some downgrades cannot keep who may read a record: they map new audiences onto older, wider ones,
delete grants or drop the column that hides a suspended record. A *guard* migration placed above
them calls :func:`refuse_lossy_downgrades` in its ``downgrade()`` before it changes anything. When
the run would go on to execute one of those downgrades and the database holds rows it would affect,
the whole run is refused with counts only (never ids, titles or names). There is no override
switch: roll forward, or restore from backup (docs/operations/tradition-ownership-recovery.md).

A target the guard cannot place exactly (relative ``-1``, ``base``, ``branch@rev``, several
targets, a missing environment) is treated as reaching every guarded downgrade: fail closed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import text

from alembic import op


@dataclass(frozen=True)
class LossyDowngrade:
    """The downgrade of ``revision`` would change who can read or own ``subject``.

    ``losses`` maps a plain description of what would be lost or widened to a ``SELECT count(*)``.
    """

    revision: str
    subject: str
    losses: Mapping[str, str]


def reaches_downgrade(revision: str) -> bool:
    """Will this run go on to execute ``revision``'s ``downgrade()``? Unknown or relative targets: yes."""
    env = op.get_context().environment_context
    if env is None:
        return True
    target = env.get_revision_argument()
    if isinstance(target, tuple):
        target = target[0] if len(target) == 1 else None
    if not isinstance(target, str) or target.startswith(("-", "+")) or "@" in target:
        return True
    try:
        script = env.script
        dest = script.get_revision(target)
        kept = {r.revision for r in script.iterate_revisions("heads", revision, inclusive=True)}
    except Exception:
        return True
    return dest is None or dest.revision not in kept


def refuse_lossy_downgrades(*checks: LossyDowngrade, runbook: str) -> None:
    """Raise before anything changes if a check this run reaches finds affected rows."""
    problems: list[str] = []
    for check in checks:
        if not reaches_downgrade(check.revision):
            continue
        if op.get_context().as_sql:  # offline (--sql): nothing can be counted, so refuse
            problems.append(f"going below {check.revision} cannot be checked in offline (--sql) mode")
            continue
        bind = op.get_bind()
        counts = {what: int(bind.execute(text(sql)).scalar() or 0) for what, sql in check.losses.items()}
        found = "; ".join(f"{n} {what}" for what, n in counts.items() if n)
        if found:
            problems.append(
                f"going below {check.revision} would change who can read or own {check.subject} ({found})"
            )
    if problems:
        raise RuntimeError(
            "lossy downgrade refused: " + ". ".join(problems) + f". Nothing was changed. Follow {runbook}."
        )
