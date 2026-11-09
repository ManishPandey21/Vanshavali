import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../client";
import type { EventMediaLinkIn, EventMediaOut, EventMediaUpdate, EventOut, EventSignificance, LifeEventCategory, Message, Page } from "../types";

export interface LifeEventFilters {
  person_id?: string;
  category?: LifeEventCategory[];
  significance?: EventSignificance[];
  important_only?: boolean;
  from_year?: number;
  to_year?: number;
  geotagged?: boolean;
  q?: string;
}

function useInvalidateTree(treeId: string) {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["tree", treeId] });
}

export function useLifeEvents(treeId: string, f: LifeEventFilters) {
  return useInfiniteQuery({
    queryKey: ["tree", treeId, "life-events", f],
    queryFn: ({ pageParam, signal }) =>
      api.get<Page<EventOut>>(
        `/trees/${treeId}/life-events`,
        { ...f, category: f.category, significance: f.significance, important_only: f.important_only || undefined, cursor: pageParam, limit: 50 },
        signal,
      ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    placeholderData: keepPreviousData,
  });
}

export function useEventMedia(treeId: string, eventId: string | null) {
  return useQuery({
    queryKey: ["tree", treeId, "event-media", eventId ?? ""],
    queryFn: () => api.get<EventMediaOut[]>(`/trees/${treeId}/events/${eventId}/media`),
    enabled: !!eventId,
  });
}

export function usePersonPhotos(treeId: string, personId: string) {
  return useQuery({
    queryKey: ["tree", treeId, "person", personId, "photos"],
    queryFn: () => api.get<EventMediaOut[]>(`/trees/${treeId}/people/${personId}/photos`),
  });
}

export interface PhotoUpload {
  file: File;
  caption?: string;
  takenYear?: number | null;
  isCover?: boolean;
  personIds?: string[];
  /** ADR-0027: omit to keep the album default (as private as the event and the people in it) */
  privacyLevel?: string;
  audienceBranchId?: string | null;
  allowDownload?: boolean;
}

export function photoFormData(input: PhotoUpload): FormData {
  const fd = new FormData();
  fd.append("file", input.file);
  if (input.caption) fd.append("caption", input.caption);
  if (input.takenYear) fd.append("taken_date", JSON.stringify({ precision: "year_only", year: input.takenYear }));
  if (input.isCover) fd.append("is_cover", "true");
  for (const id of input.personIds ?? []) fd.append("person_ids", id);
  if (input.privacyLevel) fd.append("privacy_level", input.privacyLevel);
  if (input.audienceBranchId) fd.append("audience_branch_id", input.audienceBranchId);
  if (input.allowDownload !== undefined) fd.append("allow_download", String(input.allowDownload));
  return fd;
}

export function useUploadEventPhoto(treeId: string, eventId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (input: PhotoUpload) => api.upload<EventMediaOut>(`/trees/${treeId}/events/${eventId}/media`, photoFormData(input)),
    onSuccess: invalidate,
  });
}

export function useLinkEventPhoto(treeId: string, eventId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (body: EventMediaLinkIn) => api.post<EventMediaOut>(`/trees/${treeId}/events/${eventId}/media/link`, body),
    onSuccess: invalidate,
  });
}

export function useUpdateEventMedia(treeId: string, eventId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: EventMediaUpdate }) =>
      api.patch<EventMediaOut>(`/trees/${treeId}/events/${eventId}/media/${id}`, body),
    onSuccess: invalidate,
  });
}

export function useRemoveEventMedia(treeId: string, eventId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (id: string) => api.del<Message>(`/trees/${treeId}/events/${eventId}/media/${id}`),
    onSuccess: invalidate,
  });
}
