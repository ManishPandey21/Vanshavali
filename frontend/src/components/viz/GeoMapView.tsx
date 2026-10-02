import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { MapOut } from "../../api/types";
import { useGeoMap } from "../../api/hooks/viz";
import { useTreeCtx } from "../../lib/tree-context";
import { MapPreview, type MapPin, type MapRoute } from "../geo/MapPreview";
import { ErrorAlert, Spinner } from "../ui/feedback";
import { Checkbox, Fieldset } from "../ui/form";

const LAYERS = ["events", "migrations", "heritage", "places", "properties"] as const;

export function mapPins(m: MapOut): MapPin[] {
  return m.points.map((p) => ({
    id: p.id,
    label: p.label,
    kind: p.kind,
    latitude: p.geo.latitude,
    longitude: p.geo.longitude,
    precision: p.geo.precision,
    coarsened: p.geo.coarsened,
    year: p.year,
    category: p.category,
  }));
}

export function mapRoutes(m: MapOut): MapRoute[] {
  return m.paths.map((p) => ({
    id: p.event_id,
    label: p.label,
    from: p.origin,
    to: p.destination,
    fromLabel: p.origin_label,
    toLabel: p.destination_label,
    year: p.year,
  }));
}

/** Ancestral villages, houses, temples, event places, properties and migration routes. */
export function GeoMapView({ personId, branchId }: { personId?: string; branchId?: string }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const [layers, setLayers] = useState<string[]>([...LAYERS]);
  const map = useGeoMap(treeId, { person_id: personId || undefined, branch_id: branchId || undefined, layer: layers });
  return (
    <div className="space-y-3">
      <Fieldset legend={t("geo.layers")} className="no-print">
        <div className="flex flex-wrap gap-4">
          {LAYERS.map((l) => (
            <Checkbox key={l} label={t(`geo.layer.${l}`)} checked={layers.includes(l)} onChange={(v) => setLayers(v ? [...layers, l] : layers.filter((x) => x !== l))} />
          ))}
        </div>
      </Fieldset>
      {map.isLoading && <Spinner />}
      <ErrorAlert error={map.error} />
      {map.data && (
        <>
          <MapPreview title={t("viz.chart.map")} pins={mapPins(map.data)} routes={mapRoutes(map.data)} height={460} />
          {(map.data.not_geotagged ?? 0) > 0 && <p className="text-sm text-ink-muted">{t("geo.notGeotaggedCount", { count: map.data.not_geotagged })}</p>}
        </>
      )}
    </div>
  );
}
