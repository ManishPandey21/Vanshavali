# ADR-0003: Relationships as typed, dated, sourced edges; facts as assertions

- Status: Proposed
- Date: 2026-09-25

## Context
The current `Person` stores `fatherId/motherId/spouseIds/childrenIds` in both directions. That
drifts out of sync (README F2) and can't represent adoption (including *dattak*), step or foster
parents, multiple or ordered marriages, divorce, or uncertain parentage. Attributes such as gotra
also change over a lifetime and can be disputed.

## Decision
- A single `relationship` table holds typed edges (see domain-model §3). Nothing is stored twice.
  Children, parents and spouses are derived by queries.
- A parent's role (father or mother) comes from the edge's role or from `sex_at_birth` for display
  only. Gender never restricts which edges are allowed.
- Culturally specific attributes (gotra, pravara, kula, jati, kuladevata, nakshatra, rashi,
  tharavad) are stored as `person_fact(type, value, date range, citation…)`, so conflicting sourced
  values can coexist and one is marked *preferred*.
- Dates use the `GenealogicalDate` value object (qualifiers, calendars, original text).
- GEDCOM 7 is the interchange format. Anything GEDCOM doesn't cover is exported as documented
  `_VNSH_*` extension tags, registered in a GEDCOM extension schema file.

## Consequences
- Tree rendering needs a query that turns edges into nodes (a "family unit" projection) with
  depth limits and pagination.
- Existing `types.ts` shapes become view models the API returns, not storage shapes.

## Open
See Q3 (niyoga/levirate and polygamous marriages), Q4 (whether caste/jati is stored at all) and
Q5 (matrilineal descent) in open-questions.md.
