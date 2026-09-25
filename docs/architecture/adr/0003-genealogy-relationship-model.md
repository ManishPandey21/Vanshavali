# ADR-0003: Genealogy relationship, event, name and assertion model

- Status: Accepted · Date: 2026-09-25

## Context
The prototype's `fatherId/motherId/spouseIds/childrenIds` drift out of sync. They also can't express
adoption, step, foster or guardian relationships, multiple or overlapping unions, or disputed
parentage (PRS §14). Cultural facts can be disputed and must never be inferred (PRS §2.3, §13).
Dates and times are frequently approximate (PRS §8, §9, §52).

## Decision
### Relationships
One `relationship` table of **typed edges**:
`(person_a, person_b, type, subtype, lineage, union_id, start_date, end_date, legal_status,
evidence_status, confidence, notes, provenance…)`.
- For parent types (`biological_parent, adoptive_parent, step_parent, foster_parent, guardian`),
  `person_a` is the parent and `person_b` the child.
- For symmetric types (`spouse, partner, divorced_spouse, separated_spouse, sibling, other`) the
  pair is stored ordered (`person_a < person_b`).
- A parent–child edge may name a **`union_id`**, the couple relationship it belongs to. This links a
  child to a specific union and supports multiple spouses and half-siblings.
- `lineage` ∈ {`biological, legal, ritual, social`} drives the lineage toggles. Its default comes
  from the type (adoptive gives legal, and so on) and can be overridden (e.g. *dattak* is `legal` +
  subtype `dattak`).
- Siblings are **derived** from shared parents: full or half, biological or adoptive. An explicit
  `sibling` edge is allowed when the parents are unknown.
- Uniqueness: `(tree_id, type, person_a, person_b)`. `CHECK person_a <> person_b`. Before insert,
  the service rejects parent edges that would make someone their own ancestor.
- Parents may have any sex. Parental role labels (father/mother) are presentation only.

### Names
`name_record` (0..n per person): type, given, middle, patronymic, matronymic, surname,
family_house_name, village_prefix, honorifics, `full_name_as_recorded`, language, script,
`romanized_value`, date range, confidence and preferred flag. The name as recorded is always kept.

### Events and dates
`event` (birth, death, marriage, divorce, adoption, residence, migration, education, occupation,
cremation/burial, other), with participants and roles.
- **GenealogicalDate** (JSONB): `calendar, precision (exact|day_unknown|month_unknown|year_only|
  circa|before|after|range|unknown), year, month, day, end_year…, original_text`, plus derived
  `sort_from/sort_to`. We never invent a day or month.
- **Birth time**: `time_value, time_precision (exact|approximate|family_recollection|
  document_recorded|unknown), time_source (birth_certificate|hospital_record|kundli|
  family_recorded|verbal|approximate|unknown), timezone_id, utc_offset_minutes`. The API always
  returns `time_precision`, and the UI labels non-exact times.
- Place: `place_id` (normalised) **and** `place_as_recorded` (verbatim), never overwritten
  (PRS §38).
- A person may have **several competing birth events** (for example certificate vs Kundli). One is
  `is_preferred`. Conflicts are detected and shown, never merged destructively.

### Assertions (heritage and other facts)
`assertion(subject_type person|branch, subject_id, attribute, value, value_status known|unknown|
not_applicable|withheld, evidence_status, is_preferred, privacy_level, provenance…)`.
Heritage profiles (gotra, pravara, kula/vamsha, community, jati, ancestral village, tharavad,
kuladevata/kuladevi, temple, traditions) are **read models over preferred assertions**. Values
must be entered explicitly or accepted from a reviewed extraction, so **no code path derives them**
from surname, place, language or relatives. A regression test enforces this.

### Evidence
`evidence_status` ∈ `USER_ASSERTION, FAMILY_RECOLLECTION, SOURCED, CORROBORATED, DISPUTED,
SUPERSEDED, DISPROVEN` on names, events, relationships, assertions, astrology profiles and property
interests. Citations link sources to any of these.

## Consequences
Tree views are computed projections. The API returns family units (a person with parents, unions
and children) for rendering.
