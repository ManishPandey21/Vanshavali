import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../client";
import type { CollectionIn, CollectionItemUpdate, CollectionOut, CollectionSummaryOut, Message } from "../types";

/** Standalone photo collections (ADR-0027 §6): each viewer gets only the photos they may see. */
export function useCollections(treeId: string) {
  return useQuery({
    queryKey: ["tree", treeId, "collections"],
    queryFn: () => api.get<CollectionSummaryOut[]>(`/trees/${treeId}/collections`),
  });
}

export function useCollection(treeId: string, id: string) {
  return useQuery({
    queryKey: ["tree", treeId, "collection", id],
    queryFn: () => api.get<CollectionOut>(`/trees/${treeId}/collections/${id}`),
  });
}

function useInvalidate(treeId: string) {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["tree", treeId] });
}

export function useCreateCollection(treeId: string) {
  const invalidate = useInvalidate(treeId);
  return useMutation({ mutationFn: (body: CollectionIn) => api.post<CollectionOut>(`/trees/${treeId}/collections`, body), onSuccess: invalidate });
}

export function useDeleteCollection(treeId: string) {
  const invalidate = useInvalidate(treeId);
  return useMutation({ mutationFn: (id: string) => api.del<Message>(`/trees/${treeId}/collections/${id}`), onSuccess: invalidate });
}

export function useAddCollectionItems(treeId: string, id: string) {
  const invalidate = useInvalidate(treeId);
  return useMutation({
    mutationFn: async (documentIds: string[]) => {
      let out: CollectionOut | null = null;
      for (const document_id of documentIds) out = await api.post<CollectionOut>(`/trees/${treeId}/collections/${id}/items`, { document_id });
      return out;
    },
    onSuccess: invalidate,
  });
}

export function useUpdateCollectionItem(treeId: string, id: string) {
  const invalidate = useInvalidate(treeId);
  return useMutation({
    mutationFn: ({ itemId, body }: { itemId: string; body: CollectionItemUpdate }) =>
      api.patch<CollectionOut>(`/trees/${treeId}/collections/${id}/items/${itemId}`, body),
    onSuccess: invalidate,
  });
}

export function useRemoveCollectionItem(treeId: string, id: string) {
  const invalidate = useInvalidate(treeId);
  return useMutation({ mutationFn: (itemId: string) => api.del<Message>(`/trees/${treeId}/collections/${id}/items/${itemId}`), onSuccess: invalidate });
}
