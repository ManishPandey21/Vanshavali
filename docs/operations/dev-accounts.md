# Development and test accounts

`python -m app.cli.seed_demo` creates two accounts and the fictional demo tree. It is for local
development, CI and test stacks only and **refuses to run unless `VSH_ENV` is `development` or
`test`** (exit status 2). Pilot, staging and production accounts are never seeded. See
"Pilot/staging accounts" below.

| Account | Role | Trees | First sign-in |
|---|---|---|---|
| `demo@example.com` | Ordinary verified user | `OWNER` of "Iyer Family (demo)" (fictional people) | Signs in directly |
| `superadmin@example.com` | Platform system admin (`is_system_admin`): the master-data console at `/admin/master-data` (ADR-0025) | **None.** A system admin has no implicit tree access (ADR-0006, threat T12) | Must choose a new password (`must_change_password`), then turn on two-step sign-in before the console opens |

## Required environment variables

| Variable | Used for | Rules |
|---|---|---|
| `VSH_DEMO_PASSWORD` | Password of the demo account when it is created | At least 10 characters, not a common password |
| `VSH_SUPERADMIN_PASSWORD` | Initial password of the system admin when it is created | Same rules. It is a temporary password, replaced at first sign-in |

Both must be set or the command exits with status 2 and creates nothing. Passwords are read only
from the environment, never from arguments, defaults or files in the repository. They are stored only
as Argon2 hashes and never printed. Optional flags: `--email` (demo owner, default
`demo@example.com`) and `--admin-email` (default `superadmin@example.com`).

## Commands

Docker Compose (the root `docker-compose.yml`; `VSH_ENV` defaults to `development` there). Export
the passwords in your shell first, then pass them **by name** with `-e` so they stay out of the
command line and shell history:

```bash
read -rs VSH_DEMO_PASSWORD && export VSH_DEMO_PASSWORD
read -rs VSH_SUPERADMIN_PASSWORD && export VSH_SUPERADMIN_PASSWORD
docker compose run --rm -e VSH_DEMO_PASSWORD -e VSH_SUPERADMIN_PASSWORD backend python -m app.cli.seed_demo
```

Without Docker (from `backend/`, after `uv run alembic upgrade head`), with the same two variables
exported:

```bash
make seed     # or: cd backend && uv run python -m app.cli.seed_demo
```

## Behaviour

- **Idempotent.** A second run creates nothing and changes nothing. Existing accounts keep their
  current password (it is not reset to the environment value), and the demo tree is not duplicated.
- **Never promotes.** If `superadmin@example.com` (or `--admin-email`) already belongs to an ordinary
  account, for example one registered through sign-up, the command fails (exit 1) and leaves it
  unchanged. A system-admin account cannot be the demo tree owner.
- **Audited.** Creating the system admin writes a `user.system_admin_seeded` audit event.
- Seeded accounts are created already verified, like the demo account always was. The real sign-up →
  confirmation email → verification → login flow is tested separately with new addresses and no
  seeding: `backend/tests/test_email_auth.py`, including
  `test_signup_confirmation_email_over_smtp_then_verify_and_login`, and the Playwright helpers in
  `e2e/tests/helpers.ts`.
- To reset local accounts, recreate the development database (`docker compose down -v` drops every
  local volume) and seed again.

## Pilot/staging accounts

Not provided by this command, and its environment guard must not be relaxed for them. Real
operator or admin accounts on pilot/staging would need a separate, explicitly authorised
provisioning mechanism, designed in an ADR first (CLAUDE.md rule 2). That mechanism would have
named, per-person accounts instead of a shared `superadmin@`, an approval and audit trail,
one-time invitation links instead of shared passwords, mandatory MFA for system admins, and no
tree access under ADR-0006.
