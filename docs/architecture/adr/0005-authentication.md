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

## Deferred
TOTP MFA, email verification, password reset and OAuth/OIDC (Phase 8). Password reset needs an email
provider (the current ASSUMPTION is a console outbox).

## Alternatives rejected
JWTs in localStorage (XSS exfiltration, and revocation is hard). Stateless JWT cookies (revocation
needs a denylist anyway).
