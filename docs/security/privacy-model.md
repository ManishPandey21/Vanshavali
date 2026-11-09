# Privacy model

Status: **implemented** in `backend/app/authz/privacy.py` and enforced server-side by every
serialiser. The UI only mirrors these decisions. It never enforces them.
Authoritative requirements: PRS §6, §30, §31, §32, §54, §58 ("Privacy" acceptance criterion).

## 1. Principles
1. **Living people are private by default.** A person is *protected* when `profile_status` is
   `living`, or `unknown` with a birth date less than 110 years ago or no birth date at all, or when
   they are a minor.
2. **Minors (under 18, using the youngest age the recorded birth date allows) are never public**,
   whatever the person or tree settings say.
3. **Least visibility.** Seeing a person does not mean seeing their sensitive fields, documents or
   property.
4. **No inference.** Gotra, jati/caste, community, religion and kuladevata are never derived from
   surnames, places, languages or relatives (`tests/test_heritage_family.py::test_gotra_is_never_inferred_from_surname`).
5. **Data minimisation.** No government ID numbers are collected. Aadhaar-shaped numbers are masked
   in OCR output.
6. **Sign in with Google keeps the minimum** (ADR-0012): only Google's stable subject id and the
   email at the time of linking are stored (`external_identity`), plus the name and email used to
   create the account. No Google tokens, profile photo or contacts are requested or kept; the scopes
   are `openid email profile`.
7. **Subject control (DPDP Act 2023).** Claimed-profile owners control their own privacy settings.
   A consent ledger, erasure and account closure exist (see §5).

## 2. Privacy levels (PRS §6)
From most open to most restricted:

| Level | Who can see it |
|---|---|
| `PUBLIC_DECEASED_ONLY` | Everyone, **only** if the tree's public mode is `DECEASED_ONLY` and the person is deceased and not protected. Otherwise, any tree member (including researchers). |
| `INVITED_RESEARCHER` | Any member, including `RESEARCHER` |
| `TREE_MEMBERS` (default for people) | Any member except researcher-only memberships |
| `FAMILY_BRANCH` | Admins, plus members whose branch scope or linked person shares a branch with the subject |
| `PRIVATE_TREE_ADMINS` | `OWNER`, `FAMILY_ADMIN` (plus the claimed profile owner) |
| `PRIVATE_SELF` | The claimed profile owner, plus the tree `OWNER` as archive custodian |
| `CUSTOM` | Admins, plus users holding an explicit `access_grant` |

Explicit grants (`access_grant`, per person, document or property, with an optional expiry) raise
visibility for one member. Documents also distinguish `view` from `download`. A grant belongs to the
member's membership (ADR-0027 §3): it is deleted with it (removed, or account closed), inviting the
same person again does not restore it, and it can never name a member of another tree. Privacy
managers see, create and revoke grants only on records they can see themselves (threat T53).

**Shareable records (ADR-0027).** Documents, photos, recordings and family traditions take a
record audience instead (traditions have no separate download right):

| Audience (`document.privacy_level`) | Who can see it |
|---|---|
| `ONLY_ME` | The record's owner (their *current* membership). Nobody else, whatever their role. |
| `SELECTED_MEMBERS` | The owner and memberships holding a grant on it. No role-based access. |
| `FAMILY_BRANCH` + `audience_branch_id` | The owner, members of that branch, family admins (ADR-0006's meaning) and grantees. |
| `TREE_MEMBERS` | Every member except researcher-only memberships. |
| legacy levels | As above for people; `CUSTOM`/`PRIVATE_SELF` keep their old meaning until the owner converts them. |

*View* (metadata, thumbnail, preview, playback) and *download* (the original, ZIP and video exports)
are separate: viewers download only when `allow_download` is on or they hold a `download` grant. New
vault documents and records tagged with a protected living person start as `ONLY_ME` without
download. A record is never more open than any protected person tagged in it. Grants belong to one
membership and are deleted with it; no record is public in v1.
A photo in an event's album is never more visible than the event or a protected person in it, and
becomes more private when the event does; each viewer sees only the album photos they may see.
A standalone photo collection has its own audience (new collections are Only me); a viewer sees a
photo in it only if they may see both, and sharing a collection never shares its photos.
Global search and the archive export follow the same rule: a collection is a hit or exported only
for someone who may see it, and only the photos they may see are listed in it.
When a record is made more private automatically, its owner is told in the app (which record, never
who caused it or why). A profile hidden after a "remove me" request through a claim link narrows the
records tagging it at once; declining the request never widens them again.

## 3. Field groups and defaults
A person's fields belong to groups. Each group resolves to a level: first a per-person override
(`person.field_privacy`), then the defaults below. A field is never *less* private than the person.

| Group | Protected (living/unknown/minor) default | Deceased default |
|---|---|---|
| `birth_date_full` | PRIVATE_TREE_ADMINS (others see **year only**, `redacted: true`) | person level |
| `birth_time` | PRIVATE_TREE_ADMINS | person level |
| `birth_place_detail` | FAMILY_BRANCH | person level |
| `contact`, `address` | PRIVATE_TREE_ADMINS | PRIVATE_TREE_ADMINS |
| `gender_identity` | PRIVATE_SELF | PRIVATE_TREE_ADMINS |
| `jati` | PRIVATE_TREE_ADMINS | PRIVATE_TREE_ADMINS |
| `community`, `religion` | TREE_MEMBERS | person level |
| `heritage` (gotra, pravara, kula…) | person level | person level |
| `astrology` | PRIVATE_TREE_ADMINS | person level |
| `notes` | person level | person level |

Other life events of protected people are shown with year-level dates only. Residence events fall
under `address`. Responses list the redacted groups in `redacted_fields`, so the UI can say
"hidden by privacy settings" without showing values.

## 4. Enforcement points (all server-side)
| Surface | Mechanism | Tests |
|---|---|---|
| Person/event API | `modules/genealogy/serialize.py` (`Serializer`, `_redact_event_fields`) | `test_privacy.py` |
| Lists, search, duplicates | `can_view_person` filtering **before** pagination. Hidden people are never counted or snippeted. | `test_privacy.py`, `test_search_consent.py` |
| Family views and graphs | Hidden relatives become `{person: null, hidden: true}` placeholders. Public views drop them entirely. | `test_privacy.py::test_admin_only_person_is_invisible_to_viewer_everywhere` |
| Public pages | `ctx.public=True`: deceased and not protected and `PUBLIC_DECEASED_ONLY` only; year-only dates; no provenance, coordinates or notes | `test_privacy.py::test_public_tree_never_exposes_living_or_private` |
| HTML and hydration | The SPA shell contains no data (ADR-0001). Nginx sets `X-Robots-Tag: noindex` | frontend build |
| Heritage | Attribute → group mapping (jati, community, religion) plus per-assertion level | `test_heritage_family.py` |
| Documents and property | Object level plus vault/property permissions (ADR-0004, ADR-0010) | module tests |
| Photos imported with GEDCOM | Each photo becomes a document with its person's privacy level, the strictest of them when one photo shows several people; photos of people who are not imported, or of no one, are not stored (ADR-0013) | `test_gedcom_photos.py::test_photo_privacy_follows_the_person` |
| Operational logs, metrics and job queues | Route templates only (no raw paths or query strings, so no signed tokens), no bodies, cookies or headers; masked email addresses; job descriptions without arguments, and failed jobs expire after 7 days; GEDCOM and storage failures logged by type only; metrics carry fixed low-cardinality labels, never IDs or names; the pilot edge (Caddy) keeps no access log (T18, T31; `docs/operations/monitoring-alerting.md`) | `test_observability.py`, `test_pilot_ops.py` |
| Backups | Database dumps are encrypted with age before leaving the database host; the identity is kept offline. Document objects are already app-encrypted; backup copies stay in an Indian region (ADR-0014, backup-restore runbook) | drill (`deploy/pilot/drill/run-drill.sh`) |
| Exports | GEDCOM export applies the exporter's view. Living people are excluded by default. Sensitive data needs `privacy.manage` and is audited. | `test_gedcom.py` |
| Life events (ADR-0015) | An event's own `privacy_level` is enforced at lookup (`get_event_checked`), so album, reminder and render endpoints 404 for events the viewer may not see; tree-wide listing pages over visible rows only | `test_life_events.py::test_private_events_and_people_never_listed`, `…test_photo_privacy_inherits_from_event_and_person` |
| Event photos (ADR-0015) | A new photo takes the strictest of tree default, event level and principal's level; a looser level is refused; album entries and counts include only documents the viewer may see; vault content rules (STANDARD/VAULT, grants, signed URLs) unchanged | `test_life_events.py` (album tests), `test_render_jobs.py::test_event_timeline_embeds_only_photos_the_requester_may_open` |
| Coordinates (ADR-0015) | `place.coordinate_privacy`: viewers below it get coordinates rounded to 0.1° and precision `approximate`, no geo note; event coordinates at such a place are coarsened too; public pages never get coordinates | `test_life_events.py::test_coordinate_privacy_coarsens_for_lower_roles`, `test_visualization.py::test_map_points_paths_and_coordinate_privacy` |
| Charts and maps (ADR-0017) | Every `/viz/*` endpoint builds on `visible_subjects` and the event serialiser: hidden people are placeholders without names, dates or places; the graph never expands through them; living people keep year-only dates and no birthplace detail | `test_visualization.py::test_viz_endpoints_leak_nothing_hidden` |
| Animated exports (ADR-0017) | The payload is built as the requester, encrypted at rest and purged when the job ends; artifacts are visible and downloadable only by the requester and tree admins via 5-minute user-bound signed URLs re-authorised at download | `test_render_jobs.py` |
| Reminders (ADR-0016) | Per-user, opt-in; only dates the member can see in full; re-evaluated as the recipient at send time; SMS/WhatsApp texts carry no names, places or notes; delivery records hold no message or address; phone numbers encrypted, masked and verified | `test_reminders.py` |

## 5. Subject rights and deletion (PRS §29, §31, §54)
| Need | Implementation |
|---|---|
| Claim own profile | `POST /people/{id}/claims`, then admin approval. Links the profile. **Grants no extra roles.** |
| Claim via a shared link (ADR-0011) | A member creates a single-use link (`/claim#<token>`, shared via WhatsApp or anything else). The relative signs in, reads a plain-language notice and gives their own consent (server-owned text, 18+ confirmation). This files a claim. Only admin approval creates a membership (the offered role, never wider than the inviter's scope) and writes a `consent_record` with basis `self`. |
| "This isn't me" / "remove me" from a link (ADR-0011) | "This isn't me" cancels the link and changes nothing else. "Remove me" hides the profile from everyone but tree admins at once, freezes new invites and claims, and asks an admin to erase it (the existing irreversible erasure) or keep it (the previous privacy level is restored). A link can never erase anyone by itself. |
| Family-data attestation (ADR-0011) | Before adding anyone, each contributor confirms: "I agree to add my family members' names to this private tree, and I confirm I have their permission to do so." Enforced by the server, recorded in `family_data_attestation`, withdrawable. It is an accountability record, **not** the relatives' consent. |
| Control own privacy | Claimant may `PUT /people/{id}/privacy` |
| Consent ledger | `consent_record` (grant, purpose, categories, basis incl. parent/guardian, expiry, withdrawal) |
| Remove a fact / unlink a relationship | Delete event, assertion or relationship (audited) |
| Hide a profile | Set its privacy level (e.g. `PRIVATE_TREE_ADMINS`) |
| Remove from tree | Soft delete, restorable by an admin |
| Privacy erasure | `POST /people/{id}/erase`: irreversible; leaves an anonymous placeholder |
| Delete uploaded file | Document soft delete plus retention (restore available) |
| Close account | `POST /auth/close-account`: deactivates, revokes sessions, kills emailed links, leaves trees. Refused for a sole tree owner. |
| Export own data / tree | GEDCOM export (the full archival package is tracked in `IMPLEMENTATION_STATUS.md`) |

**Account emails** (verification, "someone tried to register with your email", password reset) are
transactional only: plain text + simple HTML, no images, tracking pixels or link rewriting, in the
user's preferred language. Registration and reset never reveal whether an email has an account
(threat model T19). Emailed tokens are stored only as SHA-256 hashes and never audited.

**Landing-page privacy promises ("Kept in trust").** The public landing page states four promises;
each is enforced server-side today, and changing the enforcing code means changing the copy
(`landing.trust.*` in both locales) in the same PR:

| Promise | Enforced by |
|---|---|
| Private and invite-only | `default_person_privacy = TREE_MEMBERS`; `level_allows` denies non-members |
| Living relatives protected (birth date/time, contact, address → admins; the person once their claim is approved) | `PROTECTED_DEFAULTS` → `PRIVATE_TREE_ADMINS`; `_is_self` (admin-approved claim) |
| You decide who sees what (roles, per-person level; public pages off by default, deceased-only, marked one by one) | `ROLE_PERMISSIONS`, `Person.privacy_level` / `field_privacy`; `PublicMode.OFF` default; public branch of `level_allows` |
| Your records stay yours (GEDCOM / family archive export) | `gedcom.export` (Owner, Family admin, Contributor) in gedcom and archive services |

**Landing-page sketch ("plant your tree").** Signed-out visitors can type up to four names (self,
father, mother, paternal grandfather) on the public landing page to preview a tree. The names are
kept only in that browser tab's `sessionStorage` (`vsh.treeDraft`, ≤120 chars each), are never sent
by the landing page, and are erased on "Clear names", when the tab closes, or once onboarding has
saved them. Onboarding only pre-fills its form from the sketch: nothing is created until the user
ticks the family-data statement (ADR-0011), exactly as for typed-in names. No new server data flow.

**Open (Q13):** the lawful basis for living relatives who never claim their profile, and legal review of
the onboarding wording and its Hindi translation.

**DEFERRED:** a formal data-subject-request inbox with SLAs and a grievance officer contact
(DPDP Rules commencement is phased, so this is tracked as a legal workstream). Age-verification and
guardian-consent capture flows beyond the consent ledger are also deferred.

## 7. Heritage visualization milestone (ADR-0015, ADR-0016, ADR-0017)
- **Event visibility.** An event can be more private than its person (`event.privacy_level`). That
  level now gates every route that looks the event up, not just its serialisation.
- **Photos inherit privacy.** Event photos are vault documents whose default level is the strictest
  of the tree default, the event and its principal person; uploaders cannot loosen it. Tagging a
  person in a photo requires that the uploader can see the person (404 otherwise).
- **Exact locations are personal data** when they point at a living family's home. Place
  coordinates can be restricted (`coordinate_privacy`); others see ~11 km precision. Maps draw no
  third-party tiles; "open in OpenStreetMap" sends a point to OSM only when the user clicks it.
- **Charts and videos show what the viewer may see, no more.** Hidden relatives are anonymous
  placeholders in every chart, table alternative, map and render payload. A video is rendered from
  a payload built as its requester; other members cannot see or download it. Videos downloaded by a
  member leave the platform's control — the export panel says the render uses the requester's view.
- **Reminders** are opt-in per member and tree, stop when access is revoked, and keep minimal data:
  no message bodies or addresses in delivery history; SMS/WhatsApp (third-party processors) get no
  names, places or notes; phone numbers are encrypted (SYSTEM key), masked, and verified by code.
- **Retention.** Render payloads are deleted when a job ends; artifacts until the job is deleted.
  Delivery history is kept with the tree (deleted with it). An automatic retention period for
  render artifacts and delivery history is DEFERRED (proposed: 90 days / 1 year).


## 8. Smart Add Relative (ADR-0020)

- **No one is created without being seen.** The plan endpoint writes nothing; the user picks a
  recorded relative or explicitly chooses "add as unknown for now" at each step, sees every record
  in a preview, and confirms. An unconfirmed plan leaves no trace.
- **Provisional people** carry no name and no data except what the user enters. Sex at birth is
  "Not recorded" unless the user records it; a kinship term never fills it in. They count as people
  for attestation (ADR-0011): the family-data statement is required before Smart Add can create
  anyone. Their status is protected (unknown, so possibly living).
- **Only the creator and tree admins see a provisional person.** They are created at `CUSTOM`
  privacy with a view grant for the creator (ADR-0020 §7), so the creator can complete the record and
  only tree admins can widen access. While pending (unnamed, or with any relationship lacking
  supporting evidence) they are concealed from everyone else: no anonymous placeholder, count, graph
  node, relationship-path hop, candidate entry or public page reveals that they exist.
- **Completing is not verifying.** A name completes the profile's details; `is_provisional` stays as
  the record of how the person was created, and verification comes only from the relationships'
  existing evidence status.
- **Exports leave out pending provisional people** (GEDCOM and archive, whoever exports), together
  with the relationships that touch them; no placeholder or family link is left pointing at them. The
  archive manifest counts them only for an exporter who could see them.
- **Headline counts and the "To complete" view** (ADR-0020 §8). Branch and household member counts
  and the fan chart's "known" figure never include pending provisional people, for anyone. The
  administrative `provisional_member_count`, the chart's "to complete" figure and the "To complete"
  people view count or list only those the viewer may see (creator, tree admins, grants); for anyone
  else they are 0 or empty.
- **Hidden relatives stay hidden.** Candidate lists contain only people the user may see; a hidden
  parent is reported as a count, never identified, and prevents creating a duplicate parent.
- **Kinship terms are not stored and do not set identity.** "Mama" becomes edges; gender identity is
  never set, and sex at birth is only what the client sends. Candidate lists never drop a relative
  because of their recorded sex at birth.
- **Age order** ("older than") is family knowledge about two people, private to the tree (RLS), and
  deleted with either person. When the calculator orders two people by birth dates it uses only the
  dates the viewer may see (year-only for living people, for most viewers), and never compares a
  person hidden from the viewer.
- **Undo** soft-deletes (restorable) the people an operation created and removes its relationships
  and age-order records; it is limited to the same user for 30 minutes.

## 9. Master data vocabularies (ADR-0018)

- **Suggestions, never facts.** A vocabulary only helps typing. The value stored is what the person
  chose or typed; nothing is filled in, inferred or checked against someone's surname, place or
  relatives.
- **No lists for sensitive identity.** Community, jati and religion have no vocabulary, so the app
  never presents caste or religious categories to choose from (Q4).
- **A family's own entries are family data.** They are private to the tree (RLS), visible to its
  members only, deleted with the tree, and never copied into the global catalogue by the app. The
  audit log records that an entry was added, not what it says.
- **Global reference data holds no personal data.** Packs are versioned files in the repository,
  loaded by an operator command.

## 10. Name transliteration suggestions (ADR-0025)

- **The typed name is never changed.** A suggestion in the other script is shown, never applied;
  accepting it adds a separate name, which is never the preferred one and never counts as evidence.
- **Names stay on our servers.** Suggestions are computed locally. The text is not logged or stored,
  and no third-party transliteration service is used.
- **No learning across families.** The engine never learns from names other families enter; its name
  list changes only through code review.
- **No inference.** A name's script or spelling never sets sex, gender, community, region or anything
  else about a person.

## 11. Indian geography reference data (ADR-0019)

- **No personal data in the reference tables.** LGD units, aliases and PIN offices are national open
  data (GODL-India, attributed under the cascade, on the About page and in the family archive). They
  hold nothing about any family, and a family's own spelling never enters them.
- **Linking adds nothing about a person.** A village name stays where it was (the place, and the
  person's `BIRTH_PLACE_DETAIL` field group, redacted for protected people as before). LGD gives no
  coordinates, and PIN office coordinates are not imported.
- **Searches stay private.** Place searches go only to our own server, never to a third-party
  geocoder. They are rate-limited per user, and only request paths are logged, never the query.
- **Nothing is rewritten.** A quarterly update never changes a family's record; it shows a note the
  user may act on. The ancestral-village suggestion is offered, never filled.

## 12. Change proposals, revision history and family review (ADR-0021)

- **Revision history holds values, so it is treated like the facts.** It is read through the same
  field-group redaction as the person (a viewer who may only see a birth year sees "birth date
  changed", not the dates). It is left out of archives and GEDCOM, and erasing a person erases
  their history. The audit log keeps recording field names only, never values.
- **Proposals and comments are tree data.** Only the proposer and those who may review every
  target see them, with values redacted for the reader. An erasure removes the erased person's
  values from open proposals and makes those proposals stale.
- **Notifications carry no personal data.** They store ids only; their text is built when read,
  with the reader's current permissions, and nothing is sent outside the app.
- **Family review is not evidence.** `review_state` (unreviewed, family-reviewed, contested) is
  separate from evidence status, so a family's approval never stands in for a document.
- **Duplicate checks never reveal hidden people.** Only people the user can already see are
  compared and shown.

## 13. Heritage depth, kinship words and family traditions (ADR-0026)

- **Offers are explicit.** A family's own entry (a family deity, devak or gotra) is shared with
  the common suggestion lists only when a tree admin offers it, and the shared term never names
  the family. Promotion happens by code review and never changes a family's stored values.
- **No inference.** A gotra never fills in a pravara, community, region or religion; a kinship
  word never sets anyone's sex or age. Caste, jati and religion still have no suggestion lists.
- **Traditions have their own privacy level**, are never shown on public trees in R4, and are
  exported only as far as the exporter may see them. People linked to an entry are shown only to
  members who may see them.
- **Family words stay in the family.** A tree's own kinship words are visible only inside that
  tree.


## Family Admin nominations (ADR-0006 amendment, 9 Nov 2026)
- **Who sees a nomination:** the Owners, the Family Admins and the nominee. The nominee sees who
  nominated them and the reason (owner decision). No other member sees that a nomination exists.
- **The reason text** is personal comment about a family member. It appears only in the nomination
  itself: never in audit events, notification text or exports.
- **Notifications store ids only** (ADR-0021 §7) and render for the reader at read time.
- **Promotion changes what someone can see.** Approval needs the nominee's own acceptance first,
  because a Family Admin sees `PRIVATE_TREE_ADMINS` data of living relatives. `PRIVATE_SELF` and
  ADR-0027's private audiences stay closed to them.
- **Retention of closed nominations:** the reason text is erased the moment a nomination closes
  (approved, declined by either side, withdrawn, expired or lapsed). The row keeps only ids, the
  status and timestamps, so the notifications and audit events that point to it still resolve. It is
  deleted with the tree.
