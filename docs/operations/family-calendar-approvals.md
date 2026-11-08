# Family calendar: approvals, validation checklist and outstanding sign-offs

Product owner's decisions, 8 Nov 2026 (recorded in ADR-0022, "Owner decisions"):
- The development team prepares the evidence.
- A qualified licensing reviewer signs off the engine and data licences.
- An independent panchang-domain reviewer verifies accuracy.
- The product owner gives the final activation approval.
- Tithi conversions and lunar reminders stay **disabled** until every gate passes.
- Validation starts with one city and one convention.
- An approval is bound to the engine version, the convention, the location and the source tables.
- Any material change needs revalidation.
- Adding a test file never enables anything.

Further decisions, 8 Nov 2026 (later the same day):
- **First scope: amanta × Mumbai, for validation only.** It is not activated.
- The PAC archive editions are assessed for the 3-year rule.
- The copyright of the transcribed Panchang data, including git history, goes to qualified review.
- D-1 is kept as documented, and clarification is sought from PAC or the reviewer.
- Observance-rule sources are identified.
- The approval binding is made robust against code changes that don't bump `METHOD_VERSION`.

## 1. The gates, as the code enforces them

A convention is offered at a city (`backend/app/modules/calendar/conventions.py`, `offered`) only
when **all** of these hold. Each one is tested in `backend/tests/test_calendar_engine.py`:

| Gate | Where it is recorded | Who | Bound to |
|---|---|---|---|
| 1. Operator switch `VSH_LUNAR_CALENDAR_ENABLED=true` | deployment environment | operator, after gate 5 | — |
| 2. Ephemeris present and matching its SHA-256 | the image | build | `ephemeris.SHA256` |
| 3. **Licence sign-off** | `data/approvals.json` → `licence` | qualified licensing reviewer | `ENGINE_VERSION` (Skyfield and jplephem versions, ephemeris name, method) and the ephemeris SHA-256 |
| 4. **Accuracy approval** for this convention **and city** | `data/approvals.json` → `accuracy[]` | independent panchang reviewer (must differ from `prepared_by`) | `ENGINE_VERSION`, the ephemeris SHA-256, the **calculation code** (SHA-256 of the exact bytes of `calendar/engine.py`, `calendar/observance.py` and `core/lunar.py`), the convention's rules (digest of its month system, day rules and adhik rule), **the city's coordinates and time zone**, and the golden table's SHA-256 |
| 5. **Activation** for this convention and city | `data/approvals.json` → `activation[]` | product owner | — (meaningless without gates 3 and 4) |

Revalidation happens automatically. If anything an approval is bound to changes, the approval is
stale and the convention is no longer offered:
- a Skyfield or jplephem upgrade (it changes `ENGINE_VERSION`);
- another ephemeris;
- **any edit to the calculation code**, even a comment. This holds whether or not `METHOD_VERSION`
  is bumped: that string is a hand-kept label and is no longer relied on alone. Regression test:
  `test_a_calculation_change_withdraws_approvals_even_without_a_version_bump`;
- an edit to the convention's rules;
- a change to the approved city's coordinates or time zone
  (`test_moving_an_approved_city_withdraws_its_approval`);
- any edit to the golden table.

An edit to the calculation code that the reviewer agrees is immaterial still needs a fresh,
reviewed approval record with the new digest. It cannot be waved through.

The test `test_shipped_approvals_are_current_and_point_at_passing_tables` then fails, so the change
cannot be merged until the convention is revalidated or the approval is removed. A golden table
alone, or a passing `check-golden`, never enables anything
(`test_every_gate_is_needed_and_approvals_are_bound_to_what_was_checked`).

## 2. How to record an approval

1. Print the digests the record must carry:
   ```bash
   cd backend && uv run python -m app.cli.calendar approval-template --convention amanta --city mumbai
   ```
2. The reviewer signs the record outside the repository: the validation checklist below, completed,
   with their name, role and date. Store it where the project keeps signed records, and refer to it
   in `record`.
3. Add the entry to `backend/app/modules/calendar/data/approvals.json` in a pull request that the
   product owner approves. Never copy digests from an older entry.

Shapes:

```json
{
  "licence": {"reviewer": "…", "role": "…", "signed_on": "YYYY-MM-DD", "record": "…",
              "engine_version": "skyfield-1.55/jplephem-2.24/de440s/lahiri-iau2006/1",
              "ephemeris_sha256": "c1c7feeab882263fc493a9d5a5b2ddd71b54826cdf65d8d17a76126b260a49f2"},
  "accuracy": [{"convention": "amanta", "city": "mumbai", "engine_version": "…", "ephemeris_sha256": "…",
                "code_sha256": "…", "convention_sha256": "…", "city_sha256": "…", "golden_sha256": "…",
                "prepared_by": "…", "reviewer": "…", "reviewed_on": "YYYY-MM-DD", "record": "…"}],
  "activation": [{"convention": "amanta", "city": "mumbai", "approved_by": "…", "approved_on": "YYYY-MM-DD"}]
}
```

## 3. Validation checklist (one convention, one city)

The reviewer completes and signs this for each scope (convention × city). "Dev" items are prepared
by the development team; "Reviewer" items are the independent reviewer's own checks.

**Sources**
- [ ] Dev: every source in the golden table names its publisher, title, edition, retrieval date or
      page numbers, and page checksums; `check-golden` reports no source gap.
- [ ] Licensing reviewer: permission to use each source's values in this way is verified (S-1, L-6).
- [ ] Reviewer: spot-check at least 30 transcribed rows against the source pages: tithi, paksha,
      month, adhik, ending time and city sunrise. Include every kshaya day, every adhik-transition
      day, and the rows around each Amavasya and Purnima.

**Coverage**, from `check-golden --convention <c> --city <city>`:
- [ ] At least 3 years of tithi endings, including an adhik month.
- [ ] At least one vriddhi day (no tithi ends) and one kshaya day (two end) at the city.
- [ ] The city's published sunrise for every day compared.
- [ ] Months named the convention's way. For purnimanta this needs the supplementary source S-5.
- [ ] Published observances checked for the memorial (aparahna) and birthday (sunrise) day rules
      at the city, including vriddhi, kshaya and adhik cases (supplementary source S-6).

**Accuracy**
- [ ] Every tithi ending within 2 minutes of the source.
- [ ] Every sunrise within 90 seconds.
- [ ] Every decidable civil day equal. Undecidable days, where a tithi ends within a minute of
      sunrise, are listed and reviewed by hand.
- [ ] Every divergence decided: accepted with a reason (`accepted_by`), or the engine is fixed.
      Currently pending: **D-1** (see [sources](family-calendar-sources.md) §4). D-2 is a
      sunrise-table anomaly that the transcriber excludes; it is to be confirmed with PAC.
- [ ] `check-golden` prints `PASSED` for the scope, run on the engine version being approved.

**Binding**
- [ ] The approval carries all six digests printed by `approval-template --convention <c> --city <city>`
      for the run that was reviewed: engine, ephemeris, code, convention, city and table.
- [ ] `prepared_by` and `reviewer` are different people.

**Activation** (product owner)
- [ ] Licence sign-off recorded (gate 3) and current.
- [ ] Accuracy approval recorded (gate 4) and current for this convention and city.
- [ ] The attribution approved in the licence review (L-5) is shown in the app.
- [ ] Family-facing wording reviewed: what "computed by tithi" means, and that a conversion is a
      suggestion.
- [ ] Activation recorded (gate 5); then the operator sets `VSH_LUNAR_CALENDAR_ENABLED=true`.

## 4. Outstanding approvals and tasks

| # | Task | Owner | Blocks | Status |
|---|---|---|---|---|
| A-1 | Licence and data-use sign-off ([evidence](family-calendar-licence-review.md), items L-1 to L-8) | Qualified licensing reviewer | gate 3 | Evidence prepared and updated; **not signed**. The gate is closed. |
| A-2 | Copyright review of the transcribed Rashtriya Panchang values: may they stay in the repository, may more editions be added, and what to do about **git history** if not (L-6, L-7) | Qualified licensing reviewer; possibly a request to IMD/PAC | everything that uses golden data | **Open.** Only the 1948 SE values are committed, on the PR branch, not `main`. The 2023-24 and 2025-26 values are held back. |
| A-3 | Three years of Rashtriya Panchang data (S-2) | Development team | coverage | **Assessed:** the 2023-24 and 2025-26 PDFs from the PAC archive are accessible and suitable; with 2026-27 they give 1,144 endings and 1,052 matching Mumbai civil days, with no mismatch beyond D-1. **Transcription not committed** until A-2. |
| A-4 | Identify a purnimanta month-naming source (S-5) and verify its permission | Development team + panchang reviewer | purnimanta at any city | **Open.** Not needed for the amanta × Mumbai scope. |
| A-5 | Published observance rules for the memorial (aparahna) and birthday (sunrise) days, with vriddhi, kshaya and adhik cases, by community and region (S-6) | Development team + panchang reviewer | every scope | **In progress.** Candidates are listed in [sources](family-calendar-sources.md) §7: Kane Vol. IV read in part, Vol. V and the Nirṇayasindhu/Dharmasindhu not yet checked. No rule is verified as operational. |
| A-6 | D-1 (9 Dec 2026 Amavasya month name), also printed in the official PDF; D-2 (spurious sunrise row, 1947 SE PDF) | PAC (clarification) or the independent panchang reviewer | amanta, every city | **Pending.** Request to PAC to be sent by the owner; contact details are on the PAC site. Nothing in the source rows has been changed. |
| A-7 | Appoint the independent panchang-domain reviewer | Product owner | gate 4 | **Open** |
| A-8 | Choose the first scope | Product owner | — | **Done:** amanta × Mumbai, validation only, no activation |
| A-9 | Accuracy review and signed checklist for amanta × Mumbai | Panchang reviewer | gate 4 | Not started (needs A-2, A-3 committed, A-5, A-6, A-7) |
| A-10 | Show the approved attribution (L-5) in the app | Development team | activation | Not started (needs A-1) |
| A-11 | Activation approval | Product owner | gate 5 | **Not requested.** The owner has said validation only. |
| A-12 | Bind approvals to the calculation code and the city (`METHOD_VERSION` bypass) | Development team | integrity | **Done**, with regression tests |
