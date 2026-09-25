import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, apiBlob, saveBlob } from "../client";
import type {
  CommitIn,
  ImportJobOut,
  ImportJobSummary,
  InterestEndIn,
  InterestIn,
  InterestOut,
  LineageOut,
  MergeOut,
  Message,
  ParcelIn,
  ParcelLineageOut,
  ParcelOut,
  ParcelUpdate,
  PartitionIn,
  PersonPropertyInterestsOut,
  PropertyDetailOut,
  PropertyEventIn,
  PropertyEventOut,
  PropertyIn,
  PropertyOut,
  PropertyUpdate,
  SubdivideIn,
  SubdivideOut,
  TimelineOut,
} from "../types";

function useInvalidateTree(treeId: string) {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["tree", treeId] });
}

const P = (t: string, p: string) => `/trees/${t}/properties/${p}`;

export function useProperties(treeId: string, q = "", enabled = true) {
  return useQuery({
    queryKey: ["tree", treeId, "properties", q],
    queryFn: () => api.get<PropertyOut[]>(`/trees/${treeId}/properties`, { q }),
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useProperty(treeId: string, id: string | undefined) {
  return useQuery({ queryKey: ["tree", treeId, "property", id ?? ""], queryFn: () => api.get<PropertyDetailOut>(P(treeId, id!)), enabled: !!id });
}

export function useCreateProperty(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({ mutationFn: (body: PropertyIn) => api.post<PropertyDetailOut>(`/trees/${treeId}/properties`, body), onSuccess: invalidate });
}

export function useUpdateProperty(treeId: string, id: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({ mutationFn: (body: PropertyUpdate) => api.patch<PropertyDetailOut>(P(treeId, id), body), onSuccess: invalidate });
}

export function useDeleteProperty(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({ mutationFn: (id: string) => api.del<Message>(P(treeId, id)), onSuccess: invalidate });
}

export function useSaveParcel(treeId: string, propertyId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: ParcelIn | ParcelUpdate }) =>
      id ? api.patch<ParcelOut>(`${P(treeId, propertyId)}/parcels/${id}`, body) : api.post<ParcelOut>(`${P(treeId, propertyId)}/parcels`, body),
    onSuccess: invalidate,
  });
}

export function useDeleteParcel(treeId: string, propertyId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({ mutationFn: (id: string) => api.del<Message>(`${P(treeId, propertyId)}/parcels/${id}`), onSuccess: invalidate });
}

export function useSubdivide(treeId: string, propertyId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: SubdivideIn }) => api.post<SubdivideOut>(`${P(treeId, propertyId)}/parcels/${id}/subdivide`, body),
    onSuccess: invalidate,
  });
}

export function useParcelLineage(treeId: string, propertyId: string, parcelId: string | null) {
  return useQuery({
    queryKey: ["tree", treeId, "property", propertyId, "parcel-lineage", parcelId ?? ""],
    queryFn: () => api.get<ParcelLineageOut>(`${P(treeId, propertyId)}/parcels/${parcelId}/lineage`),
    enabled: !!parcelId,
  });
}

export function useInterests(treeId: string, propertyId: string) {
  return useQuery({ queryKey: ["tree", treeId, "property", propertyId, "interests"], queryFn: () => api.get<InterestOut[]>(`${P(treeId, propertyId)}/interests`) });
}

export function useCreateInterest(treeId: string, propertyId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({ mutationFn: (body: InterestIn) => api.post<InterestOut>(`${P(treeId, propertyId)}/interests`, body), onSuccess: invalidate });
}

export function useEndInterest(treeId: string, propertyId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: InterestEndIn }) => api.post<InterestOut>(`${P(treeId, propertyId)}/interests/${id}/end`, body),
    onSuccess: invalidate,
  });
}

export function useDeleteInterest(treeId: string, propertyId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({ mutationFn: (id: string) => api.del<Message>(`${P(treeId, propertyId)}/interests/${id}`), onSuccess: invalidate });
}

export function useRecordPropertyEvent(treeId: string, propertyId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({ mutationFn: (body: PropertyEventIn) => api.post<PropertyEventOut>(`${P(treeId, propertyId)}/events`, body), onSuccess: invalidate });
}

export function useRecordPartition(treeId: string, propertyId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({ mutationFn: (body: PartitionIn) => api.post<PropertyEventOut>(`${P(treeId, propertyId)}/partition`, body), onSuccess: invalidate });
}

export function useTimeline(treeId: string, propertyId: string, at: string) {
  return useQuery({
    queryKey: ["tree", treeId, "property", propertyId, "timeline", at],
    queryFn: () => api.get<TimelineOut>(`${P(treeId, propertyId)}/timeline`, { at: at || undefined }),
    placeholderData: keepPreviousData,
  });
}

export function usePropertyLineage(treeId: string, propertyId: string) {
  return useQuery({ queryKey: ["tree", treeId, "property", propertyId, "lineage"], queryFn: () => api.get<LineageOut>(`${P(treeId, propertyId)}/lineage`) });
}

export function usePersonPropertyInterests(treeId: string, personId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["tree", treeId, "person", personId, "property-interests"],
    queryFn: () => api.get<PersonPropertyInterestsOut>(`/trees/${treeId}/people/${personId}/property-interests`),
    enabled,
    retry: false,
  });
}

// ---- GEDCOM
export function useImports(treeId: string, enabled: boolean) {
  return useQuery({ queryKey: ["tree", treeId, "imports"], queryFn: () => api.get<ImportJobSummary[]>(`/trees/${treeId}/imports`), enabled, retry: false });
}

export function useImport(treeId: string, id: string | null) {
  return useQuery({ queryKey: ["tree", treeId, "import", id ?? ""], queryFn: () => api.get<ImportJobOut>(`/trees/${treeId}/imports/${id}`, { limit: 1000 }), enabled: !!id });
}

export function useUploadGedcom(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return api.upload<ImportJobOut>(`/trees/${treeId}/imports`, fd);
    },
    onSuccess: invalidate,
  });
}

export function useCommitImport(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({ mutationFn: ({ id, body }: { id: string; body: CommitIn }) => api.post<ImportJobOut>(`/trees/${treeId}/imports/${id}/commit`, body), onSuccess: invalidate });
}

export function useCancelImport(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({ mutationFn: (id: string) => api.post<ImportJobSummary>(`/trees/${treeId}/imports/${id}/cancel`), onSuccess: invalidate });
}

export async function downloadGedcom(treeId: string, opts: { exclude_living: boolean; include_sensitive: boolean }) {
  const { blob, filename } = await apiBlob(`/trees/${treeId}/exports/gedcom`, opts);
  saveBlob(blob, filename ?? "tree.ged");
}

// ---- merges
export function useMerges(treeId: string, enabled: boolean) {
  return useQuery({ queryKey: ["tree", treeId, "merges"], queryFn: () => api.get<MergeOut[]>(`/trees/${treeId}/merges`), enabled, retry: false });
}

export interface MergePreview {
  survivor_id: string;
  merged_id: string;
  references_to_move: Record<string, number>;
  relationships_to_move: number;
  relationships_between_them_removed: number;
  warnings: string[];
}

export function useMergePreview(treeId: string, survivor: string, merged: string) {
  return useQuery({
    queryKey: ["tree", treeId, "merge-preview", survivor, merged],
    queryFn: () => api.get<MergePreview>(`/trees/${treeId}/merges/preview`, { survivor, merged }),
    retry: false,
  });
}

export function useMerge(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (body: { survivor_id: string; merged_id: string; reason?: string | null }) => api.post<MergeOut>(`/trees/${treeId}/merges`, body),
    onSuccess: invalidate,
  });
}

export function useRevertMerge(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({ mutationFn: (id: string) => api.post<MergeOut>(`/trees/${treeId}/merges/${id}/revert`), onSuccess: invalidate });
}
