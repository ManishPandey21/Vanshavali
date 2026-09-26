"""Create a verified demo account with a temporary password (development and test only).

Usage:
    VSH_DEMO_ACCOUNT_PASSWORD=... uv run python -m app.cli.create_demo_account \\
        --email someone@example.com --name "Display Name" [--language hi]

The password is read only from ``VSH_DEMO_ACCOUNT_PASSWORD`` (never a command-line argument, so it
stays out of shell history and process listings), stored only as an Argon2 hash, and never printed.
The account must replace it on first sign-in (``must_change_password``). The command refuses to run
unless ``VSH_ENV`` is ``development`` or ``test``. No family tree is created.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

from sqlalchemy import select

from app.core import audit
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.security import hash_password, password_problems
from app.models import User
from app.modules.identity.service import normalise_email

PASSWORD_ENV = "VSH_DEMO_ACCOUNT_PASSWORD"  # noqa: S105 - name of an environment variable, not a secret
ALLOWED_ENVS = ("development", "test")


def create(email: str, name: str, language: str, password: str) -> User:
    env = get_settings().env
    if env not in ALLOWED_ENVS:
        raise RuntimeError(
            f"demo accounts can only be created when VSH_ENV is development or test (it is {env})"
        )
    problems = password_problems(password)
    if problems:
        raise ValueError("; ".join(problems))
    email = normalise_email(email)
    with get_sessionmaker()() as db:
        if db.scalar(select(User).where(User.email == email)) is not None:
            raise ValueError(f"an account already exists for {email}")
        now = dt.datetime.now(dt.UTC)
        user = User(
            email=email,
            password_hash=hash_password(password),
            display_name=name.strip(),
            preferred_language=language,
            email_verified_at=now,
            must_change_password=True,
        )
        db.add(user)
        db.flush()
        audit.record(
            db,
            action="user.demo_account_created",
            actor_user_id=None,
            target_type="user",
            target_id=user.id,
            details={"env": env},
        )
        db.commit()
        return user


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--language", default="en", choices=["en", "hi"])
    args = parser.parse_args(argv)
    password = os.environ.get(PASSWORD_ENV, "")
    if not password:
        print(f"{PASSWORD_ENV} must be set", file=sys.stderr)
        return 2
    try:
        user = create(args.email, args.name, args.language, password)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 2
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"created verified demo account {user.email}; a new password is required at first sign-in")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
