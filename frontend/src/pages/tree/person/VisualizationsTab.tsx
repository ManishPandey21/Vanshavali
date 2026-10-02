import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { BarChart3, CalendarRange, GitFork, Map, Network, PieChart, Sprout } from "lucide-react";
import type { PersonOut } from "../../../api/types";
import { useGeoMap } from "../../../api/hooks/viz";
import { useTreeCtx } from "../../../lib/tree-context";
import { MapPreview } from "../../../components/geo/MapPreview";
import { mapPins, mapRoutes } from "../../../components/viz/GeoMapView";

const CHARTS = [
  { id: "fan", icon: PieChart },
  { id: "pedigree", icon: GitFork },
  { id: "family", icon: Sprout },
  { id: "graph", icon: Network },
  { id: "lifespan", icon: BarChart3 },
  { id: "events", icon: CalendarRange },
  { id: "map", icon: Map },
] as const;

/** Charts centred on this person, and where their life happened. */
export function VisualizationsTab({ person }: { person: PersonOut }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const map = useGeoMap(treeId, { person_id: person.id });
  return (
    <section aria-labelledby="pviz-title" className="space-y-4">
      <h2 id="pviz-title" className="font-display text-lg font-semibold">
        {t("viz.forPerson", { name: person.display_name })}
      </h2>
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {CHARTS.map((c) => (
          <li key={c.id}>
            <Link to={`/t/${treeId}/visualizations?chart=${c.id}&root=${person.id}`} className="card flex h-full flex-col items-start gap-2 p-3 hover:border-kumkum-300">
              <c.icon className="size-5 text-kumkum-800" aria-hidden />
              <span className="font-semibold">{t(`viz.chart.${c.id}`)}</span>
              <span className="text-xs text-ink-muted">{t(`viz.chartHint.${c.id}`)}</span>
            </Link>
          </li>
        ))}
      </ul>
      {map.data && (map.data.points.length > 0 || map.data.paths.length > 0) && (
        <div>
          <h3 className="mb-2 font-semibold">{t("viz.whereTheyLived")}</h3>
          <MapPreview title={person.display_name} pins={mapPins(map.data)} routes={mapRoutes(map.data)} height={280} />
        </div>
      )}
    </section>
  );
}
