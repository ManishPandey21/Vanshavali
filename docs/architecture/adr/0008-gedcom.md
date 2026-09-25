# ADR-0008: GEDCOM 7 interoperability and Indian extensions

- Status: Accepted · Date: 2026-09-25

## Decision
- **Export** targets FamilySearch GEDCOM 7.0. `HEAD.GEDC.VERS 7.0`, UTF-8, and a `HEAD.SCHMA` that
  maps every `_IND_*` tag used to a URI under `GEDCOM_EXT_BASE_URI` (default
  `https://vanshavali.app/gedcom/ext/v1/`, an ASSUMPTION until the owner's domain is fixed):
  `_IND_GOTRA, _IND_PRAVARA, _IND_KULA, _IND_ANCESTRAL_PLACE, _IND_KULADEVATA, _IND_KULADEVI,
  _IND_THARAVAD, _IND_NAKSHATRA, _IND_NAKSHATRA_PADA, _IND_RASHI, _IND_LAGNA,
  _IND_BIRTH_TIME_CONF, _IND_PROPERTY_REF`.
  The extension documentation lives in `docs/gedcom/indian-extensions.md`.
- Mapping: INDI (NAME with TRAN for transliterations, SEX, BIRT/DEAT/MARR with DATE, TIME and PLAC),
  FAM built from unions (HUSB/WIFE are GEDCOM's role names and are assigned by sex where known,
  else in order), FAMC with PEDI `BIRTH|ADOPTED|FOSTER|OTHER`, SOUR/citations, and OBJE references.
  Dates map to GEDCOM `ABT/BEF/AFT/BET…AND/FROM…TO`.
- Export respects the exporter's privacy view. "Exclude living people" and "include sensitive
  fields" are explicit options, and both are audited.
- **Import pipeline** (PRS §22): keep the original file as a Document → detect the version (5.5/5.5.1
  or 7) and encoding (BOM, `HEAD.CHAR`, UTF-8 with a latin-1 fallback, reported as a warning) → parse
  into a staging JSON → validate → build the report (counts, unsupported or extension tags,
  warnings) → map the standard structures and the known `_IND_*` URIs (by SCHMA URI, falling back to
  the tag name) → keep unknown extension subtrees verbatim in `gedcom_extension` rows and re-emit
  them on export → find duplicate candidates against the existing tree → preview → the user confirms
  per person (`create | skip | attach`) → commit in one transaction → audit. **No silent
  overwrite.** `attach` only adds names and events as extra claims.
- A media package (ZIP + manifest + checksums) is part of the full archive export (PRS §43).

## Consequences
The internal model is richer than GEDCOM. What isn't representable (astrology provenance, property
interests) goes into the JSON archive export instead.
