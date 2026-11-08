# Hindi review checklist

**Status: not reviewed.** No native-Hindi speaker and no lawyer has approved any of this text.
- The Hindi was written during development; it has not been reviewed.
- Native-Hindi review of the priority 1–4 groups is a **pilot blocker**.
- Legal review of the consent and privacy wording is a **public-launch blocker**. It is also a
  pilot blocker if the pilot includes families outside the owner's circle (go-live checklist).
- This document records what has to be reviewed and how. Record approvals only in the sign-off
  table below, with the reviewer's name and date.

## The pack
Each review run gets a fresh pack, generated from the code:
```bash
cd backend && uv run python ../ops/i18n/hindi_review_pack.py   # writes docs/localization/hindi-review/*.csv
```
- **Contents:** every user-facing Hindi string, each exactly once, paired with its English source.
- **Sources:**
  - the SPA locale (`frontend/src/i18n/locales/hi.json`, key-identical to `en.json` by test);
  - regional kinship terms (`frontend/src/lib/kinship.ts`);
  - the server-owned consent statements (`backend/app/modules/consent/statements.py`);
  - the account emails (`backend/app/modules/identity/emails.py`);
  - Hindi written inline in SPA code.
- **Columns:** `priority, area, source, key, english, hindi, legal_review, language_ok (yes/no),
  suggested_hindi, reviewer, notes`. The reviewer fills the last four.

Pack regenerated 6 Nov 2026, after release R1: Smart Add, master data, age-aware kinship, "To complete"
and name transliteration (ADR-0025). The generator now also reads the master-data pack labels and the
name transliteration lexicon.

| Priority | Area | File | Strings | Also needs legal review |
|---|---|---|---|---|
| 1 | consent and attestation, profile claims, "remove me", erasure | `hindi-review/p1-consent.csv` | 164 | 164 |
| 2 | privacy settings and notices, sharing, public view, grants | `hindi-review/p2-privacy.csv` | 75 | 75 |
| 3 | registration, sign-in, account, invitations | `hindi-review/p3-registration.csv` | 119 | 0 |
| 4 | email verification, password reset, existing-account emails | `hindi-review/p4-email.csv` | 18 | 0 |
| 5 | family relationship labels (incl. चाचा/ताऊ, मामा, बुआ…, age-aware terms), households, branches, joint family | `hindi-review/p5-relationships.csv` | 236 | 1 |
| 5 | **name transliteration lexicon** (Latin ⇄ Devanagari pairs suggested to every family, ADR-0025) | `hindi-review/p5-name-lexicon.csv` | 340 | 0 |
| 5 | Hindi inline in the landing page code | `hindi-review/p5-inline-code.csv` | 24 | 0 |
| 6 | property, partition, land terminology | `hindi-review/p6-property.csv` | 243 | 1 |
| 7 | error messages | `hindi-review/p7-errors.csv` | 35 | 0 |
| 8 | master-data pack labels (gotra, kula, kuladevata, kuladevi, occupation, honorific, language) | `hindi-review/p8-master-data.csv` | 71 | 0 |
| 8 | everything else (dates, documents, GEDCOM, astrology, picker vocabularies…) | `hindi-review/p8-other.csv`, `p8-inline-code.csv` | 1,863 | 102 |
| | **total** | | **3,188** | **343** |

## Language review (native Hindi speaker)
Review priorities 1–4 before the pilot, and 5–7 before inviting families who will use Hindi.
For each row, check:
1. **Meaning:** it says exactly what the English says, and nothing more. This matters most for
   consent: no softening, no added promises.
2. **Register:** respectful, plain, everyday Hindi of the kind elderly family members read
   comfortably.
   - The UI uses the "आप" form and imperative "करें" (162 uses; "कीजिए" appears 3 times). Choose
     one style.
   - Avoid Sanskritised words where a common word exists, and English loanwords where a common
     Hindi word exists. Established loanwords (पासवर्ड, ईमेल, प्रोफ़ाइल) are acceptable.
3. **Gender:** first-person consent statements use "करता/करती हूँ" and "सकता/सकती हूँ". Decide
   whether the slash form is acceptable, or whether the statement should be shown in the form
   matching the user's choice. The latter is a product change, and the statement hash is per text
   (ADR-0011).
4. **Consistency:** one term per concept. Automated check, 2 Oct 2026: consistent spellings
   throughout. वंशवृक्ष 105×, प्रोफ़ाइल 50×, फ़ाइल 87×, दस्तावेज़ 44×, संपत्ति 25×, साइन इन 16×, all
   with nukta where used; no variant spellings found. Confirm वंशवृक्ष (tree) vs वंशावली (the
   product name, "genealogy") is the right split.
5. **Relationship terms (priority 5):**
   - Regional variation is expected: चाचा/ताऊ (father's younger/elder brother) is shown as both
     because the app does not know birth order.
   - Mark any term that is wrong for a major Hindi-speaking region. Do not "fix" a term to one
     region's usage silently; note the region.
6. **Property terms (priority 6):** खतौनी, जमाबंदी, खसरा, पट्टा, ROR. Use the names land records
   actually carry, in the states the pilot families come from.
7. **Placeholders:**
   - `{{name}}`, `{{count}}` and similar must survive unchanged.
   - Plural forms must read naturally for 1 and for many.
8. **Devanagari rendering:** check the screens (not only the CSV) on a phone. Look for broken
   conjuncts, clipped matras in buttons, and line breaks.

Record a "no" in `language_ok` with a `suggested_hindi`.
- **UI strings:** developers apply accepted suggestions to `hi.json`.
- **Consent statements:** changing their Hindi wording **requires a new statement version**
  (`statements.py`), because each attestation stores the SHA-256 of the exact text shown. Users
  then confirm again.

## Legal review (separate from language review)
A lawyer advising on the DPDP Act 2023 reviews the **meaning** of these texts, in both languages.
Open question Q13 in `docs/architecture/open-questions.md`. Rows with `legal_review = yes` in
the pack are:

| Text | Where | Why it needs legal review |
|---|---|---|
| Family-data attestation ("I agree to add my family members' names… I confirm I have their permission") | `statements.py` (FAMILY_DATA 2026-09-v1), onboarding screens | It is the platform's record of the contributor's confirmation. It is **not** the relatives' own consent (s.6). Is it adequate as notice and as a basis for processing relatives' data? |
| Profile-claim consent ("This profile is about me… I can withdraw this consent or ask for my profile to be erased") | `statements.py` (PROFILE_CLAIM 2026-09-v1), claim screens | A data principal's consent under s.6: specific, informed, withdrawable. Do the promises match what the product does? |
| Privacy settings, notices and the landing page's privacy claims | p2 rows, landing rows flagged | Promises must be accurate (no overstatement), e.g. "private by default" and "only family can see". |
| Erasure and "remove me" | `erase.*`, `claim*.*` | Rights under s.12 (correction and erasure). Response times and exceptions. |
| Property legal notice ("Genealogical/documentary record only — not a legal title opinion") | `property.legalNoticeFallback` and the API's `legal_notice` | Disclaimer adequacy. **Note:** the API's `legal_notice` field is English-only; the SPA shows the Hindi fallback string. |
| Email footers ("If you did not create an account, you can ignore this email") | p4 | Low risk; included for completeness. |

The lawyer's output is approved English text, approved Hindi text and any required product
changes (e.g. a separate notice to relatives). Statement text changes go through a version bump.

## Screens to check in context (with the accessibility pass)
The checklist in `docs/accessibility/manual-test-checklist.md` §3 lists the screens in Hindi
priority order. Run the language review on the live staging UI in Hindi (`/settings` → language),
not only in the CSV:
1. `/register`, `/verify-email/*`, `/login`, `/forgot-password`, `/reset-password/*`;
2. `/welcome` (onboarding and attestation);
3. the claim link page (`/claim#…`) and the claim review;
4. privacy settings on a person;
5. add-relative dialogs and the relationship calculator;
6. property pages and the partition view;
7. error states (wrong password, rate limited, offline).

## Sign-off (fill in; do not pre-fill)

| Group | Language reviewer (name, date) | Result | Legal reviewer (name, date) | Result |
|---|---|---|---|---|
| p1 consent | | | | |
| p2 privacy | | | | |
| p3 registration | | | n/a | |
| p4 email | | | | |
| p5 relationships | | | n/a | |
| p6 property | | | | |
| p7 errors | | | n/a | |
| p8 other | | | n/a | |

When a group is signed off, record it in `docs/release/production-readiness.md` and tick the
go-live checklist item.
