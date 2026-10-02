# Manual accessibility checklist (screen readers and Hindi review)

Automated checks (`e2e/tests/a11y.spec.ts`: axe WCAG 2.2 A/AA plus scripted keyboard and semantics
checks) **do not replace** these. A person has to run them before release and record the outcome in
`docs/release/production-readiness.md`. Background: `docs/accessibility/audit-2026-09.md`.

Use a fresh account and the demo tree (`python -m app.cli.seed_demo`), or a copy of real data with
consent. Record for each row: pass / fail / note, the reader and browser versions, and the date.

## 1. Screen reader matrix

| Reader | Platform and browser | Minimum to cover |
|---|---|---|
| NVDA (latest) | Windows 11, Firefox | All scenarios, English and Hindi |
| JAWS (latest) | Windows 11, Chrome | Scenarios A, C, D, F |
| VoiceOver | macOS, Safari | Scenarios A, B, C, D |
| VoiceOver | iOS, Safari | Scenarios A, C, G (mobile) |
| TalkBack | Android, Chrome | Scenarios A, C, G (mobile) |

Install a Hindi voice for each reader first (NVDA: eSpeak NG or the Windows "Hemant/Kalpana"
voices; VoiceOver: "Lekha"; TalkBack: Google TTS Hindi) and turn on automatic language switching.

## 2. Scenarios

### A. Sign up and first run
1. Open `/` signed out. The landing page has one `h1`, landmarks (banner, main, contentinfo) and a
   working "Skip to main content" link as the first Tab stop.
2. Register. After submitting, the reader announces the "Check your email" heading. Focus must not
   be lost to the page body.
3. Open the verification link. You land on the guided first run (`/welcome`). The privacy notice
   is read as text, and "I understand, continue" is a button.
4. Name the tree, add yourself with a **Devanagari** name, then add your parents. The family-data
   statement checkbox is announced with its full text, unticked, and errors on missing fields are
   announced and focused.

### B. Building the family
1. On a profile, open "Add relative" for a parent, a spouse and a child. Each dialog: focus moves
   in, Tab stays inside, Escape closes, and focus returns to the button that opened it.
2. Pick an existing person with the person picker: the number of results is announced, arrow keys
   move through options, and the chosen person is read back.

### C. Exploring the tree
1. Tree chart: arrow keys move between relatives, each node is read with name, years, status
   (living, deceased or unknown) and "minor" or "protected" where they apply. Enter opens the profile,
   Tab leaves the chart (no trap). The "Move view" buttons pan the chart.
2. Switch to the list view (`?view=list`). Devanagari and Tamil names switch to the Hindi or Tamil
   voice (they carry `lang`). **Known limit:** in the chart itself, names are part of one
   `aria-label` and cannot switch voice. Confirm the list view is a usable alternative.
3. Route changes (People → Tree → Relationship) announce the new page heading, and the browser tab
   title changes.

### D. Relationship calculator
1. Choose two people. The result ("first cousin", "मामा"…) is announced **once**, in the UI
   language. Repeat in Hindi.

### E. Documents and extraction
1. Upload an image and a PDF. Progress and the result are announced.
2. Open the extracted-values review. Each proposal can be accepted, edited or rejected by
   keyboard, and its status is spoken in words, not colour alone.
3. Image previews are named "Preview of ‹title›". For scanned text, the OCR tab is the text
   alternative.

### F. Property partition wizard
1. Each step has a heading, fractions are read meaningfully ("one third"), and validation errors
   are linked to their fields.

### G. Mobile (iOS VoiceOver and TalkBack)
1. The bottom navigation is reachable by swipe and its items are named. **Known issue:** "More"
   is not marked as current when the current page is one of its items.
2. Focus is never hidden under the bottom bar while moving through a long form.
3. At 200% text size, nothing is cut off and there is no sideways scrolling.

### H. Also check by hand
- Windows High Contrast (forced colours): chart status bars stay distinguishable (they differ by
  shape, not only colour).
- Text spacing (WCAG 1.4.12): apply the bookmarklet. No text is clipped.
- Session expiry: an expired session sends you to sign-in and returns you to the same page after.
  There is no advance warning yet (WCAG 2.2.1); record that this was observed.
- Badge hints (privacy, evidence) are `title` tooltips and hover-only. Confirm the visible badge
  text carries the essential meaning.

## 3. Native-Hindi review

A native Hindi speaker should review these, highest priority first. The automated checks only
prove a translation **exists** for every key (1,809 Hindi strings; only `documents.ocr`, "OCR", is
the same as English). They say nothing about whether it is correct, natural or legally accurate.

| Priority | Screen or text | Where it lives | Why it matters |
|---|---|---|---|
| 1 | Family-data statement and profile-claim consent wording | `backend/app/modules/consent/statements.py` (server-owned, versioned, hashed) | Legal meaning (DPDP; ADR-0011, open question Q13). Needs a **legal** review of the Hindi text too, not only language. |
| 1 | Account emails: verification, "someone tried to register", password reset | `backend/app/modules/identity/emails.py` | Security wording; users act on it. |
| 2 | Onboarding (`/welcome`) and the claim-link page (`/claim`) | `onboarding.*`, `claimLink.*`, `claimInvite.*`, `consent.*`, `privacy.*` | First impression and consent. |
| 2 | Kinship terms and relationship results | `kin.*`, `relationship.*`, `relatives.*`, `family.*` | Indian kinship words (मामा, बुआ, चाचा…) must match the relationship exactly. |
| 2 | Privacy levels, erase and grants | `privacy.*`, `erase.*`, `grants.*`, `enum.privacyLevel*` | Users choose who can see living relatives. |
| 3 | Property and partition | `property.*`, `partition.*`, `lineage.*` | Legal and land-record terms (खसरा, खतौनी, बँटवारा). |
| 3 | Heritage, astrology, dates and times | `heritage.*`, `astrology.*`, `date.*`, `time.*`, `enum.*` | Gotra, nakshatra and rashi names; calendar wording. |
| 3 | Landing page | `landing.*` | Public text. |
| 4 | Everything else | `hi.json` | General UI. |

Also check the **accessible names** in Hindi (button labels, chart node labels, live-region
messages). These are what screen readers speak, and some never appear on screen.

## 4. Recording results

Add one row per reader to the "Accessibility" section of `docs/release/production-readiness.md`.
Open an issue for every failure, with the scenario number, reader, browser and steps to reproduce.
