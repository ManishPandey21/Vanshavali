# Vanshavali — Family Profiles, Birth Details, Smart Indian Addresses, Ancestral Villages, Contacts, Invitations & Multichannel Reminders

**Repository:** `ManishPandey21/Vanshavali`

## Objective

Perform a comprehensive audit, design and phased implementation of an enhanced **Family Member Profile and Communication Management System** for Vanshavali.

The goal is to make it easy for families in India and abroad to maintain accurate personal details, contact information, present and historical addresses, ancestral villages, social profiles, invitations and family-event reminders.

The solution must integrate seamlessly with Vanshavali's existing genealogy engine, person records, India geography reference data, privacy model, invitation services and notification scheduler.

**Important principles:**

1. Reuse existing functionality rather than creating duplicate data models or services.
2. Provide simple, responsive interfaces suitable for both elderly users and younger family members.
3. Support English, Hindi and extensible regional-language interfaces.
4. Preserve historically accurate information, including former village and district names.
5. Never infer personal facts from surnames, kinship relationships, geography or other family members.
6. Protect personal information through field-level permissions, consent and server-side authorization.
7. All changes must be auditable and must respect the existing family review process.
8. Start with design and architecture verification before coding.

---

## Phase 1 — Repository Audit and Existing Feature Assessment

Read:

- `CLAUDE.md` and applicable repository instructions.
- ADR-0003 — Genealogy relationship and event model.
- ADR-0006 — Authorization and privacy.
- ADR-0011 — Onboarding and family invitations.
- ADR-0015 — Life events, places and photo albums.
- ADR-0016 — Event reminders and notifications.
- ADR-0018 — Master data vocabularies.
- ADR-0019 — Indian geography reference data and place cascades.
- ADR-0020 — Smart Add Relative and provisional people.
- ADR-0021 — Family review and change proposals.
- ADR-0022 — Family calendar and tithi reminders.
- ADR-0027 — Record visibility and selective sharing.
- Relevant newer ADRs, open PRs, threat-model entries and implementation-status documentation.

Verify the latest `main`, Alembic migration head, ongoing branches and feature implementations.

Examine existing modules for:

- Person creation and editing.
- Birth, death and marriage events.
- Birth date and birth time.
- Person addresses and places.
- LGD reference-data integration.
- PIN-code lookup and PlaceCascade.
- Family branches and households.
- Private contact details.
- Account contact verification.
- Family invitations.
- Birthday and anniversary reminders.
- Notification providers.
- Existing UI forms and reusable components.

Prepare a detailed **Existing / Missing / Needs Improvement / Reuse** matrix.

Do not duplicate existing genealogy events, place tables, address functionality or notification services.

---

# Phase 2 — Enhanced Family Member Profile

Create or improve a unified **View / Edit Family Member Profile** interface.

The profile should organize information into understandable sections.

### A. Personal Information

Support:

- Full name.
- Alternative names.
- Name in Hindi or regional script.
- Preferred/display name.
- Gender, optional and never inferred.
- Relationship to other family members.
- Family branch.
- Household.
- Living/deceased/unknown status.
- Profile verification status.
- Supporting documents where applicable.

### B. Birth Date — View and Edit

Provide an explicit **Edit Birth Date** action.

Support:

- Date picker.
- Manual date entry.
- Day, month and year.
- Year-only date.
- Month and year.
- Approximate date.
- Before/after date.
- Unknown or withheld.
- Optional Gregorian/lunar display where supported by existing calendar rules.

**Rules:**

1. Reuse the existing birth event as the source of truth.
2. Do not create a separate, contradictory date-of-birth field.
3. Preserve incomplete dates exactly as recorded.
4. Never invent missing day/month components.
5. Keep competing or disputed historical evidence where the existing genealogy model supports it.
6. Apply date-specific privacy restrictions.
7. Record the editor, timestamp and change history.
8. Use the existing change-proposal and review workflow where required.
9. Show the birthday reminder option only when the available date is sufficient for that reminder rule.

Provide a clearly visible **Edit Date of Birth** action on the profile.

### C. Birth Time — View and Edit

Provide an explicit **Edit Birth Time** action.

Support:

- Hour and minute.
- 12-hour and 24-hour input.
- AM/PM selection.
- Unknown time.
- Approximate time.
- Optional seconds where a source supports them.
- Optional source/reference.
- Time zone or UTC offset where known.

Birth time is sensitive personal information.

It must have stricter privacy controls and must not become visible merely because another member can see the birth date.

Do not automatically generate a birth time from astrology, a Rashi, a Nakshatra or any other inferred information.

Do not reinterpret a historical local time as an exact UTC instant without adequate time-zone evidence.

### D. Birthplace

Support:

- Country.
- State/Union Territory.
- District.
- Sub-district / Tehsil / Taluk.
- City / Town / Village.
- Birthplace or hospital, optional.
- PIN code, if known.
- Historical/local place name.

Allow a birthplace to reuse an existing place reference without forcing it to share the person's present postal address.

---

# Phase 3 — Smart Indian Address Management

Implement or improve a reusable **Smart Address Form**.

## A. Address Fields

Support:

1. Country.
2. State / Union Territory.
3. District.
4. Sub-district / Tehsil / Taluk.
5. Gram Panchayat, where supported by verified reference data.
6. City / Town / Village.
7. Locality / Area.
8. Street / Road.
9. House / Flat / Building number.
10. Landmark.
11. Post office.
12. PIN code.
13. Address label or type.
14. Additional address notes, optional.

The form must work for urban and rural Indian addresses.

Do not require a house number or road name for rural villages that do not use them.

For addresses outside India, support country-appropriate free-text/local address fields rather than requiring an Indian six-digit PIN.

## B. Dependent Dropdowns

Implement cascading selections:

**Country → State → District → Sub-district/Tehsil → City/Town/Village → Locality/Post Office → PIN Code**

Behavior:

- Selecting India enables Indian reference-data suggestions.
- Selecting a State filters Districts.
- Selecting a District filters sub-districts and cities/villages.
- Selecting a Village or City presents matching PIN/post-office candidates.
- A searchable dropdown must support English, Hindi and available local spellings.
- Include a clear **"My village/city is not listed"** option.
- Allow a user to retain a historical or alternate name.

Use the existing ADR-0019 geography model and APIs rather than introducing another independent geography database.

## C. Automatic Address Suggestions from PIN Code

**High-priority requirement:**

When a user enters a valid Indian six-digit PIN code, the application should automatically look up the corresponding geographic reference information.

Suggested flow:

1. User enters PIN code.
2. System validates that it has six digits.
3. System queries the available India Post reference dataset.
4. Display matching State, District, Post Office and City/Locality candidates.
5. Auto-select unambiguous values.
6. If multiple post offices or localities share the PIN, ask the user to choose.
7. Allow the user to confirm or correct the suggested details.

**Important:**

A PIN code does not uniquely determine an individual's exact city, village or physical address.

Do not silently assume a village or street from PIN code alone.

Never overwrite user-entered address values without confirmation.

If the PIN code conflicts with a selected State/District, display a clear warning and provide correction options.

If the source dataset is unavailable or has not been approved for use, retain manual address entry.

## D. Reverse Lookup

Also support:

- State → District → City/Village → possible PIN codes.
- City/Village name search → matching districts.
- PIN code search → post offices and geographic suggestions.
- Historical name search where reference aliases exist.

Show useful disambiguation when two villages share the same name.

## E. Geography Source and Data Quality

Prefer the existing LGD and India Post snapshot architecture.

Requirements:

- No duplicate importer.
- Preserve original LGD codes where available.
- Preserve snapshot provenance and date.
- Respect existing licensing and attribution gates.
- Do not import unapproved official datasets.
- Do not automatically overwrite historical family place names.
- Use a controlled fallback when master data is incomplete.

---

# Phase 4 — Multiple Addresses for Each Family Member

Every family member must be able to maintain **more than one address**.

## Address Types

Support:

- Current residential address.
- Permanent address.
- Previous residential address.
- Ancestral village / ancestral home.
- Native place.
- Birthplace.
- Correspondence address.
- Other address.

Do not make all address types mandatory.

### A. Add New Address

Provide an **Add Address** button.

The user selects an address type, enters the information through the Smart Address Form, and saves it with appropriate privacy controls.

### B. Edit Existing Address

Provide **Edit Address** and **Delete/Remove Address** actions, subject to permissions.

For a current address that changes, provide:

- Replace existing address.
- Move existing address to address history and add a new current address.
- Correct an erroneous address entry.

Preserve the previous address by default when a member moves residence.

Do not silently erase historical information.

### C. Address History

Support:

- Valid from date.
- Valid until date.
- Current / Former status.
- Historical or approximate dates.
- Optional relocation reason.
- Source or evidence.
- Updated by and updated at.

Display previous residences chronologically where dates are known.

### D. Location of Each Member

Each person's profile should show their **Current City and State**, where that information is available and the viewer is authorized to see it.

The UI may display:

- Current location: Lucknow, Uttar Pradesh.
- Native place: Varanasi, Uttar Pradesh.
- Ancestral village: a separately recorded village.
- Previous cities: where the member has agreed to make them visible.

Do not expose the full street address merely to show the city.

Allow city-level visibility to be controlled independently from full address visibility.

Do not use a device's live location without an explicit, separate user request and permission.

---

# Phase 5 — Ancestral Village and Family Address Reuse

This is a core Vanshavali feature.

Many family members share the same ancestral village or ancestral household address.

The application must avoid asking every relative to enter the same information repeatedly.

## A. Ancestral Village Record

Support a structured ancestral place containing:

- Ancestral village name.
- Alternative/local name.
- Village in Hindi or regional script.
- State.
- District.
- Tehsil / Sub-district.
- Gram Panchayat where known.
- PIN code where known.
- Historical village or district name.
- Associated family branch.
- Ancestral house or property name.
- Historical period, optional.
- Supporting records and sources.
- Optional family history or description.

Preserve historical names separately from modern administrative identifiers.

For example, an ancestor's record may use an older district name while today's LGD reference identifies its present district.

Do not replace either value automatically.

## B. Reuse Existing Family Addresses

When adding or editing an address, offer:

**Choose Address Source**

- Enter a new address.
- Use an existing family address.
- Use an existing ancestral village.
- Use my current address.
- Use my permanent address.
- Use an authorized address from another family member.
- Copy an existing address and modify it.

The address picker must be searchable.

It should display only addresses and ancestral places the acting user has permission to view.

Suggested grouping:

- My Addresses.
- Family Shared Addresses.
- Ancestral Villages.
- Family Branch Addresses.
- Recently Used Addresses.

## C. Reuse Without Unwanted Synchronization

Distinguish clearly between:

**Link to Existing Place**

Multiple relatives refer to one canonical geographical or family address record.

**Copy Address**

The address is copied into a new, independently editable record.

**Create a New Address**

A completely new entry is created.

Do not assume editing one person's private residential address should update every relative who previously copied it.

Where shared records exist, use explicit confirmation before changes affecting multiple people.

For historical records, preserve the address details as they were recorded at the relevant time.

## D. Ancestral Village Inheritance

Allow a family branch to define a suggested ancestral village.

When a person is added through Smart Add Relative, the system may offer:

"Use the ancestral village already recorded for this family branch?"

The user can:

- Accept the suggestion.
- Choose another recorded ancestral village.
- Enter a new village.
- Leave the field unknown.

**Never infer or automatically assign an ancestral village based solely on surname, Gotra, caste, kinship or family branch.**

An ancestral village is a recorded fact, not a mandatory inherited identity.

## E. Genealogy and Property Integration

Where appropriate:

- Link an ancestral village to family branches.
- Link an ancestral house to existing ancestral property records.
- Show authorized relatives associated with a place.
- Preserve migration and relocation history.
- Avoid creating duplicate property ownership facts.
- Never infer ownership rights merely because a person is linked to an ancestral house.

---

# Phase 6 — Contact and Social Profiles

Support optional contact details for each family member:

- Email address.
- Mobile phone.
- WhatsApp number.
- Checkbox: "WhatsApp number is same as mobile."
- Telegram username.
- Instagram username.
- Preferred contact language.
- Preferred notification channel.

Keep contact information associated with a genealogy person separate from the verified messaging endpoints of a signed-in user.

A relative's contact details entered by another member are not automatically verified or consented to.

Use encrypted storage and masked responses where appropriate.

Restrict contact visibility according to the existing field-level privacy and authorization rules.

Provide appropriate editing and verification flows for claimed profiles.

---

# Phase 7 — Unified Family Invitations

Build a single **Invite Family Member** interface.

Support:

- Invite by email.
- Share invitation through WhatsApp.
- Share invitation through Telegram.
- Copy invitation link.
- Automated WhatsApp invitation after provider approval and recipient consent.

Reuse `tree_invitation` and `profile_claim_invite`.

The invitation must not automatically grant family-tree access merely because someone possesses a link.

Preserve existing claim, consent, identity confirmation and administrator approval requirements.

Show invitation status where reliably available:

- Created.
- Sent.
- Accepted.
- Expired.
- Revoked.
- Failed.

A submitted phone number or social username is not proof of identity.

Avoid leaking private family details into link previews or forwarded invitation messages.

---

# Phase 8 — Birthday, Wedding Anniversary and Family Reminders

Extend the existing reminder system.

Support:

- Birthdays.
- Wedding anniversaries.
- Punyatithi.
- Family festivals.
- Custom family occasions.
- Gregorian recurrence.
- Lunar recurrence only where ADR-0022 approvals and activation gates permit it.

### Reminder Preferences

Each member can choose:

- On the day.
- 1 day before.
- 7 days before.
- Custom lead time where supported.
- Preferred notification hour.
- Preferred time zone.
- Preferred language.
- One or more permitted notification channels.

### Integration With Birth Details

When the birth date changes:

- Validate and update affected birthday reminders.
- Recalculate future delivery dates.
- Prevent duplicate reminders.
- Preserve incomplete-date semantics.
- Respect privacy and authorization immediately.

Birth time should not be needed merely to send a birthday reminder.

### Marriage Anniversary

Reuse marriage events and the associated participants.

Handle multiple marriages, incomplete dates and disputed dates without guessing.

Do not create conflicting independent marriage-date fields.

### Privacy

Reminders belong to the subscribing user.

An administrator cannot silently subscribe another adult.

Recheck event/date visibility, contact verification, channel consent and membership immediately before delivery.

Use the existing scheduler, delivery records, retry logic and notification preferences.

---

# Phase 9 — Messaging Integrations

## Email

Reuse the existing verified-email and SMTP infrastructure.

## Telegram

Use the official Telegram Bot API.

A user must initiate bot interaction and authorize account linking.

Store a verified chat identifier for delivery; the username alone is insufficient.

Support unlinking and revocation.

## WhatsApp

Reuse the existing Meta WhatsApp Cloud API adapter.

Verify current Meta requirements, template categorization, pricing and recipient opt-in before activation.

Use approved, purpose-specific templates.

Do not use unofficial WhatsApp Web automation.

## Instagram

Store an optional username and provide an appropriate profile link.

Do not assume the username authorizes proactive DM reminders.

Evaluate official messaging APIs separately.

## SMS

Reuse the existing SMS provider abstraction.

Review applicable Indian DLT and consent requirements before sending production traffic.

## Chatwoot

Do not add Chatwoot to the primary notification architecture.

Evaluate it later only if a unified human-support inbox or two-way conversation feature is required.

---

# Phase 10 — Privacy, Authorization and Data Protection

Apply deny-by-default authorization.

### Birth Details

- Full birth date may be restricted.
- Birth time may have an even stricter visibility policy.
- Incomplete dates must not be inferred or expanded.
- Changing an event should use existing review and revision controls.

### Address Privacy

Allow separate visibility for:

- Current city/state.
- Full current address.
- Former addresses.
- Ancestral village.
- Ancestral house details.
- Contact information.

An ancestral village shared at branch level must not inadvertently expose an individual's residential address.

Reusing another member's address must not bypass their privacy settings.

Do not assume ADR-0027's record-only privacy levels can be assigned directly to person fields. Extend the appropriate existing field-level privacy model instead.

### Contact and Invitations

Separate:

- Profile contact data.
- Verified notification endpoints.
- Consent to receive invitations.
- Consent to receive reminders.
- Consent for each external messaging channel.

No role, including Super Admin, should automatically obtain access to private personal contact information.

### General Security

Require:

- Tree isolation and RLS.
- Cross-tree IDOR/BOLA testing.
- Server-side authorization on every read/write.
- Audit logs without sensitive field values.
- No sensitive data in delivery logs.
- Rate limits and abuse controls.
- Consent withdrawal.
- Safe migration and rollback.
- Protection for minors and living relatives.
- No unsafe inference from kinship or cultural information.

---

# Phase 11 — User Interface and Experience

Create or improve the Family Member Profile with these tabs or sections:

1. **Personal Details** — Name, birth date, birth time, birthplace.
2. **Family Relationships** — Parents, spouses, children and other relatives.
3. **Addresses & Locations** — Current, permanent, previous, ancestral.
4. **Contacts & Social Profiles** — Email, mobile, WhatsApp, Telegram, Instagram.
5. **Family Events** — Birthday, marriage anniversary and other important dates.
6. **Invitations & Membership** — Join invitations and claim status, where authorized.
7. **Privacy & Permissions** — Who can see and edit information.
8. **History & Sources** — Changes, evidence and genealogy provenance.

### Essential Actions

Provide clear actions for:

- Edit birth date.
- Edit birth time.
- Edit birthplace.
- Add an address.
- Edit an address.
- Move a current address to history.
- Select an existing family address.
- Select an ancestral village.
- Copy another authorized address.
- Invite a family member.
- Set birthday reminder.
- Set anniversary reminder.
- Change contact preferences.

### Smart Address User Journey

Example:

**Add Address → India → Enter PIN 226001 → Show matching State, District and Post Offices → Select appropriate locality → Complete street details → Save**

This is a suggested flow, not permission to infer an exact street or residence.

The same form should allow:

**Add Address → Use Existing Family Address → Choose Ancestral Village → Confirm → Save**

The entire interface must be responsive, accessible and usable on mobile devices.

---

# Phase 12 — Architecture and Data Model

Before designing new tables, identify which existing models already satisfy the requirements.

Prefer reuse of:

- `person`
- `event`
- `place`
- `family_branch`
- `household`
- `tree_membership`
- Existing source and citation models
- Existing geography tables and APIs
- `notification_contact`
- `notification_preference`
- `event_reminder`
- `notification_delivery`
- Existing invitation models

Consider new tables only for genuinely missing behavior, such as:

- Multiple person-address associations with purposes and validity periods.
- Reusable family/branch address records.
- Verified external notification endpoints.
- Optional person contact methods not already represented.
- Historical address revision data where the existing event model is insufficient.

Avoid storing the same birth date, birth time or marriage date independently in multiple modules.

Define ownership, uniqueness, privacy, historical validity, referential integrity and deletion rules.

Ensure new models support migration from existing data without breaking existing person profiles or events.

Document the choice between referencing a shared address and copying it.

---

# Phase 13 — Implementation Strategy

Split development into focused, independently testable PRs.

| Increment | Scope | Priority |
|---|---|---|
| PR A | Profile editing: birth date, birth time and birthplace | P0 |
| PR B | Smart Indian Address Form, dependent dropdowns and PIN lookup | P0 |
| PR C | Multiple addresses, history and address editing | P0 |
| PR D | Ancestral village and reusable family addresses | P0 |
| PR E | Contact details and social profiles | P0 |
| PR F | Unified family invitations | P1 |
| PR G | Birthday and anniversary reminder UX improvements | P1 |
| PR H | Telegram integration | P2 |
| PR I | WhatsApp provider readiness and approved templates | P2 |
| PR J | Optional SMS and Instagram/Chatwoot evaluation | P3 |

Build on the latest accepted migrations and ensure one Alembic head.

Never independently introduce an address/geography schema that duplicates a merged or active implementation.

### Required Tests

**Backend:**

- Birth date edit and privacy.
- Birth time edit and privacy.
- Partial/approximate birth dates.
- Birth and marriage event consistency.
- PIN lookup with one and multiple post offices.
- Unknown and invalid PIN codes.
- State/District/City cascade.
- Historical village preservation.
- Adding multiple addresses.
- Reusing or copying existing addresses.
- Address history after relocation.
- Duplicate-place prevention.
- Branch-scoped and cross-tree authorization.
- Private address leakage prevention.
- Reminder recalculation following date edits.
- Invitation permissions and consent.

**Frontend:**

- Profile editor.
- Date/time input.
- Dependent dropdowns.
- PIN-code lookup.
- Address selection and reuse.
- Multiple-address editing.
- Hindi labels and search.
- Privacy controls.
- Invitations and reminders.

**E2E:**

1. Create a family member → edit birth date/time → save → reopen and verify.
2. Add current address using PIN lookup.
3. Change current address → verify previous address preserved.
4. Add an ancestral village → reuse it for another authorized member.
5. Attempt unauthorized access to a private address → access denied.
6. Invite a relative → complete the approved joining flow.
7. Set a birthday reminder → edit the birth date → verify scheduling updates.
8. Create a marriage event → set anniversary reminder.
9. Verify member visibility is not broadened by administrative role changes.

Run all relevant linting, type checks, backend tests, frontend tests, E2E tests, migrations and security checks.

---

# Phase 14 — Deliverables

Produce:

1. **Repository audit** identifying existing and missing functionality.
2. **Feature-gap matrix** with recommended reuse of existing modules.
3. **Detailed user experience and form designs.**
4. **Smart Indian address architecture**, including PIN-to-State/District/Locality lookup.
5. **Ancestral village and address-reuse model.**
6. **Data-model and migration design.**
7. **Privacy and authorization analysis.**
8. **New ADR or carefully scoped amendments**, after checking existing numbering.
9. **Threat-model entries** allocated without conflicting with open branches.
10. **Implementation sequence and dependencies.**
11. **Acceptance-test matrix.**
12. **Final recommended development plan.**

## Execution Instructions

Start by inspecting the live repository and current implementation.

Do not assume a feature is absent merely because it was missing in an older PR.

Use existing approved geography datasets and APIs when available.

Do not invent geographical reference data or claim a PIN uniquely identifies an address.

Prefer small reusable components and focused backend services.

Do not silently widen privacy permissions.

Keep the design phase separate from production implementation.

Prepare an ADR and concrete implementation plan first, including proposed UI behavior, schema changes and integration points.

Do not merge, deploy, enable external notification providers or send actual invitations until the relevant approvals and verification requirements are satisfied.

**Success criterion:**

A Vanshavali member can view and edit authorized birth details, maintain multiple current and historical addresses, find an Indian locality using a PIN code, select previously recorded ancestral villages or shared family addresses, manage permitted contact details, invite relatives and receive personalized birthday and marriage-anniversary reminders—all without duplicating genealogical records or compromising family privacy.