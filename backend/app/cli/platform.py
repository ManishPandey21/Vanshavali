"""Grant and revoke platform capabilities (ADR-0028 §7). Run on the server as the schema owner.

    uv run python -m app.cli.platform grant EMAIL --capability master_data.admin \
        --name "Full Name" --reason "why" --operator "who is running this"
    uv run python -m app.cli.platform revoke EMAIL --capability master_data.admin \
        --reason "why" --operator "who is running this"
    uv run python -m app.cli.platform list [--all]

``platform_capability_grant`` is read-only to the application role, so these commands need the owner
connection (the pilot ``migrate`` service's ``VSH_DATABASE_URL``); with the application role they
fail with "permission denied". A capability goes to one named person only: the account needs a
verified email and two-step sign-in, and role mailboxes (admin@, ops@, …) are refused.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy.exc import ProgrammingError

from app.core.db import get_sessionmaker
from app.models import PlatformCapability
from app.modules.platform import service
from app.modules.platform.service import GrantRefused

CAPABILITIES = [c.value for c in PlatformCapability]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli.platform")
    sub = parser.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grant", help="give a named person a platform capability")
    g.add_argument("email")
    g.add_argument("--capability", required=True, choices=CAPABILITIES)
    g.add_argument("--name", required=True, help="the holder's full name (one person per account)")
    g.add_argument("--reason", required=True)
    g.add_argument("--operator", required=True, help="your own name, recorded with the grant")
    r = sub.add_parser("revoke", help="take a platform capability away")
    r.add_argument("email")
    r.add_argument("--capability", required=True, choices=CAPABILITIES)
    r.add_argument("--reason", required=True)
    r.add_argument("--operator", required=True)
    ls = sub.add_parser("list", help="current holders")
    ls.add_argument("--all", action="store_true", help="include revoked grants")
    args = parser.parse_args(argv)

    with get_sessionmaker()() as db:
        try:
            if args.cmd == "grant":
                service.grant(
                    db,
                    email=args.email,
                    capability=PlatformCapability(args.capability),
                    holder_name=args.name,
                    reason=args.reason,
                    operator=args.operator,
                )
                db.commit()
                print(f"granted {args.capability} to {args.email}")
            elif args.cmd == "revoke":
                service.revoke(
                    db,
                    email=args.email,
                    capability=PlatformCapability(args.capability),
                    reason=args.reason,
                    operator=args.operator,
                )
                db.commit()
                print(f"revoked {args.capability} from {args.email}")
            else:
                rows = service.list_grants(db, include_revoked=args.all)
                for row in rows:
                    state = f"revoked {row.revoked_at:%Y-%m-%d}" if row.revoked_at else "active"
                    print(
                        f"{row.capability}\t{row.email}\t{row.holder_name}\t"
                        f"granted {row.granted_at:%Y-%m-%d} by {row.granted_by}\t{state}"
                    )
                print(f"{len(rows)} grant(s)")
        except GrantRefused as e:
            db.rollback()
            print(f"refused: {e}", file=sys.stderr)
            return 2
        except ProgrammingError as e:
            db.rollback()
            if "permission denied" not in str(e):
                raise
            print(
                "refused: permission denied. Run this with the schema owner's database URL "
                "(the application role cannot write capability grants).",
                file=sys.stderr,
            )
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
