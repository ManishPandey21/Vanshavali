import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../client";
import type {
  BranchDetailOut,
  BranchIn,
  BranchOut,
  DeriveOut,
  GenealogicalDate,
  HouseholdDetailOut,
  HouseholdIn,
  HouseholdMemberIn,
  HouseholdMemberOut,
  HouseholdOut,
  Message,
  PersonHouseholdOut,
  PersonOut,
  PersonSummary,
  Page,
  PublicTreeOut,
  FamilyOut,
  GraphOut,
} from "../types";

function useInvalidateTree(treeId: string) {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["tree", treeId] });
}

export function useBranches(treeId: string) {
  return useQuery({ queryKey: ["tree", treeId, "branches"], queryFn: () => api.get<BranchOut[]>(`/trees/${treeId}/branches`) });
}

export function useBranch(treeId: string, branchId: string) {
  return useQuery({
    queryKey: ["tree", treeId, "branch", branchId],
    queryFn: () => api.get<BranchDetailOut>(`/trees/${treeId}/branches/${branchId}`),
  });
}

export function useCreateBranch(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (body: BranchIn) => api.post<BranchOut>(`/trees/${treeId}/branches`, body),
    onSuccess: invalidate,
  });
}

export function useUpdateBranch(treeId: string, branchId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (body: Partial<BranchIn>) => api.patch<BranchOut>(`/trees/${treeId}/branches/${branchId}`, body),
    onSuccess: invalidate,
  });
}

export function useDeleteBranch(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (branchId: string) => api.del<Message>(`/trees/${treeId}/branches/${branchId}`),
    onSuccess: invalidate,
  });
}

export function useDeriveBranch(treeId: string, branchId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: () => api.post<DeriveOut>(`/trees/${treeId}/branches/${branchId}/derive-members`),
    onSuccess: invalidate,
  });
}

export function useAddBranchMembers(treeId: string, branchId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (personIds: string[]) =>
      api.post<DeriveOut>(`/trees/${treeId}/branches/${branchId}/members`, { person_ids: personIds }),
    onSuccess: invalidate,
  });
}

export function useRemoveBranchMember(treeId: string, branchId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (personId: string) => api.del<Message>(`/trees/${treeId}/branches/${branchId}/members/${personId}`),
    onSuccess: invalidate,
  });
}

// ---- households
export function useHouseholds(treeId: string, branchId?: string) {
  return useQuery({
    queryKey: ["tree", treeId, "households", branchId ?? ""],
    queryFn: () => api.get<HouseholdOut[]>(`/trees/${treeId}/households`, { branch_id: branchId }),
  });
}

export function useHousehold(treeId: string, householdId: string, enabled = true) {
  return useQuery({
    queryKey: ["tree", treeId, "household", householdId],
    queryFn: () => api.get<HouseholdDetailOut>(`/trees/${treeId}/households/${householdId}`),
    enabled,
  });
}

export function useCreateHousehold(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (body: HouseholdIn) => api.post<HouseholdOut>(`/trees/${treeId}/households`, body),
    onSuccess: invalidate,
  });
}

export function useUpdateHousehold(treeId: string, id: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (body: Partial<HouseholdIn>) => api.patch<HouseholdOut>(`/trees/${treeId}/households/${id}`, body),
    onSuccess: invalidate,
  });
}

export function useDeleteHousehold(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (id: string) => api.del<Message>(`/trees/${treeId}/households/${id}`),
    onSuccess: invalidate,
  });
}

export function useAddHouseholdMember(treeId: string, householdId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (body: HouseholdMemberIn) =>
      api.post<HouseholdMemberOut>(`/trees/${treeId}/households/${householdId}/members`, body),
    onSuccess: invalidate,
  });
}

export function useEndHouseholdMember(treeId: string, householdId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: ({ id, endDate, remove }: { id: string; endDate: GenealogicalDate | null; remove?: boolean }) =>
      api.post<Message>(`/trees/${treeId}/households/${householdId}/members/${id}/end`, {
        end_date: endDate,
        delete: !!remove,
      }),
    onSuccess: invalidate,
  });
}

export function usePersonHouseholds(treeId: string, personId: string) {
  return useQuery({
    queryKey: ["tree", treeId, "person", personId, "households"],
    queryFn: () => api.get<PersonHouseholdOut[]>(`/trees/${treeId}/people/${personId}/households`),
  });
}

// ---- public (unauthenticated, deceased-only)
export function usePublicTree(slug: string) {
  return useQuery({ queryKey: ["public", slug], queryFn: () => api.get<PublicTreeOut>(`/public/trees/${slug}`), retry: false });
}

export function usePublicPeople(slug: string) {
  return useQuery({
    queryKey: ["public", slug, "people"],
    queryFn: () => api.get<Page<PersonSummary>>(`/public/trees/${slug}/people`, { limit: 200 }),
  });
}

export function usePublicPerson(slug: string, id: string) {
  return useQuery({
    queryKey: ["public", slug, "person", id],
    queryFn: () => api.get<PersonOut>(`/public/trees/${slug}/people/${id}`),
    retry: false,
  });
}

export function usePublicFamily(slug: string, id: string) {
  return useQuery({
    queryKey: ["public", slug, "person", id, "family"],
    queryFn: () => api.get<FamilyOut>(`/public/trees/${slug}/people/${id}/family`),
    retry: false,
  });
}

export function usePublicAncestors(slug: string, id: string, depth: number) {
  return useQuery({
    queryKey: ["public", slug, "person", id, "ancestors", depth],
    queryFn: () => api.get<GraphOut>(`/public/trees/${slug}/people/${id}/ancestors`, { depth }),
    retry: false,
  });
}

export type { PersonOut };
