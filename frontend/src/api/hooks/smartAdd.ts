import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../client";
import type { Message, SmartAddCommitIn, SmartAddCommitOut, SmartAddPlan, SmartAddTerm } from "../types";
import { peopleKeys } from "./people";

/** Smart Add Relative (ADR-0020): term catalogue, side-effect-free plan, confirmed commit, undo. */
export function useSmartAddTerms(treeId: string) {
  return useQuery({
    queryKey: ["tree", treeId, "smart-add", "terms"],
    queryFn: () => api.get<SmartAddTerm[]>(`/trees/${treeId}/smart-add/terms`),
    staleTime: Infinity,
  });
}

export function useSmartAddPlan(treeId: string, anchorId: string, term: string | null, choices: string[]) {
  return useQuery({
    queryKey: ["tree", treeId, "smart-add", "plan", anchorId, term, choices.join(",")],
    queryFn: () => api.post<SmartAddPlan>(`/trees/${treeId}/people/${anchorId}/smart-add/plan`, { term, choices }),
    enabled: !!term,
    placeholderData: keepPreviousData,
    staleTime: 0,
    retry: false,
  });
}

export function useSmartAddCommit(treeId: string, anchorId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SmartAddCommitIn) => api.post<SmartAddCommitOut>(`/trees/${treeId}/people/${anchorId}/smart-add`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: peopleKeys.tree(treeId) }),
  });
}

export function useSmartAddUndo(treeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (operationId: string) => api.post<Message>(`/trees/${treeId}/smart-add/${operationId}/undo`),
    onSuccess: () => qc.invalidateQueries({ queryKey: peopleKeys.tree(treeId) }),
  });
}
