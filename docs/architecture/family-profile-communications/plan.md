# Family profiles: UX and implementation plan

Status: **Accepted for phased development**. The owner chose staged retention of legacy access
and explicit source-owner consent before independent address-copy sharing (ADR-0031 §11).
The first birth-editing slice is in development from audited main `b8c248b`; strict field-policy
conversion and address/contact schemas remain unimplemented. No factory tickets are queued.
[Audit](audit.md) · [ADR-0031](../adr/0031-family-profile-addresses-and-communications.md) ·
[Acceptance matrix](acceptance.md) · [original request](brief.md).

## 1. Profile information architecture

Retain the existing person URL and current tabs/deep links. Introduce grouped navigation, with
an accessible section selector on narrow screens. Existing documents, astrology, photos and
visualizations remain reachable; do not remove them to force eight new tabs.

| Section | Content and actions | Existing integration |
|---|---|---|
| Personal details | Preferred and alternate names, scripts, optional gender/status, evidence/review badges, birth date/time/place with three explicit edit actions | Overview, NameFields, GenealogicalDateEditor, TimeEditor, EventDialog |
| Family relationships | Existing parents/spouses/children, family branches, household membership; no inferred ancestry or identity | FamilyTab, HouseholdsTab, SmartAddDialog |
| Addresses & locations | Authorized current-city summary, current/permanent/native/ancestral cards and former-address history; Add, Correct, Move, Remove, Reuse | New address services, PlacePicker/Cascade, existing heritage assertions |
| Contacts & social profiles | Masked methods; authorized reveal/edit; separate explanatory account-verification link | New person contact service; existing user notification endpoints |
| Family events | Existing timeline/calendar, all authorized birth/marriage claims, eligible personal reminders | EventsTab, ReminderControl, calendar |
| Invitations & membership | Claim status, email-bound membership invitation or profile-claim invitation; reliable statuses only | Tree and onboarding invitation APIs |
| Privacy & permissions | Server-computed field audience, exact added-reader preview, stricter time and address detail controls | Existing PrivacyTab extended with new policy schemas |
| History & sources | Authorized revisions, review/proposal status, citations, document links | HistoryTab, review and evidence modules |

Header shows display name, living/deceased/unknown, review status and optional authorized current
city. “Verified” never means merely named or claimed; show evidence, family review and account
claim as different labels. Empty, unknown, withheld and hidden are distinct states. Hidden entries
do not expose values through tooltips, accessible labels, field defaults or network requests.

## 2. Concrete form behaviour

### Birth editing

- Date row: “Edit date of birth” / “जन्म तिथि बदलें”. Exact Gregorian picker plus manual
  date parts; precision selector first for historical entry. Show formatted preview and original
  text. Unknown does not save 1 January. “Withheld” and “Keep this date private” are separate.
- Time row: “Edit birth time” / “जन्म समय बदलें”. Start unknown; choose 12/24-hour display,
  AM/PM when appropriate, optional seconds, precision/source, optional zone/offset and citation.
  Changing display format preserves the local time; no guessed Asia/Kolkata default.
- Place row: “Edit birthplace” / “जन्म स्थान बदलें”. Reuse geographic place selection, keep
  as-recorded/hospital detail private. A present address is not a birthplace default.
- Loading shows a labelled status. Missing/forbidden event shows a recoverable message and closes
  or reloads the action state; no null-render dead end or silent new claim. Competing events have
  an explicit selector and evidence labels. Never choose the first returned event arbitrarily.
- Save is field-scoped and revision-bound. A 409 prompts reload/review without discarding the
  unsaved draft. `review_required` opens the existing rationale/proposal flow. Success refreshes
  profile, timeline, history, calendar and reminder queries. Cancel writes nothing.
- Birthday reminder action is offered only for a visible, schedulable date. An explanatory message
  replaces it for unknown/withheld/incomplete dates; time is irrelevant to solar eligibility.

### Add or reuse address

1. Choose purpose and source: New / My address / Family shared / Ancestral village / Authorized
   person's address. Missing groups are omitted, not shown with hidden-result counts.
2. For New, choose country. India enables existing LGD/PIN suggestions. Enter six-digit PIN:
   show loading, provenance and matching offices; auto-select only unique untouched upper fields.
   An office choice never fills exact village/street. Outside India uses free text postal fields.
3. Preserve entered/historical labels. Disagreement shows both values and explicit keep/replace
   controls. “My village/city is not listed” keeps manual entry. Unavailable data shows a brief
   explanation and usable manual form; no spinner that blocks saving indefinitely.
4. Optional building/street/landmark/notes, dates, evidence and privacy. Separate current city/state
   from full address. Gram panchayat is optional recorded text until approved reference data exists.
5. For reuse, show authorized results with locality/district/state disambiguation. Select **Link
   this version** or **Copy and edit**; explain synchronization and retained source privacy limits.
   Copy form defaults to the same or a narrower audience and re-authorizes the source at Save.
6. Preview the new record, purpose, source, audience and primary-current choice; confirm and save.
   No precise device location, third-party geocoding or implicit household assignment.

### Existing address and ancestral village

- Card: purpose, authorized locality, valid dates with precision, current/former, source, updated
  date. Full postal content appears only to its audience. Sort known dates chronologically;
  uncertain/unknown dates stay labelled separately, not at an invented earliest date.
- “I moved” defaults to retaining the selected old address. Ask for move date (unknown allowed),
  new address, optional reason and whether to make it primary. “Correct a mistake” keeps one
  record with protected revision history. “Remove” explains withdrawal versus erasure.
- Ancestral picker reuses heritage assertion + place. Old district/name and modern LGD reference
  appear separately. Shared ancestral house is optional; property link gives no ownership right.
- Smart Add offers “Use this branch's recorded ancestral village?” with Accept / Choose another /
  Enter / Unknown. Acceptance creates a person assertion explicitly; it never fills birthplace.

### Contacts, invitations and reminders

- Contact form shows why profile data is unverified. “Same as mobile” is explicit draft copying;
  no enrollment or send. Telegram/Instagram username produces a safe profile link only.
- Invitation mode and permissions are server-supplied. Claim flow explains consent and admin review
  before access; email-bound invitation explains verified email matching and offered role. Manual
  share button cannot attest delivery. Tokens remain absent from previews/logs.
- Reminder dialog keeps 0/1/7/custom lead times and existing preference zone/hour/language.
  Show available, consented channels only. Each marriage claim is identified by visible spouse/date
  and event; ambiguous/disputed dates need an explicit selection, never an inferred anniversary.
  A source edit displays the resulting future schedule or pause reason, not a second editable DOB.

Every new state needs en/hi key parity and native-language review before public release. Keyboard
focus returns to the action; dialogs have labelled errors and status regions. Verify 390 px,
large-text layout, 44 px principal targets, keyboard-only use and axe; automated checks do not
replace the repository's outstanding screen-reader/native-Hindi reviews.

## 3. Proposed API surface and service boundaries

These are contracts for review, not implemented endpoints. Every tree route uses TreeCtx, CSRF
on writes, rate limits, typed schemas, central field checks and non-enumerating errors.

| Surface | Contract |
|---|---|
| Existing event PATCH/create | Field-scoped changes, expected revision, withheld state; shared event-change/reschedule hook. Typed `editable_fields` and reminder eligibility in authorized responses |
| `/trees/{t}/people/{p}/field-policies` | GET authorized policies; PATCH a controlled group with expected revision and widening preview token; member grant operations scoped to the controller |
| `/trees/{t}/people/{p}/addresses` and `/{id}` | Cursor list, create, authorized detail, revision-bound correction and withdrawal |
| `/trees/{t}/people/{p}/addresses/{id}/move` | Atomic old-to-former + create-current, idempotency key, expected revision and optional explicit relocation event |
| `/trees/{t}/address-candidates` | Cursor/search by source/purpose; authorization before pagination/counts; coarse projections when full payload is unavailable, and no full-copy permission from coarse access |
| `/trees/{t}/family-addresses` and version operations | Create, authorized list/detail, new immutable version, explicit adoption; no broad update-all by default |
| `/trees/{t}/people/{p}/contact-methods` | Masked list, create/edit/remove, explicit authorized reveal; no messaging side effects |
| Existing heritage assertion endpoints | Person/branch ancestral-village record and evidence; use existing place references |
| Existing `/geo`, plus reverse PIN query | Same read-only snapshot source, authentication/rate limits/ETag; additive reverse API with precision/provenance metadata |
| Existing invitation/reminder APIs | Preserve security semantics; additive capability/status projections; event-change scheduling hook |
| User notification endpoints | Explicit channel/purpose consent and Telegram linking, isolated from person/contact APIs |

Extend the existing genealogy/review services for person facts; a small addresses service owns
postal mutations and delegates authorization, evidence and history. Do not embed permissions or
copy operations in React. Existing notification service owns scheduling/delivery. Generated
OpenAPI and frontend schema types change with every API increment.

## 4. Focused implementation sequence

This is a dependency plan, not a set of executable factory tickets. ADR-0031 and its two policy choices are accepted. The initial birth slice is being implemented
by the coordinator under existing legacy audiences; subsequent factory tickets still need their own gates. Use the verified Claude-only builder/reviewer
configuration; coordinator prepares migrations/manifests/trusted configuration where factory
builders are prohibited from editing them. Each ticket must name protected paths, exact tests,
base SHA and EGM approval evidence. Never manufacture approval receipts.

| Increment | Scope / dependency | Acceptance boundary |
|---|---|---|
| Design | Audit, ADR, UX, migration/privacy decisions and tests | Accepted phased design; historic reviews in review.md |
| A0 — field privacy foundation, P0 | Staged conversion after explicit audience preview; retain legacy access until conversion; central policy/grants and old-client guards | Converted fields pass promotion/reinvite/claim negatives; legacy fields keep documented legacy audiences |
| A1 — birth editing, P0 | Initial slice reuses #74 and fixes its loading dead end; separate date/time/place actions, partial dates, unknown zone, legacy visibility write guard and revision check. Strict policy UI, withheld state and 12/24 selector follow A0 | Create → edit → reload, hidden-field negative tests, stale save; full A1 remains partial |
| A2 — birth edit scheduling, P0 | Part of PR A completion, cannot wait for G. Event-change hook, pending-delivery invalidation, recomputation and occurrence check | Moved-earlier date fires correctly; queued old occurrence never sends; no duplicate deliveries |
| B — smart address form, P0 | Existing geo APIs; reusable form can be developed with isolated fixtures while C schema is reviewed | PIN/manual/mismatch/overseas/Hindi states; reverse candidates clearly labelled; no new importer |
| C — person addresses/history, P0 | A0 + B; additive schema, encrypted legacy migration and revision/proposal adapters | Multiple/primary addresses, correction/move/remove, transaction race and safe rollback tests |
| D — ancestral and reuse, P0 | C; shared versions, ceiling-aware copy/link, existing heritage/property associations and Smart Add offer | Authorized reuse, historical names, no inference, no private-copy escape |
| E — contact/social profiles, P0 | A0; typed encrypted methods, legacy text migration, claimant reconciliation | Mask/reveal/negative tests; profile contacts remain unverified and send nothing |
| F — invitation front door, P1 | E only for optional authorized draft suggestions; existing invites can stand alone | Consent/identity/approval preserved; manual share does not report sent |
| G — reminder UX, P1 | A2; profile actions and exact marriage-claim choice | Eligibility/zone/language/lead controls; personal consent only |
| H — Telegram, P2 | Channel-purpose consent and provider review | Official bot private-chat binding, unlink/replay negatives, mock transport first |
| I — WhatsApp readiness, P2 | Consent and dated official-policy review | Separate approved purpose templates, account evidence; activation remains a separate decision |
| J — SMS / Instagram / Chatwoot evaluation, P3 | DLT/provider evidence for SMS; profile links covered by E | Written go/no-go; no unofficial DMs, no Chatwoot unless support scope appears |

Use independently reviewable PRs, splitting each letter further by vertical slice where needed.
Do not merge an incomplete P0 privacy migration merely to meet a UI milestone. Refresh main/open PRs
before each migration, enforce one head and preserve other branches' work. No automatic merge,
deploy or external traffic is part of this development authorization.

## 5. Release gates and recovery

- Developer completion: relevant negative/backend/component/E2E tests, lint/types/build, regenerated
  schema and migration roundtrip; report exact commit and failed/skipped checks honestly.
- Privacy completion: all readers/writers/exporters/history/proposal surfaces have migrated;
  an old binary cannot re-expose plaintext or bypass new policies. Run count-only migration preview,
  encrypted equality check, backup/restore compatibility and fail-closed downgrade tests.
- Real-data readiness: official dataset provenance/licence review and operator activation recorded;
  manual entry remains usable. A synthetic fixture is never evidence of real PIN coverage.
- Messaging readiness: recipient verification and purpose consent, current official policy and
  template/DLT evidence, credentials in secret manager and separately authorized live tests.
- Release review: native Hindi, screen-reader and deployment/legal gates already in repository
  remain open until their owners supply evidence. Development tests do not satisfy them implicitly.

**Current implementation order:** a legacy-compatible A1/A2 birth slice first, then staged A0
conversion and remaining A1 controls. Build B's reusable form next, then C/D/E. All work remains local or in reviewed draft PRs until
the user separately authorizes merging/deployment.
