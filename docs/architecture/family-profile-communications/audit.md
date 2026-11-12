# Family profiles and communications: repository audit

Status: design work in progress; no product feature is claimed implemented by this document.
Audit date: 12 November 2026. Requested scope: [original brief](brief.md).
Decisions: [proposed ADR-0031](../adr/0031-family-profile-addresses-and-communications.md).
Execution sequence: [plan](plan.md). Verification: [acceptance matrix](acceptance.md).

## Baseline and concurrent work

- Fetched `origin` on the audit date. Latest accepted `main` is
  `b8c248bc1a4802dd90552b20a5ded3738f400d20` (merged #73, factory invocation fix).
  This design branch starts there. The earlier environment repair branch
  `setup/development-ready` remains preserved at `7736e11`.
- Both the checked-out Alembic graph and the running development database have one head,
  `a4d7e2c9b153`. The database contains **zero `geo_snapshot` rows**. Do not describe real PIN
  suggestions as available here or load synthetic geography into a family database.
- Read `CLAUDE.md`, open questions, implementation status, ADRs 0003, 0006, 0011, 0015,
  0016, 0018–0022, 0027, and the newer factory and master-data context. Implementation status
  mixes older milestone results with later increments; source code and dated checks take precedence.
- Open PR inventory obtained from GitHub; remote branches inspected. No open PR was merged,
  edited or closed. Numbers below are references, not acceptance decisions.

| Open work | Effect on this programme |
|---|---|
| [#74](https://github.com/ManishPandey21/Vanshavali/pull/74), head `8b2c9f6` | Already implements inline Overview birth/death actions using `EventDialog`. Five changed files; real paths are under `frontend/src/pages/tree/person`, despite `features/person` in its description. Reuse after review; known missing-event/loading dead end must be fixed. It does not deliver separate date/time/place editors, strict privacy, or rescheduling. |
| [#67](https://github.com/ManishPandey21/Vanshavali/pull/67) | Proposed platform capability migration `e7c2a9f4b310` after current head; reserves T65. Recheck merge order before allocating any new migration. Does not implement person-field privacy. |
| [#61](https://github.com/ManishPandey21/Vanshavali/pull/61), [#64](https://github.com/ManishPandey21/Vanshavali/pull/64) | Proposed ADR-0028 and master-data consolidation; real geography licensing remains gated. Do not duplicate console or snapshot administration. |
| [#35](https://github.com/ManishPandey21/Vanshavali/pull/35), [#19](https://github.com/ManishPandey21/Vanshavali/pull/19) | Older conflicting geography/vocabulary implementations. Current main already has the accepted equivalents. Their schema and ADR numbers are not a template for new migrations. |
| [#42](https://github.com/ManishPandey21/Vanshavali/pull/42) | Proposed ADR-0023 oral history, with OH-prefixed threats. Keep recording/consent work separate. |
| [#25](https://github.com/ManishPandey21/Vanshavali/pull/25) | Sample-tree landing UI, not profile infrastructure. Its privacy wording will need to follow any accepted field-policy change. |

ADR-0031 is unused in the fetched tree and the inspected open PRs. Proposed threats use the
`FP-` namespace rather than claiming T65 or unverified subsequent T numbers. Recheck both at merge.

## Existing / missing / needs improvement / reuse matrix

Paths in this table are relative to the repository root; symbols identify the implementation.
“Existing” means code is present; test results are recorded separately in the acceptance matrix.

| Requirement | Existing evidence | Missing or needs improvement | Reuse / action |
|---|---|---|---|
| Personal identity, alternative/script names, preferred name, status | `backend/app/models/genealogy.py`: `Person`, `NameRecord`; `frontend/src/pages/tree/person/OverviewTab.tsx`, `components/person/NameFields.tsx` | Unified navigation and clearer status labels; gender stays optional | Reuse person/name services and `ReviewBadge`; no second profile table |
| Relationships, branches, households | `models/genealogy.py`: `Relationship`; `models/family.py`: branch and household membership with dates; Family/Households tabs | Branch/household shortcuts and location links; household membership does not prove residence | Preserve typed relationships and server kinship terms |
| Birth/death/marriage facts | `modules/genealogy/service.py`: `create_event`, `update_event`; `EventParticipant` | Profile shortcuts pending #74; distinct field actions absent | One birth event source of truth, selected by event ID; keep competing claims |
| Partial/approximate dates | `core/dates.py`: `GenealogicalDate`; `components/dates/GenealogicalDateEditor.tsx` | No explicit withheld state; no exact-date picker; unknown and withheld must differ | Keep JSON precision, original text and lunar fields; augment existing editor |
| Birth time | `GenealogicalTime`, event timezone/offset; `TimeEditor.tsx`, `EventDialog.tsx` | Explicit 12/24-hour choice and seconds entry; offset editor; birth defaults to Asia/Kolkata without recorded evidence | Keep event time; default zone unknown; never convert historical local time without evidence |
| Field read privacy | `authz/privacy.py`: `FieldGroup`, `field_level`, `can_view_field`; genealogy serializer | Birth time independently redacted but same default audience as full date. Legacy private levels admit admins; promotion can broaden access | Extend central field evaluator with explicit controller and membership grants; do not use record-only privacy enums on people |
| Sensitive field writes | `genealogy/service.py`: `update_person`, `update_event`; client omits redacted fields | These service methods check person-write/review, but do not check permission for each changed sensitive field | Add server-side field-write checks, including alternate create/import/proposal paths; UI hiding is insufficient |
| Review, revisions, evidence | `modules/review/{policy,service,revisions,history,redaction}.py`; sources/citations | New address/contact targets and encrypted history require integration | Existing proposals, stale checks, reviewer visibility, no self-approval; no second review queue |
| Birthplace | `Place`, event `place_id` + `place_as_recorded`; `PlacePicker` | Hospital/detail cannot be put into a broadly listed tree place without protection | Existing place for geographical reference; private recorded detail stays in an authorized fact |
| Indian cascade and aliases | `modules/geo/{service,router,schemas}.py`, `components/geo/PlaceCascade.tsx` | No gram panchayat reference level; listing limited by UI needs searchable/paged continuation | Reuse LGD unit identity `(level, code)` and snapshot; no duplicate importer |
| PIN lookup | `GET /geo/pincodes/{pin}`, `PincodeOut`; `useGeoPincode` | UI currently lists offices as text and offers district buttons. No persistent office choice, mismatch resolution or reverse-PIN endpoint | Build controlled suggestions over existing `pincode_office`, only auto-select untouched unambiguous upper-level drafts |
| Geography activation | `app/cli/geo.py`, ADR-0019 snapshot import/activate; synthetic fixtures | Real approved/licensed data absent from local DB | Manual fallback, explicit unavailable state; no invented answer for PIN 226001 |
| Postal address | `Person.residential_address` is one plaintext text field; residence/migration events; household `place_id` | No structured multi-address CRUD, purpose, separate city visibility or relocation operation | Add associations and private postal payload, not a second geographical database |
| Tree place privacy | `genealogy/router.py::list_places`, `_place_out` | Tree members can list place names/context; only coordinates are separately coarsened. A private residence must not become a searchable tree place | Keep private postal lines outside Place and all global reference tables |
| Address history | Residence/migration events, revision infrastructure | No first-class address validity, correction versus move, or independently protected history | Date precision reused; one transactional move operation; optional existing event reference, no automatic duplicate event |
| Ancestral village | Heritage `ancestral_village` assertion with `place_id`, branch heritage; `PersonForm.tsx::useAncestralVillage` | Current offer is used as a **birthplace** suggestion; it is not ancestral assignment. Shared house/address versions absent | Preserve assertion as ancestral fact; new explicit ancestral offer, never silent birthplace/residence inheritance |
| Address reuse | PlacePicker can link existing places | No authorized address picker, copy/link distinction, private-source ceilings, immutable shared postal version | Add reuse service over authorized records and existing places |
| Property integration | Existing property/parcel `place_id` and interests | Link ancestral house by reference only | No ownership or inheritance inference; property visibility checked separately |
| Profile contact data | `Person.contact_info` plaintext free text, field-redacted; `primary_language` | No typed email/mobile/WhatsApp/social methods, encryption or claim reconciliation | Migrate verbatim into an encrypted legacy note; do not parse or mark verified |
| Verified endpoints | `NotificationContact.address_enc`, masked hint, code verification; verified user email | Telegram chat binding and distinct durable channel-purpose consent absent | Keep user-owned endpoint infrastructure separate from person contact methods |
| Invitations | `tree_invitation`, `profile_claim_invite`, onboarding service; `ClaimInviteShare.tsx` | Split interfaces, no explicit Telegram share action; no reliable delivery acknowledgement for manual sharing | Unified front door retaining two distinct authorization flows; never mark a clicked share link “sent” |
| Reminder UX | `ReminderControl`, personal preferences, lead 0/1/7 plus custom, zone/hour, delivery history | Add eligibility-driven profile actions; retain choice of exact marriage/birth claim | Reuse reminders and calendar, no new scheduler |
| Event edit → scheduling | `notifications/service.py`: `_reschedule_all` (preferences), `tick`, `_attempt` | Event update has no reschedule hook. `tick` filters old `next_fire_at`; a moved-earlier date can be missed. `_attempt` checks schedulability but not that queued occurrence still matches edited date | Recompute on accepted edits and reject stale deliveries; required in PR A, not postponed to UX PR G |
| Lunar calendar | ADR-0022, calendar module and approval manifest | Activation and reviewed golden/reference evidence remain separate gates | Input/display works independently; no guessed conversion |
| External channels | `notifications/channels.py`: SMTP, mock, Twilio, Meta | Live WhatsApp/SMS not verified; provider runbook reuses reminder template for verification and needs separation. No Telegram adapter | Official APIs only, mocks for development; current category/pricing rules must be freshly verified before activation |
| Instagram / Chatwoot | No implementation found in app source | Instagram profile link; optional later official-API evaluation | No proactive DM assumption; no Chatwoot dependency |
| Accessibility / locales | en/hi parity tests, common Dialog/Combobox/Field, Playwright axe | New form states, keyboard navigation and elder-friendly labels need coverage | Reuse primitives, 44 px main actions, mobile-first, no giant eight-tab strip |

## Main design risks

1. Strict new privacy cannot be delivered by renaming `PRIVATE_SELF`: it includes the tree owner.
   A migration policy for existing fields must be accepted explicitly; narrowing is proposed.
2. Place search is a separate exposure surface. Redacting a person's address does not make a new
   place containing that address private.
3. Copying a private address must not launder it into a wider audience. Independent editing and
   revocable authorization are separate properties.
4. A hidden birth field must not be cleared by a whole-event edit or overwritten directly by a
   caller with general person-write permission. Check fields on the server, not just the dialog.
5. “Invite” has two existing meanings. Email-bound membership invitation and profile-claim
   review must remain visibly different; sharing a bearer link never proves identity.
6. An event edit must invalidate queued occurrences as well as recompute future ones.

These are code-inspection findings unless accompanied by a named test in the acceptance matrix;
they are not claims that a new security implementation has passed verification.
