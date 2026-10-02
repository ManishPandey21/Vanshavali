import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, apiBlob } from "../client";
import type {
  AstrologyIn,
  AstrologyOut,
  AstrologyUpdate,
  BirthConflictsOut,
  DocumentCategory,
  DocumentLinkIn,
  DocumentLinkOut,
  DocumentLinkTarget,
  DocumentOut,
  DocumentUpdate,
  DownloadUrlOut,
  GrantCreate,
  GrantOut,
  Message,
  MetadataVersionOut,
  OcrTextOut,
  Page,
  ProposalOut,
  ReprocessOut,
  ReviewIn,
} from "../types";

function useInvalidateTree(treeId: string) {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["tree", treeId] });
}

export interface DocumentFilters {
  category?: DocumentCategory;
  target_type?: DocumentLinkTarget;
  target_id?: string;
  q?: string;
  deleted?: boolean;
}

export function useDocuments(treeId: string, f: DocumentFilters, enabled = true) {
  return useQuery({
    queryKey: ["tree", treeId, "documents", f],
    queryFn: ({ signal }) =>
      api.get<Page<DocumentOut>>(
        `/trees/${treeId}/documents`,
        { category: f.category, target_type: f.target_type, target_id: f.target_id, q: f.q, deleted: f.deleted || undefined, limit: 200 },
        signal,
      ),
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useDocument(treeId: string, id: string) {
  return useQuery({
    queryKey: ["tree", treeId, "document", id],
    queryFn: () => api.get<DocumentOut>(`/trees/${treeId}/documents/${id}`),
    // Scanning/OCR may still be running (job mode rq): poll until the pipeline settles.
    refetchInterval: (q) => {
      const d = q.state.data;
      if (!d) return false;
      const busy = [d.ocr_status, d.extraction_status, d.preview_status].some((s) => s === "pending" || s === "running") || d.scan_status === "pending";
      return busy ? 3000 : false;
    },
  });
}

export interface UploadInput {
  file: File;
  category: DocumentCategory;
  title: string;
  description?: string;
  privacy_level?: string;
  document_date?: unknown;
  language?: string;
  issuing_authority?: string;
  link_target_type?: DocumentLinkTarget;
  link_target_id?: string;
}

/** Builds the multipart body exactly as the upload endpoint expects (document_date as JSON). */
export function uploadFormData(input: UploadInput): FormData {
  const fd = new FormData();
  fd.append("file", input.file);
  fd.append("category", input.category);
  fd.append("title", input.title);
  const opt: [string, string | undefined][] = [
    ["description", input.description],
    ["privacy_level", input.privacy_level],
    ["language", input.language],
    ["issuing_authority", input.issuing_authority],
    ["link_target_type", input.link_target_type],
    ["link_target_id", input.link_target_id],
  ];
  for (const [k, v] of opt) if (v) fd.append(k, v);
  if (input.document_date) fd.append("document_date", JSON.stringify(input.document_date));
  return fd;
}

export function useUploadDocument(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (input: UploadInput) => api.upload<DocumentOut>(`/trees/${treeId}/documents`, uploadFormData(input)),
    onSuccess: invalidate,
  });
}

export function useUpdateDocument(treeId: string, id: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (body: DocumentUpdate) => api.patch<DocumentOut>(`/trees/${treeId}/documents/${id}`, body),
    onSuccess: invalidate,
  });
}

export function useDocumentVersions(treeId: string, id: string) {
  return useQuery({
    queryKey: ["tree", treeId, "document", id, "versions"],
    queryFn: () => api.get<MetadataVersionOut[]>(`/trees/${treeId}/documents/${id}/versions`),
  });
}

export function useDeleteDocument(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({ mutationFn: (id: string) => api.del<Message>(`/trees/${treeId}/documents/${id}`), onSuccess: invalidate });
}

export function useRestoreDocument(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({ mutationFn: (id: string) => api.post<DocumentOut>(`/trees/${treeId}/documents/${id}/restore`), onSuccess: invalidate });
}

export function useAddDocumentLink(treeId: string, id: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (body: DocumentLinkIn) => api.post<DocumentLinkOut>(`/trees/${treeId}/documents/${id}/links`, body),
    onSuccess: invalidate,
  });
}

export function useRemoveDocumentLink(treeId: string, id: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (linkId: string) => api.del<Message>(`/trees/${treeId}/documents/${id}/links/${linkId}`),
    onSuccess: invalidate,
  });
}

/** Two-step signed delivery: POST /download-url (authorised, audited) then GET /files/{token}. */
export async function fetchDocumentFile(treeId: string, id: string, variant: "original" | "preview" | "thumbnail") {
  const signed = await api.post<DownloadUrlOut>(`/trees/${treeId}/documents/${id}/download-url?variant=${variant}`);
  return apiBlob(signed.url);
}

export function useDocumentPreview(treeId: string, id: string, enabled: boolean) {
  return useQuery({
    queryKey: ["tree", treeId, "document", id, "preview-blob"],
    queryFn: async () => {
      const { blob } = await fetchDocumentFile(treeId, id, "preview");
      return URL.createObjectURL(blob);
    },
    enabled,
    staleTime: 240_000, // signed URLs live ≤ 300 s; the object URL is local and stays valid
    retry: false,
  });
}

/** Thumbnail (or preview) as an object URL, for photo grids and albums. */
export function useDocumentImage(treeId: string, id: string, variant: "thumbnail" | "preview", enabled = true) {
  return useQuery({
    queryKey: ["tree", treeId, "document", id, `${variant}-blob`],
    queryFn: async () => {
      const { blob } = await fetchDocumentFile(treeId, id, variant);
      return URL.createObjectURL(blob);
    },
    enabled,
    staleTime: 240_000,
    retry: false,
  });
}

export function useReprocess(treeId: string, id: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({ mutationFn: () => api.post<ReprocessOut>(`/trees/${treeId}/documents/${id}/reprocess`), onSuccess: invalidate });
}

// ---- extraction
export function useProposals(treeId: string, documentId: string) {
  return useQuery({
    queryKey: ["tree", treeId, "document", documentId, "proposals"],
    queryFn: () => api.get<ProposalOut[]>(`/trees/${treeId}/documents/${documentId}/proposals`),
  });
}

export function useOcrText(treeId: string, documentId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["tree", treeId, "document", documentId, "ocr"],
    queryFn: () => api.get<OcrTextOut>(`/trees/${treeId}/documents/${documentId}/ocr-text`),
    enabled,
    retry: false,
  });
}

export function useReviewProposal(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ReviewIn }) => api.post<ProposalOut>(`/trees/${treeId}/extraction-proposals/${id}/review`, body),
    onSuccess: invalidate,
  });
}

// ---- astrology
export function useAstrology(treeId: string, personId: string) {
  return useQuery({
    queryKey: ["tree", treeId, "person", personId, "astrology"],
    queryFn: () => api.get<AstrologyOut[]>(`/trees/${treeId}/people/${personId}/astrology`),
  });
}

export function useSaveAstrology(treeId: string, personId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: AstrologyIn | AstrologyUpdate }) =>
      id ? api.patch<AstrologyOut>(`/trees/${treeId}/astrology/${id}`, body) : api.post<AstrologyOut>(`/trees/${treeId}/people/${personId}/astrology`, body),
    onSuccess: invalidate,
  });
}

export function useDeleteAstrology(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({ mutationFn: (id: string) => api.del<Message>(`/trees/${treeId}/astrology/${id}`), onSuccess: invalidate });
}

export function useBirthConflicts(treeId: string, personId: string) {
  return useQuery({
    queryKey: ["tree", treeId, "person", personId, "birth-conflicts"],
    queryFn: () => api.get<BirthConflictsOut>(`/trees/${treeId}/people/${personId}/birth-conflicts`),
  });
}

// ---- access grants (CUSTOM privacy)
export function useGrants(treeId: string, enabled: boolean) {
  return useQuery({ queryKey: ["tree", treeId, "grants"], queryFn: () => api.get<GrantOut[]>(`/trees/${treeId}/grants`), enabled, retry: false });
}

export function useCreateGrant(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({ mutationFn: (body: GrantCreate) => api.post<GrantOut>(`/trees/${treeId}/grants`, body), onSuccess: invalidate });
}

export function useDeleteGrant(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({ mutationFn: (id: string) => api.del<Message>(`/trees/${treeId}/grants/${id}`), onSuccess: invalidate });
}
