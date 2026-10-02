import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../client";
import type {
  ChannelsOut,
  ContactIn,
  ContactOut,
  DeliveryOut,
  Message,
  Page,
  PreferenceIn,
  PreferenceOut,
  ReminderIn,
  ReminderOut,
  ReminderUpdate,
  UpcomingOut,
} from "../types";

const keys = {
  root: (t: string) => ["tree", t, "reminders"] as const,
  contacts: ["me", "notification-contacts"] as const,
};

function useInvalidate(treeId: string) {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: keys.root(treeId) });
}

export function useChannels() {
  return useQuery({ queryKey: ["notification-channels"], queryFn: () => api.get<ChannelsOut>("/notification-channels"), staleTime: 300_000 });
}

export function usePreferences(treeId: string) {
  return useQuery({ queryKey: [...keys.root(treeId), "prefs"], queryFn: () => api.get<PreferenceOut>(`/trees/${treeId}/notification-preferences`) });
}

export function useSavePreferences(treeId: string) {
  const invalidate = useInvalidate(treeId);
  return useMutation({ mutationFn: (body: PreferenceIn) => api.put<PreferenceOut>(`/trees/${treeId}/notification-preferences`, body), onSuccess: invalidate });
}

export function useReminders(treeId: string, eventId?: string) {
  return useQuery({
    queryKey: [...keys.root(treeId), "list", eventId ?? ""],
    queryFn: () => api.get<ReminderOut[]>(`/trees/${treeId}/reminders`, { event_id: eventId }),
  });
}

export function useCreateReminder(treeId: string) {
  const invalidate = useInvalidate(treeId);
  return useMutation({ mutationFn: (body: ReminderIn) => api.post<ReminderOut>(`/trees/${treeId}/reminders`, body), onSuccess: invalidate });
}

export function useUpdateReminder(treeId: string) {
  const invalidate = useInvalidate(treeId);
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ReminderUpdate }) => api.patch<ReminderOut>(`/trees/${treeId}/reminders/${id}`, body),
    onSuccess: invalidate,
  });
}

export function useDeleteReminder(treeId: string) {
  const invalidate = useInvalidate(treeId);
  return useMutation({ mutationFn: (id: string) => api.del<Message>(`/trees/${treeId}/reminders/${id}`), onSuccess: invalidate });
}

export function useTestReminder(treeId: string) {
  const invalidate = useInvalidate(treeId);
  return useMutation({ mutationFn: (id: string) => api.post<DeliveryOut[]>(`/trees/${treeId}/reminders/${id}/test`), onSuccess: invalidate });
}

export function useUpcoming(treeId: string, days: number, scope: "tree" | "mine") {
  return useQuery({
    queryKey: [...keys.root(treeId), "upcoming", days, scope],
    queryFn: () => api.get<UpcomingOut[]>(`/trees/${treeId}/reminders/upcoming`, { days, scope }),
  });
}

export function useDeliveryHistory(treeId: string) {
  return useInfiniteQuery({
    queryKey: [...keys.root(treeId), "history"],
    queryFn: ({ pageParam }) => api.get<Page<DeliveryOut>>(`/trees/${treeId}/notifications`, { cursor: pageParam, limit: 25 }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}

export function useContacts() {
  return useQuery({ queryKey: keys.contacts, queryFn: () => api.get<ContactOut[]>("/me/notification-contacts") });
}

export function useAddContact() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (body: ContactIn) => api.post<ContactOut>("/me/notification-contacts", body), onSuccess: () => qc.invalidateQueries({ queryKey: keys.contacts }) });
}

export function useVerifyContact() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, code }: { id: string; code: string }) => api.post<ContactOut>(`/me/notification-contacts/${id}/verify`, { code }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.contacts }),
  });
}

export function useDeleteContact() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (id: string) => api.del<Message>(`/me/notification-contacts/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: keys.contacts }) });
}
