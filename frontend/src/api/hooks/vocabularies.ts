import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../client";
import type { TreeTermIn, TreeTermOut, VocabularyTerms } from "../types";

/**
 * Suggestions from a master-data vocabulary (ADR-0018): global terms plus, inside a tree, the
 * family's own entries. Errors (e.g. 404 while the service is switched off) are left to the
 * caller, which falls back to a plain text field.
 */
export function useVocabulary(treeId: string | null, key: string, q: string, lang: string, enabled = true) {
  const path = treeId ? `/trees/${treeId}/vocabularies/${key}` : `/vocabularies/${key}`;
  return useQuery({
    queryKey: treeId ? ["tree", treeId, "vocabulary", key, q, lang] : ["vocabulary", key, q, lang],
    queryFn: () => api.get<VocabularyTerms>(path, { q, lang }),
    enabled,
    staleTime: 5 * 60_000,
    placeholderData: keepPreviousData,
    retry: false,
  });
}

export function useAddVocabularyTerm(treeId: string, key: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TreeTermIn) => api.post<TreeTermOut>(`/trees/${treeId}/vocabularies/${key}/terms`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tree", treeId, "vocabulary", key] }),
  });
}

/** Pravaras linked to a gotra by a reviewed, sourced link only (ADR-0026 §3). */
export function usePravaraSuggestions(gotraCode: string | null, lang: string) {
  return useQuery({
    queryKey: ["vocabulary", "pravara", "reviewed", gotraCode, lang],
    queryFn: () => api.get<VocabularyTerms>("/vocabularies/pravara", { parent: gotraCode!, reviewed_only: true, lang }),
    enabled: !!gotraCode,
    staleTime: 5 * 60_000,
    retry: false,
  });
}
