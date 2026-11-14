# Phase F increment — invitation front door

Status: **implemented and verified locally** on `feature/invitation-front-door`, based on
main commit `678f93bc8c476b9ae2fe7367bdc46378abfdd0f0` (merged Phase D / PR #79).

## Delivered boundary

- One **Invite family member** page now keeps the two existing authorization flows visibly
  distinct:
  - an email-bound membership invitation pre-authorizes roles and can be accepted only by an
    account that has verified the exact recipient address;
  - a profile-claim invitation creates a fragment-token link whose holder still has to sign in,
    provide their own consent and adult confirmation, and wait for administrator review.
- The available modes come from the caller's server-supplied tree permissions. Members with
  `person.write` can reach the claim-link front door even when they cannot manage memberships;
  only members with `members.manage` see the email-bound flow and its role controls.
- Claim-link history adds only authorized person labels and the linked claim/removal kind and
  review status. The UI maps these backend facts to Created, Claim requested, Removal requested,
  Accepted, Rejected, Withdrawn, Wrong person, Expired or Revoked.
- WhatsApp, Telegram, native share and copy actions use generic text. They do not include a person
  name or tree name, do not address a phone number, username or chat, and never change the status
  to Sent. Provider delivery remains disabled.
- The generated one-time link stays available while its creator briefly checks the other invitation
  mode, but is reset whenever the selected relative changes. Copy includes the same generic message
  and private link used by the share actions rather than exposing a context-free URL.
- Email-bound invitation creation is limited to 30 attempts per user per hour, matching the
  existing claim-link abuse boundary. Existing role, branch, expiry, revoke, verified-email,
  single-use and scope-conflict checks are unchanged.
- English and Hindi keys are kept in parity. Generated OpenAPI JSON and TypeScript contracts now
  include the additive claim-history projection.

## Security and privacy invariants

- A bearer claim link still creates only a requested claim; it never creates membership.
- Approval, rejection, consent capture, minor/deceased/claimed-profile exclusions and branch scope
  remain enforced by the existing backend services.
- The claim token remains in the URL fragment and is absent from server paths, logs and link
  previews. Email invitation identity remains bound to a verified address even when its one-time
  link is copied manually.
- Manual share clicks are not delivery evidence. No provider call, phone number, Telegram binding,
  automated message or external notification was added.
- Only an active claim invitation can be revoked; a consumed link and its approved/requested claim
  cannot be rewritten into a contradictory revoked state.
- Claim history remains tree-scoped and visibility-filtered before names or statuses are projected.

## Verification evidence

- Backend focused invitation/security regressions: `test_onboarding.py`, `test_trees.py`,
  `test_email_auth.py`, and `test_security_audit.py` passed.
- Backend lint/format and mypy passed (`358 files already formatted`; `280 source files`).
- Frontend focused Vitest coverage passed for the front door, permission-derived navigation and
  generic WhatsApp/Telegram/share-copy construction, including one-time-link lifecycle checks.
- Frontend TypeScript, ESLint and production build passed.
- Real-stack Playwright passed the new front-door journey: create generic links, confirm Created,
  submit the relative's consent, observe Claim requested, approve, then observe Accepted.
- Complete regression suites passed sequentially: 46 frontend files / 242 tests and the full
  backend suite. Backend Ruff format/check passed for the maintained `app` and `tests` scope, and
  mypy passed all 280 source files. Repository-wide Ruff still reports pre-existing Alembic import
  ordering and S608 debt outside this increment.

## Explicitly deferred

- Automated Telegram, WhatsApp or SMS delivery, provider credentials, delivery receipts and a
  truthful Sent/Failed state remain H–J work and require separate operational authorization.
- Contact-to-account verification suggestions remain optional; person contact records are not
  treated as verified user endpoints.
- Native-Hindi and screen-reader review remain release gates; automated parity and axe checks do
  not replace them.

## Next planned increment

After Phase F verification, continue with **G — reminder UX**. A0 strict field-controller
conversion, remaining B smart-address refinements and C proposal/export hardening remain release
gates and are not implied complete by this increment.
