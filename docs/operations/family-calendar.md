# Family calendar: operator notes (ADR-0022)

What ships today: tithi dates entered and shown as the family wrote them, the family calendar by
Gregorian date, and the private ICS feed. **Nothing lunar is computed** (no tithi days on the
calendar, no tithi reminders, no conversion suggestions) until all five gates below are open.

## Gates

Computed lunar dates are offered for a **convention at a city** only when all five gates hold:

1. the operator switch;
2. the ephemeris;
3. the licence sign-off;
4. the accuracy approval for that convention and city;
5. the product owner's activation.

Gates 3 to 5 are records in `backend/app/modules/calendar/data/approvals.json`, bound to the engine,
ephemeris, convention and golden table. See
[family-calendar-approvals.md](family-calendar-approvals.md) for the records, the validation
checklist and the outstanding sign-offs. None is recorded, so nothing lunar is offered.

| Gate | How it opens |
|---|---|
| `VSH_LUNAR_CALENDAR_ENABLED=true` | Set by the operator only after the product owner's activation is recorded. Default `false`. |
| Licence sign-off | A qualified licensing reviewer signs [the evidence](family-calendar-licence-review.md). |
| Accuracy approval | An independent panchang reviewer signs the validation checklist for one convention at one city, against the golden table ([sources](family-calendar-sources.md)). |
| Activation | The product owner, per convention and city. |

A golden table or a passing `check-golden` never opens a gate. The calendar page tells families
when tithi days are unavailable (`lunar_unavailable`).

## Ephemeris

The engine reads JPL DE440s (32 MB, not in git). It is accepted only with its pinned SHA-256.

```bash
cd backend && uv run python -m app.cli.calendar fetch-ephemeris
```

- Default path `var/ephemeris/de440s.bsp`; override with `VSH_EPHEMERIS_PATH`.
- The Docker image fetches it at build time (`/app/ephemeris/de440s.bsp`); CI caches it.
- Without it the engine reports itself unavailable and nothing lunar is offered; nothing else
  breaks.

## Golden tables and approvals

```bash
cd backend
uv run python -m app.cli.calendar check-golden --convention amanta --city mumbai
uv run python -m app.cli.calendar approval-template --convention amanta --city mumbai
uv run python -m app.cli.calendar transcribe-rp --pages <saved pages> --out app/modules/calendar/golden/amanta.json
```

`check-golden` reports coverage gaps and every mismatch for one convention at one city. A pass is
evidence for the reviewer, never an approval. `transcribe-rp` re-reads saved Rashtriya Panchang
pages (with `SHA256SUMS` and `RETRIEVED`) and keeps the divergences and observances that reviewers
added. Any change to a golden table makes its accuracy approvals stale.

## Caching calendar days (optional)

The app computes days in memory with caches. To fill the read-only `panchang_day` table for a city
and year (for inspection or a later optimisation):

```bash
cd backend && uv run python -m app.cli.calendar compute --city varanasi --year 2027
```

Run it as the migration/owner role: the application role can only read the table.

## Feed incidents

A leaked feed URL: the member replaces or turns off the link on the Calendar page; the old token
stops working at once. The token is never logged (only the route template is), and only its
SHA-256 is stored, so there is nothing to scrub from logs or the database.
