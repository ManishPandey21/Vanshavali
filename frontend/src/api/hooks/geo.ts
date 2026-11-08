import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "../client";
import type { GeoLevel, GeoUnitsPage, PincodeOut } from "../types";

/**
 * LGD units for the place cascade (ADR-0019 §6): children of a parent, or a search scoped to an
 * ancestor. Reference data changes only when an operator activates a snapshot, so answers are
 * cached for a while. Errors (404 while switched off or not loaded) are left to the caller, which
 * then keeps the free-text place fields.
 */
export function useGeoUnits(
  params: { level?: GeoLevel; parent?: string | null; parentLevel?: GeoLevel; q?: string; limit?: number },
  enabled = true,
) {
  const { level, parent, parentLevel, q, limit } = params;
  const query = { level, parent: parent ?? undefined, parent_level: parentLevel, q: q || undefined, limit: limit ?? 200 };
  return useQuery({
    queryKey: ["geo", "units", query],
    queryFn: ({ signal }) => api.get<GeoUnitsPage>("/geo/units", query, signal),
    enabled,
    staleTime: 10 * 60_000,
    placeholderData: keepPreviousData,
    retry: false,
  });
}

/** Post offices for a PIN code and the upper levels they suggest. Never picks a village. */
export function useGeoPincode(pin: string) {
  return useQuery({
    queryKey: ["geo", "pincode", pin],
    queryFn: ({ signal }) => api.get<PincodeOut>(`/geo/pincodes/${pin}`, undefined, signal),
    enabled: /^[1-9]\d{5}$/.test(pin),
    staleTime: 10 * 60_000,
    retry: false,
  });
}
