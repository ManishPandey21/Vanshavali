# ADR-0017: Visualization data APIs and Remotion animated exports

- Status: Accepted · Date: 2026-10-02
- Relates to: ADR-0001 (modular monolith), ADR-0004 (storage), ADR-0006 (privacy)
- Detail: [remotion-rendering.md](../remotion-rendering.md)

## Context
The product needs fan, pedigree, family-tree, dynamic graph, lifespan, life-event-timeline and map
views, static exports, and animated video exports. Large joint families must not be loaded eagerly,
and no chart or video may reveal more than the viewer may see.

## Decision

### Data APIs, not a client-side tree
Charts call purpose-built endpoints under `/trees/{id}/viz/…` (`ancestry`, `neighbourhood`,
`lifespans`, `people/{id}/story`, `map`) returning compact cards (`VizPerson`), never full person
records. Every endpoint is built from the existing privacy primitives (`visible_subjects`, the event
serialiser's field-group redaction, `geo.place_coordinates`). Hidden people are placeholders without
names, dates or places; the graph never expands through them. Caps: ancestry ≤ 10 generations,
neighbourhood radius ≤ 3 and ≤ 300 nodes with `expandable` flags (progressive loading), lifespans
≤ 500 rows, map ≤ 2,000 points.

### Interactive charts in the SPA, static exports in the browser
Charts are SVG React components with keyboard-focusable nodes, a detail panel, legends and a text
alternative. Static export (SVG, PNG, print-to-PDF) uses the SVG the user sees.

### Maps without third parties
No tile server, geocoder or boundary data by default: they would disclose family locations to a
third party, need CSP changes, and drawing India's external boundary has legal requirements. The
map is a projected plot (points, migration arcs, graticule) with an opt-in "open in
OpenStreetMap" link per point. A tile provider can be added later behind configuration.

### Animated exports with Remotion, rendered off the request path
- `renderer/` is an isolated Node package (Remotion 4) with compositions `FanChart`,
  `PedigreeChart`, `FamilyTree`, `LifespanTimeline`, `EventTimeline`, a shared theme set
  (`heritage`, `dusk`, `minimal`), a title card, branding footer and optional music/narration
  slots. It renders only from a JSON payload; it never calls the API.
- The API builds the payload **as the requester** when the job is created, stores it encrypted,
  and enqueues the job on a separate RQ queue (`vanshavali-render`) served by a render worker. The
  worker calls the pre-built bundle (`node scripts/render.mjs`) in a subprocess with a timeout, a
  private temp directory and no app secrets in its environment, stores the poster PNG and MP4
  encrypted, and purges the payload.
- Artifacts are visible and downloadable only by the requester and tree admins, through 5-minute
  signed URLs bound to the user and re-authorised at download time.
- Backends: `remotion`, `stub` (tests), `disabled` (default; `503 render_unavailable`). Per-user
  active-job and per-tree daily quotas, payload size and duration caps.

### Licence
Remotion is source-available under the Remotion License: free for individuals, non-profits and
companies with up to 3 employees; larger companies need a company licence. Rendering is isolated
behind `VSH_RENDER_BACKEND` and a separate worker image, so a deployment can leave it disabled or
replace it. Recorded on the go-live checklist.

## Consequences
- New tables `chart_preset`, `render_job`, `render_artifact` (RLS). The orphan sweep knows render
  keys.
- A render worker image (`deploy/render-worker/Dockerfile`) and an opt-in compose profile.
- CI renders every composition for real (`renderer` job) and runs the API's render test against the
  bundle.

## Alternatives considered
- **Client-side video capture (MediaRecorder)**: inconsistent across browsers, ties up the user's
  device, cannot run in the background. Rejected.
- **Rendering in the web process**: blocks requests and mixes Chromium into the API image. Rejected.
- **Remotion Lambda**: sends family data to a cloud function outside the pilot's India-hosted
  boundary. Rejected for now.
