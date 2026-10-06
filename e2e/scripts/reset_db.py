"""Drop and recreate the dedicated E2E database, then migrate it to head.

Run with the backend's environment:  uv run --project ../backend python scripts/reset_db.py
Env:
  VSH_E2E_ADMIN_URL  admin connection (default postgresql+psycopg://vanshavali:vanshavali@localhost:5432/postgres)
  VSH_E2E_DB         database name (default vsh_e2e)
  VSH_E2E_APP_ROLE   non-owner role the backend connects as, so RLS applies (default vsh_app_e2e;
                     its password equals its name - test-only)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

admin_url = os.environ.get(
    "VSH_E2E_ADMIN_URL", "postgresql+psycopg://vanshavali:vanshavali@localhost:5432/postgres"
)
db_name = os.environ.get("VSH_E2E_DB", "vsh_e2e")
if not db_name.replace("_", "").isalnum():
    sys.exit("refusing unsafe database name")

engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
with engine.connect() as conn:
    conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
    owner = make_url(admin_url).username
    conn.execute(text(f'CREATE DATABASE "{db_name}" OWNER "{owner}"'))
engine.dispose()

target = make_url(admin_url).set(database=db_name).render_as_string(hide_password=False)
backend = Path(__file__).resolve().parents[2] / "backend"
env = {**os.environ, "VSH_DATABASE_URL": target}
subprocess.run(["uv", "run", "alembic", "upgrade", "head"], cwd=backend, env=env, check=True)
subprocess.run(["uv", "run", "python", "-m", "app.cli.load_vocabularies"], cwd=backend, env=env, check=True)
app_role = os.environ.get("VSH_E2E_APP_ROLE", "vsh_app_e2e")
role_env = {**env, "VSH_APP_DB_ROLE": app_role, "VSH_APP_DB_PASSWORD": app_role}
subprocess.run(["uv", "run", "python", "-m", "app.cli.ensure_app_role"], cwd=backend, env=role_env, check=True)
print(f"E2E database {db_name} ready")
