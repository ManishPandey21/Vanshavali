# ADR-0033: Omit removed people from graphs; render the connected family component
- Status: Proposed · 13 November 2026
- Scope: same-tree display and deletion semantics only, no Phase G or cross-tree discovery.

## Context
The current profile Remove action soft-deletes `person.deleted_at`, but genealogy graph traversal
still walks relationship records with that person. Serializer hides deleted people, so a
"Private person" placeholder remains in overview and tree charts.
The overview's "Open full tree" links to `?dir=descendants`, and the viewer starts with
three generations. It does not mean the entire connected component.

## Decision
1. **Removed means absent, not anonymous.** Soft-deleted people, and any relationship
   touching them, are excluded from family projections, ancestry/descendant graphs and the
   new connected-component graph. Traversal stops at a removed person; it never bridges
   to relatives through the deleted vertex. Restore remains available to authorized
   tree admins. A merely privacy-hidden, *nondeleted* person may still be an anonymous
   placeholder, subject to existing privacy rules. Pending concealed provisional people
   remain completely absent.
2. **Two distinct actions.** Keep "Remove from tree" as the existing, restorable soft
   delete. Surface a separate "Delete permanently" action only to authorized tree
   managers, with explicit irreversible-erasure confirmation and a required reason.
   It reuses the existing audited `/erase` service, which retains an *erased-person*
   structural record; the complete-tree projection excludes erased records as a
   display choice. Do not hard-delete database rows and accidentally cascade other
   family records. No new irreversible operation is automatically invoked.
3. **Connected component endpoint.** `GET /trees/{tree_id}/people/{person_id}/connected`
   returns parent/child, union/spouse and explicit sibling edges in the component
   reachable from an authorized root, up to the configured traversal/hard node budgets.
   Use a new graph direction `connected`. All nodes are rendered in the complete
   chart or list, with ancestors and descendant branches, rather than silently
   reducing to a descendant slice. Disconnected family components are never
   falsely joined. Render a visible "incomplete" warning whenever limits are hit.
4. **Server-side authorization.** No raw person names, ids or edge details for
   invisible people are exposed through the connected endpoint; hidden nodes use
   per-response opaque aliases, matching existing graph semantics. Never use a
   private person as a chart root without authorization. No cross-tree references.
5. **Layout.** The connected chart lays out the whole returned component as a
   generation-aware forest (roots plus partners), preserving all returned edges.
   Components without connections are represented as their own one-person view.

## Rejected alternatives
- Relabeling the old three-generation descendant view as "full".
- Turning deleted people into the "private person" placeholder.
- Auto-merging unrelated components or restoring historical relationships by guesswork.
- Hard-deleting person/relationship rows without a full retention/provenance analysis.

## Acceptance gates
- Remove a nonleaf person: neither its identity nor placeholder appears in
  overview, descendants, ancestors, family view, or connected view, and no
  bridge through that person remains.
- Privacy-hidden living person remains subject to the existing anonymity contract.
- A user selected mid-tree can open ancestors, descendants, side branches and spouses
  from the same connected component.
- Authorized restores bring the removed person back; unrelated isolated people
  remain separate; no cross-tree access works.
- Larger-than-budget component reports `truncated=true`, never pretends completeness.
- Negative tests for nonmembers, branch/field privacy, concealed provisional people;
  no membership or record write privilege changes.

## Rollout
Draft PR with unit, integration, frontend and E2E regression gates. Do not
merge/deploy before this ADR is reviewed and accepted.
