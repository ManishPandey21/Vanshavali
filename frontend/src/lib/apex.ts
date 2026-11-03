import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { BranchOut, GraphOut, Page, PersonSummary } from "../api/types";
import { useBranches } from "../api/hooks/family";
import { peopleKeys } from "../api/hooks/people";

/**
 * The family "elder": the person a whole-family view grows down from.
 *
 * - A family that has named its line (a top-level branch with a founder) starts there; with several,
 *   the branch with the most members wins.
 * - Otherwise we climb: from the viewer's own profile (or, failing that, the earliest-born person
 *   they can see) up the recorded ancestors to the most distant generation. Imported trees often
 *   have few dates, so "earliest-born" alone would land mid-tree; the climb fixes that.
 *
 * Only people the server already returned to this viewer are used, so nothing is revealed: a
 * founder the viewer cannot see is skipped, and hidden ancestors (no `person`) are never chosen.
 */

/** A branch founder the viewer can see, from the branch with the most members. */
export function pickFounder(branches: readonly BranchOut[], visible: ReadonlySet<string>): string | null {
  const best = [...branches]
    .filter((b) => !b.parent_branch_id && b.founder_person_id && visible.has(b.founder_person_id))
    .sort((a, b) => (b.member_count ?? 0) - (a.member_count ?? 0))[0];
  return best?.founder_person_id ?? null;
}

/** Earliest birth year first; people with no year last; then by name, so the choice is stable. */
function byAge(a: PersonSummary, b: PersonSummary) {
  const ya = a.birth_year ?? Number.POSITIVE_INFINITY;
  const yb = b.birth_year ?? Number.POSITIVE_INFINITY;
  return ya - yb || a.display_name.localeCompare(b.display_name);
}

/** Where to start climbing: the viewer's own profile when visible, else the earliest-born person. */
export function pickSeed(people: readonly PersonSummary[], linkedId?: string | null): string | null {
  if (linkedId && people.some((p) => p.id === linkedId)) return linkedId;
  return [...people].sort(byAge)[0]?.id ?? null;
}

/**
 * The most distant visible ancestor in an ancestors graph. Ties (several great-great-grandparents)
 * go to the paternal line first, as a vanshavali is traditionally reckoned, then to the earliest
 * born. Returns the graph root when it has no visible ancestors.
 */
export function pickTopAncestor(graph: GraphOut): string {
  const visible = graph.nodes.filter((n) => n.person && !n.partner);
  const far = Math.max(0, ...visible.map((n) => Math.abs(n.generation)));
  const top = visible
    .filter((n) => Math.abs(n.generation) === far)
    .map((n) => n.person!)
    .sort((a, b) => Number(b.sex_at_birth === "male") - Number(a.sex_at_birth === "male") || byAge(a, b))[0];
  return top?.id ?? graph.root_id;
}

const SAMPLE = 200;
const CLIMB_DEPTH = 25;

export function useFamilyApex(treeId: string, linkedId?: string | null) {
  const branches = useBranches(treeId);
  const people = useQuery({
    queryKey: ["tree", treeId, "people-count", ""],
    queryFn: () => api.get<Page<PersonSummary>>(`/trees/${treeId}/people`, { limit: SAMPLE }),
  });
  const items = people.data?.items ?? [];
  const listed = !branches.isLoading && !!people.data;
  const founder = listed ? pickFounder(branches.data ?? [], new Set(items.map((p) => p.id))) : null;
  const seed = listed && !founder ? pickSeed(items, linkedId) : null;
  const climb = useQuery({
    queryKey: peopleKeys.graph(treeId, seed ?? "", "ancestors", CLIMB_DEPTH, ""),
    queryFn: () => api.get<GraphOut>(`/trees/${treeId}/people/${seed}/ancestors`, { depth: CLIMB_DEPTH }),
    enabled: !!seed,
  });
  // A failed climb still leaves a usable start: the seed itself.
  const climbed = seed ? (climb.data ? pickTopAncestor(climb.data) : climb.error ? seed : null) : null;
  const apexId = founder ?? climbed;
  return {
    isLoading: !people.error && (!listed || (!!seed && climb.isLoading)),
    error: people.error,
    people: people.data,
    apexId,
  };
}
