# Vanshavali GEDCOM 7 extensions for Indian family heritage

Status: version 1 · Decision record: [ADR-0008](../architecture/adr/0008-gedcom.md)

Vanshavali exports FamilySearch GEDCOM 7.0 files. Facts that GEDCOM has no structure for, such as
gotra, kuladevata, tharavad, nakshatra and how reliable a birth time is, travel as **documented
extension structures**. Each tag starts with `_IND_` and is declared in `HEAD.SCHMA` with a URI.
Any GEDCOM 7 reader can find out what a tag means, and it can safely ignore tags it doesn't
understand.

## URIs and SCHMA

Each tag's URI is `GEDCOM_EXT_BASE_URI + slug`. The default base,
`https://vanshavali.app/gedcom/ext/v1/`, is configured with `VSH_GEDCOM_EXT_BASE_URI` and is an
assumption until the production domain is fixed.

An export declares **only the tags it actually uses**:

```gedcom
0 HEAD
1 GEDC
2 VERS 7.0
1 SCHMA
2 TAG _IND_GOTRA https://vanshavali.app/gedcom/ext/v1/gotra
2 TAG _IND_KULADEVATA https://vanshavali.app/gedcom/ext/v1/kuladevata
2 TAG _IND_NAKSHATRA https://vanshavali.app/gedcom/ext/v1/nakshatra
2 TAG _IND_BIRTH_TIME_CONF https://vanshavali.app/gedcom/ext/v1/birth-time-confidence
1 SOUR Vanshavali
2 NAME Vanshavali
1 DATE 25 SEP 2026
```

On import, the tag is matched **by its SCHMA URI first**:

- A file may use another tag name for one of our URIs, for example `2 TAG _CLAN
  https://vanshavali.app/gedcom/ext/v1/kuladevata`. `_CLAN` is then imported as kuladevata.
- A file may declare one of our tag names with a *different* URI. That tag is then treated as an
  unknown extension and kept verbatim.
- If a tag has no SCHMA entry, the importer falls back to the tag name.

## Vocabulary

| Tag | Slug (URI suffix) | Context | Payload | Canonical model |
|---|---|---|---|---|
| `_IND_GOTRA` | `gotra` | `INDI` | Text | Heritage assertion `gotra` |
| `_IND_PRAVARA` | `pravara` | `INDI` | Text | Heritage assertion `pravara` |
| `_IND_KULA` | `kula` | `INDI` | Text | Heritage assertion `kula_or_vamsha` |
| `_IND_ANCESTRAL_PLACE` | `ancestral-place` | `INDI` | Text (place name) | Heritage assertion `ancestral_village`, linked to a Place with the same name (the Place is created if missing) |
| `_IND_KULADEVATA` | `kuladevata` | `INDI` | Text | Heritage assertion `kuladevata` |
| `_IND_KULADEVI` | `kuladevi` | `INDI` | Text | Heritage assertion `kuladevi` |
| `_IND_THARAVAD` | `tharavad` | `INDI` | Text | Heritage assertion `tharavad_or_equivalent` |
| `_IND_NAKSHATRA` | `nakshatra` | `INDI` | Text | `AstrologyProfile.nakshatra` |
| `_IND_NAKSHATRA_PADA` | `nakshatra-pada` | `INDI` | Integer 1–4 | `AstrologyProfile.nakshatra_pada` |
| `_IND_RASHI` | `rashi` | `INDI` | Text | `AstrologyProfile.rashi` |
| `_IND_LAGNA` | `lagna` | `INDI` | Text | `AstrologyProfile.lagna` |
| `_IND_BIRTH_TIME_CONF` | `birth-time-confidence` | `INDI.BIRT` (also accepted at `INDI`, where it applies to the first `BIRT`) | `<precision> [<source>]` | Birth event `time.precision` and `time.source` |
| `_IND_PROPERTY_REF` | `property-ref` | `INDI` | Text (opaque reference) | Kept verbatim in `gedcom_extension` and never linked automatically |

All the extensions are singletons in the sense that one line carries one value. A tag may be
repeated when a source records competing values (see below).

### Heritage assertions: `_IND_GOTRA`, `_IND_PRAVARA`, `_IND_KULA`, `_IND_ANCESTRAL_PLACE`, `_IND_KULADEVATA`, `_IND_KULADEVI`, `_IND_THARAVAD`

```gedcom
0 @I1@ INDI
1 NAME Ramesh /Sharma/
1 _IND_GOTRA Kashyapa
2 SOUR @S1@
3 PAGE Bahi vol. 4, p. 112
1 _IND_PRAVARA Kashyapa, Avatsara, Naidhruva
1 _IND_KULA Suryavamsha
1 _IND_ANCESTRAL_PLACE Gaya, Bihar
1 _IND_KULADEVATA Vindhyavasini
1 _IND_THARAVAD Puthenveettil
```

- **Import.** Each value becomes an `Assertion` on the person with `evidence_status =
  USER_ASSERTION`, `prov_origin = gedcom` and `value_status = known`. The first value for an
  attribute is preferred. Repeated values are kept as non-preferred alternatives, which the
  heritage profile shows as disputed. `SOUR` citations under the tag become citations on the
  assertion. Empty payloads are ignored with a warning.
- **Export.** Only the **preferred**, *known* assertion for each attribute is written, and only if
  the exporter may see the person's `heritage` field group and the assertion's own privacy level.
  Assertions marked disproven or superseded are never written.
- Vanshavali **never derives** these values from surname, place, language or relatives (ADR-0003).
  The importer only records what the file states.

### Astrology: `_IND_NAKSHATRA`, `_IND_NAKSHATRA_PADA`, `_IND_RASHI`, `_IND_LAGNA`

```gedcom
1 _IND_NAKSHATRA Rohini
1 _IND_NAKSHATRA_PADA 2
1 _IND_RASHI Vrishabha
1 _IND_LAGNA Simha
```

- **Import.** The values create one `AstrologyProfile`, through the astrology service, with
  `provenance_kind = imported`, `prov_origin = gedcom` and `evidence_status = USER_ASSERTION`. It
  is linked to the person's preferred birth event and gets the default privacy
  `PRIVATE_TREE_ADMINS`. Values are normalised against the astrology vocabulary. A value the
  vocabulary doesn't recognise is not guessed at: it is kept word for word in the profile's
  `notes`, and the commit report carries a warning. A pada outside 1–4 is rejected with a warning.
  Nothing is calculated.
- **Export.** Astrology is a **sensitive** field group. The profile (the preferred one, or failing
  that the most recent) is only written when `include_sensitive=true` and the exporter may see
  the person's astrology.

### `_IND_BIRTH_TIME_CONF`

```gedcom
1 BIRT
2 DATE 12 MAR 1895
3 TIME 06:30
2 _IND_BIRTH_TIME_CONF approximate kundli
```

- The payload is `<precision>` optionally followed by a space and `<source>`.
- **precision** is one of `exact`, `approximate`, `family_recollection`, `document_recorded` or
  `unknown`.
- **source** is one of `birth_certificate`, `hospital_record`, `kundli`, `family_recorded`,
  `verbal`, `approximate` or `unknown`. If it is left out, the source is `unknown`.
- Invalid combinations are ignored with a warning. For example, `exact` can't be paired with a
  `verbal`, `approximate` or `unknown` source.
- **Without this tag**, an imported `TIME` has precision `unknown`, because an unqualified time
  is never presented as exact.
- A `TIME` ending in `Z` is stored with the `UTC` time zone.
- **Export.** The tag is written under `BIRT` whenever a birth time is written. Birth time is a
  sensitive field group, so this needs `include_sensitive=true`.

### `_IND_PROPERTY_REF`

```gedcom
1 _IND_PROPERTY_REF KH-1234/Mauza Rampur
```

An opaque pointer to a land or property record in another system. It is recognised, counted in
the report and **stored verbatim** in `gedcom_extension`. The importer never links it to a
Vanshavali property record, because property interests are sensitive and need explicit review.
It is re-emitted only as part of the preserved payloads (see below).

## Standard structures and Indian naming

- **Names.** The preferred name is the first `NAME`. Names in another script are written as
  `TRAN` under it, with a BCP 47 `LANG`. When the language is known it is combined with the script
  (`hi-Deva`, `sa-Deva`, `ta-Taml`). When only the script is known, the language is written as
  `und`, for example `und-Deva`, because Vanshavali never guesses a language from a script. `TYPE`
  maps `birth`, `married`, `alias` (`AKA`) and `professional` directly. Other name types are
  written as `OTHER` with a `PHRASE`.
- **Dates.** Dates follow the GEDCOM 7 grammar:
  - `ABT`, `CAL` and `EST` become *circa*; `BEF` and `TO` become *before*; `AFT` and `FROM`
    become *after*; `BET … AND …` and `FROM … TO …` become a *range*.
  - `JULIAN` dates keep the Julian calendar.
  - The importer never invents a missing day or month. The verbatim payload, or its `PHRASE`, is
    kept as `original_text`.
  - Vikram Samvat, Shaka, Hijri and other calendars have no GEDCOM form. They are exported as an
    empty `DATE` with a `PHRASE` holding the original text.
- **Relationships.**
  - Each couple (`spouse`, `partner`, `divorced_spouse` or `separated_spouse`) is one `FAM`.
    `divorced_spouse` adds `DIV`, `separated_spouse` adds `EVEN`/`TYPE Separation` and `partner`
    adds `NO MARR`.
  - Children are linked through `union_id`, and `FAMC.PEDI` carries the relationship type:
    `BIRTH` for biological, `ADOPTED` for adoptive (including *dattak*), `FOSTER` for foster, and
    `OTHER` with `PHRASE step` or `PHRASE guardian` for step-parents and guardians.
  - When a child's parent is not part of a recorded couple, that parent gets a single-parent
    `FAM`, so no marriage is invented.
  - On import, `SEALING` and any other unrecognised pedigree become a biological link with
    `evidence_status USER_ASSERTION` and subtype `gedcom_pedi_<value>`, and a review warning is
    reported.

## Religion (`RELI`)

- An `INDI`-level `RELI` with a value (e.g. `1 RELI Hindu`) becomes a **religion** heritage
  assertion: `evidence_status USER_ASSERTION`, import provenance, and its `SOUR` citations. It is an
  explicit statement in the file, so this is not inference; nothing is ever derived from names,
  places or relatives.
- A `RELI` without a value is kept verbatim (see below) rather than guessed at.
- Religion is sensitive. Viewing follows the `religion` field-privacy group. On export the
  preferred religion is written back as a standard `RELI`, **only** with `include_sensitive=true`
  and only if the exporter may see it. That is the same bar a preserved `RELI` had before.

## Media-only records and undated events

- An `INDI` record that holds only media is skipped with a `photo_container_skipped` warning.
  Such a record has `OBJE` but no name, no family links, no events and no known sex; MyHeritage
  exports its "Unassociated photos" album this way (`_UID Unassociated photos`). Its photos still
  count towards `media_refs`. An unnamed person with a family link or an event is a real person,
  and is imported as "Unnamed".
- The import preview reports an event recorded without a date (e.g. `1 BIRT` with only a `PLAC`,
  or `1 DEAT Y`) as "India, date unknown" or "date unknown". No date is invented.

## Photos (`OBJE`) and GEDCOM packages

- Upload the `.ged` on its own, or a **zip** of the `.ged` with its photos folder (for example
  MyHeritage's `…_Photos`), or a GEDZIP (`.gdz`). Details and limits: ADR-0013.
- Each person's `OBJE` (inline, or a pointer to an `OBJE` record) is matched to a file in the zip,
  first by relative path (GEDZIP), then by file name (for absolute paths such as MyHeritage's
  `C:\Users\…\P1.jpg`). The report lists photos that are missing or match more than one file.
- On import, each matched photo of a newly created person goes through the normal document
  pipeline (type check, malware scan, encrypted storage) and is linked to that person, with the
  person's privacy level. Photos held by no person are counted as `photos_unlinked` and not stored.
- `_PRIM`, `_POSITION` and `_CUTOUT` (MyHeritage primary photo and face crops) are not modelled yet.

## Unknown extensions (round-trip)

Anything the importer doesn't model is stored verbatim in `gedcom_extension`, with levels
relative to the structure and the SCHMA URI when there is one. This covers unknown `_TAG` subtrees
at `INDI` or `FAM` level or inside events, and standard `INDI`/`FAM` substructures such as `NATI`
or `ASSO`.

- Pointers to imported people are rewritten to stable internal ids. Other pointers become
  `@VOID@`.
- On export, preserved payloads are written back at the same place and their URIs are added to
  `SCHMA`. Because their content is unknown, and possibly sensitive, they are only included with
  `include_sensitive=true`.

## Privacy on export

- An export is generated from the **exporter's privacy view**:
  - People the exporter can't see are never written.
  - Living and other protected people are left out by default (`exclude_living=true`).
  - With `exclude_living=false`, a protected person is written in full only if the exporter can
    see their full birth date. Otherwise they are written as a `NAME Living` / `RESN PRIVACY`
    placeholder that keeps only the family links.
  - Dates are cut down to the year according to the normal field rules.
- `include_sensitive=true` adds birth time, astrology, residence events, notes, citation
  transcripts and preserved payloads. It needs the `privacy.manage` permission (tree owner or
  family admin).
- People whose privacy level is admin-only or stricter are written with `RESN CONFIDENTIAL`.
  Importing `RESN CONFIDENTIAL` gives the person `PRIVATE_TREE_ADMINS` privacy. Importing
  `RESN PRIVACY` marks a person with no death evidence as living.
- On import, a person with no death, burial or cremation event is marked *living* if born less
  than 110 years ago, and *unknown* otherwise. Living people, and unknown-status people with no
  birth date, get the protected-field privacy defaults. The person's privacy level is the tree
  default.
- Every export is audited as `gedcom.exported`, with the options and counts (no personal data).
