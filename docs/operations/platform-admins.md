# Platform administrators (master-data console)

ADR-0028 §7, increment 1. A **platform capability** lets one named person use an administration
surface outside any family tree. Today there is one: `master_data.admin`, for the master-data
console (`/admin/master-data`). It gives **no** access to any family tree.

## Rules
- **Named people only.** One person per account. Role or shared mailboxes (`admin@`, `ops@`,
  `support@`, … see `VSH_PLATFORM_MAILBOX_DENYLIST`) are refused. Never share the credentials.
- **The account must already have** a verified email and two-step sign-in (authenticator app).
- **Only this CLI grants or revokes,** as the schema owner. The application role can read the grants
  but cannot write them, so nothing reachable from the web can grant a capability.
- **`is_system_admin` is not a capability.** The demo seeder never grants one.
- Every grant and revocation is audited (`platform.capability_granted` / `…_revoked`, no tree).

## Granting and revoking
Run with the **schema owner's** database URL. On the pilot that is the `migrate` service's
environment (`migrate.env`):

```bash
dc run --rm migrate python -m app.cli.platform grant asha.rao@example.org \
  --capability master_data.admin --name "Asha Rao" \
  --reason "Pilot master-data curator" --operator "Your Name"
```

```bash
dc run --rm migrate python -m app.cli.platform revoke asha.rao@example.org \
  --capability master_data.admin --reason "Left the project" --operator "Your Name"
```

```bash
dc run --rm migrate python -m app.cli.platform list --all
```

With the application's own URL the commands stop with "permission denied"; that is intended.

## Signing in to the console
- The console is **off** until `VSH_MASTERDATA_CONSOLE_ENABLED=true`. Leave it off until two named
  administrators hold the capability (go-live checklist): publication will need a second
  administrator's approval (ADR-0028 §4).
- A holder must sign in with **password + authenticator code**. Email-link and Google sessions never
  qualify. A qualifying session lasts 12 hours (`VSH_PLATFORM_SESSION_MFA_MAX_AGE_HOURS`).
- Turning two-step sign-in off removes access at once. After turning it on again, sign in again:
  older sessions no longer qualify.
- Every change will also need a fresh code (step-up, `POST /api/v1/auth/step-up`), valid for 15
  minutes (`VSH_PLATFORM_STEP_UP_MAX_AGE_MINUTES`).
- Revoking a grant, closing the account, or a password change or reset ends access on the next
  request.
