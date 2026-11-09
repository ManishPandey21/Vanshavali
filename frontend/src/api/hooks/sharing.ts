import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../client";
import type { SharingOut, SharingUpdate } from "../types";

/**
 * Visibility & Sharing for any shareable record (ADR-0027). `path` is the record's path inside the
 * tree, e.g. `documents/<id>` or `traditions/<id>`; the server applies the same rules to both.
 */
export function useSharing(treeId: string, path: string) {
  return useQuery({
    queryKey: ["tree", treeId, "sharing", path],
    queryFn: () => api.get<SharingOut>(`/trees/${treeId}/${path}/sharing`),
  });
}

/** Who would have access with these settings, computed by the server. Changes nothing. */
export function useSharingPreview(treeId: string, path: string, body: SharingUpdate | null) {
  return useQuery({
    queryKey: ["tree", treeId, "sharing", path, "preview", body],
    queryFn: () => api.post<SharingOut>(`/trees/${treeId}/${path}/sharing/preview`, body),
    enabled: body !== null,
    placeholderData: keepPreviousData,
    retry: false,
  });
}

export function useUpdateSharing(treeId: string, path: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SharingUpdate) => api.put<SharingOut>(`/trees/${treeId}/${path}/sharing`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tree", treeId] }),
  });
}
