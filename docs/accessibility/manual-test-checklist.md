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
1. The bottom navigation is reachable by swipe and its items are named. When the current page is
   one of the "More" items, "More" is announced as current (fixed 1 Oct 2026, `TreeLayout.test.tsx`;
   confirm with the reader).
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

## 4. Pilot verification pack (October 2026)

Run this before inviting pilot families. Use the **staging** environment, a fresh account and the
demo tree. **Nothing below has been run yet.** Automated tests (axe, keyboard and semantics checks
in `e2e/tests/a11y.spec.ts`) pass, but they do not substitute for these checks.

### Matrix for the pilot

| # | Reader | Browser / platform | Scenarios | Languages |
|---|---|---|---|---|
| P1 | NVDA (latest) | Chrome, Windows 11 | A, I, J, B, C, E, F | en + hi |
| P2 | NVDA (latest) | Firefox, Windows 11 | A, C, D, J | en |
| P3 | JAWS (latest) | Chrome, Windows 11 | A, C, E, F | en |
| P4 | JAWS (latest) | Edge, Windows 11 | A, I, J | en |
| P5 | VoiceOver | Safari, macOS | A, B, C, D, I | en + hi |
| P6 | VoiceOver | Safari, iOS | A, C, G | en |
| P7 | TalkBack | Chrome, Android | A, C, G, J | en + hi |

**Pilot minimum:** P1, P5 and P7. The rest is required before public launch (go-live checklist).

### Flows to cover (mapped to the scenarios)

| Flow | Scenario | What to listen for |
|---|---|---|
| Login | A + below | labels read; wrong password announced and focused; "Forgot password" reachable |
| Registration | A.2 | each field's label and requirement read; password rules announced before submit; "Check your email" heading announced |
| Consent (family-data statement, profile claim) | A.3–A.4, claim page | the **whole statement** read before the checkbox; the checkbox unticked by default; claim page usable without sight |
| Create tree | A.4 | the name field labelled; success announced; focus moves to the new tree |
| Add person | A.4, B.1 | dialogs trap focus and return it; Devanagari names switch voice in lists |
| Family-tree navigation | C | arrow keys in the chart; list view as the alternative; route changes announced |
| Forms (dates, places, privacy) | B, F | date precision explained; errors linked to fields; required fields marked in text |
| Documents | E | upload progress and scan result announced; previews named; OCR text reachable |
| Property | F | fractions read meaningfully; the legal notice read; parcel tables have headers |
| Search | I (below) | result count announced; results reachable by heading or list navigation; "no results" announced |
| Error states | J (below) | every error reaches the reader without moving the mouse |

### I. Search
1. Use the global search with a Latin name, then with a Devanagari name. The number of results is
   announced (live region). Results are a list with names and life years, and the person's
   privacy hides living details as it does on screen.
2. A search with no results announces "no results" and keeps focus in the search box.

### J. Error states
1. Wrong password: the error is announced and focus lands on it or on the field. Repeat until
   rate-limited: the "too many attempts" message is announced and says when to retry.
2. Submit an empty required field in "Add person": the error is announced and linked
   (`aria-describedby`), and focus moves to the first invalid field.
3. Go offline (airplane mode) and save: the network error is announced, and nothing is silently
   lost.
4. Open a tree you are not a member of (a copied URL): the "not found" page has a heading and a
   way back.
5. Upload a file that is too large or of an unsupported type: the reason is announced.

## 5. Recording results

Fill in this table, then add a summary row to `docs/release/production-readiness.md`. Leave a
row empty until someone has run it. **Never pre-fill a result.**

| # | Tester | Date | Reader + version | Browser + version | Scenarios run | Pass / fail / blocked | Issues opened |
|---|---|---|---|---|---|---|---|
| P1 | | | | | | | |
| P2 | | | | | | | |
| P3 | | | | | | | |
| P4 | | | | | | | |
| P5 | | | | | | | |
| P6 | | | | | | | |
| P7 | | | | | | | |

The Hindi language review has its own pack and sign-off: `docs/localization/hindi-review-checklist.md`.
Open an issue for every failure, with the scenario number, reader, browser and steps to reproduce.
