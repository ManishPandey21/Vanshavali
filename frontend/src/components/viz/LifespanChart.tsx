import { useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { LifespanRow } from "../../api/types";
import { useLifespans } from "../../api/hooks/viz";
import { useBranches } from "../../api/hooks/family";
import { useTreeCtx } from "../../lib/tree-context";
import { ErrorAlert, Spinner } from "../ui/feedback";
import { Checkbox, Field, Select } from "../ui/form";
import { ChartFrame } from "./ChartFrame";
import { PersonPanel } from "./PersonPanel";
import { AnimatedExport } from "./AnimatedExport";

const LABEL_W = 190;
const ROW_H = 24;

/** Lifespans across generations: overlap, eras and major events, with a zoom slider. */
export function LifespanChart({ rootId }: { rootId?: string }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const branches = useBranches(treeId);
  const [generations, setGenerations] = useState(4);
  const [branchId, setBranchId] = useState("");
  const [withEvents, setWithEvents] = useState(true);
  const [generation, setGeneration] = useState<string>("");
  const [scale, setScale] = useState(6); // pixels per year
  const [selected, setSelected] = useState<LifespanRow | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const data = useLifespans(treeId, { root: rootId || undefined, generations, branch_id: branchId || undefined, include_events: withEvents });
  const thisYear = new Date().getFullYear();
  const rows = useMemo(
    () => (data.data?.rows ?? []).filter((r) => generation === "" || String(r.generation ?? "") === generation),
    [data.data, generation],
  );
  const gens = [...new Set((data.data?.rows ?? []).map((r) => r.generation).filter((g) => g !== null && g !== undefined))].sort((a, b) => (a as number) - (b as number));
  const lo = Math.floor(((data.data?.min_year ?? thisYear - 100) - 5) / 10) * 10;
  const hi = Math.max(data.data?.max_year ?? thisYear, thisYear) + 3;
  const width = LABEL_W + (hi - lo) * scale + 20;
  const height = 40 + rows.length * ROW_H + 30;
  const x = (y: number) => LABEL_W + (y - lo) * scale;
  const step = scale >= 10 ? 10 : scale >= 5 ? 20 : 50;
  const ticks: number[] = [];
  for (let y = Math.ceil(lo / step) * step; y <= hi; y += step) ticks.push(y);
  const controls = (
    <>
      {rootId && (
        <Field label={t("viz.generations")}>
          {(p) => (
            <Select {...p} value={generations} onChange={(e) => setGenerations(Number(e.target.value))}>
              {[1, 2, 3, 4, 5, 6, 8, 10].map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
            </Select>
          )}
        </Field>
      )}
      {rootId && gens.length > 1 && (
        <Field label={t("viz.generation")}>
          {(p) => (
            <Select {...p} value={generation} onChange={(e) => setGeneration(e.target.value)}>
              <option value="">{t("viz.all")}</option>
              {gens.map((g) => (
                <option key={String(g)} value={String(g)}>
                  {t("viz.generationN", { n: g })}
                </option>
              ))}
            </Select>
          )}
        </Field>
      )}
      <Field label={t("viz.filterBranch")}>
        {(p) => (
          <Select {...p} value={branchId} onChange={(e) => setBranchId(e.target.value)}>
            <option value="">{t("viz.all")}</option>
            {(branches.data ?? []).map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label={t("viz.zoom")}>
        {(p) => <input {...p} type="range" min={2} max={20} value={scale} onChange={(e) => setScale(Number(e.target.value))} aria-valuetext={t("viz.zoomValue", { n: scale })} />}
      </Field>
      <div className="pb-2">
        <Checkbox label={t("viz.majorEvents")} checked={withEvents} onChange={setWithEvents} />
      </div>
    </>
  );
  if (data.isLoading) return <Spinner />;
  if (data.error || !data.data) return <ErrorAlert error={data.error} />;
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_18rem]">
      <ChartFrame
        title={t("viz.chart.lifespan")}
        summary={data.data.summary + ((data.data.without_dates ?? 0) > 0 ? ` ${t("viz.withoutDates", { count: data.data.without_dates })}` : "")}
        filename="lifespans"
        svgRef={svgRef}
        controls={controls}
        legend={[
          { key: "deceased", color: "#9a3412", label: t("enum.profileStatus.deceased") },
          { key: "living", color: "#1d4ed8", label: t("enum.profileStatus.living") },
          { key: "unknown", color: "#a8a29e", label: t("viz.endUnknown"), pattern: "dashed" },
        ]}
        alternative={<LifespanTable rows={rows} />}
      >
        <div className="max-h-[70vh] overflow-auto">
          <svg ref={svgRef} viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="group" aria-label={t("viz.chart.lifespan")}>
            {(data.data.periods ?? [])
              .filter((p) => p.end_year >= lo && p.start_year <= hi)
              .map((p, i) => (
                <g key={p.label}>
                  <rect x={x(Math.max(lo, p.start_year))} y={14} width={Math.max(2, x(Math.min(hi, p.end_year)) - x(Math.max(lo, p.start_year)))} height={height - 30} fill="#9f1239" opacity={i % 2 ? 0.04 : 0.08} />
                  <text x={x(Math.max(lo, p.start_year)) + 3} y={26} fontSize={10} fill="#6b5e55">
                    {p.label}
                  </text>
                </g>
              ))}
            {ticks.map((y) => (
              <g key={y}>
                <line x1={x(y)} x2={x(y)} y1={32} y2={height - 24} stroke="#e7dfd0" />
                <text x={x(y)} y={height - 8} fontSize={10} textAnchor="middle" fill="#6b5e55">
                  {y}
                </text>
              </g>
            ))}
            {rows.map((r, i) => {
              const y = 40 + i * ROW_H;
              const end = r.end_year ?? thisYear;
              const living = r.person.profile_status === "living";
              const color = !r.end_known ? "#a8a29e" : living ? "#1d4ed8" : "#9a3412";
              return (
                <g
                  key={r.person.id}
                  tabIndex={0}
                  role="button"
                  aria-label={`${r.person.display_name}: ${r.start_year}–${r.end_year ?? (living ? t("viz.present") : "?")}`}
                  className="cursor-pointer focus:outline-none [&:focus>rect.bar]:stroke-[#1f1a17] [&:focus>rect.bar]:stroke-2"
                  onClick={() => setSelected(r)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setSelected(r);
                    }
                  }}
                >
                  <text x={LABEL_W - 8} y={y + 15} fontSize={12} textAnchor="end" fill="#1f1a17">
                    {r.person.display_name.length > 26 ? `${r.person.display_name.slice(0, 25)}…` : r.person.display_name}
                  </text>
                  <rect
                    className="bar"
                    x={x(r.start_year)}
                    y={y + 4}
                    width={Math.max(3, x(end) - x(r.start_year))}
                    height={ROW_H - 8}
                    rx={4}
                    fill={color}
                    fillOpacity={living ? 0.55 : 0.85}
                    strokeDasharray={!r.end_known ? "4 3" : undefined}
                    stroke={!r.end_known ? "#57534e" : "none"}
                  />
                  {(r.events ?? []).map((ev) => (
                    <circle key={ev.event_id} cx={x(ev.year)} cy={y + ROW_H / 2} r={4} fill="#fff" stroke="#1f1a17" strokeWidth={1.5}>
                      <title>{`${ev.year}: ${ev.label}`}</title>
                    </circle>
                  ))}
                </g>
              );
            })}
          </svg>
        </div>
      </ChartFrame>
      <div className="space-y-4">
        {selected && (
          <PersonPanel
            person={selected.person}
            onClose={() => setSelected(null)}
            extra={
              (selected.events ?? []).length > 0 ? (
                <ul className="text-sm">
                  {(selected.events ?? []).map((e) => (
                    <li key={e.event_id}>
                      {e.year}: {e.label}
                    </li>
                  ))}
                </ul>
              ) : null
            }
          />
        )}
        <AnimatedExport chartType="lifespan" settings={{ root_person_id: rootId || null, generations: Math.min(generations, 8), branch_id: branchId || null }} />
      </div>
    </div>
  );
}

function LifespanTable({ rows }: { rows: LifespanRow[] }) {
  const { t } = useTranslation();
  return (
    <table className="w-full text-left">
      <thead>
        <tr className="border-b border-stone-200">
          <th scope="col" className="py-1 pr-2">{t("viz.col.person")}</th>
          <th scope="col" className="py-1 pr-2">{t("viz.col.born")}</th>
          <th scope="col" className="py-1 pr-2">{t("viz.col.died")}</th>
          <th scope="col" className="py-1 pr-2">{t("viz.col.generation")}</th>
          <th scope="col" className="py-1">{t("viz.col.events")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.person.id} className="border-b border-stone-100">
            <td className="py-1 pr-2">{r.person.display_name}</td>
            <td className="py-1 pr-2">{r.person.birth_display ?? r.start_year}</td>
            <td className="py-1 pr-2">{r.person.profile_status === "living" ? t("viz.present") : r.person.death_display ?? "?"}</td>
            <td className="py-1 pr-2">{r.generation ?? ""}</td>
            <td className="py-1">{(r.events ?? []).map((e) => `${e.year}: ${e.label}`).join("; ")}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
