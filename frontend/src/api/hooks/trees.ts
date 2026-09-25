import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../client";
import type {
  AuditEventOut,
  ClaimOut,
  InvitationCreate,
  InvitationOut,
  InvitationPreview,
  MemberOut,
  MemberUpdate,
  Message,
  Page,
  TreeOut,
  TreeUpdate,
} from "../types";

export const treeKeys = {
  all: ["trees"] as const,
  detail: (t: string) => ["tree", t] as const,
  members: (t: string) => ["tree", t, "members"] as const,
  invitations: (t: string) => ["tree", t, "invitations"] as const,
  audit: (t: string, action?: string) => ["tree", t, "audit", action ?? ""] as const,
  claims: (t: string) => ["tree", t, "claims"] as const,
};

export function useTrees() {
  return useQuery({ queryKey: treeKeys.all, queryFn: () => api.get<TreeOut[]>("/trees") });
}

export function useTree(treeId: string | undefined) {
  return useQuery({
    queryKey: treeKeys.detail(treeId ?? ""),
    queryFn: () => api.get<TreeOut>(`/trees/${treeId}`),
    enabled: !!treeId,
  });
}

export function useCreateTree() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; description?: string | null }) => api.post<TreeOut>("/trees", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: treeKeys.all }),
  });
}

export function useUpdateTree(treeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TreeUpdate) => api.patch<TreeOut>(`/trees/${treeId}`, body),
    onSuccess: (tree) => {
      qc.setQueryData(treeKeys.detail(treeId), tree);
      qc.invalidateQueries({ queryKey: treeKeys.all });
    },
  });
}

export function useMembers(treeId: string) {
  return useQuery({
    queryKey: treeKeys.members(treeId),
    queryFn: () => api.get<MemberOut[]>(`/trees/${treeId}/members`),
  });
}

export function useUpdateMember(treeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: MemberUpdate }) =>
      api.patch<MemberOut>(`/trees/${treeId}/members/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: treeKeys.members(treeId) }),
  });
}

export function useRemoveMember(treeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.del<Message>(`/trees/${treeId}/members/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: treeKeys.members(treeId) }),
  });
}

export function useInvitations(treeId: string, enabled = true) {
  return useQuery({
    queryKey: treeKeys.invitations(treeId),
    queryFn: () => api.get<InvitationOut[]>(`/trees/${treeId}/invitations`),
    enabled,
  });
}

export function useCreateInvitation(treeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: InvitationCreate) => api.post<InvitationOut>(`/trees/${treeId}/invitations`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: treeKeys.invitations(treeId) }),
  });
}

export function useRevokeInvitation(treeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.del<Message>(`/trees/${treeId}/invitations/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: treeKeys.invitations(treeId) }),
  });
}

export function useInvitationPreview(token: string, enabled: boolean) {
  return useQuery({
    queryKey: ["invitation", token],
    queryFn: () => api.get<InvitationPreview>(`/invitations/${encodeURIComponent(token)}`),
    enabled,
    retry: false,
  });
}

export function useAcceptInvitation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (token: string) => api.post<TreeOut>(`/invitations/${encodeURIComponent(token)}/accept`),
    onSuccess: () => qc.invalidateQueries({ queryKey: treeKeys.all }),
  });
}

export function useAudit(treeId: string, action?: string) {
  return useInfiniteQuery({
    queryKey: treeKeys.audit(treeId, action),
    queryFn: ({ pageParam }) =>
      api.get<Page<AuditEventOut>>(`/trees/${treeId}/audit`, { cursor: pageParam, limit: 50, action }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}

export function useClaims(treeId: string) {
  return useQuery({
    queryKey: treeKeys.claims(treeId),
    queryFn: () => api.get<ClaimOut[]>(`/trees/${treeId}/claims`),
  });
}

export function useReviewClaim(treeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, approve, note }: { id: string; approve: boolean; note?: string }) =>
      api.post<ClaimOut>(`/trees/${treeId}/claims/${id}/${approve ? "approve" : "reject"}`, { note: note || null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: treeKeys.claims(treeId) });
      qc.invalidateQueries({ queryKey: ["tree", treeId, "person"] });
    },
  });
}
