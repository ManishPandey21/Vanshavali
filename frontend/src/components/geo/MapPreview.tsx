import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { ExternalLink } from "lucide-react";
import { boundsOf, formatCoords, gridLines, osmLink, projector, type LatLng } from "../../lib/geo";

export interface MapPin extends LatLng {
  id: string;
  label: string;
  kind: string; // event | heritage | property | place
  precision?: string | null;
  coarsened?: boolean;
  year?: number | null;
  category?: string | null;
}

export interface MapRoute {
  id: string;
  label: string;
  from: LatLng;
  to: LatLng;
  fromLabel: string;
  toLabel: string;
  year?: number | null;
}

const KIND_STYLE: Record<string, { color: string; shape: "circle" | "diamond" | "square" | "triangle" }> = {
  event: { color: "#9f1239", shape: "circle" },
  heritage: { color: "#a16207", shape: "diamond" },
  property: { color: "#047857", shape: "square" },
  place: { color: "#1d4ed8", shape: "triangle" },
};

function Marker({ kind, x, y, r }: { kind: string; x: number; y: number; r: number }) {
  const s = KIND_STYLE[kind] ?? KIND_STYLE.event;
  const common = { fill: s.color, stroke: "#fff", strokeWidth: 1.5 };
  if (s.shape === "diamond") return <polygon points={`${x},${y - r} ${x + r},${y} ${x},${y + r} ${x - r},${y}`} {...common} />;
  if (s.shape === "square") return <rect x={x - r * 0.8} y={y - r * 0.8} width={r * 1.6} height={r * 1.6} {...common} />;
  if (s.shape === "triangle") return <polygon points={`${x},${y - r} ${x + r},${y + r * 0.8} ${x - r},${y + r * 0.8}`} {...common} />;
  return <circle cx={x} cy={y} r={r * 0.85} {...common} />;
}

/**
 * Tile-free map preview: projected points, migration routes and a graticule, with a full table
 * as the text alternative. No request leaves the app unless the user opens an OpenStreetMap link.
 */
export function MapPreview({ pins, routes = [], height = 360, title }: { pins: MapPin[]; routes?: MapRoute[]; height?: number; title: string }) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<string | null>(null);
  const width = 720;
  const all = useMemo(() => [...pins, ...routes.flatMap((r) => [r.from, r.to])], [pins, routes]);
  const b = boundsOf(all);
  if (!b) return <p className="text-sm text-ink-muted">{t("geo.noPoints")}</p>;
  const project = projector(b, width, height);
  const grid = gridLines(b);
  const sel = pins.find((p) => p.id === selected) ?? null;
  const kinds = [...new Set(pins.map((p) => p.kind))];
  return (
    <figure className="space-y-2">
      <div className="overflow-hidden rounded-xl border border-stone-200 bg-[#f4efe4]">
        <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full" role="img" aria-label={t("geo.mapLabel", { title, count: pins.length })}>
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#7c2d12" />
            </marker>
          </defs>
          {grid.lats.map((lat) => {
            const y = project({ latitude: lat, longitude: b.minLng }).y;
            return (
              <g key={`lat${lat}`}>
                <line x1={0} x2={width} y1={y} y2={y} stroke="#d6cbb6" strokeDasharray="3 4" />
                <text x={4} y={y - 3} fontSize={10} fill="#78716c">
                  {lat}°
                </text>
              </g>
            );
          })}
          {grid.lngs.map((lng) => {
            const x = project({ latitude: b.minLat, longitude: lng }).x;
            return (
              <g key={`lng${lng}`}>
                <line x1={x} x2={x} y1={0} y2={height} stroke="#d6cbb6" strokeDasharray="3 4" />
                <text x={x + 3} y={height - 4} fontSize={10} fill="#78716c">
                  {lng}°
                </text>
              </g>
            );
          })}
          {routes.map((r) => {
            const a = project(r.from);
            const c = project(r.to);
            const mx = (a.x + c.x) / 2 - (c.y - a.y) * 0.25;
            const my = (a.y + c.y) / 2 + (c.x - a.x) * 0.25;
            return (
              <path key={r.id} d={`M ${a.x} ${a.y} Q ${mx} ${my} ${c.x} ${c.y}`} fill="none" stroke="#7c2d12" strokeWidth={2} markerEnd="url(#arrow)" opacity={0.8}>
                <title>{`${r.label}: ${r.fromLabel} → ${r.toLabel}${r.year ? ` (${r.year})` : ""}`}</title>
              </path>
            );
          })}
          {pins.map((p) => {
            const { x, y } = project(p);
            const active = p.id === selected;
            return (
              <g
                key={p.id}
                role="button"
                tabIndex={0}
                aria-label={`${p.label}${p.year ? `, ${p.year}` : ""}`}
                aria-pressed={active}
                className="cursor-pointer focus:outline-none [&:focus>circle.ring]:stroke-[3]"
                onClick={() => setSelected(active ? null : p.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setSelected(active ? null : p.id);
                  }
                }}
              >
                {p.coarsened && <circle cx={x} cy={y} r={16} fill="#a8a29e" opacity={0.25} />}
                <circle className="ring" cx={x} cy={y} r={11} fill="transparent" stroke={active ? "#1f1a17" : "transparent"} strokeWidth={2} />
                <Marker kind={p.kind} x={x} y={y} r={7} />
                <title>{p.label}</title>
              </g>
            );
          })}
        </svg>
      </div>
      <figcaption className="flex flex-wrap items-center gap-3 text-xs text-ink-muted">
        {kinds.map((k) => (
          <span key={k} className="inline-flex items-center gap-1">
            <svg width="14" height="14" aria-hidden>
              <Marker kind={k} x={7} y={7} r={6} />
            </svg>
            {t(`geo.kind.${k}`)}
          </span>
        ))}
        {routes.length > 0 && <span>→ {t("geo.migrationRoutes", { count: routes.length })}</span>}
        <span>{t("geo.noTiles")}</span>
      </figcaption>
      {sel && (
        <div className="card flex flex-wrap items-center justify-between gap-2 p-3 text-sm" role="status">
          <span>
            <strong>{sel.label}</strong> · {formatCoords(sel)} · {t(`enum.locationPrecision.${sel.precision ?? "unknown"}`)}
            {sel.coarsened ? ` · ${t("geo.coarsened")}` : ""}
          </span>
          <a href={osmLink(sel)} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-kumkum-800 underline">
            {t("geo.openOsm")} <ExternalLink className="size-3.5" aria-hidden />
          </a>
        </div>
      )}
      <details className="text-sm">
        <summary className="cursor-pointer text-kumkum-800">{t("geo.listView", { count: pins.length + routes.length })}</summary>
        <table className="mt-2 w-full text-left text-sm">
          <caption className="sr-only">{t("geo.tableCaption", { title })}</caption>
          <thead>
            <tr className="border-b border-stone-200">
              <th scope="col" className="py-1 pr-2">{t("geo.col.what")}</th>
              <th scope="col" className="py-1 pr-2">{t("geo.col.kind")}</th>
              <th scope="col" className="py-1 pr-2">{t("geo.col.where")}</th>
              <th scope="col" className="py-1">{t("geo.col.precision")}</th>
            </tr>
          </thead>
          <tbody>
            {pins.map((p) => (
              <tr key={p.id} className="border-b border-stone-100">
                <td className="py-1 pr-2">{p.label}{p.year ? ` (${p.year})` : ""}</td>
                <td className="py-1 pr-2">{t(`geo.kind.${p.kind}`)}</td>
                <td className="py-1 pr-2">{formatCoords(p)}</td>
                <td className="py-1">{t(`enum.locationPrecision.${p.precision ?? "unknown"}`)}{p.coarsened ? ` (${t("geo.coarsened")})` : ""}</td>
              </tr>
            ))}
            {routes.map((r) => (
              <tr key={r.id} className="border-b border-stone-100">
                <td className="py-1 pr-2">{r.label}{r.year ? ` (${r.year})` : ""}</td>
                <td className="py-1 pr-2">{t("geo.kind.migration")}</td>
                <td className="py-1 pr-2" colSpan={2}>{r.fromLabel} → {r.toLabel}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
