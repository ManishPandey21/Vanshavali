# ADR-0022: Indian family calendar: tithi dates, Punyatithi reminders, family calendar and ICS feed

- Status: Proposed · Date: 2026-11-08 · Release: R5 (first ADR of R5)
- Relates to: ADR-0016 (reminders: opt-in, visible dates only, re-check at send time),
  ADR-0015 (life events), ADR-0006 (privacy, field groups), ADR-0021 (provenance of calculated
  values, review), ADR-0025 (a calculated suggestion is confirmed, never applied), Q6, Q16
- Plan: [india-master-data-and-smart-forms-plan.md](../india-master-data-and-smart-forms-plan.md),
  release R5, phase H. The other R5 phases get their own ADRs: oral history (ADR-0023), the family
  book (phase K) and elder-friendly mobile (phase L).

## Context
- **Families remember dates by tithi.** A grandparent's death is remembered as "Bhadrapada Krishna
  Ashtami", and the annual Punyatithi or Shraddha is observed on that tithi, not on the Gregorian
  date. For many older ancestors the tithi is the only date anyone knows.
- **What exists today:**
  - `GenealogicalDate` keeps a `calendar` (Gregorian, Julian, Vikram Samvat, Shaka, Hijri, other),
    a precision and the original text. It has no lunar month, paksha or tithi.
  - Reminders (ADR-0016) are solar only. Lunar anniversaries were explicitly deferred. The
    `memorial` reminder kind and the `memorial` life-event category exist.
  - Places can carry coordinates; events can carry an IANA time zone.
  - There is no calendar view and no calendar feed.
- **Two open questions gate this work:**
  - **Q16, the engine.** A tithi needs the Sun's and Moon's positions. Swiss Ephemeris and its
    Python binding `pyswisseph` are AGPL-3.0 (or a paid licence). AGPL would reach the whole
    networked backend.
  - **Q6, conventions.** Which month system (amanta or purnimanta), which day rule, which regional
    calendars. The plan says this phase implements whatever Q6 decides and does not decide it alone.
- **A feasibility spike (8 Nov 2026)** used Skyfield 1.55 (MIT, per its PyPI metadata), jplephem
  (MIT) and NASA JPL's DE440s ephemeris (32 MB). It computed 366 sunrises for Varanasi and the tithi
  at each in 1.5 s. This shows the approach is fast enough. **It does not show accuracy**: nothing
  was compared with a published panchang yet.

## Decision

### 1. Engine (proposed answer to Q16)
- **Skyfield + jplephem + JPL DE440s**, pinned versions, the ephemeris file checksummed and shipped
  with the backend image (no download at run time). No Swiss Ephemeris, no AGPL code.
- **The licence review still happens before lunar reminders are switched on.** Skyfield and jplephem
  report MIT on PyPI. The terms of use of the JPL ephemeris file must be confirmed by the owner
  (and counsel if needed). Until signed off, the engine ships disabled (§8).
- **What the engine computes, nothing more:**
  - local sunrise (and the day parts derived from sunrise and sunset) for a place and date;
  - the tithi (Moon–Sun elongation in 12° steps) at any instant, and its start and end;
  - the lunar month: new moon to new moon (amanta) or full moon to full moon (purnimanta), named by
    the sidereal solar sign at its new moon; an adhik (extra) month is a lunar month with no solar
    sankranti; a kshaya month the reverse. The sidereal positions use the **Lahiri (Chitrapaksha)
    ayanamsa**, the one the Indian Calendar Reform Committee adopted. The tithi itself does not
    depend on the ayanamsa.
  - No horoscope, no nakshatra-based predictions, no muhurta. Q9 (no chart computation) stands.

### 2. Lunar dates on `GenealogicalDate`
- An optional `lunar` component: `masa`, `paksha` (shukla, krishna), `tithi` (1–15, with Purnima
  and Amavasya), `is_adhik`, `month_convention` (amanta, purnimanta), `samvat` (Vikram, Shaka) and
  year when known. The original text is always kept, as today.
- **A lunar date never fills in a Gregorian one, and vice versa.** Converting is a calculation:
  - offered as a suggestion ("Bhadrapada Krishna Ashtami, VS *year*, was probably *weekday, day
    month year*, computed for Varanasi, purnimanta"), stating the convention and place it used;
  - stored only if the user accepts it, with provenance `calculation` and the convention, place
    and engine version, exactly as an accepted transliteration is (ADR-0025);
  - a year-less lunar date ("Ashtami of Bhadrapada Krishna") is valid on its own and is enough for
    an annual reminder.
- Entering a lunar date is available as soon as this ships; conversion follows the engine gate (§8).

### 3. Conventions (proposed answer to Q6)
A **convention** is a named, code-reviewed setting, chosen per tree with a per-reminder override:

| Convention | Month system | Annual observance falls on | Regions (default suggestion only) |
|---|---|---|---|
| `purnimanta` | full moon to full moon | the tithi, by the day rule | most of North India (UP, Bihar, MP, Rajasthan, Punjab, Haryana, Himachal, Jharkhand, Chhattisgarh) |
| `amanta` | new moon to new moon | the tithi, by the day rule | Maharashtra, Gujarat, Karnataka, Andhra Pradesh, Telangana, Goa |

- **Day rule** (which civil day a tithi "falls on"), a field of the convention:
  - `sunrise` (*udaya tithi*): the tithi in force at local sunrise. Used for birthdays by tithi.
  - `aparahna`: the tithi in force during the afternoon (the fourth of five parts of daylight).
    Proposed default for Punyatithi and Shraddha.
  - Tie rules (the tithi touches the period on two days, or on none because it is *kshaya*) are
    written down per rule and golden-tested.
- **Adhik masa:** an anniversary of a death in an ordinary month is observed in the ordinary
  (*nija*) month of that name, not in the adhik month before it. A death that happened in an adhik
  month is observed in the nija month of the same name in years without one. Practices differ
  (for example for the first anniversary), so this is a convention field, not a hard rule.
- **Regional solar calendars** (Tamil, Malayalam/Kollam, Bengali, Odia) and nakshatra-based
  observances (common in Kerala) are **out of this ADR**. They need their own golden tables and
  reviewers and are added later as further conventions, by demand (as with kinship packs, Q14).
- **No convention is inferred** from a surname, a place or a community. A tree admin picks the
  tree's convention; each member may override it on their own reminders.

### 4. Place of observance
- A tithi depends on where sunrise is. Every lunar reminder states its **place of observance**:
  - a tree place with coordinates (the family's home, for example), or
  - a city from a small code-reviewed list of Indian and diaspora cities with coordinates and time
    zones (`calendar/cities.json`).
- Default: the tree's observance place, set by a tree admin; else the member must choose one.
- The place's coordinates are used only for the calculation and are never shown beyond what the
  place itself already shows.

### 5. Reminders
- `event_reminder` gains `date_rule` (`solar`, the current behaviour, or `lunar`), plus `convention`
  and `observance_place` for lunar reminders. Everything else in ADR-0016 holds: opt-in, per member,
  visible dates only, re-check at send time, minimal content on SMS and WhatsApp.
- **The lunar date must be visible to the member**, like the solar date today.
- **The message states how the date was found:** "Punyatithi of Ram Sharma: *weekday, day month
  year* (Bhadrapada Krishna Ashtami, purnimanta, afternoon rule, Varanasi)". SMS and WhatsApp keep
  only the kind, the date and a link.
- **The next date is computed ahead**: when a reminder is created and each year after it fires,
  never on the request path for many reminders at once.

### 6. Calculated days are cached, not recomputed
- A global, read-only table `panchang_day` (date, place key, sunrise, tithi at sunrise, tithis
  touching the day with their times, masa, adhik flag, engine and ephemeris version), filled by an
  operator CLI or a background job per place and year. Like the LGD tables (ADR-0019), the
  application role can only read it.
- Recomputing after an engine update is a versioned refresh; reminders already scheduled keep the
  date they announced unless it changed, and a change is shown on the calendar.

### 7. Family calendar page and ICS feed
- **Family calendar:** a month and list view of upcoming birthdays, anniversaries and Punyatithis
  (solar and lunar), plus events with a future date. Same visibility as reminders: a living
  person's date shows only if the member may see the full date.
- **ICS feed:** one feed per member per tree, behind a 256-bit random token (stored hashed),
  revocable and replaceable in one click.
  - Each fetch is evaluated as that member at that moment: if they lost access, the feed is empty.
  - **Minimal by default:** "Punyatithi", "Birthday" and a link, no names, because the feed is read
    by a third-party calendar service. Names are an explicit opt-in per feed, as email is in
    ADR-0016 §8.
  - Rate-limited; never cached by a CDN; no living person's full birth date unless the member may
    see it.

### 8. Gates and switches
- **Ships first (no engine needed):** lunar date entry and display, conventions and observance
  places as settings, the family calendar with solar dates, the ICS feed.
- **Behind `VSH_LUNAR_CALENDAR_ENABLED` (default off):** conversion suggestions, lunar reminders,
  lunar entries on the calendar and in the feed. It is turned on only when:
  1. the licence review of §1 is signed off, and
  2. the golden tables pass (§9) for every convention offered.

### 9. Accuracy: golden tables, never invented
- For each convention: at least 3 years (including one with an adhik masa and several kshaya and
  vriddhi tithis), at least 4 places (Varanasi, Delhi, Pune, Bengaluru) and 2 overseas time zones
  (London, San Francisco).
- Each row cites its published source (panchang name, edition or URL, retrieval date). The rows are
  entered by a reviewer, not generated by the engine under test.
- Tolerance: the civil day must match exactly; tithi start and end within 2 minutes of the source.
  Documented divergences (sources disagree among themselves) are listed with both answers.
- The test suite fails if a convention is enabled without its golden table.

### 10. API (all under `/api/v1`, typed, authorised)
- `GET /trees/{t}/calendar?from=&to=`: the family calendar (visible entries only, cursor pages).
- `POST /trees/{t}/calendar/convert`: a conversion suggestion (flag on); nothing is stored.
- `GET|PUT /trees/{t}/calendar-settings`: the tree's convention and observance place (tree admin).
- `POST|DELETE /trees/{t}/calendar-feed`: create, rotate or revoke the member's feed;
  `GET /calendar-feeds/{token}.ics`: the feed itself (no session; the token is the credential).
- Reminder create and update accept `date_rule`, `convention` and `observance_place`.

### 11. Interface
- The date editor gains an optional "Hindu calendar date" section (masa, paksha, tithi, adhik,
  convention, samvat year) with the original text field kept.
- Under a lunar date, "Find the Gregorian date" shows the suggestion and how it was computed; the
  user accepts or ignores it.
- A Calendar page (month and list, 390 px first), with "Add to my calendar app" for the ICS feed and
  its privacy note. Every Punyatithi shows its convention, rule and place in plain words.
- English and Hindi UI; masa and tithi names in Devanagari and Latin.

## Consequences
- **One migration, with a downgrade:** reminder columns (`date_rule`, `convention`,
  `observance_place_id` or city key), tree calendar settings, `calendar_feed` (tree-scoped, RLS,
  hashed token), `panchang_day` (global, read-only to the application role). The lunar component
  lives in the existing date JSON and needs no column.
- **New dependency:** Skyfield, jplephem and the DE440s file (32 MB) in the backend image.
- **Threat model:**
  - a new entry for the ICS feed (token leakage in URLs and logs, data sent to third-party calendar
    services, stale access after removal);
  - a new entry for observance places and lunar dates of living people (location precision,
    dates visible through the calendar or the feed);
  - wrong dates are a trust problem, not a security one: covered by §8 and §9.
- **Privacy model:** a section on the calendar and the feed.
- **Operations:** a yearly `panchang_day` refresh per observance place; engine and ephemeris
  versions recorded with every cached day.

## Alternatives considered
- **Swiss Ephemeris (`pyswisseph`).** The reference most panchang software uses, but AGPL-3.0 or a
  paid licence. AGPL would apply to the whole networked backend. Rejected unless the owner buys the
  commercial licence.
- **An own implementation from published formulas (Meeus).** No dependency, but we would own the
  astronomy and its errors. Rejected while a maintained MIT library exists.
- **A hosted panchang API.** Sends family dates and places to a third party, and costs per call.
  Rejected.
- **Pre-printed tables only (no engine).** Fails for diaspora places and future years. Rejected,
  but such tables are exactly what the golden tests use.
- **Storing only Gregorian dates and computing lunar ones.** Loses the many ancestors whose only
  date is a tithi. Rejected.
- **One national convention.** Wrong for half the country. Rejected.

## Stress test
1. *A family in Pune and a cousin in Lucknow observe the same Punyatithi on different days.* Both
   are right: each member's reminder carries its own convention and place.
2. *The tithi spans two sunrises (vriddhi) or none (kshaya).* The day rule's tie rule decides; both
   cases are in the golden table.
3. *A death happened in an adhik masa.* The convention's adhik field decides; the reminder says
   which month it used.
4. *Someone in San Francisco.* Sunrise and the civil day are computed there; the cities list and
   the golden table include overseas time zones.
5. *The engine is upgraded and a date moves by a day.* Cached days are versioned; changed upcoming
   dates are flagged on the calendar, and the reminder announces the new date.
6. *A living relative's tithi-only birthday.* Visible-dates-only applies to lunar dates too.
7. *The ICS URL ends up in a shared calendar or a log.* Rotate or revoke it at once; minimal content
   by default; every fetch re-checks access.
8. *The licence review says no.* Lunar reminders stay off; lunar entry, the calendar and the feed
   still work; the next options are buying the Swiss Ephemeris licence or an own implementation.
9. *Could a convention be guessed from the surname or village?* No. It is a setting chosen by a
   person, like every heritage value.

## Open points for the reviewer
- **Q16 engine:** Skyfield + JPL DE440s as proposed, subject to the licence review (who signs it
  off: owner or counsel?).
- **Q6 conventions for R5:** `purnimanta` and `amanta` with the afternoon rule for Punyatithi, and
  the nija-month rule for adhik masa. Regional solar calendars and nakshatra observances later.
- **Who enters the golden tables** (a reviewer with access to published panchangs), and which
  panchangs count as sources.
- **ICS content default:** minimal (no names), names only by opt-in, as proposed.
