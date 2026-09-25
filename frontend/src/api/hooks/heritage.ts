import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../client";
import type {
  AssertionIn,
  AssertionOut,
  AssertionUpdate,
  CitationIn,
  CitationOut,
  CitationTarget,
  ClaimOut,
  ConsentIn,
  ConsentOut,
  DuplicateCandidate,
  HeritageProfileOut,
  Message,
  Page,
  SearchOut,
  SourceIn,
  SourceOut,
  SourceType,
} from "../types";

const treeKey = (t: string) => ["tree", t] as const;

function useInvalidateTree(treeId: string) {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: treeKey(treeId) });
}

// ---- heritage
export type HeritageSubject = { kind: "person" | "branch"; id: string };

const subjectPath = (s: HeritageSubject) => (s.kind === "person" ? `people/${s.id}` : `branches/${s.id}`);

export function useHeritage(treeId: string, subject: HeritageSubject) {
  return useQuery({
    queryKey: ["tree", treeId, subject.kind === "person" ? "person" : "branch", subject.id, "heritage"],
    queryFn: () => api.get<HeritageProfileOut>(`/trees/${treeId}/${subjectPath(subject)}/heritage`),
  });
}

export function useAddAssertion(treeId: string, subject: HeritageSubject) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (body: AssertionIn) => api.post<AssertionOut>(`/trees/${treeId}/${subjectPath(subject)}/heritage`, body),
    onSuccess: invalidate,
  });
}

export function useUpdateAssertion(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: AssertionUpdate }) =>
      api.patch<AssertionOut>(`/trees/${treeId}/assertions/${id}`, body),
    onSuccess: invalidate,
  });
}

export function useDeleteAssertion(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (id: string) => api.del<Message>(`/trees/${treeId}/assertions/${id}`),
    onSuccess: invalidate,
  });
}

// ---- sources & citations
export function useSources(treeId: string, q: string, sourceType?: SourceType) {
  return useInfiniteQuery({
    queryKey: ["tree", treeId, "sources", q, sourceType ?? ""],
    queryFn: ({ pageParam }) =>
      api.get<Page<SourceOut>>(`/trees/${treeId}/sources`, { q, source_type: sourceType, cursor: pageParam, limit: 50 }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}

export function useCreateSource(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (body: SourceIn) => api.post<SourceOut>(`/trees/${treeId}/sources`, body),
    onSuccess: invalidate,
  });
}

export function useUpdateSource(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<SourceIn> }) => api.patch<SourceOut>(`/trees/${treeId}/sources/${id}`, body),
    onSuccess: invalidate,
  });
}

export function useCitations(treeId: string, targetType: CitationTarget, targetId: string, enabled = true) {
  return useQuery({
    queryKey: ["tree", treeId, "citations", targetType, targetId],
    queryFn: () =>
      api.get<CitationOut[]>(`/trees/${treeId}/citations`, { target_type: targetType, target_id: targetId }),
    enabled,
  });
}

export function useAddCitation(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (body: CitationIn) => api.post<CitationOut>(`/trees/${treeId}/citations`, body),
    onSuccess: invalidate,
  });
}

export function useDeleteCitation(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (id: string) => api.del<Message>(`/trees/${treeId}/citations/${id}`),
    onSuccess: invalidate,
  });
}

// ---- search
export function useSearch(treeId: string, q: string, kinds?: string[]) {
  return useQuery({
    queryKey: ["tree", treeId, "search", q, (kinds ?? []).join(",")],
    queryFn: ({ signal }) => api.get<SearchOut>(`/trees/${treeId}/search`, { q, kinds, limit: 30 }, signal),
    enabled: q.trim().length > 0,
  });
}

export function useDuplicates(treeId: string, minScore: number) {
  return useQuery({
    queryKey: ["tree", treeId, "duplicates", minScore],
    queryFn: () => api.get<DuplicateCandidate[]>(`/trees/${treeId}/duplicates`, { min_score: minScore, limit: 100 }),
  });
}

// ---- consent & claims
export function useConsents(treeId: string, personId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["tree", treeId, "person", personId, "consents"],
    queryFn: () => api.get<ConsentOut[]>(`/trees/${treeId}/people/${personId}/consents`),
    enabled,
    retry: false,
  });
}

export function useRecordConsent(treeId: string, personId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (body: ConsentIn) => api.post<ConsentOut>(`/trees/${treeId}/people/${personId}/consents`, body),
    onSuccess: invalidate,
  });
}

export function useWithdrawConsent(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (id: string) => api.post<ConsentOut>(`/trees/${treeId}/consents/${id}/withdraw`),
    onSuccess: invalidate,
  });
}

export function useRequestClaim(treeId: string, personId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (message: string) =>
      api.post<ClaimOut>(`/trees/${treeId}/people/${personId}/claims`, { message: message || null }),
    onSuccess: invalidate,
  });
}
