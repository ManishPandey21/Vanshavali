# ADR-0011: Onboarding, family-data attestation and shareable claim invites

- Status: Accepted · Date: 2026-09-25
- Relates to: ADR-0005 (sessions), ADR-0006 (authorisation), privacy model §5, PRS §29 and §31

## Context
New users need a guided first run: create a private tree, add themselves and close relatives, then
bring those relatives in. Two product asks shape this:

1. A plain-language checkbox before anyone adds relatives: *"I agree to add my family members'
   names to this private tree, and I confirm I have their permission to do so."*
2. A "Share via WhatsApp" invite so relatives can claim their own profiles and grow the tree.

Under the DPDP Act 2023 the platform is a Data Fiduciary for relatives' data. **A user confirming
that they have a relative's permission is not the relative's consent** under s.6: consent must come
from the Data Principal, after notice (s.5), by a clear affirmative act. Minors need verifiable
parental consent (s.9). Deceased people are outside the Act's definition of a Data Principal.
We therefore treat the checkbox as an *accountability record* for the person entering the data.
The relative's own consent is captured separately, when they claim their profile.

WhatsApp is the dominant channel in India, but the WhatsApp Business API needs phone numbers and
makes Meta a processor. Existing tree invitations (ADR-0006, T3) are bound to an email address and
grant roles immediately. A WhatsApp link is a bearer token that can be forwarded, so it must not
grant access on its own.

## Decision

### Family-data attestation
- New table `family_data_attestation(tree_id, user_id, statement_version, language, statement_sha256,
  accepted_at, ip, user_agent, withdrawn_at)`. Rows are never deleted; withdrawal sets
  `withdrawn_at`.
- The **server owns the statement text** (`app/modules/consent/statements.py`, per language and
  version). The client shows the text the server returns and posts back `{version, language}`.
  The server rejects stale versions (`409 statement_outdated`) and stores the SHA-256 of the exact
  text shown. Changing the wording means a new version, and users must re-attest.
- **Creating a person** needs an active attestation by the acting user for that tree. This covers
  `POST /people`, `POST /people/{id}/relatives` with `new_person`, and GEDCOM upload. Without one the
  server answers `403 attestation_required`, including for trees created before this ADR. The UI
  shows the checkbox inline and retries.
  Editing existing people does not need it.
- The checkbox is unticked by default and is never bundled with terms of service. Attestation,
  withdrawal and re-attestation are audited (`attestation.accepted`, `attestation.withdrawn`).

### Claim invites (share via WhatsApp or any app)
- New table `profile_claim_invite(tree_id, person_id, token_hash, offered_role, expires_at,
  created_by, used_by, used_at, revoked_at)`. The token is 256-bit, stored only as a SHA-256 hash,
  valid for 7 days, single use, and revocable by its creator or a tree admin.
- **Who can create one:** anyone with `person.write` on that person (branch scope applies) who can
  see the person. The person must be unclaimed, not deceased, and not a recorded minor. Only
  admins may offer `CONTRIBUTOR`; everyone else can offer `VIEWER` only. Creation is rate limited
  per user.
- **Link shape:** `{public_base_url}/claim#<token>`. The token is in the URL **fragment**, so it
  never reaches our servers, proxies or access logs, and it is not in `Referer` headers or
  WhatsApp's link-preview fetch. The SPA shell has no data, so the preview shows nothing
  personal. The frontend opens `https://wa.me/?text=…` (no phone number is collected or stored)
  with a generic message and the link. It contains **no names, dates or tree details**, because
  WhatsApp messages get forwarded.
- **Opening the link** needs a signed-in account. The preview returns the tree name, the
  inviter's display name and the person's preferred display name only. Accepting takes the
  relative's own notice acknowledgment and consent (`{version, language, confirm_adult}`, using
  the same server-owned text mechanism). It creates a `profile_claim` in state `requested` and uses
  up the invite. **It gives no tree access.**
- **A tree admin approves the claim** (existing workflow; the queue now shows who is claiming).
  Approval links the profile. If the claimant is not yet a member, approval creates a membership
  with the invite's `offered_role` and `linked_person_id`. It also writes a `consent_record`
  (basis `self`) dated when the claimant consented. Rejection leaves no membership.
- Once claimed, the relative controls their own privacy settings, consent ledger and erasure
  request through the existing screens (privacy model §5).

### Onboarding
A `/welcome` flow after registration, and from the empty trees list, has four steps:
1. A plain-language privacy notice.
2. Name the tree.
3. Add yourself and your parents, behind the attestation checkbox.
4. Invite living relatives, with WhatsApp or copy-link per relative.

Every step uses the public APIs above. There is no onboarding-only backdoor.

## Consequences
- Every contributor, not just the tree creator, must attest before adding people. Seed data and
  tests record an attestation explicitly.
- A forwarded link can lead to a *claim request* by the wrong person, but not to access: an admin
  still has to approve. The claimant's name and email are shown to admins for that decision.
- Profiles with an unknown birth date may belong to minors. The claimant must confirm they are 18
  or older, and a recorded minor can never be invited. Guardian-consent capture is still deferred
  (privacy model §5).
- The attestation does not make storing living relatives' data lawful by itself. Legal review of
  the notice text, the Hindi translation and the lawful basis (s.6 consent from the claimant, and
  what to do for relatives who never claim) is tracked in `open-questions.md` (Q13).

## Alternatives considered
- **Pre-filled phone number (`wa.me/<number>`)**: rejected. We would have to collect and store
  relatives' phone numbers without their consent.
- **Token in the path** (like `/invite/<token>`): rejected. It ends up in access logs, `Referer`
  headers and link-preview crawlers.
- **Membership on link acceptance**: rejected. A forwarded bearer link would give tree access
  without anyone reviewing it.
- **Treating the checkbox as the relatives' consent** (`consent_record` basis
  `tree_admin_attestation` for every relative): rejected. It would make the ledger overstate
  consent that the relative never gave.
