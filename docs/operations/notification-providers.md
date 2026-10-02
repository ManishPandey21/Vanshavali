# Notification providers (reminders)

Design: [ADR-0016](../architecture/adr/0016-reminders-and-notifications.md),
[event-reminder-model.md](../architecture/event-reminder-model.md).

## Status

| Channel | Implemented | Default | Needs |
|---|---|---|---|
| Email | Yes, end to end (existing mailer: console / file / SMTP) | on | SMTP already required in production (email runbook) |
| SMS | Adapter + `mock`; Twilio adapter written against the public REST API, **not yet exercised against the live service** | `disabled` | Twilio account, an Indian sender ID with **DLT registration** (TRAI) and a registered template, or another Indian aggregator (adapter to add) |
| WhatsApp | Adapter + `mock`; Twilio (WhatsApp) and Meta WhatsApp Business Cloud API adapters, **not yet exercised live** | `disabled` | A WhatsApp Business account, a verified sender number, an **approved template** for business-initiated messages |

A disabled channel is not offered in the UI (`GET /notification-channels`) and the API refuses it
(`422 channel_unavailable`).

## Settings (environment / secret manager — never in the repository)

| Variable | Purpose |
|---|---|
| `VSH_SMS_BACKEND` | `disabled` \| `mock` \| `twilio` |
| `VSH_WHATSAPP_BACKEND` | `disabled` \| `mock` \| `twilio` \| `meta` |
| `VSH_NOTIFICATION_OUTBOX_DIR` | `mock` writes JSON here (tests, E2E, demos). Production refuses `mock` |
| `VSH_TWILIO_ACCOUNT_SID`, `VSH_TWILIO_AUTH_TOKEN` | Twilio credentials (**secret**) |
| `VSH_TWILIO_SMS_FROM` | E.164 sender, or a Messaging Service SID (`MG…`, recommended for DLT) |
| `VSH_TWILIO_WHATSAPP_FROM` | WhatsApp-enabled sender (sent as `whatsapp:+…`) |
| `VSH_WHATSAPP_META_TOKEN` | Meta Cloud API access token (**secret**, system user token) |
| `VSH_WHATSAPP_META_PHONE_NUMBER_ID` | Sender phone number id |
| `VSH_WHATSAPP_META_TEMPLATE`, `VSH_WHATSAPP_META_TEMPLATE_LANGUAGE` | Approved template (default `family_reminder`, `en`) |
| `VSH_PROVIDER_TIMEOUT_SECONDS` | HTTP timeout (15) |
| `VSH_REMINDER_GRACE_HOURS` | Missed fires still delivered after downtime (36) |

### WhatsApp template (Meta)
Business-initiated messages must use an approved template. Submit, category **Utility**:

```
Vanshavali: family reminder ({{1}}) {{2}}. Open: {{3}}
```
`{{1}}` = birthday / anniversary / remembrance / event, `{{2}}` = "in 7 days, 12 Mar 2027",
`{{3}}` = link. The verification-code message uses the same mechanism (`{{1}}` = code) — a separate
**Authentication** template is recommended; set its name in a follow-up setting before enabling
phone verification over WhatsApp.

### SMS in India (DLT)
Commercial SMS to Indian numbers must use a DLT-registered entity, header (sender ID) and content
template. Register two templates (reminder, verification code) with the wording in
`app/modules/notifications/service.py` (`_LABELS[...]["short"]` and the code message). Use a Twilio
Messaging Service configured with the DLT entity and template ids, or add an adapter for an Indian
aggregator (MSG91, Gupshup, …): implement `send(OutboundMessage) -> SendResult` in
`app/modules/notifications/channels.py` and register it in `provider_for`.

## Running the scheduler
- Pilot compose: service `reminders` (`python -m app.cli.reminders tick --loop --interval 300`).
- Elsewhere: cron every 5 minutes `python -m app.cli.reminders tick`. Idempotent; safe on two hosts.
- Deliveries run on the normal worker queue (`python -m app.cli.worker`).

## Monitoring
`vsh_events_total{event=~"notification_(sent|retrying|failed|cancelled)"}` in `/metrics`. Alert on a
rising `notification_failed` rate (provider outage or expired credentials). Delivery history per
member: `GET /trees/{t}/notifications`. Logs carry the delivery id, channel, attempt and error code
only — never the address or message.

## Go-live checklist for a provider
1. Credentials in the secret manager; `VSH_*_BACKEND` set; restart API, worker and scheduler.
2. Send yourself a verification code (`POST /me/notification-contacts`) and a test reminder
   ("Send me a test" on the reminders page).
3. Check the provider console shows delivery, and `notification_delivery.status = sent`.
4. Record the provider, DLT/template ids and the date in the release notes.
