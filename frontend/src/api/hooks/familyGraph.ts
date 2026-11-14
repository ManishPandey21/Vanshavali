import { useEffect, useMemo, useRef } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../client";
import type { FamilyGraphOut } from "../types";
import { peopleKeys } from "./people";

export type FamilyScope = "connected" | "all";

/**
 * - `loading`: nothing to show yet.
 * - `partial`: some people are shown and more are on their way.
 * - `incomplete`: loading stopped (an error); what is shown is *not* the whole family.
 * - `complete`: the server has said this is everyone the viewer may see.
 */
export type FamilyGraphStatus = "loading" | "partial" | "incomplete" | "complete";

const PAGE = 500;
const MAX_RESTARTS = 3;

export const familyGraphKey = (treeId: string, scope: FamilyScope, personId: string | null) =>
  // under the tree's key, so every genealogy write (remove, delete, restore, edit) refreshes it
  [...peopleKeys.tree(treeId), "family-graph", scope, personId ?? ""] as const;

/**
 * The complete family graph (ADR-0034), loaded page by page until the server says it is complete.
 * A page is never presented as the whole: `status` and `loadedPeople` / `totalPeople` say how far
 * loading has got. If the tree changes underneath (409 `graph_changed`) loading starts again, so
 * pages from two states of the tree are never mixed and a removed person cannot linger.
 */
export function useFamilyGraph(treeId: string, scope: FamilyScope, personId: string | null, enabled = true) {
  const qc = useQueryClient();
  const key = familyGraphKey(treeId, scope, personId);
  const q = useInfiniteQuery({
    queryKey: key,
    queryFn: ({ pageParam, signal }) =>
      api.get<FamilyGraphOut>(
        `/trees/${treeId}/family-graph`,
        { scope, person_id: scope === "connected" ? (personId ?? undefined) : undefined, cursor: pageParam ?? undefined, limit: PAGE },
        signal,
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => (last.complete ? null : last.next_cursor),
    enabled: enabled && (scope === "all" || !!personId),
    retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 2,
  });

  const { hasNextPage, isFetchingNextPage, isFetching, isError, fetchNextPage, error } = q;
  useEffect(() => {
    if (hasNextPage && !isFetchingNextPage && !isFetching && !isError) void fetchNextPage();
  }, [hasNextPage, isFetchingNextPage, isFetching, isError, fetchNextPage]);

  const restarts = useRef(0);
  const keyText = key.join("|");
  useEffect(() => {
    restarts.current = 0;
  }, [keyText]);
  const changed = error instanceof ApiError && error.code === "graph_changed";
  useEffect(() => {
    if (!changed || restarts.current >= MAX_RESTARTS) return;
    restarts.current += 1;
    void qc.resetQueries({ queryKey: key, exact: true });
    // `key` is described by keyText
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [changed, keyText, qc]);

  const pages = q.data?.pages;
  const merged = useMemo(() => {
    const first = pages?.[0];
    return {
      nodes: pages?.flatMap((p) => p.nodes) ?? [],
      edges: pages?.flatMap((p) => p.edges) ?? [],
      links: pages?.flatMap((p) => p.links) ?? [],
      components: first?.components ?? [],
      totalNodes: first?.total_nodes ?? 0,
      totalPeople: first?.total_people ?? 0,
    };
  }, [pages]);
  const complete = !!pages?.length && pages[pages.length - 1].complete;
  const status: FamilyGraphStatus = complete
    ? "complete"
    : !pages?.length
      ? isError && !changed
        ? "incomplete"
        : "loading"
      : isError && !(changed && restarts.current < MAX_RESTARTS)
        ? "incomplete"
        : "partial";
  return {
    ...merged,
    loadedPeople: merged.nodes.filter((n) => n.person).length,
    status,
    complete,
    error: status === "incomplete" ? error : null,
    /** Continue after an error: carry on from the last page, or start again if the tree changed. */
    resume: () => (changed || !pages?.length ? qc.resetQueries({ queryKey: key, exact: true }) : fetchNextPage()),
  };
}
