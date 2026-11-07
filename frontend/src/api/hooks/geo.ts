import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../client";
import type { GeoLevel, GeoPin, GeoSnapshot, GeoUnit, GeoUnitPage } from "../types";

/**
 * Geography reference lookups (ADR-0019): public reference data, cached for a while because a
 * snapshot changes rarely. Errors (404 when the feature is off) are left to the caller, which then
 * hides the directory and keeps the free-text place fields.
 */
export interface GeoQuery {
  level?: GeoLevel;
  parent_level?: GeoLevel;
  parent_code?: string;
  q?: string;
}

export function useGeoUnits(params: GeoQuery, enabled = true) {
  return useQuery({
    queryKey: ["geo", "units", params],
    queryFn: () => api.get<GeoUnitPage>("/geo/units", { ...params, limit: 100 }),
    enabled,
    staleTime: 30 * 60_000,
    placeholderData: keepPreviousData,
    retry: false,
  });
}

export function useGeoPin(pin: string) {
  const valid = /^[1-9][0-9]{5}$/.test(pin);
  return useQuery({
    queryKey: ["geo", "pin", pin],
    queryFn: () => api.get<GeoPin>(`/geo/pincodes/${pin}`),
    enabled: valid,
    staleTime: 30 * 60_000,
    retry: false,
  });
}

const ADMIN = "/admin/master-data/geo/snapshots";

export function useGeoSnapshots() {
  return useQuery({ queryKey: ["md-admin", "geo-snapshots"], queryFn: () => api.get<GeoSnapshot[]>(ADMIN), retry: false });
}

export type SnapshotDecision = "approve" | "activate" | "rollback" | "discard";

export function useGeoDecision() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, decision, reason }: { id: string; decision: SnapshotDecision; reason: string }) =>
      api.post<GeoSnapshot | undefined>(`${ADMIN}/${id}/${decision}`, { reason }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["md-admin", "geo-snapshots"] });
      void qc.invalidateQueries({ queryKey: ["geo"] });
    },
  });
}

/** One unit by level and code; a code from an older snapshot still resolves (status retired). */
export function useGeoUnit(level: GeoLevel | null | undefined, code: string | null | undefined) {
  return useQuery({
    queryKey: ["geo", "unit", level, code],
    queryFn: () => api.get<GeoUnit>(`/geo/units/${level}/${code}`),
    enabled: !!level && !!code,
    staleTime: 30 * 60_000,
    retry: false,
  });
}
