# ADR-0016: Event reminders and notification delivery (email, SMS, WhatsApp)

- Status: Accepted · Date: 2026-10-02
- Relates to: ADR-0005 (mailer), ADR-0006 (privacy), ADR-0015 (life events)
- Detail: [event-reminder-model.md](../event-reminder-model.md),
  [notification-providers.md](../../operations/notification-providers.md)

## Context
Members want to be reminded of birthdays, wedding anniversaries, death anniversaries (punyatithi,
barsi) and other dates, by email and, in India especially, by SMS or WhatsApp. Reminders send
family data out of the system, to inboxes and through third-party messaging providers.

## Decision
1. **Per-user, opt-in subscriptions.** A reminder (`event_reminder`) belongs to the member who
   created it and is visible only to them (other members, admins included, get 404). Nobody can
   subscribe someone else. The first reminder a member sets in a tree creates their
   `notification_preference` with sending enabled (that action is the opt-in); turning
   preferences off pauses every reminder in the tree.
2. **Visible dates only.** A reminder needs the event's Gregorian day and month *as the member sees
   them*. A living relative's birthday whose full date is hidden from the member cannot be
   subscribed (`date_hidden` / `date_incomplete`). One-time reminders need a full future date.
   Lunar (tithi) anniversaries are deferred.
3. **Re-check at send time.** Each delivery is evaluated as the recipient when it is sent: still a
   member, preferences enabled, event and full date still visible, contact still verified.
   Otherwise the delivery is `cancelled` with a reason. Revoking access stops reminders at once.
4. **Scheduling.** `next_fire_at` (UTC) is computed from the occurrence, the lead days (0–365, up
   to six) and the member's send hour in their IANA time zone. A scheduler tick
   (`python -m app.cli.reminders tick`, every 5 minutes) materialises due deliveries idempotently
   (unique per reminder, channel, occurrence date and lead), then enqueues one job per delivery.
   Missed fires within `VSH_REMINDER_GRACE_HOURS` (36 h) are still delivered after downtime.
5. **Delivery records, not messages.** `notification_delivery` keeps status (`pending`, `sent`,
   `retrying`, `failed`, `cancelled`), attempts, next attempt, a short error code, provider and
   provider message id. It never stores the message text or the address.
6. **Retries.** Retryable provider errors (network, 429, 5xx) back off 2 min, 15 min, 1 h; the
   fourth failure is final. Non-retryable errors (bad number, unapproved template, disabled
   channel) fail at once.
7. **Channels behind adapters.** Email uses the existing mailer backends synchronously inside the
   delivery job. SMS and WhatsApp use adapters: `mock` (JSON outbox; tests and demos, refused in
   production), `twilio` (SMS and WhatsApp), `meta` (WhatsApp Business Cloud API with an approved
   template). Credentials only from the environment / secret manager.
8. **Minimal third-party content.** SMS and WhatsApp texts carry the kind of reminder, the date and
   a link — no names, places or notes. Email (to the member's verified account address) may carry
   the event label, place and the member's private note.
9. **Phone numbers.** `notification_contact` is user-level (not tree data): AES-GCM encrypted with
   the SYSTEM key, masked in every response, verified with a 6-digit code (HMAC-hashed, 10 min,
   5 attempts, 5 codes per hour) before use.

## Consequences
- New tables: `event_reminder`, `notification_preference`, `notification_delivery` (tree-scoped,
  RLS) and `notification_contact` (identity table, service-layer protected).
- Operations must run the scheduler (pilot compose service `reminders`) and, for SMS/WhatsApp,
  configure a provider (sender ID / DLT registration for India, WhatsApp template approval).

## Alternatives considered
- **RQ scheduled jobs per reminder**: jobs would hold stale decisions (privacy, preferences) and be
  hard to reschedule; a periodic tick over indexed `next_fire_at` is simpler and idempotent.
- **Admins subscribing members**: violates opt-in; rejected.
- **Storing rendered messages for audit**: would duplicate personal data in logs; rejected.
