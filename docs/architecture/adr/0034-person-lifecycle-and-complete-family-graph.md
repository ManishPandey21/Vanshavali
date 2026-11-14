# ADR-0034: Person lifecycle (remove, restore, permanently delete) and the complete family graph

- Status: **Proposed** 2026-11-14. Implemented on a draft pull request for review; not to be merged
  or deployed until the owner accepts this ADR. §3 changes an accepted privacy rule and is
  irreversible in its effect on data.
- Amends: [ADR-0003](0003-genealogy-relationship-model.md) (tree views are computed projections),
  the privacy model §4–§5 (PRS §54: "privacy erasure leaves an anonymous placeholder") and
  [ADR-0017](0017-visualizations-and-animated-exports.md) (what charts show).
  Keeps: [ADR-0006](0006-authorization.md) roles and permissions unchanged;
  [ADR-0020](0020-smart-add-relative-provisional-people-age-order.md) §6 concealment unchanged.
- Supersedes the proposal in draft PR #82 (which reserved the number 0033, since taken by the
  accepted retention ADR). What was reused, changed and rejected from it is listed in §9.
- Related: issues #84 (complete traversal with pagination) and #85 (release gates);
  [threat model](../../security/threat-model.md) T69–T71; [privacy model](../../security/privacy-model.md) §5.

## Context

Two reported problems, both reproduced on `main` (`666d6e5`):

1. **A removed person comes back as "Private person".** `DELETE /people/{id}` sets `deleted_at` and
   leaves the relationship rows. `engine.graph` and `engine.family` walk the `relationship` table
   without looking at the people, then ask the visibility rule about whoever they reached. A removed
   person is correctly "not visible", and the code turned every not-visible person into an anonymous
   placeholder. One bucket held three different situations: hidden by privacy, removed, and
   permanently erased. Even the Owner who removed the person saw the placeholder, and the walk
   continued *through* the removed person to the relatives beyond.
2. **"Open full tree" was not the full tree.** The link opened the descendants of one person, three
   generations deep. No endpoint returned a connected family: the only traversal followed parent
   edges in one direction from one root, with a 25-generation and 500-node cap and no way to load
   the rest.

The same omission existed outside the tree views: branch and household counts, the
two-biological-parents limit, Smart Add, the chart endpoints and branch derivation each decided for
themselves whether a referenced person still counted, and most did not ask.

Permanent erasure had no state of its own. An erased person was an ordinary live row whose display
name happened to be "Erased person".

## Decision

### 1. Three lifecycle states, one place that decides them

| State | Stored as | Who can cause it | Reversible |
|---|---|---|---|
| **Active** | `deleted_at IS NULL` | — | — |
| **Removed from tree** | `deleted_at` set, `erased_at IS NULL` | `person.write` on that person (Owner, Family Admin, Contributor; Branch Admin within their branch), subject to the family's review policy | Yes: `tree.manage` (Owner, Family Admin) |
| **Permanently deleted** | `erased_at` set (and `deleted_at` with it) | `tree.manage` (Owner, Family Admin), with `confirm=true` and a reason | No |

`app/authz/lifecycle.py` answers "is this person still part of the tree?". `app/authz/privacy.py`
keeps answering the separate question "may this viewer see them?". `can_view_person`,
`get_person_subject` and `visible_subjects` refuse both removed and permanently deleted people.

`erased_at` is new (migration `b7f2c4e8d915`). It is backfilled only from the append-only audit log
(`person.erased`, matched on tree and person id) and never inferred from a name; a family may
legitimately record someone as "Erased person". Setting `deleted_at` together with it means every
existing "live people only" filter (search, GEDCOM and archive export, people list) leaves
tombstones out without each having to learn a new column.

### 2. Absent means absent

A removed or permanently deleted person is **absent** from every projection:

| Situation | In a family view or graph |
|---|---|
| Active, visible | Named card |
| Active, hidden by privacy | Anonymous placeholder, as before (privacy model §4) |
| Active, concealed provisional (ADR-0020 §6) | Nothing, as before |
| Removed from tree | **Nothing** |
| Permanently deleted | **Nothing** |
| A reference to a person who does not exist | Nothing; no placeholder is ever synthesised |

"Nothing" means no node, no edge, no placeholder, no count, and **nothing is reached through them**.
The rule is applied *before* traversal: `engine.absent_ids(ctx)` (removed + permanently deleted +
concealed provisional) is taken out of the edge list, so the walk cannot pass through. A
placeholder can now only come from an active person the viewer may not see.

Consequences that are intended:

- Removing or deleting a person who links two parts of a family **splits it**. The relatives on
  each side stay exactly as recorded and are no longer connected through that person. Nobody is
  re-linked to stand in (a grandchild is not attached to the grandparents), and no other relative is
  removed. Restoring a removed person restores the links, because the relationship rows were kept.
- A removed parent no longer counts towards the two-biological-parents limit, so a replacement can
  be recorded.
- Branch and household member counts, the charts, branch derivation and the relationship
  calculator all use the same set.

### 3. Permanent delete

`POST /people/{id}/erase` (the existing endpoint; the name is kept for compatibility) now means
*permanently delete*. In one transaction, under a row lock:

| Record | What happens |
|---|---|
| Names, events where the person is the principal, heritage claims, astrology, addresses and contacts, notes, revision history | Deleted (as before) |
| **Relationship rows touching the person**, and citations on those relationships | **Deleted** (new). A child edge that named one of the person's unions keeps its own parent and loses only the union reference (`ON DELETE SET NULL`) |
| Relative-age records, branch and household memberships of the person | Deleted (new). The branch and the household stay; a branch founded by the person keeps its members and loses the founder reference |
| Document, photo and tradition links to the person | Unlinked (as before). The document, photo or tradition itself stays with its owner |
| Claim, membership link, outstanding claim invites | Cleared or revoked (as before) |
| Other people, their records, and relationships between them | **Untouched** |
| The person row | Kept as an inert tombstone: no name data, no links, `erased_at` set. It exists so the audit entry and old foreign keys still resolve. It appears in no view, list, export or count, cannot be opened, and cannot be restored — for admins as well |
| Audit | `person.erased` with the reason (first 200 characters); no personal data |

This replaces "erasure leaves an anonymous placeholder so the tree's structure stays intact". The
reason: the placeholder was the reported defect, and a link kept "for structure" still discloses
that the deleted person existed and how they were related. The cost is stated in §2: the tree may
split. The confirmation dialog says so before the fact.

People erased *before* this change keep their relationship rows in the database (the migration is
deliberately non-destructive); §2 keeps those rows out of every projection.

Not covered by permanent delete, and listed as open in §8: property interests held by the person.

### 4. The complete family graph

`GET /api/v1/trees/{tree}/family-graph?scope=connected|all&person_id=…&cursor=…&limit=…`

| Scope | What it is |
|---|---|
| *Focused* (existing `/people/{id}/ancestors`, `/descendants`, `/family`) | A small person-centred view, with its documented depth limit. Unchanged except for §2 |
| **`connected`** | Everyone the viewer is authorised to see who is linked to `person_id` through recorded relationships. What "Open full tree" opens |
| **`all`** | Every group of the tree. Groups with no recorded relationship between them are returned as separate components and drawn apart; nothing joins them |

Traversal (`modules/genealogy/familygraph.py`):

- The family is a graph. Parent/child edges (biological, adoptive, step, foster, guardian), unions
  (spouse, partner, divorced, separated), explicit sibling edges and `other` edges are followed in
  both directions. Edge types are kept for display. Nothing is inferred from names, places or
  surnames; disproven and superseded edges are not followed.
- **No generation or hop limit.** A visited set makes cycles and repeated ancestors harmless and
  guarantees one node per person.
- It is breadth-first by frontier with batched queries, so the number of queries grows with the
  family's depth, not its size. `scope=all` loads the tree's edges once.
- Every query is filtered by `tree_id` and runs under row-level security. A person id from another
  tree is not a valid root (404).
- The server assigns each person a row (`generation`): partners and recorded siblings share a row
  and children sit below their parents, whichever way the family was reached. A contradictory
  record (a marriage across generations) cannot loop; the link that would close a cycle is ignored
  for row assignment only.

### 5. Privacy in the complete graph

1. **Absent people** (§2) are never there.
2. **A hidden active person is a placeholder with an opaque alias** (`hidden-<group>-<position>`,
   never derived from their id). No name, date, sex or id is sent.
3. **How far the walk goes past a hidden person** matches what members can already see today and
   no more: it continues along **parent/child** links (the ancestor and descendant views already
   do), and **never through a hidden person's marriage, sibling or other link** into another family.
   A hidden person reached only by such a link is a leaf.
4. A link between two hidden people is not sent.
5. **A group in which the viewer may see nobody is not returned and not counted.** `total_people`
   and `total_nodes` count only what this viewer receives.
6. A hidden or absent person is never a valid root (404, the same as "does not exist").
7. The same hidden person may be a placeholder in two groups under two aliases; the response never
   says they are the same person.

"Complete" therefore means *complete for this viewer*. The interface says "everyone … that you are
allowed to see", not "everyone".

### 6. Pages, completeness and change

The result is served in pages (default 500 people, at most 1,000) in a stable order: nearest
relatives first. Each edge is sent once, on the page that contains the later of its two people.

- `complete` is true only on the last page. Until then the client holds a partial family and must
  say so. There is no server-side cap that silently drops people: if it is not complete, there is a
  `next_cursor`.
- `total_people` / `total_nodes` describe the whole authorised result, so progress can be shown.
- The cursor carries a position and a **revision** of the tree (people and relationships: counts
  and latest change; plus the viewer's membership and roles). If the tree changes between pages the
  next page is refused with **409 `graph_changed`** and the client starts again. Pages from two
  states of the tree are never stitched together, so a person removed mid-load cannot linger.
- The cursor grants nothing. Every page is authorised from scratch for the caller; a forged or
  borrowed cursor can at most select a different page of what the caller may already see, or is
  refused (422 `invalid_cursor`, 409).

The interface has four explicit states: loading, partly loaded (with counts), stopped before the
end (with "Continue loading"), and complete. Only the last is described as the whole family.

### 7. Interface

- Profile: **Remove from tree** (anyone who may edit the person) and **Delete person** (tree
  admins), with separate dialogs. Delete requires a reason and typing the person's exact name. The
  controls only hide what the server would refuse.
- Tree viewer: a third mode, **Whole family**, with the scope switch (connected family / all groups
  in this tree), search within the loaded people, centre on a person, fit to screen, reset, zoom,
  pan, keyboard navigation, and a text list alternative. Large families draw only what is on screen
  and switch to plain boxes when zoomed far out.
- Layout (`frontend/src/lib/familyLayout.ts`) only chooses horizontal positions; it adds and joins
  nothing.

### 8. Not decided here

1. **Property interests** held by a removed or permanently deleted person. They are still shown as
   a hidden holder. What happens to a share when its holder is deleted is a property-model decision
   (ADR-0010).
2. **Reminders and review proposals** that point at a removed person are still listed, without the
   person.
3. **Optimistic concurrency** (an expected revision on remove/delete). Row locks make concurrent
   remove, restore and delete of the same person consistent; a stale-form check is not added.
4. **Collapse and expand of branches** in the Whole family mode, and a mini-map.
5. Whether an existing legacy erasure's relationship rows should be physically deleted by a later,
   separately reviewed data migration.
6. An in-process cache of the computed traversal keyed by the revision, if page latency on very
   large trees needs it. The revision makes this safe to add; correctness does not depend on it.

### 9. Draft PR #82

| From PR #82 | Here |
|---|---|
| Explicit `erased_at`, backfilled from the audit log, never from a name; downgrade refuses to drop populated markers | **Reused**, re-pointed onto the current head (`a6e3d9b1f204`; the original would have created a second Alembic head). Also sets `deleted_at` and adds a partial index |
| Excluding removed and erased people from `family`, `graph` and their edges | **Reused**, moved into one shared rule (`authz.lifecycle`, `engine.absent_ids`) and applied to charts, counts, the parent limit, branch derivation and the calculator as well |
| Tests: placeholder absence, restore, a person really named "Erased person", erased person not a root, viewer refused, failed delete does not navigate | **Reused**, rewritten for the new endpoint and extended |
| `GET /people/{id}/connected` capped at 500 people / 25 hops | **Replaced** by the paged, uncapped `family-graph` endpoint with explicit completeness (issue #84) |
| Generation from discovery order | **Replaced** (§4): it put partners on different rows in families with cousin marriage or cross-generation unions |
| One row per generation sorted by sex and birth year | **Replaced** by a layout that keeps couples together and children under parents |
| Walking through hidden people along any link, including marriages | **Rejected** (§5.3): wider disclosure than any existing view |
| A second, reason-only delete dialog on the profile | **Rejected**: weaker than the existing name-typing gate, which both entry points now share |
| Erased row kept with its relationship rows, hidden "as a display choice" | **Changed** (§3): the links are deleted |
| ADR number 0033 | **Changed** to 0034 |

## Consequences

- The reported placeholder cannot come from a removed or deleted person in any tree view.
- Families can split when a linking person is removed or deleted. This is visible (separate
  groups) and, for removal, reversible.
- `POST /erase` is more destructive than before: relationship rows go. It was already irreversible
  and admin-only; the confirmation text now says what is lost.
- Viewing a very large family costs one traversal per page. Measured figures are in
  `docs/operations/performance.md`.
- Rollback: the code can be rolled back while no person carries `erased_at` set by the new code.
  Once one does, the migration refuses to downgrade (older code would show the tombstone as a
  person named "Erased person"); roll forward or restore from backup.
