# ADR-0015: Important life events, geo-tagged places and event photo albums

- Status: Accepted · Date: 2026-10-02
- Relates to: ADR-0003 (events), ADR-0004 (documents), ADR-0006 (authorisation and privacy)
- Milestone: [heritage-visualization-milestone.md](../heritage-visualization-milestone.md)

## Context
Families want to record the events that matter to them (naming ceremony, mundan, upanayana,
graduation, migration, awards, illness and recovery, memorials) with photos and a place on a map,
and to see ancestral villages, houses, temples and land on a map. The product already has typed
events with genealogical dates (ADR-0003), places with coordinates, a document vault with links to
events and people (ADR-0004), and heritage assertions that point at places (ancestral village,
temple, kuladevata).

## Decision

### Events: a category on top of the structural type
- `event.type` stays the structural genealogy type (birth, death, marriage, migration, …). It
  drives vitals, privacy rules for birth/residence, GEDCOM mapping and relationship logic.
- New `event.category` (`LifeEventCategory`: `naming_ceremony`, `annaprashan`, `mundan`,
  `upanayana`, `initiation`, `education`, `graduation`, `engagement`, `marriage`, `migration`,
  `employment`, `retirement`, `award`, `property_acquisition`, `illness`, `recovery`, `pilgrimage`,
  `death`, `memorial`, `custom`, `birth`) refines it. A client may send only a category; the type
  is then derived (`mundan` → `religious_ceremony`, `award` → `other`, …). Not a new event table.
- New `title`, `significance` (`standard` / `important` / `milestone`) and `location_precision` for
  the event's own coordinates. Dates, date ranges and approximate dates keep using
  `GenealogicalDate` (precision, `circa`, `before`/`after`, ranges, calendars).
- An event's own `privacy_level` is now enforced everywhere the event is looked up
  (`get_event_checked`), not only in serialisation. Before this, the album and reminder endpoints
  could have been reached for an event whose principal was visible but whose own level was not.

### Places: administrative context, precision, provenance, coordinate privacy
- `place` gains `locality`, `district`, `state`, `country`, `map_label`, `location_precision`
  (`exact` … `country`, `unknown`), `geo_confidence`, `geo_note` (provenance) and
  `coordinate_privacy`. New place types: `ancestral_house`, `shrine`, `land_parcel`,
  `neighbourhood`.
- Coordinates are optional. Coordinates entered without a precision are stored as `approximate`,
  never `exact`.
- `coordinate_privacy` (a privacy level) protects exact points such as a family house: viewers below
  the level receive coordinates rounded to 0.1° (~11 km), precision `approximate`, and no geo note.
  Public pages never receive coordinates. Only privacy managers change it.
- Ancestral village, temple and kuladevata stay heritage *assertions* that point at places; property
  and land parcels keep their `place_id`. Geo-tagging these is therefore geo-tagging their places.
- No PostGIS, geocoder or tile server (see ADR-0017 §maps).

### Event photos: an album over the vault
- `event_media(event_id, document_id, caption, taken_date, is_cover, sort_order)`; at most one cover
  per event (partial unique index). The first photo becomes the cover.
- A photo is an ordinary vault document (category `photo`, magic-byte validation, malware scan,
  encryption, previews/thumbnails, signed URLs). People shown in it are ordinary `document_link`
  rows to `person`, so one photo can belong to many people and appears in their documents.
- **Privacy inheritance**: a new event photo defaults to the strictest of the tree default, the
  event's level and its principal's level; a looser explicit level is refused
  (`422 privacy_too_open`). The vault's own checks still apply: an album entry is shown only when
  both the event and the document are visible; counts (`media_count`) only count visible photos.
- Removing a photo from an album keeps the document (and its person tags) in the vault.
- Editing an album needs the same permission as editing the event (`person.write` on its
  principal, branch scope included); uploading also needs `document.upload`.

## Consequences
- One migration (with downgrade) adds the columns, widens the place-type CHECK and creates
  `event_media` under RLS.
- `GET /life-events` lists events tree-wide, privacy-filtered, paging over visible rows only.
- GEDCOM export keeps exporting the structural type; categories and titles are carried as notes in
  a later change (not required for round-tripping today's data).

## Alternatives considered
- **Dozens of new `EventType` values**: would ripple through vitals, privacy rules, GEDCOM mapping
  and every `type` switch. Rejected in favour of a category.
- **A separate photo table**: would duplicate the vault's scanning, encryption and access control.
  Rejected.
- **PostGIS geometry columns**: unnecessary at expected tree sizes (thousands of points); can be
  added behind the same API later.
