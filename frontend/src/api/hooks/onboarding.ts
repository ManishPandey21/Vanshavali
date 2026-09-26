import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../client";
import type {
  AttestationOut,
  AttestationStatus,
  ClaimInviteAccept,
  ClaimInviteCreated,
  ClaimInviteOut,
  ClaimInvitePreview,
  ClaimSubmitted,
  Message,
  RemovalRequestIn,
  StatementKind,
  StatementOut,
} from "../types";

export const onboardingKeys = {
  statement: (kind: StatementKind, lang: string) => ["statement", kind, lang] as const,
  attestation: (t: string) => ["tree", t, "attestation"] as const,
  claimInvites: (t: string, personId?: string) => ["tree", t, "claim-invites", personId ?? ""] as const,
  invitePreview: (token: string) => ["claim-invite", token] as const,
};

/** The server-owned wording (ADR-0011): what the user sees is exactly what gets recorded. */
export function useStatement(kind: StatementKind, lang: string) {
  const short = lang.split("-")[0] ?? "en";
  return useQuery({
    queryKey: onboardingKeys.statement(kind, short),
    queryFn: () => api.get<StatementOut>(`/consent-statements/${kind}`, { lang: short }),
    staleTime: Infinity,
  });
}

export function useAttestation(treeId: string | undefined) {
  return useQuery({
    queryKey: onboardingKeys.attestation(treeId ?? ""),
    queryFn: () => api.get<AttestationStatus>(`/trees/${treeId}/attestation`),
    enabled: !!treeId,
  });
}

export function useAttest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ treeId, statement }: { treeId: string; statement: StatementOut }) =>
      api.post<AttestationOut>(`/trees/${treeId}/attestation`, {
        statement_version: statement.version,
        language: statement.language,
      }),
    onSuccess: (_row, { treeId }) => qc.invalidateQueries({ queryKey: onboardingKeys.attestation(treeId) }),
  });
}

export function useClaimInvites(treeId: string, personId?: string) {
  return useQuery({
    queryKey: onboardingKeys.claimInvites(treeId, personId),
    queryFn: () => api.get<ClaimInviteOut[]>(`/trees/${treeId}/claim-invites`, { person_id: personId }),
  });
}

export function useCreateClaimInvite(treeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ personId, offeredRole }: { personId: string; offeredRole: "VIEWER" | "CONTRIBUTOR" }) =>
      api.post<ClaimInviteCreated>(`/trees/${treeId}/people/${personId}/claim-invites`, { offered_role: offeredRole }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tree", treeId, "claim-invites"] }),
  });
}

export function useRevokeClaimInvite(treeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.del<Message>(`/trees/${treeId}/claim-invites/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tree", treeId, "claim-invites"] }),
  });
}

export function useClaimInvitePreview(token: string, enabled: boolean) {
  return useQuery({
    queryKey: onboardingKeys.invitePreview(token),
    queryFn: () => api.get<ClaimInvitePreview>(`/claim-invites/${encodeURIComponent(token)}`),
    enabled: enabled && !!token,
    retry: false,
  });
}

export function useAcceptClaimInvite(token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ClaimInviteAccept) => api.post<ClaimSubmitted>(`/claim-invites/${encodeURIComponent(token)}/accept`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: onboardingKeys.invitePreview(token) }),
  });
}

/** "This isn't me": cancels the link without touching anyone's data. */
export function useDeclineClaimInvite(token: string) {
  // No refetch afterwards: the link is dead, and the page shows its own confirmation.
  return useMutation({ mutationFn: () => api.post<Message>(`/claim-invites/${encodeURIComponent(token)}/decline`) });
}

/** "This is me, remove me": hides the profile at once and asks a tree admin to erase it. */
export function useRequestRemoval(token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RemovalRequestIn) => api.post<ClaimSubmitted>(`/claim-invites/${encodeURIComponent(token)}/request-removal`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: onboardingKeys.invitePreview(token) }),
  });
}
