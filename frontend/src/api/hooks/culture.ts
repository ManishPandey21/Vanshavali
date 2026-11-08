import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../client";
import type {
  KinshipOverrideIn,
  KinshipOverrideOut,
  KinshipPackOut,
  KinshipPreferenceIn,
  Message,
  OfferIn,
  OfferOut,
  TraditionEntryIn,
  TraditionEntryUpdate,
  TraditionKind,
  TraditionOut,
  TraditionRevisionOut,
  TraditionsOut,
  UserOut,
  VocabularyTerms,
} from "../types";
import { authKeys } from "./auth";

/** Cultural depth (ADR-0026): relationship words, family words, offers and traditions. */
const keys = {
  packs: ["kinship", "packs"] as const,
  overrides: (treeId: string) => ["tree", treeId, "kinship-overrides"] as const,
  offers: (treeId: string) => ["tree", treeId, "vocabulary-offers"] as const,
  family: (treeId: string, key: string) => ["tree", treeId, "vocabulary", key, "family"] as const,
  traditions: (treeId: string) => ["tree", treeId, "traditions"] as const,
  traditionList: (treeId: string, filters: TraditionFilters) => ["tree", treeId, "traditions", "list", filters] as const,
  tradition: (treeId: string, id: string) => ["tree", treeId, "traditions", "one", id] as const,
  traditionHistory: (treeId: string, id: string) => ["tree", treeId, "traditions", "history", id] as const,
};

// ---------------------------------------------------------------- relationship words
export function useKinshipPacks() {
  return useQuery({ queryKey: keys.packs, queryFn: () => api.get<KinshipPackOut[]>("/kinship/packs"), staleTime: 10 * 60_000 });
}

export function useSetKinshipPreference() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: KinshipPreferenceIn) => api.put<KinshipPreferenceIn>("/me/kinship-preference", body),
    onSuccess: (pref) => {
      qc.setQueryData<UserOut | null>(authKeys.me, (u) => (u ? { ...u, kinship_lang: pref.lang ?? null, kinship_region: pref.region ?? null } : u));
      qc.invalidateQueries({ predicate: (q) => q.queryKey.includes("path") });
    },
  });
}

export function useKinshipOverrides(treeId: string) {
  return useQuery({ queryKey: keys.overrides(treeId), queryFn: () => api.get<KinshipOverrideOut[]>(`/trees/${treeId}/kinship-overrides`) });
}

export function usePutKinshipOverride(treeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: KinshipOverrideIn) => api.put<KinshipOverrideOut>(`/trees/${treeId}/kinship-overrides`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tree", treeId] }),
  });
}

export function useDeleteKinshipOverride(treeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.del<Message>(`/trees/${treeId}/kinship-overrides/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tree", treeId] }),
  });
}

// ---------------------------------------------------------------- offers (ADR-0026 §4)
export const OFFERABLE = ["kuladevata", "kuladevi", "devak", "gotra", "kula"] as const;

/** This family's own entries in one list (global suggestions left out). */
export function useFamilyEntries(treeId: string, key: string) {
  return useQuery({
    queryKey: keys.family(treeId, key),
    queryFn: () => api.get<VocabularyTerms>(`/trees/${treeId}/vocabularies/${key}`, { q: "" }),
    select: (d) => d.items.filter((i) => i.origin === "family"),
    retry: false,
  });
}

export function useOffers(treeId: string) {
  return useQuery({ queryKey: keys.offers(treeId), queryFn: () => api.get<OfferOut[]>(`/trees/${treeId}/vocabulary-offers`) });
}

export function useOfferEntry(treeId: string, key: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ code, body }: { code: string; body: OfferIn }) =>
      api.post<OfferOut>(`/trees/${treeId}/vocabularies/${key}/terms/${encodeURIComponent(code)}/offer`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.offers(treeId) });
      qc.invalidateQueries({ queryKey: keys.family(treeId, key) });
    },
  });
}

export function useWithdrawOffer(treeId: string, key: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (code: string) => api.del<OfferOut>(`/trees/${treeId}/vocabularies/${key}/terms/${encodeURIComponent(code)}/offer`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.offers(treeId) });
      qc.invalidateQueries({ queryKey: keys.family(treeId, key) });
    },
  });
}

// ---------------------------------------------------------------- traditions (ADR-0026 §7)
export interface TraditionFilters {
  kind?: TraditionKind | "";
  q?: string;
  person_id?: string;
  branch_id?: string;
}

export function useTraditions(treeId: string, filters: TraditionFilters, enabled = true) {
  return useQuery({
    queryKey: keys.traditionList(treeId, filters),
    queryFn: ({ signal }) =>
      api.get<TraditionsOut>(
        `/trees/${treeId}/traditions`,
        { kind: filters.kind || undefined, q: filters.q || undefined, person_id: filters.person_id, branch_id: filters.branch_id },
        signal,
      ),
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useTradition(treeId: string, id: string) {
  return useQuery({ queryKey: keys.tradition(treeId, id), queryFn: () => api.get<TraditionOut>(`/trees/${treeId}/traditions/${id}`) });
}

export function useTraditionHistory(treeId: string, id: string, enabled: boolean) {
  return useQuery({
    queryKey: keys.traditionHistory(treeId, id),
    queryFn: () => api.get<TraditionRevisionOut[]>(`/trees/${treeId}/traditions/${id}/history`),
    enabled,
  });
}

export function useCreateTradition(treeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TraditionEntryIn) => api.post<TraditionOut>(`/trees/${treeId}/traditions`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.traditions(treeId) }),
  });
}

export function useUpdateTradition(treeId: string, id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TraditionEntryUpdate) => api.patch<TraditionOut>(`/trees/${treeId}/traditions/${id}`, body),
    onSuccess: (e) => {
      qc.setQueryData(keys.tradition(treeId, id), e);
      qc.invalidateQueries({ queryKey: keys.traditions(treeId) });
    },
  });
}

export function useWithdrawTradition(treeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.del<Message>(`/trees/${treeId}/traditions/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.traditions(treeId) }),
  });
}
