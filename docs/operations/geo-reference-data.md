# Runbook: Indian geography reference data (LGD, India Post)

Decision: [ADR-0019](../architecture/adr/0019-india-geography-reference-lgd.md). Code:
`backend/app/modules/geo`, CLI `python -m app.cli.geo`.

The place cascade (State → District → Sub-district → Village/Town, village search, PIN suggestions)
reads **reference data that an operator loads by hand**. The application never downloads anything,
and it can only read these tables (the app role has `SELECT` only). Until a snapshot is active, the
`/geo` endpoints answer 404 and the UI keeps its free-text place fields.

## 1. Get the files

Download on a workstation, not on the server:

| Stage | Source | Files (CSV) |
|---|---|---|
| 1 | Local Government Directory (lgdirectory.gov.in → Download Directory) | States, Districts, Sub-districts |
| 2 | the same, per state | Villages of the state; Urban Local Bodies of the state |
| 3 | data.gov.in, "All India Pincode Directory" (India Post) | the national CSV |

Both are published under the Government Open Data Licence – India (GODL-India). Note the source URL
and download date for each file, and record its checksum:

```bash
sha256sum states.csv districts.csv subdistricts.csv
```

The importer matches column headers tolerantly (case, spacing and punctuation are ignored, and
title lines above the header are skipped). It refuses a file it does not recognise rather than
guessing; if LGD changes its layout, add the new header spelling to `geo/formats.py` by code review.
Merges and splits are not in the plain downloads: when LGD's change reports list them, prepare a
small `successors.csv` (`level,lgd_code,successor_codes`, codes separated by `;`) and pass it with
the stage it belongs to.

## 2. Stage a snapshot

Snapshots are named `YYYY-MM` (the LGD download month). Run every stage into the same snapshot,
as the schema owner (the migrate service's database URL), from `backend/`:

```bash
uv run python -m app.cli.geo import --stage 1 --snapshot 2027-02 \
  --file states.csv --sha256 <hex> --file districts.csv --sha256 <hex> \
  --file subdistricts.csv --sha256 <hex> \
  --source-url https://lgdirectory.gov.in/ --downloaded 2027-02-03 --operator "<your name>"
```

```bash
uv run python -m app.cli.geo import --stage 2 --state 9 --snapshot 2027-02 \
  --file villages_9.csv --sha256 <hex> --file ulb_9.csv --sha256 <hex> --operator "<your name>"
```

```bash
uv run python -m app.cli.geo import --stage 3 --snapshot 2027-02 \
  --file pincodes.csv --sha256 <hex> --operator "<your name>"
```

Each import is checked as a whole: one bad row (unknown parent, repeated code, control character,
over-long name, wrong checksum) refuses the file and writes nothing. Only the newest snapshot can
be imported into, and each scope (a level nationally, or a level in one state) only once.

## 3. Review the change report

Every import writes `geo-reports/geo-changes-<snapshot>-stage<n>[-state<code>].csv` and prints a
summary per level: `new`, `renamed`, `moved`, `changed`, `retired`, `merged`, `split`,
`unchanged`; for PIN offices also `unmatched_district` and `duplicates`. Check:

- renames and moves look like real LGD changes (e.g. Allahabad → Prayagraj);
- retirements have successors where LGD records them;
- PIN offices whose district could not be matched (`pin_district_unmatched`): usually a district
  renamed in LGD and not yet in India Post's file. Add a curated alias
  (`geo/aliases.json`, by code review) if it is a lasting spelling difference.

## 4. Activate (and roll back)

```bash
uv run python -m app.cli.geo activate 2027-02 --operator "<your name>"
```

Activation is refused when more than 5% of a scope's units would retire at once. Read the report,
then pass `--accept-large-change` if it is genuine. Activation is written to the audit log
(`geo.snapshot.activated`). Users see the new data immediately (responses carry the snapshot id,
so cached answers revalidate).

Rollback is activating the previous snapshot:

```bash
uv run python -m app.cli.geo activate 2026-11 --operator "<your name>"
```

To throw away a staged or rolled-back snapshot (only the newest, never the active one, and never
one that tree places were linked under):

```bash
uv run python -m app.cli.geo discard 2027-02 --operator "<your name>"
```

`uv run python -m app.cli.geo status` lists snapshots, their status and what each imported.

## 5. What families see

Tree places linked to an LGD code are **never rewritten**. When the active snapshot renames, moves
or retires a linked unit (or renames its district), the place shows a note such as "LGD now lists
this village under Prayagraj, Uttar Pradesh (since 2027-02)", with a button to update the place;
nothing changes until the user does.

## 6. Switching it off

Set `VSH_GEO_ENABLED=false` and restart the API: `/geo/*` answers 404 and the UI falls back to
free-text place fields. Existing links stay on the places. Same rollback pattern as master data
(ADR-0018).

## 7. Cadence, backups and size

- **Cadence:** quarterly LGD snapshots; PIN data when India Post publishes.
- **Backups:** the tables are in the normal PostgreSQL backup (backup drill). They can also be
  rebuilt from the recorded files: each snapshot stores file names, checksums, source URL and
  download date.
- **Size and speed:** the ADR's targets are cascade children p95 < 50 ms, name search p95 < 150 ms
  and importing the largest state in < 5 min, with an estimated 300–500 MB. The national benchmark on
  pilot hardware is still to be run (see `IMPLEMENTATION_STATUS.md`); a synthetic-scale measurement
  is recorded in [performance.md](performance.md).

## 8. Never in production

`python -m app.cli.geo load-test-fixture` loads the **synthetic** test fixture
(`backend/tests/fixtures/geo`). It is refused when `VSH_ENV=production`.
