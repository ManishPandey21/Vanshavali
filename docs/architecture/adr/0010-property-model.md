# ADR-0010: Ancestral property as properties, parcels, interests and events

- Status: Accepted · Date: 2026-09-25

## Decision
- `property` (a logical estate): type, display name, place, status, privacy (default
  `PRIVATE_TREE_ADMINS`).
- `land_parcel`: fixed optional columns for the common identifiers (survey number, khasra/gata,
  khata, khatauni, patta, plot, subdivision, ULPIN, area + unit, land use, coordinates, cadastral
  and portal references) **plus** `extra_identifiers JSONB` for state-specific keys.
  `parent_parcel_id` records subdivision and consolidation lineage.
- `property_interest`: holder (`person | family_branch | trust | entity | unknown`), interest type,
  **exact rational share** (numerator/denominator, with share_percent derived), valid from/to,
  status (`asserted | documented | disputed | relinquished | transferred | unknown`), evidence
  status and provenance.
- `property_event`: type (purchase, inheritance, succession, partition, settlement, relinquishment,
  gift, sale, mutation, acquisition, court order, mortgage, lease, consolidation, subdivision,
  merger, boundary change, dispute, other), date, parcels affected, linked documents, **the interests
  it ends and the interests it creates** (all in one transaction).
- Invariant: at any moment, the active `owner/co_owner` interests of a property **with status
  `documented`** add up to ≤ 1. Asserted or disputed claims may overlap (that's what disputes look
  like), and the timeline shows the overlap.
- Every property response carries `legal_notice`: *"Genealogical/documentary record only — not a
  legal title opinion."* (PRS §17.3, §37).

## Consequences
The timeline is a query that orders events by date and attaches interests and documents. The
lineage view walks the interests' holders back through the genealogy graph.
