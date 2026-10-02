import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, apiBlob } from "../client";
import type {
  AncestryOut,
  ChartType,
  LifespansOut,
  MapOut,
  Message,
  NeighbourhoodOut,
  PresetIn,
  PresetOut,
  RenderDownloadOut,
  RenderJobIn,
  RenderJobOut,
  StoryOut,
} from "../types";

export function useAncestry(treeId: string, root: string, generations: number) {
  return useQuery({
    queryKey: ["tree", treeId, "viz", "ancestry", root, generations],
    queryFn: ({ signal }) => api.get<AncestryOut>(`/trees/${treeId}/viz/ancestry`, { root, generations }, signal),
    enabled: !!root,
    placeholderData: keepPreviousData,
  });
}

export function fetchNeighbourhood(treeId: string, root: string, radius: number) {
  return api.get<NeighbourhoodOut>(`/trees/${treeId}/viz/neighbourhood`, { root, radius, max_nodes: 120 });
}

export function useNeighbourhood(treeId: string, root: string, radius: number) {
  return useQuery({
    queryKey: ["tree", treeId, "viz", "neighbourhood", root, radius],
    queryFn: () => fetchNeighbourhood(treeId, root, radius),
    enabled: !!root,
  });
}

export function useLifespans(treeId: string, q: { root?: string; generations: number; branch_id?: string; include_events: boolean }) {
  return useQuery({
    queryKey: ["tree", treeId, "viz", "lifespans", q],
    queryFn: ({ signal }) => api.get<LifespansOut>(`/trees/${treeId}/viz/lifespans`, { ...q, limit: 300 }, signal),
    placeholderData: keepPreviousData,
  });
}

export function useStory(treeId: string, personId: string) {
  return useQuery({
    queryKey: ["tree", treeId, "viz", "story", personId],
    queryFn: () => api.get<StoryOut>(`/trees/${treeId}/viz/people/${personId}/story`),
    enabled: !!personId,
  });
}

export function useGeoMap(treeId: string, q: { person_id?: string; branch_id?: string; layer?: string[] }) {
  return useQuery({
    queryKey: ["tree", treeId, "viz", "map", q],
    queryFn: ({ signal }) => api.get<MapOut>(`/trees/${treeId}/viz/map`, q, signal),
    placeholderData: keepPreviousData,
  });
}

// ---- presets
export function usePresets(treeId: string, chartType: ChartType) {
  return useQuery({
    queryKey: ["tree", treeId, "presets", chartType],
    queryFn: () => api.get<PresetOut[]>(`/trees/${treeId}/chart-presets`, { chart_type: chartType }),
  });
}

export function useSavePreset(treeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PresetIn) => api.post<PresetOut>(`/trees/${treeId}/chart-presets`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tree", treeId, "presets"] }),
  });
}

export function useDeletePreset(treeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.del<Message>(`/trees/${treeId}/chart-presets/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tree", treeId, "presets"] }),
  });
}

// ---- render jobs (animated exports)
export function useRenderJobs(treeId: string) {
  return useQuery({
    queryKey: ["tree", treeId, "render-jobs"],
    queryFn: () => api.get<RenderJobOut[]>(`/trees/${treeId}/render-jobs`, { limit: 20 }),
    // poll while something is queued or running
    refetchInterval: (q) => (q.state.data?.some((j) => j.status === "queued" || j.status === "running") ? 2000 : false),
  });
}

export function useCreateRenderJob(treeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RenderJobIn) => api.post<RenderJobOut>(`/trees/${treeId}/render-jobs`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tree", treeId, "render-jobs"] }),
  });
}

export function useCancelRenderJob(treeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<RenderJobOut>(`/trees/${treeId}/render-jobs/${id}/cancel`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tree", treeId, "render-jobs"] }),
  });
}

export function useDeleteRenderJob(treeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.del<Message>(`/trees/${treeId}/render-jobs/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tree", treeId, "render-jobs"] }),
  });
}

/** Signed two-step delivery (like documents): POST download-url, then GET the file. */
export async function fetchRenderArtifact(treeId: string, jobId: string, artifactId: string) {
  const signed = await api.post<RenderDownloadOut>(`/trees/${treeId}/render-jobs/${jobId}/artifacts/${artifactId}/download-url`);
  return apiBlob(signed.url);
}

export function useRenderPoster(treeId: string, jobId: string, artifactId: string | undefined) {
  return useQuery({
    queryKey: ["tree", treeId, "render-poster", jobId, artifactId ?? ""],
    queryFn: async () => URL.createObjectURL((await fetchRenderArtifact(treeId, jobId, artifactId!)).blob),
    enabled: !!artifactId,
    staleTime: Infinity,
    retry: false,
  });
}
