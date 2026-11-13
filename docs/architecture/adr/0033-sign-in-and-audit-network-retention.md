# ADR-0033: Retention of sign-in records and audit-log network identifiers

- Status: **Accepted** 2026-11-13 (owner decision on both periods). The legal anchors below are
  the team's understanding and are to be confirmed by counsel alongside Q13/Q20.
- Amends: [ADR-0005](0005-authentication.md) (sessions) and the append-only audit trail of the
  initial schema (PRS §34). Related: [privacy model](../../security/privacy-model.md),
  [threat model](../../security/threat-model.md) T68, the public notice at `/privacy`.

## Context

Two tables hold network identifiers (IP address and browser user agent) of identifiable users,
with no deletion schedule:

- `user_session`: one row per sign-in, with `ip` and `user_agent`. Rows are revoked or expire
  (14 days idle, 30 days absolute) but are never deleted.
- `audit_event`: one row per important action, with `ip` and `user_agent`. A database trigger makes
  the table strictly append-only: every `UPDATE` and `DELETE` raises.

The public privacy notice (PR #78) had to say these were "kept without a fixed end date". Data
minimisation (privacy-model principle 5) and the DPDP Act's storage limitation need a period.
Security investigations need the opposite: enough history to trace misuse.

The audit log is two different things in one row:
- **The family's change history.** `action`, `actor_user_id`, `target`, `summary`, `details` and
  `created_at` are shown to tree admins on the tree's audit page and used by features (Smart Add,
  family addresses). Families expect this history to last as long as the tree.
- **Security telemetry.** `ip` and `user_agent` are never returned by any API. They exist only for
  operators investigating misuse.

## Decision

1. **Sign-in records are deleted 365 days after the session ended.** A session ends when it is
   revoked or when its idle or absolute expiry passes, whichever is first. Live sessions are never
   touched. Setting: `VSH_SESSION_RECORD_RETENTION_DAYS` (default and minimum 365).
2. **Audit entries keep their change history. Their IP address and user agent are erased 365 days
   after the event.** Setting: `VSH_AUDIT_NETWORK_RETENTION_DAYS` (default and minimum 365).
3. **The database enforces the audit floor.** The append-only trigger now allows exactly one kind
   of change: setting `ip` and `user_agent` to NULL on a row whose `created_at` is more than 365
   days old, with every other column unchanged. The comparison covers the whole row except those two
   columns (`to_jsonb(NEW) - 'ip' - 'user_agent' = to_jsonb(OLD) - 'ip' - 'user_agent'`), so a column
   added later is protected automatically. `DELETE` stays forbidden. A compromised application role
   therefore still cannot erase the trail of recent activity, rewrite any history, or delete
   entries. Shortening the floor needs a new migration and an ADR amendment, not a setting.
4. **How it runs.** Two idempotent maintenance commands, scheduled daily by the pilot host's cron
   next to the existing document purge:
   - `python -m app.cli.maintenance purge-sign-in-records`
   - `python -m app.cli.maintenance scrub-audit-network`

   The scrub works in batches so a first run over a large table cannot hold long locks. Each run
   prints its count. Neither run is itself audited: an audit row per purge would add network-free
   noise, and the cron log records the counts.
5. **Backups.** Encrypted database backups follow their own rotation (backup-restore runbook). A
   restore brings back rows older than the period until the next daily run removes them again.
   The notice does not promise erasure from backups faster than their rotation.

### Legal anchors (to be confirmed by counsel)

Our understanding is that India's CERT-In directions of 28 April 2022 expect ICT system logs to be
kept for 180 days, and that the Digital Personal Data Protection Rules 2025 expect logs relevant to
detecting unauthorised access to be kept for one year. One year satisfies both as we understand
them. If counsel reads either differently, change the period by amending this ADR (and, for the
audit floor, with a migration).

## Options considered

| Option | Why not chosen |
|---|---|
| Keep everything indefinitely (status quo) | No storage limitation; the notice had to admit it. |
| 180 days for both | Matches CERT-In as we understand it, but may fall short of a one-year log expectation under the DPDP Rules. Owner chose one year. |
| Delete whole audit entries after a period | Destroys the family's change history, which tree admins use and features read. Would need `DELETE` allowed on the audit table, weakening its strongest guarantee. |
| Scrub audit network identifiers with a setting-only floor (no trigger change) | The trigger blocks every `UPDATE`, so the scrub needs a trigger change anyway; enforcing the floor in the database also stops a compromised app role from scrubbing recent rows to cover its tracks. |
| Hash IPs instead of erasing them | A hashed IPv4 address is trivially reversible by enumeration, so it remains personal data. Erasure is simpler and honest. |

## Consequences

- The privacy notice states both periods instead of "no fixed end date".
- The audit page and all features keep working unchanged: they never read `ip` or `user_agent`.
- Investigations of events older than a year have actors and actions but no network identifiers.
- The migration is reversible. Downgrading restores the strict append-only trigger; values already
  erased stay erased (nothing to restore). The downgrade loses no data, so no downgrade guard is
  needed.
- Not in scope: `auth_token` rows (single-use, hashed, expiring within 48 hours) hold no IP or
  browser; they could be purged later for tidiness.
