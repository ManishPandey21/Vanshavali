# Geography snapshots: import, review, activation and rollback (ADR-0019)

Official LGD units and India Post offices are loaded as **snapshots**. Users only ever see the
*active* snapshot of each source. A new snapshot is staged by an operator, reviewed and approved by
one system admin in the console (**Master data → Geography**), and activated by a **different**
admin. The previous snapshot stays for rollback.

> **Licensing is still open** (ADR-0019, open questions). Do not stage official LGD or India Post
> data on a shared environment until the owner has confirmed the licence and attribution wording.
> Tests and e2e use the fictional fixtures in `backend/tests/fixtures/geo/`.

## 1. Canonical file formats

UTF-8 CSV, one header row exactly as below, `|` between list entries. Limits: 300 MB per file,
1,500,000 rows, 200 characters per field, 20 entries per list, no control characters or NUL bytes.
A file that breaks these is refused outright; a file whose *rows* are wrong becomes a **failed**
snapshot with the first 200 errors listed and no rows stored.

### LGD units (`--source lgd`)

```
level,code,parent_level,parent_code,name_en,name_local,local_script,local_term,category,alternate_names,former_names,valid_from,valid_to,successor_codes
```

| Column | Rule |
|---|---|
| `level` | `country`, `state`, `district`, `subdistrict`, `block`, `gram_panchayat`, `village`, `town`, `ulb` |
| `code` | LGD code, digits only; the country is `IN` |
| `parent_level`, `parent_code` | Required except for the country. Allowed parents: state → country; district → state; sub-district, block, ULB → district; town → sub-district or district; village → sub-district; gram panchayat → block or sub-district. The database refuses anything else. |
| `name_en`, `name_local` | English and local-script names; `local_script` is ISO 15924 (`Deva`, `Beng`, `Taml`…) |
| `local_term` | What the state calls a sub-district (Tehsil, Taluka, Mandal, Circle…); shown as the field label |
| `category` | Town or ULB type |
| `alternate_names`, `former_names` | Other spellings and earlier names; both are searchable |
| `valid_from`, `valid_to`, `successor_codes` | A unit with a past `valid_to` stays resolvable as *historical* and is not offered in the cascade |

The file must contain the country row and every parent it references.

### India Post offices (`--source india_post`)

```
pin,office_name,office_type,delivery,district,state,unit_codes
```

`pin` six digits not starting with 0; `office_type` `H.O.`/`S.O.`/`B.O.`; `delivery` `Delivery`,
`Non-Delivery` or empty; `unit_codes` the LGD units the office serves, e.g.
`village:123456|town:802345`. One PIN can have many offices and an office many units. Units that
the active LGD snapshot does not know are kept as links but reported as warnings and not shown.

**Mapping real downloads.** LGD and India Post publish their own column layouts. Convert them to
these formats with a reviewed script before staging; check the mapping against a real download
before the first pilot import (the source column names are not confirmed in this repository).

## 2. Stage (operator, on the server)

```bash
cd backend
uv run python -m app.cli.geo stage --source lgd --label 2026-10 --file /data/lgd-2026-10.csv \
  --licence "GODL-India" --attribution "Local Government Directory, Ministry of Panchayati Raj" \
  --source-url https://lgdirectory.gov.in/ --downloaded-on 2026-10-15 --operator "Your Name"
```

Exit status 0 = validated, 1 = failed (errors printed), 2 = file refused. Nothing is visible to
users yet. `uv run python -m app.cli.geo list` shows every snapshot.

## 3. Review, approve, activate (console)

1. **Master data → Geography**: the report shows row counts per level, the SHA-256 of the file,
   errors and warnings, and the change against the active snapshot (added, retired, renamed, moved
   units, with examples).
2. An admin **approves** it (reason required).
3. A **different** admin **activates** it. The previous active snapshot becomes *superseded*.

Single-admin pilot: after an admin approved it in the console, an operator may activate it from
the server (audited as `geo.snapshot_activated_by_operator`):

```bash
uv run python -m app.cli.geo activate --snapshot <id> --reason "pilot go-live" --operator "Your Name"
```

## 4. Rollback and clean-up

- **Rollback**: in the console, **Restore** a superseded snapshot. It becomes active again and the
  current one becomes superseded. Codes that only existed in the other snapshot keep resolving as
  *retired*.
- **Discard** deletes a staged, failed, validated or approved snapshot and its rows. Active and
  superseded snapshots are never discarded.
- Family places are never changed by any of this: a place keeps its own name, `lgd_level` and
  `lgd_code`, and a code that disappears from the directory still resolves (as retired).
- Switch the feature off with `VSH_GEO_ENABLED=false`: `/geo` answers 404 and the place form shows
  free-text fields only.
- Migration `9e3b5d7f2a14` downgrade drops every snapshot (re-stage from the source files) and
  `place.lgd_level`; `place.lgd_code` is kept.

## 5. Size and speed (measured 6 Nov 2026)

Synthetic national-scale file (`uv run python -m app.cli.geo synth --villages 650000 --out units.csv`):
650,000 villages, 300 sub-districts, 50 districts, 10 states, 58 MB, on the development container
(PostgreSQL 16, local disk).

| Measure | Result | Plan target |
|---|---|---|
| Stage the whole file (parse, validate, insert, diff) | 84 s | < 5 min for one large state |
| Children of a sub-district (≈ 2,170 villages, first page of 50) | median 9.6 ms, p95 14 ms | p95 < 50 ms |
| Children of a sub-district filtered by name | median 21 ms, p95 76 ms | (search) p95 < 150 ms |
| Country-wide name search, English prefix | median 64 ms, p95 70 ms | p95 < 150 ms |
| Country-wide name search, Devanagari | median 40 ms, p95 52 ms | p95 < 150 ms |
| `geo_unit` size with indexes | 273 MB per snapshot | documented |

Synthetic names are very repetitive ("Synth Gaon 123"), which is a hard case for the trigram index;
repeat the measurement on pilot hardware with the real file before go-live. Each kept (superseded)
snapshot costs the same space again: discard old superseded snapshots once a newer one has been
stable for a release, and include the geography tables in the backup drill.
