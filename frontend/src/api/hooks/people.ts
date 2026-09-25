import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../client";
import type {
  EventIn,
  EventOut,
  EventUpdate,
  FamilyOut,
  GraphOut,
  Lineage,
  Message,
  NameIn,
  NameOut,
  NameUpdate,
  Page,
  PersonCreate,
  PersonOut,
  PersonSummary,
  PersonUpdate,
  PlaceIn,
  PlaceOut,
  PrivacyUpdate,
  ProfileStatus,
  RelationshipOut,
  RelationshipPathOut,
  RelativeIn,
  RelativeOut,
} from "../types";

export const peopleKeys = {
  tree: (t: string) => ["tree", t] as const,
  list: (t: string, q: string, status?: string) => ["tree", t, "people", q, status ?? ""] as const,
  person: (t: string, id: string) => ["tree", t, "person", id] as const,
  family: (t: string, id: string, lineage: string) => ["tree", t, "person", id, "family", lineage] as const,
  events: (t: string, id: string) => ["tree", t, "person", id, "events"] as const,
  graph: (t: string, id: string, dir: string, depth: number, lineage: string) =>
    ["tree", t, "graph", id, dir, depth, lineage] as const,
  places: (t: string, q: string) => ["tree", t, "places", q] as const,
  place: (t: string, id: string) => ["tree", t, "place", id] as const,
  path: (t: string, a: string, b: string, lineage: string) => ["tree", t, "path", a, b, lineage] as const,
};

/** Any genealogy write can change derived views (family, graph, counts), so refresh the tree's data. */
function useInvalidateTree(treeId: string) {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: peopleKeys.tree(treeId) });
}

export function usePeople(treeId: string, q: string, status?: ProfileStatus) {
  return useInfiniteQuery({
    queryKey: peopleKeys.list(treeId, q, status),
    queryFn: ({ pageParam, signal }) =>
      api.get<Page<PersonSummary>>(`/trees/${treeId}/people`, { q, status, cursor: pageParam, limit: 50 }, signal),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    placeholderData: keepPreviousData,
  });
}

export function usePerson(treeId: string, personId: string | undefined) {
  return useQuery({
    queryKey: peopleKeys.person(treeId, personId ?? ""),
    queryFn: () => api.get<PersonOut>(`/trees/${treeId}/people/${personId}`),
    enabled: !!personId,
  });
}

export function useCreatePerson(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (body: PersonCreate) => api.post<PersonOut>(`/trees/${treeId}/people`, body),
    onSuccess: invalidate,
  });
}

export function useUpdatePerson(treeId: string, personId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (body: PersonUpdate) => api.patch<PersonOut>(`/trees/${treeId}/people/${personId}`, body),
    onSuccess: invalidate,
  });
}

export function useSetPrivacy(treeId: string, personId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (body: PrivacyUpdate) => api.put<PersonOut>(`/trees/${treeId}/people/${personId}/privacy`, body),
    onSuccess: invalidate,
  });
}

export function useDeletePerson(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (personId: string) => api.del<Message>(`/trees/${treeId}/people/${personId}`),
    onSuccess: invalidate,
  });
}

export function useDeletedPeople(treeId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["tree", treeId, "people-deleted"],
    queryFn: () => api.get<PersonSummary[]>(`/trees/${treeId}/people/deleted`),
    enabled,
  });
}

export function useErasePerson(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      api.post<Message>(`/trees/${treeId}/people/${id}/erase`, { reason, confirm: true }),
    onSuccess: invalidate,
  });
}

export function useRestorePerson(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (personId: string) => api.post<PersonOut>(`/trees/${treeId}/people/${personId}/restore`),
    onSuccess: invalidate,
  });
}

// ---- names
export function useAddName(treeId: string, personId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (body: NameIn) => api.post<NameOut>(`/trees/${treeId}/people/${personId}/names`, body),
    onSuccess: invalidate,
  });
}

export function useUpdateName(treeId: string, personId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: NameUpdate }) =>
      api.patch<NameOut>(`/trees/${treeId}/people/${personId}/names/${id}`, body),
    onSuccess: invalidate,
  });
}

export function useDeleteName(treeId: string, personId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (id: string) => api.del<Message>(`/trees/${treeId}/people/${personId}/names/${id}`),
    onSuccess: invalidate,
  });
}

// ---- events
export function usePersonEvents(treeId: string, personId: string, enabled = true) {
  return useQuery({
    queryKey: peopleKeys.events(treeId, personId),
    queryFn: () => api.get<EventOut[]>(`/trees/${treeId}/people/${personId}/events`),
    enabled: enabled && !!personId,
  });
}

export function useCreateEvent(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (body: EventIn) => api.post<EventOut>(`/trees/${treeId}/events`, body),
    onSuccess: invalidate,
  });
}

export function useUpdateEvent(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: EventUpdate }) =>
      api.patch<EventOut>(`/trees/${treeId}/events/${id}`, body),
    onSuccess: invalidate,
  });
}

export function useDeleteEvent(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (id: string) => api.del<Message>(`/trees/${treeId}/events/${id}`),
    onSuccess: invalidate,
  });
}

// ---- places
export function usePlaces(treeId: string, q: string, enabled = true) {
  return useQuery({
    queryKey: peopleKeys.places(treeId, q),
    queryFn: ({ signal }) => api.get<Page<PlaceOut>>(`/trees/${treeId}/places`, { q, limit: 100 }, signal),
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function usePlace(treeId: string, placeId: string | null | undefined) {
  return useQuery({
    queryKey: peopleKeys.place(treeId, placeId ?? ""),
    queryFn: () => api.get<PlaceOut>(`/trees/${treeId}/places/${placeId}`),
    enabled: !!placeId,
  });
}

export function useCreatePlace(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (body: PlaceIn) => api.post<PlaceOut>(`/trees/${treeId}/places`, body),
    onSuccess: invalidate,
  });
}

export function useUpdatePlace(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<PlaceIn> }) =>
      api.patch<PlaceOut>(`/trees/${treeId}/places/${id}`, body),
    onSuccess: invalidate,
  });
}

// ---- relationships & family
export function useFamily(treeId: string, personId: string, lineage: Lineage[] = []) {
  return useQuery({
    queryKey: peopleKeys.family(treeId, personId, lineage.join(",")),
    queryFn: () => api.get<FamilyOut>(`/trees/${treeId}/people/${personId}/family`, { lineage }),
  });
}

export function useAddRelative(treeId: string, personId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (body: RelativeIn) => api.post<RelativeOut>(`/trees/${treeId}/people/${personId}/relatives`, body),
    onSuccess: invalidate,
  });
}

export function useDeleteRelationship(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: (id: string) => api.del<Message>(`/trees/${treeId}/relationships/${id}`),
    onSuccess: invalidate,
  });
}

export function useUpdateRelationship(treeId: string) {
  const invalidate = useInvalidateTree(treeId);
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      api.patch<RelationshipOut>(`/trees/${treeId}/relationships/${id}`, body),
    onSuccess: invalidate,
  });
}

export function useGraph(
  treeId: string,
  personId: string,
  direction: "ancestors" | "descendants",
  depth: number,
  lineage: Lineage[],
) {
  return useQuery({
    queryKey: peopleKeys.graph(treeId, personId, direction, depth, lineage.join(",")),
    queryFn: () => api.get<GraphOut>(`/trees/${treeId}/people/${personId}/${direction}`, { depth, lineage }),
    enabled: !!personId,
    placeholderData: keepPreviousData,
  });
}

export function useRelationshipPath(treeId: string, from: string, to: string, lineage: Lineage[]) {
  return useQuery({
    queryKey: peopleKeys.path(treeId, from, to, lineage.join(",")),
    queryFn: () => api.get<RelationshipPathOut>(`/trees/${treeId}/relationship-path`, { from, to, lineage }),
    enabled: !!from && !!to,
  });
}
