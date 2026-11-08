# Family calendar: operator notes (ADR-0022)

What ships today: tithi dates entered and shown as the family wrote them, the family calendar by
Gregorian date, and the private ICS feed. **Nothing lunar is computed** (no tithi days on the
calendar, no tithi reminders, no conversion suggestions) until all three gates below are open.

## Gates

| Gate | Where | How it opens |
|---|---|---|
| Engine licence review signed off | ADR-0022 §1 | The owner (or counsel) signs off Skyfield, jplephem and JPL DE440s. |
| `VSH_LUNAR_CALENDAR_ENABLED=true` | environment | Only after the sign-off. Default `false`. |
| A convention is `golden_verified` | `backend/app/modules/calendar/data/conventions.json` | Only with a passing golden table in `golden/<convention>.json`, cited row by row from a published panchang (see `golden/README.md`). A test fails a verified convention without one. Never generate rows with the engine. |

The calendar page tells families which gate is closed (`lunar_unavailable`).

## Ephemeris

The engine reads JPL DE440s (32 MB, not in git). It is accepted only with its pinned SHA-256.

```bash
cd backend && uv run python -m app.cli.calendar fetch-ephemeris
```

- Default path `var/ephemeris/de440s.bsp`; override with `VSH_EPHEMERIS_PATH`.
- The Docker image fetches it at build time (`/app/ephemeris/de440s.bsp`); CI caches it.
- Without it the engine reports itself unavailable and nothing lunar is offered; nothing else
  breaks.

## Checking a golden table

```bash
cd backend && uv run python -m app.cli.calendar check-golden --convention purnimanta
```

It reports coverage gaps (cities, years, an adhik year, sources) and every mismatch. Mark a
convention `golden_verified` only when this passes, in a reviewed change.

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
