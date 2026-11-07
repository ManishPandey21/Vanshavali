import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../client";
import type {
  AdminTermDetail,
  AdminTermPage,
  AdminVocabulary,
  ChangeIn,
  VocabularyDuplicate,
  MasterDataChange,
  MasterDataChangePage,
} from "../types";

/**
 * Super Admin master-data console (ADR-0026). The server is the authority: it answers 404 to
 * anyone without the platform capability and 403 `admin_mfa_required` to an admin without MFA.
 */
const BASE = "/admin/master-data";
export const mdKeys = {
  all: ["md-admin"] as const,
  vocabularies: ["md-admin", "vocabularies"] as const,
  terms: (key: string, params: object) => ["md-admin", "terms", key, params] as const,
  term: (key: string, code: string) => ["md-admin", "term", key, code] as const,
  changes: (params: object) => ["md-admin", "changes", params] as const,
};

export function useAdminVocabularies() {
  return useQuery({
    queryKey: mdKeys.vocabularies,
    queryFn: () => api.get<AdminVocabulary[]>(`${BASE}/vocabularies`),
    retry: false,
  });
}

export interface TermQuery {
  q: string;
  status: string;
  sort: string;
  cursor: string | null;
}

export function useAdminTerms(key: string, query: TermQuery) {
  return useQuery({
    queryKey: mdKeys.terms(key, query),
    queryFn: () =>
      api.get<AdminTermPage>(`${BASE}/vocabularies/${key}/terms`, {
        q: query.q,
        status: query.status || undefined,
        sort: query.sort,
        cursor: query.cursor ?? undefined,
        limit: 25,
      }),
    placeholderData: keepPreviousData,
    retry: false,
  });
}

export function useAdminTerm(key: string, code: string | null) {
  return useQuery({
    queryKey: mdKeys.term(key, code ?? ""),
    queryFn: () => api.get<AdminTermDetail>(`${BASE}/vocabularies/${key}/terms/${code}`),
    enabled: !!code,
    retry: false,
  });
}

export function useAdminChanges(params: { status?: string; vocabulary?: string; cursor?: string | null }) {
  return useQuery({
    queryKey: mdKeys.changes(params),
    queryFn: () =>
      api.get<MasterDataChangePage>(`${BASE}/changes`, {
        status: params.status || undefined,
        vocabulary: params.vocabulary || undefined,
        cursor: params.cursor ?? undefined,
        limit: 25,
      }),
    placeholderData: keepPreviousData,
    retry: false,
  });
}

export function checkDuplicates(key: string, labels: Record<string, string>, aliases: string[], excludeCode?: string) {
  return api.post<VocabularyDuplicate[]>(`${BASE}/vocabularies/${key}/duplicates`, {
    labels,
    aliases,
    exclude_code: excludeCode ?? null,
  });
}

/** Any console write refreshes the console and the users' suggestion lists (no deployment needed). */
function useInvalidateAll() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: mdKeys.all });
    void qc.invalidateQueries({ queryKey: ["vocabulary"] });
    void qc.invalidateQueries({ predicate: (q) => q.queryKey[0] === "tree" && q.queryKey[2] === "vocabulary" });
  };
}

export function useProposeChange(key: string) {
  const done = useInvalidateAll();
  return useMutation({
    mutationFn: (body: ChangeIn) => api.post<MasterDataChange>(`${BASE}/vocabularies/${key}/changes`, body),
    onSuccess: done,
  });
}

export function useDecideChange() {
  const done = useInvalidateAll();
  return useMutation({
    mutationFn: ({ id, decision, note }: { id: string; decision: "publish" | "reject" | "withdraw"; note?: string }) =>
      api.post<MasterDataChange>(`${BASE}/changes/${id}/${decision}`, decision === "withdraw" ? {} : { note: note || null }),
    onSuccess: done,
  });
}
