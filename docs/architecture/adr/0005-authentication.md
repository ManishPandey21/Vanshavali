# ADR-0005: Authentication — server-side sessions

- Status: Accepted · Date: 2026-09-25

## Decision
- Email + password. Hashing is **Argon2id** (`argon2-cffi` defaults). Passwords are at least 10
  characters and are checked against a small built-in list of common passwords.
- **Opaque session tokens** (32 random bytes). Only their SHA-256 is stored in `user_session`
  (user, created, last_seen, expires, ip, user_agent, revoked_at). The cookie `vsh_session` is
  HttpOnly, `SameSite=Lax`, `Secure` when `COOKIE_SECURE=true`, with an idle timeout of 14 days and
  an absolute timeout of 30.
- **CSRF**: a double-submit token. The `vsh_csrf` cookie (readable) must match the
  `X-CSRF-Token` header on POST, PUT, PATCH and DELETE.
- **Revocation**: logout revokes the current session. `POST /auth/sessions/revoke-all` revokes the
  rest. A password change revokes every other session.
- **Rate limiting**: login and registration are limited per IP and per email, using Redis in
  production and an in-memory store in tests.
- Login failures return a generic error (no user enumeration).

## Email verification and password reset (Phase 8, implemented)
- **Mailer** (`app/core/mailer.py`), chosen by `VSH_MAIL_BACKEND`: `console` (logs the message; outside
  development tokens and the recipient are redacted), `file` (writes `.eml` + `.json` into
  `VSH_MAIL_FILE_DIR`; used by tests and E2E) or `smtp` (stdlib `smtplib`, STARTTLS, settings
  `VSH_SMTP_HOST/PORT/USER/PASSWORD`, `VSH_MAIL_FROM`). Production refuses anything but SMTP with
  STARTTLS. Sending always goes through `app.core.jobs.enqueue` (inline in sync mode); a delivery
  failure is logged and never changes the HTTP answer. Emails are plain text + simple HTML with no
  images, tracking pixels or link rewriting, in English or Hindi (`preferred_language`).
- **Tokens** live in `auth_token (id, user_id, purpose, token_hash unique, expires_at, used_at,
  created_at)`: 32 random bytes, only the SHA-256 stored, single use, `verify_email` valid 48 h and
  `password_reset` 1 h. Issuing a token kills the user's earlier unused tokens of the same purpose.
  Tokens never appear in audit details, and the console mailer redacts them outside development.
- **Registration never enumerates** (closes SEC-12): `POST /auth/register` always answers `202` with
  the same body and always hashes the password. A new email gets an *unverified* account and a
  verification link; an existing account's owner instead gets "someone tried to register with your
  email — sign in or reset your password". Nobody is signed in by registering.
- `POST /auth/verify-email {token}` sets `app_user.email_verified_at` and starts a session.
  `POST /auth/resend-verification {email}` is generic (202) and rate limited (10/min per IP,
  3/h per email). The link may carry a same-site `?next=` path (e.g. an invitation) chosen at
  registration.
- **Unverified accounts cannot sign in**: login answers `403 email_not_verified` only *after* the
  correct password, so it reveals nothing to someone guessing. Sessions of unverified users are not
  honoured, and accepting an invitation requires a verified email.
- **Password reset**: `POST /auth/password-reset/request {email}` is always `202` (10/min per IP,
  5/h per email) and mails a link only to an active account. `POST /auth/password-reset/confirm
  {token, new_password}` applies the password rules, sets the password, marks the email verified
  (the link proves mailbox control), revokes **every** session, marks the token used and audits
  `user.password_reset`. MFA still applies at the next sign-in. A password change (or reset) kills
  outstanding reset links (they are marked used, and a token older than `password_changed_at` is
  refused).
- Existing users were backfilled as verified (`email_verified_at = created_at`) by the migration.

Residual: with `JOB_MODE=sync` + SMTP, a reset request for a real account takes longer than for an
unknown one (the send is inline). Production uses RQ, where both paths only enqueue. An attacker who
pre-registers a victim's address cannot sign in while it is unverified; if the victim later tries to
register they get the "account exists" notice and a reset replaces the attacker's password. The
remaining pre-hijack case — the victim clicks a verification link for an account they never asked
for — is mitigated only by the email's "if you did not create an account, ignore this" wording.

## Deferred
OAuth/OIDC — now decided in [ADR-0012](0012-google-sign-in.md) (Sign in with Google).

## Alternatives rejected
JWTs in localStorage (XSS exfiltration, and revocation is hard). Stateless JWT cookies (revocation
needs a denylist anyway).
