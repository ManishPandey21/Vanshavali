# ADR-0012: Sign in with Google (OpenID Connect) and forced password change

- Status: Accepted · Date: 2026-09-26
- Amends: ADR-0005 (which deferred OAuth/OIDC)

## Context
Many families already have a Google (gmail.com) account and find passwords a barrier, especially
elders who are invited by a relative. ADR-0005 deferred OAuth/OIDC. We also need a safe way to hand
out a development/demo account with a temporary password.

## Decision

### Sign in with Google
- **Protocol**: OpenID Connect authorization-code flow with **PKCE (S256)**, run entirely by the
  backend. The browser never sees an access or ID token; the result is an ordinary Vanshavali session
  (ADR-0005: opaque cookie, CSRF double-submit, same timeouts and revocation).
- **Off by default.** Enabled only when `VSH_GOOGLE_CLIENT_ID` and `VSH_GOOGLE_CLIENT_SECRET` are set.
  `GET /auth/providers` tells the SPA whether to show the button; the Google routes answer `404` when
  disabled. The redirect URI defaults to `<public_base_url>/api/v1/auth/google/callback` and must use
  `https` in production.
- **Start** — `GET /auth/google/start?next=/path`: creates `state` (32 random bytes), `nonce`
  (32 bytes) and a PKCE verifier, stores them with the sanitised `next` path and an expiry (10 min) in
  a short-lived cookie `vsh_oidc` that is **HMAC-signed with `VSH_SIGNING_KEY`**, HttpOnly,
  `SameSite=Lax`, `Secure` as configured, scoped to the Google callback path; then redirects to
  Google with `scope=openid email profile` and `prompt=select_account`.
- **Callback** — `GET /auth/google/callback?code&state`: refuses unless the cookie is present,
  untampered, unexpired and its `state` matches (constant-time). The cookie is deleted either way
  (single use). The code is exchanged at Google's token endpoint over TLS with the client secret and
  the PKCE verifier. The ID token received from that **back channel** is validated for `iss`
  (`https://accounts.google.com` / `accounts.google.com`), `aud == client_id`, `exp`/`iat`, and
  `nonce`. Its signature is not re-verified: OIDC Core §3.1.3.7(6) allows TLS server authentication of
  the token endpoint instead, and this keeps us free of a JWT library.
- **Account resolution** (in order):
  1. A linked `external_identity (provider='google', subject=sub)` → that account.
  2. Otherwise an account with the same email is linked **only if** Google says `email_verified`
     **and** Google is authoritative for the address (`@gmail.com` / `@googlemail.com`, or a Google
     Workspace `hd` claim). Other addresses must sign in with their password; linking them is future
     work from Account settings.
     - If that account was **unverified** (the pre-registration hijack case in ADR-0005), linking
       marks it verified, **replaces its password with a random one** (a reset link restores
       password sign-in) and revokes every session. So a squatter's password stops working.
     - Accounts with **two-step verification** cannot use Google sign-in yet (it would bypass TOTP).
       They get an explicit error and continue with password + code.
  3. Otherwise a **new account** is created: verified email, display name from `name`, language
     `hi` if the Google locale is Hindi, and a random unusable password (the user may set one via
     "Forgot password").
- **Identity table** `external_identity (user_id, provider, subject, email_at_link, created_at,
  last_used_at)`, unique on `(provider, subject)`. Accounts are matched by `sub`, never by email
  after the first link, so a later change of email at Google does not move the login.
- **Redirects**: success goes to the stored `next` (same-origin path only, same rules as the SPA's
  `safeNext`) or `/`. Every failure goes to `/login?oauth_error=<code>` with a short code and no
  token or claim data. Codes: `oauth_failed`, `oauth_state`, `email_unverified`, `link_requires_password`,
  `mfa_enabled`, `account_inactive`.
- **Rate limits**: start 20/min per IP; callback 20/min per IP.
- **Audit**: `user.login` (details `method: google`), `user.external_identity_linked`,
  `user.registered` (details `method: google`), `user.oauth_failed` (reason code only).
- **Privacy**: we keep only `sub` and the email at link time. We do not store Google tokens, profile
  photo, or anything beyond the name and email used to create the account.

### Forced password change
- `app_user.must_change_password` (default false). While it is set, every authenticated endpoint
  answers `403 password_change_required` except `POST /auth/password` and `POST /auth/logout`;
  `GET /auth/me` reports the flag so the SPA can show the change-password screen. The server is the
  authority; the SPA screen is only a convenience.
- A forced change must choose a password different from the temporary one. A successful change or a
  password reset clears the flag. The flag also applies after Google sign-in, because the temporary
  password stays valid until replaced.
- **Demo accounts** are created only by `python -m app.cli.create_demo_account`, which refuses unless
  `VSH_ENV` is `development` or `test`. It reads the password only from `VSH_DEMO_ACCOUNT_PASSWORD`
  (never a CLI argument), stores only the Argon2 hash, never prints it, and sets
  `must_change_password`. No credential lives in source, seed files, fixtures or docs.
- The dev/test seed (`python -m app.cli.seed_demo`, `docs/operations/dev-accounts.md`) follows the
  same rules: the same environment guard, passwords only from `VSH_DEMO_PASSWORD` and
  `VSH_SUPERADMIN_PASSWORD`, and `must_change_password` on the seeded system admin.

## Stress test (questions we asked ourselves)
- *Can an attacker log in as someone by owning a Google account with their email?* Only for addresses
  where Google is the mailbox provider (Gmail/Workspace) and says the email is verified — i.e. the
  attacker would already own the mailbox and could reset the password anyway.
- *Login CSRF (attacker makes the victim's browser finish the attacker's Google login)?* The
  callback requires the signed `state` cookie set by *this* browser's `/start`; an injected callback
  URL has no matching cookie.
- *Code interception / replay?* PKCE binds the code to the verifier in our cookie; the state cookie is
  single use and expires in 10 minutes.
- *Open redirect via `next`?* Sanitised to a same-origin path at `/start`, and signed inside the
  cookie so it cannot be swapped at the callback.
- *Does Google sign-in weaken MFA?* It is refused for MFA-enabled accounts until we design a
  step-up.
- *What if Google is unreachable or returns junk?* The exchange has a timeout. Any failure becomes
  `oauth_failed`, is audited, and never creates or links an account.

## Consequences
- New settings, one table and one column (migration `d5f2a9c1e7b3`, with downgrade).
- Operators must register the redirect URI in Google Cloud Console and keep the client secret in the
  secret manager.
- Residual: an account created by Google has a random password. If the user loses the Google account,
  "Forgot password" restores access through the same mailbox.

## Alternatives rejected
- **Front-channel Google Identity Services (JS button + ID token posted to us)**: needs JWT signature
  verification against Google's JWKS, and puts tokens in the browser.
- **Linking by email for any Google-verified address**: Google may have verified a non-Google mailbox
  long ago; for those we require the password first.
- **Storing OIDC state in the database**: the signed cookie is enough, needs no cleanup, and binds
  the flow to the browser that started it.
