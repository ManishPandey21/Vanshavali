# ADR-0005: Ancestral property as parcels, interests and events

- Status: Proposed
- Date: 2026-09-25

## Decision
- `Property` (a logical estate) has many `LandParcel`s (khasra/survey no., recorded area + unit,
  Place).
- Ownership is never stored as one "owner" column. It is a set of time-bounded `PropertyInterest`
  rows, each with a rational share, held by a Person, Household or FamilyBranch.
- Every change is a `PropertyEvent` (inheritance, partition, sale, gift, will, mutation, court order)
  that ends some interests and creates others. The timeline is these events plus the interests
  valid at any date (valid-time queries).
- Shares are exact rationals, never floats. Partition arithmetic is tested.
- The app **records what documents say. It does not give legal advice** or compute statutory
  succession shares. Any "suggested shares" feature needs its own ADR and a legal review.

## Consequences
Property documents are the highest sensitivity class (privacy-model §2). Only tree owners and
property managers can see them by default.
