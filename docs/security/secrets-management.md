# Secrets management

The pilot topology (ADR-0014) runs on one VM, with secrets in root-owned files
(`/etc/vanshavali/*.env`, mode 600, owned by the deploy user).
- **Source of truth:** the owner's password manager or the cloud secret manager. The VM files are
  copies.
- **Generated on the VM:** `bootstrap-host.sh` generates the data keys, signing key, metrics token
  and app-role password with a CSPRNG.
- **Escrow:** they must be escrowed into the source of truth **immediately**.

Variable details are in `docs/deployment/environment-variables.md`.

## Inventory

| Secret | Where supplied | Who/what uses it | Blast radius if leaked | Escrow |
|---|---|---|---|---|
| `VSH_STANDARD_DATA_KEY` | app.env | backend, worker (encrypt/decrypt STANDARD objects) | With bucket access: read STANDARD documents (photos, letters) | **Mandatory**: offline, two people. Loss = those documents are unrecoverable |
| `VSH_VAULT_DATA_KEY` | app.env | backend, worker (VAULT objects: certificates, property papers, Kundli) | With bucket access: read the most sensitive documents | **Mandatory**, as above, stored separately from the STANDARD key |
| `VSH_SIGNING_KEY` | app.env | backend (download-link tokens) | Forge download links for documents (needs document IDs; links are user-bound and expire in 5 min) | Recommended (can be regenerated) |
| App DB role password (`vanshavali_app`) | app.env URL + migrate.env | backend, worker | Read/write tree data **subject to RLS** (each statement still needs a tree binding) | Regenerable |
| DB owner password | migrate.env (+ the provider's console) | migrate step, backups | Full database: bypasses RLS, DDL | Password manager |
| Managed DB master/admin password | provider console only, **not on the VM** | humans, for break-glass | Full instance | Password manager |
| S3 document-bucket key (`VSH_S3_*`) | app.env | backend, worker | Read/write/delete **ciphertext**; useless without the data keys, but deletion = availability loss (versioning mitigates) | Regenerable |
| Backup-bucket key (`BACKUP_S3_*`) | backup.env | backup.sh, restore.sh | Put/get encrypted dumps (no delete; Object Lock) | Regenerable |
| age **identity** (backup private key) | **offline only** (password manager / sealed envelope), brought to the VM only during a restore | restore.sh | Decrypt every database dump | **Mandatory**; loss = dumps unreadable (PITR still works) |
| `VSH_SMTP_USER` / `VSH_SMTP_PASSWORD` | app.env | worker | Send email as the sender domain (phishing in our name) | Regenerable |
| `VSH_GOOGLE_CLIENT_SECRET` | app.env | backend (OIDC code exchange) | Combined with a stolen code, impersonate the app to Google; cannot sign users in by itself | Regenerable |
| `VSH_METRICS_TOKEN` (+ `metrics_token` file) | app.env, `/etc/vanshavali/metrics_token` | backend, Prometheus | Read operational counters (no personal data) | Regenerable |
| Smoke account password | smoke.env | smoke test | Access to synthetic "Smoke" trees only (dedicated account) | Regenerable |
| GHCR pull token | `~vanshavali/.docker/config.json` | docker pull on the VM | Read the private images (no secrets inside images) | Regenerable |
| Deploy SSH key | GitHub environment secret `DEPLOY_SSH_KEY`; public half in `authorized_keys` with a forced command | deploy workflow | Run `deploy.sh <tag>` (deploy any **published** image tag) | Regenerable |
| Alertmanager SMTP credentials | `/etc/vanshavali/alertmanager.yml` | Alertmanager | Send email | Regenerable |
| `BACKUP_HEARTBEAT_URL` | backup.env | backup.sh | Fake "backup OK" pings (masks a failure) | Regenerable |

**Not secrets:**
- `VSH_GOOGLE_CLIENT_ID`;
- the age **recipient** (public key);
- the domain, bucket names, replica counts.

## Handling rules
1. Never commit secrets.
   - Only `*.env.example` files with `CHANGE_ME` placeholders are tracked.
   - `.env`, `*.env` and `.env.*` are git-ignored.
   - gitleaks scans the history (production-readiness report).
2. Never put a secret on a command line, where `ps` and shell history keep it.
   - The scripts read files or pass environment variables **by name** (`docker run -e PGPASSWORD`).
   - `create_demo_account` reads its password from the environment only.
3. Never log a secret.
   - The app never logs settings.
   - Mail logs mask addresses and redact tokens.
   - `mail_check` prints `password=set`.
   - Access logs carry route templates, not query strings (signed links).
   - Caddy has no access log.
4. **CI never echoes secrets.**
   - The deploy job writes the SSH key to a file with `printf`, uses `BatchMode` and
     `StrictHostKeyChecking=yes`, and deletes the key in an `always()` step.
   - GitHub masks secret values in logs.
   - No workflow runs with `set -x` around secrets.
   - Pull-request workflows receive no deployment secrets: the secrets are **environment**
     secrets, available only to the approved deploy job on `main`.
5. **Development and production never share a secret.**
   - Development uses the built-in dev keys, which production refuses.
   - staging and pilot each have their own keys, buckets, DB roles, SMTP identity, Google client
     and GitHub environment.
   - Never copy pilot data or keys into staging.

## Rotation

| Secret | Procedure | Redeploy/restart needed | Sessions/data impact |
|---|---|---|---|
| Signing key | New value in app.env → `dc up -d backend` | restart backend | Outstanding download links (≤ 5 min) stop working; nothing else |
| App DB role password | New value in migrate.env **and** app.env URL → `dc --profile release run --rm migrate` (ensure_app_role sets it) → `dc up -d backend worker` | restart backend + worker | None (brief reconnect) |
| DB owner password | Change in the provider console → update migrate.env | no (used at release/backup time) | None |
| S3 document key | Create the new key → app.env → `dc up -d backend worker` → delete the old key | restart backend + worker | None |
| Backup bucket key | Create the new key → backup.env → delete the old key | no | None |
| SMTP credentials | Create new → app.env → `dc up -d worker backend` → `mail_check` → revoke old | restart worker (+ backend) | None (failed sends retry) |
| Google client secret | Add a second secret in Google Cloud → app.env → `dc up -d backend` → delete the old secret | restart backend | None (in-flight sign-ins retry) |
| Metrics token | New value in app.env and `metrics_token` → `dc up -d backend` → `dc --profile monitoring restart prometheus` | restart backend + Prometheus | None |
| Smoke password | Change in the UI → smoke.env | no | None |
| Deploy SSH key | Generate → add to authorized_keys (forced command) → update the GitHub secret → remove the old line | no | None |
| age backup key | New pair → recipient in backup.env → escrow the new identity → **keep the old identity** until every dump encrypted to it has expired | no | Old dumps still need the old identity |
| **Data keys (STANDARD / VAULT)** | **Not rotatable in place yet.** Objects carry the key class in their header but not a key version, so a new key cannot read old objects. A re-encryption tool (read with the old key, write with the new) is a planned follow-up (ADR-0004 "key rotation"). Until then: rotate only on compromise, by restoring from the escrow + re-encryption run, and treat compromise of a data key **and** the bucket as a data breach | — | — |

Schedule (pilot):
- quarterly: SMTP, S3 keys, app DB password, metrics token;
- yearly: deploy key;
- immediately: anything that left the VM or a person's custody.

## Revoking compromised credentials (summary; full steps in `docs/operations/incident-response.md`)
1. **Contain:** revoke the credential at its issuer first:
   - DB: `ALTER ROLE … PASSWORD …` (or the console);
   - cloud: delete the access key;
   - SMTP: delete the credentials;
   - Google: delete the client secret;
   - GitHub: delete the environment secret, and the key from `authorized_keys`.
2. **Replace:** issue a new value and restart the users of it (table above).
3. **Assess:**
   - for a DB or bucket credential, review the provider's access logs (S3 server access logs /
     CloudTrail, DB logs) for the exposure window;
   - for an app-level secret, review `audit_event`.
4. **Data-key compromise:** if the bucket was also exposed, this is a personal-data breach.
   Follow the incident runbook (DPDP Act notification).
5. Record it in the incident log; review how it leaked.

## Development vs production
| | Development / tests | Staging | Pilot |
|---|---|---|---|
| Data keys, signing key | built-in dev constants (`config.py`) | own random keys | own random keys, escrowed |
| DB | local superuser for setup; tests use a separate non-owner role | own instance, own roles | own instance, own roles |
| Email | console/file backends | SMTP sandbox or sink | production SMTP |
| Google OAuth | off, or a test client | separate client | separate client |
| Where secrets live | not secret (dev defaults), `.env` (git-ignored) | `/etc/vanshavali` on the staging VM | `/etc/vanshavali` on the pilot VM + escrow |
