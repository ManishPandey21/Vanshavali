# ADR-0032: Anonymous landing-page visitor estimate with a first-party cookie

- Status: **Proposed** · Date: 2026-11-12
- Scope: the optional `unique_visitors_30d` figure of `GET /api/v1/public/site-impact` and its
  `vsh_impact_visitor` cookie (PR #78). The family-tree count on the same endpoint is an aggregate of
  existing rows, sets nothing on the browser and is **not** governed by this ADR.
- Related: [ADR-0005](0005-authentication.md) (cookie conventions), [ADR-0014](0014-pilot-hosting.md)
  (Redis on the pilot VM), [privacy model](../../security/privacy-model.md),
  [threat model](../../security/threat-model.md) `LP-*`,
  [design note](../landing-impact-and-support.md), [open question Q20](../open-questions.md).

## Context

The landing page shows a "community at a glance" panel. The product owner wants to show
how many people the site reaches as well as how many family trees exist.

Until now Vanshavali has measured nothing about visitors. It has no analytics script. The pilot edge
(Caddy) keeps no access log. Operational logs record route templates only, never cookies, headers or
query strings (T18, T31). The only cookies are the session and CSRF cookies needed to sign in
(ADR-0005). The privacy model's principles are data minimisation and least visibility. Under the
DPDP Act 2023 the platform is a Data Fiduciary.

A "distinct visitors over the last 30 days" figure cannot be computed without *something* that
recognises the same browser on different days. Whatever that is, it is a new kind of data about
people who have not signed up and may never sign up, possibly including minors. That makes it a
privacy decision, which CLAUDE.md rule 2 says needs an ADR before code. PR #78 contains the code,
switched off. This ADR records the decision it implements and the conditions for switching it on.

## Decision

1. **Off by default.** `VSH_VISITOR_STATS_ENABLED=false`. While it is off, the endpoint sets no
   cookie, writes nothing to Redis and returns `unique_visitors_30d: null`. The landing page then
   hides the figure. Enabling it is a deployment decision that needs the activation conditions
   in §Activation.
2. **Identifier.** The server issues a random 192-bit token (`secrets.token_urlsafe(24)`), signed
   with HMAC-SHA256 under `VSH_SIGNING_KEY`, in a first-party cookie with these properties:
   - `vsh_impact_visitor`, `HttpOnly`, `SameSite=Lax`;
   - `Secure` when `VSH_COOKIE_SECURE` (as ADR-0005);
   - `Path=/api/v1/public`, `Max-Age` 90 days.

   The token carries no information. It is not derived from IP, user agent, account or time. A
   cookie with a missing or invalid signature is replaced, never trusted.
3. **What is stored.** Only `HMAC-SHA256(signing_key, "impact:" + token)` is added to a Redis
   HyperLogLog bucket per UTC day (`vsh:impact:unique:YYYY-MM-DD`). Each bucket expires 35 days after
   its last write. HyperLogLog keeps register maxima, not members, so the digests cannot be listed
   or read back. The figure is `PFCOUNT` over the last 30 buckets, roughly ±0.81 % standard error.
   Nothing else about the visit is stored: no IP, user agent, referrer, path, account, tree or
   timestamp per visitor.
4. **Never linked to an account.** The handler does not read the session cookie or any user or tree
   identifier, and must not start doing so. A signed-in user's browser is counted exactly like an
   anonymous one. Joining this token to an account, or reusing it for any other purpose
   (personalisation, attribution, marketing, security decisions), needs a new ADR.
5. **Browser privacy signals win.** A request with `Sec-GPC: 1` or `DNT: 1` is not counted and gets
   no cookie. It still receives the aggregate figures.
6. **Inflation control.** At most 20 *new* browsers are counted per client address per hour. This
   uses the shared rate limiter (`VSH_RATE_LIMIT_BACKEND=redis` in production). The address is used
   only as that limiter's key, which expires with its one-hour window. It is never stored with the
   digest. Returning browsers with a valid cookie are not limited.
7. **Honest presentation.** The UI calls the figure "unique visiting browsers · last 30 days", never
   people or users. It explains that browsers, devices, private windows and cleared cookies count
   separately, and that bots may affect it. It hides the figure when it is `null` (off or Redis
   unavailable) rather than showing a dash or a zero. The figure is not used in investor,
   donor or press material as "unique users" without that qualification.
8. **Failure.** Redis or limiter errors make the figure `null`. They never break the landing page
   or produce a false zero. Responses are `Cache-Control: no-store`, so no shared cache replays a
   `Set-Cookie`.

### Lawful basis and notice

We treat the token as **personal data**. It is pseudonymous and has no link to a name. But the DPDP
Act's test is whether an individual is identifiable "by or in relation to" the data, and the browser
that carries it usually belongs to one person. We do not rely on it being anonymous. The intended
basis is a clear notice plus easy refusal (the GPC/DNT signals, deleting the cookie, or simply
leaving it off). No consent banner is planned, because no data leaves first-party storage, the
purpose is a single aggregate, and there is no profiling or sharing. **Counsel must confirm this
basis before activation** (Q20). If counsel requires prior consent, the measurement stays off or
moves to option F below.

## Activation

All of these, recorded in the release checklist, before `VSH_VISITOR_STATS_ENABLED=true` anywhere
real visitors reach:

1. A public privacy notice, in English and Hindi and linked from the landing page footer, describes:
   - the cookie: name, purpose, 90-day lifetime, path;
   - the 35-day aggregate retention;
   - the GPC/DNT behaviour and how to delete the cookie.

   The page exists at `/privacy` (`frontend/src/pages/public/PrivacyPage.tsx`) and covers all of
   this. Before activation it still needs:
   - counsel's review of the wording, in both languages;
   - `VITE_PRIVACY_CONTACT_EMAIL` set to a monitored mailbox.
2. Counsel's view on the lawful basis (Q20), and product-owner approval of this ADR.
3. `VSH_RATE_LIMIT_BACKEND=redis` in that environment. Per-process memory limiting would multiply
   the inflation cap by the number of backend replicas.
4. A review date 90 days after activation. If nobody uses the figure, switch it off.

**Switching off** is immediate and complete:
- Set the flag to `false`. New cookies stop at once.
- Existing cookies are never read again and expire in the browser within 90 days.
- Delete `vsh:impact:unique:*` for immediate erasure, or let the buckets expire within 35 days.

## Options considered

| Option | Why not chosen |
|---|---|
| A. **No visitor figure**: show only the family-tree count | Zero privacy cost, and the default until activation. Rejected as the *only* option because the owner wants a reach figure; it remains the fallback if any activation condition fails. |
| B. Count IP addresses (or IP + user agent) from access logs | Stores network identifiers of non-users. Contradicts the "no access log" control (T18). NAT and mobile networks make it inaccurate in both directions. |
| C. Third-party analytics (hosted Google Analytics, Plausible, etc.) | Sends every visitor's request data to a third party. Adds a third-party script and CSP exceptions. Collects far more than one number. Data residency (Q12). |
| D. Self-hosted analytics product (Umami, self-hosted Plausible) | A new service to run, patch and back up, for one number. These products collect page paths, referrers and devices by default. Their cookie-less mode hashes IP + user agent with a daily salt, which cannot deduplicate across 30 days and still processes the IP for every visit. |
| E. **Random signed first-party cookie + HMAC + HyperLogLog (chosen)** | One opaque token, one aggregate, nothing retrievable per visitor, short retention, off by default, honours browser signals. |
| F. Cookie-less client flag: the browser keeps "last counted" in `localStorage` and the server just increments a daily counter when told "not counted in 30 days" | The most private option: the server never receives any identifier. Not chosen because the server cannot deduplicate or verify it, so a single request can inflate it. A rolling 30-day distinct count is not possible from daily increments (a browser seen on day 1 and day 20 counts twice unless the client reports precisely). The figure would also differ from the cookie version only in where the marker lives. **Kept as the fallback if counsel requires prior consent for the cookie**, accepting a weaker "visits counted once per browser per 30 days" figure. |

## Consequences

- **Positive.** One honest reach figure, with no third party, no IP retention and no per-visitor
  record. It is reversible within 35 days and covered by tests (`test_site_impact.py`) and the
  `LP-*` threat rows.
- **Negative.**
  - The figure is an estimate. A distributed bot can still inflate it within the per-address cap.
  - Visitors who block cookies, browse privately or use GPC are not counted, so it undercounts
    privacy-conscious people. We accept that.
- **Signing-key rotation** (`VSH_SIGNING_KEY`) invalidates every visitor cookie and changes every
  digest. For up to 30 days afterwards, returning browsers are counted again, so the figure roughly
  doubles. Note the rotation date beside the figure, or switch the figure off for 30 days after a
  rotation.
- **New personal-data category** in the privacy model's data inventory: "landing visitor token
  (opt-in deployment)". Erasure requests need no per-person action because nothing is retrievable
  per person. The notice should say so.
- **The session cookie is also sent** to `/api/v1/public/*`, because its path is `/`. The handler
  ignores it (decision 4). A test or review checklist item must keep it that way.
