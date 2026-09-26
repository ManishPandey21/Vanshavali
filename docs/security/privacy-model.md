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
6. **Subject control (DPDP Act 2023).** Claimed-profile owners control their own privacy settings.
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
visibility for one member. Documents also distinguish `view` from `download`.

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
| Exports | GEDCOM export applies the exporter's view. Living people are excluded by default. Sensitive data needs `privacy.manage` and is audited. | `test_gedcom.py` |

## 5. Subject rights and deletion (PRS §29, §31, §54)
| Need | Implementation |
|---|---|
| Claim own profile | `POST /people/{id}/claims`, then admin approval. Links the profile. **Grants no extra roles.** |
| Claim via a shared link (ADR-0011) | A member creates a single-use link (`/claim#<token>`, shared via WhatsApp or anything else). The relative signs in, reads a plain-language notice and gives their own consent (server-owned text, 18+ confirmation). This files a claim. Only admin approval creates a membership (the offered role, never wider than the inviter's scope) and writes a `consent_record` with basis `self`. |
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

**Open (Q13):** the lawful basis for living relatives who never claim their profile, and legal review of
the onboarding wording and its Hindi translation.

**DEFERRED:** a formal data-subject-request inbox with SLAs and a grievance officer contact
(DPDP Rules commencement is phased, so this is tracked as a legal workstream). Age-verification and
guardian-consent capture flows beyond the consent ledger are also deferred.
