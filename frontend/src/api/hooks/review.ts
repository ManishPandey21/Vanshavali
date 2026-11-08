import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../client";
import type {
  ChallengeIn,
  ChangeProposalOut,
  DuplicateCheckIn,
  DuplicateCheckOut,
  NotificationsOut,
  Page,
  ProposalIn,
  ProposalSummary,
  RevertOut,
  ReviewPolicy,
  RevisionOut,
} from "../types";

/** Change proposals, family review, history and duplicates at entry (ADR-0021). */
const keys = {
  all: (treeId: string) => ["tree", treeId, "review"] as const,
  list: (treeId: string, view: string, personId?: string) => ["tree", treeId, "review", "list", view, personId ?? ""] as const,
  one: (treeId: string, id: string) => ["tree", treeId, "review", "one", id] as const,
  notes: (treeId: string) => ["tree", treeId, "review", "notifications"] as const,
  history: (treeId: string, personId: string) => ["tree", treeId, "review", "history", personId] as const,
};

export type ProposalView = "to_review" | "mine" | "closed" | "all";

export function useProposals(treeId: string, view: ProposalView, personId?: string, enabled = true) {
  return useQuery({
    queryKey: keys.list(treeId, view, personId),
    queryFn: ({ signal }) => api.get<Page<ProposalSummary>>(`/trees/${treeId}/proposals`, { view, person_id: personId }, signal),
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useProposal(treeId: string, id: string) {
  return useQuery({
    queryKey: keys.one(treeId, id),
    queryFn: ({ signal }) => api.get<ChangeProposalOut>(`/trees/${treeId}/proposals/${id}`, undefined, signal),
    // diffs are against today's records: always fetch fresh
    staleTime: 0,
  });
}

function useInvalidate(treeId: string) {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["tree", treeId] });
}

export function useCreateProposal(treeId: string) {
  const invalidate = useInvalidate(treeId);
  return useMutation({
    mutationFn: (body: ProposalIn) => api.post<ChangeProposalOut>(`/trees/${treeId}/proposals`, body),
    onSuccess: invalidate,
  });
}

export function useCreateChallenge(treeId: string) {
  const invalidate = useInvalidate(treeId);
  return useMutation({
    mutationFn: (body: ChallengeIn) => api.post<ChangeProposalOut>(`/trees/${treeId}/challenges`, body),
    onSuccess: invalidate,
  });
}

export type Decision = "approve" | "reject" | "withdraw" | "rebase" | "uphold" | "dismiss";

export function useDecide(treeId: string, id: string) {
  const invalidate = useInvalidate(treeId);
  return useMutation({
    mutationFn: ({ action, note }: { action: Decision; note?: string }) =>
      api.post<ChangeProposalOut>(`/trees/${treeId}/proposals/${id}/${action}`, action === "withdraw" || action === "rebase" ? {} : { note: note || null }),
    // a stale proposal answers 409 but is now marked stale: refresh either way
    onSettled: invalidate,
  });
}

export function useComment(treeId: string, id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: string) => api.post<ChangeProposalOut>(`/trees/${treeId}/proposals/${id}/comments`, { body }),
    onSuccess: (data) => qc.setQueryData(keys.one(treeId, id), data),
  });
}

export function useHistory(treeId: string, personId: string, enabled = true) {
  return useQuery({
    queryKey: keys.history(treeId, personId),
    queryFn: ({ signal }) => api.get<Page<RevisionOut>>(`/trees/${treeId}/people/${personId}/history`, { limit: 100 }, signal),
    enabled,
  });
}

export function useRevert(treeId: string) {
  const invalidate = useInvalidate(treeId);
  return useMutation({
    mutationFn: (revisionId: string) => api.post<RevertOut>(`/trees/${treeId}/revisions/${revisionId}/revert`, {}),
    onSuccess: invalidate,
  });
}

export function useNotifications(treeId: string) {
  return useQuery({
    queryKey: keys.notes(treeId),
    queryFn: ({ signal }) => api.get<NotificationsOut>(`/trees/${treeId}/inbox`, undefined, signal),
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  });
}

export function useMarkNotificationsRead(treeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => api.post<NotificationsOut>(`/trees/${treeId}/inbox/read`, { ids }),
    onSuccess: (data) => qc.setQueryData(keys.notes(treeId), data),
  });
}

export function useSetReviewPolicy(treeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (review_policy: ReviewPolicy) => api.put<{ review_policy: ReviewPolicy }>(`/trees/${treeId}/review-policy`, { review_policy }),
    onSuccess: () => qc.invalidateQueries(),
  });
}

/** "Is this person already in the tree?" Only people the user can already see are suggested. */
export function useDuplicateCheck(treeId: string, body: DuplicateCheckIn | null) {
  return useQuery({
    queryKey: ["tree", treeId, "duplicate-check", body],
    queryFn: () => api.post<DuplicateCheckOut>(`/trees/${treeId}/duplicates/check`, body),
    enabled: !!body,
    staleTime: 30_000,
    retry: false,
  });
}
