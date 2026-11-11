import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../client";
import type { CalendarOut, CalendarSettingsIn, CalendarSettingsOut, ConvertIn, ConvertOut, FeedOut } from "../types";

/** Family calendar (ADR-0022): settings, the calendar, conversion suggestions and the feed. */
const keys = {
  settings: (treeId: string) => ["tree", treeId, "calendar-settings"] as const,
  calendar: (treeId: string, from: string, to: string) => ["tree", treeId, "calendar", from, to] as const,
  feed: (treeId: string) => ["tree", treeId, "calendar-feed"] as const,
};

export function useCalendarSettings(treeId: string | null) {
  return useQuery({
    queryKey: keys.settings(treeId ?? ""),
    queryFn: () => api.get<CalendarSettingsOut>(`/trees/${treeId}/calendar-settings`),
    enabled: !!treeId,
    staleTime: 60_000,
  });
}

export function useSetCalendarSettings(treeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CalendarSettingsIn) => api.put<CalendarSettingsOut>(`/trees/${treeId}/calendar-settings`, body),
    onSuccess: (s) => {
      qc.setQueryData(keys.settings(treeId), s);
      qc.invalidateQueries({ queryKey: ["tree", treeId, "calendar"] });
    },
  });
}

export function useFamilyCalendar(treeId: string, from: string, to: string) {
  return useQuery({
    queryKey: keys.calendar(treeId, from, to),
    queryFn: ({ signal }) => api.get<CalendarOut>(`/trees/${treeId}/calendar`, { from, to }, signal),
    placeholderData: keepPreviousData,
  });
}

export function useConvertLunar(treeId: string) {
  return useMutation({ mutationFn: (body: ConvertIn) => api.post<ConvertOut>(`/trees/${treeId}/calendar/convert`, body) });
}

export function useCalendarFeed(treeId: string) {
  return useQuery({ queryKey: keys.feed(treeId), queryFn: () => api.get<FeedOut>(`/trees/${treeId}/calendar-feed`) });
}

export function useCreateCalendarFeed(treeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (include_names: boolean) => api.post<FeedOut>(`/trees/${treeId}/calendar-feed`, { include_names }),
    onSuccess: (f) => qc.setQueryData(keys.feed(treeId), { ...f, url: null }),
  });
}

export function useRevokeCalendarFeed(treeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.del<FeedOut>(`/trees/${treeId}/calendar-feed`),
    onSuccess: (f) => qc.setQueryData(keys.feed(treeId), f),
  });
}
