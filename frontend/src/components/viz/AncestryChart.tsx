import { useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { AncestryNode, AncestryOut, VizPerson } from "../../api/types";
import { useAncestry } from "../../api/hooks/viz";
import { useBranches } from "../../api/hooks/family";
import { useTreeCtx } from "../../lib/tree-context";
import { buildLegend, COLOR_BYS, colorKey, HIDDEN_COLOR, MISSING_FILL, yearsLabel, type ColorBy } from "../../lib/vizColors";
import { ErrorAlert, Spinner } from "../ui/feedback";
import { Checkbox, Field, Select } from "../ui/form";
import { ChartFrame, type LegendItem } from "./ChartFrame";
import { PersonPanel } from "./PersonPanel";
import { AnimatedExport } from "./AnimatedExport";

export interface AncestrySettings {
  generations: number;
  colorBy: ColorBy;
  showMissing: boolean;
}

export const DEFAULT_ANCESTRY: AncestrySettings = { generations: 5, colorBy: "side", showMissing: true };

function truncate(s: string, n: number) {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

function arcPath(cx: number, cy: number, r0: number, r1: number, a0: number, a1: number) {
  const p = (r: number, a: number) => `${(cx + r * Math.cos(a)).toFixed(2)} ${(cy + r * Math.sin(a)).toFixed(2)}`;
  return `M ${p(r1, a0)} A ${r1} ${r1} 0 0 1 ${p(r1, a1)} L ${p(r0, a1)} A ${r0} ${r0} 0 0 0 ${p(r0, a0)} Z`;
}

interface Drawn {
  slot: number;
  node: AncestryNode | null; // null = research gap
  generation: number;
}

/** Fan chart or pedigree from the ancestry API, with colour modes, gap highlighting and exports. */
export function AncestryChart({ kind, rootId, settings, onSettings }: { kind: "fan" | "pedigree"; rootId: string; settings: AncestrySettings; onSettings: (s: AncestrySettings) => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const data = useAncestry(treeId, rootId, settings.generations);
  const branches = useBranches(treeId);
  const branchNames = useMemo(() => Object.fromEntries((branches.data ?? []).map((b) => [b.id, b.name])), [branches.data]);
  const [selected, setSelected] = useState<VizPerson | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const set = (patch: Partial<AncestrySettings>) => onSettings({ ...settings, ...patch });
  const a = data.data;
  const keys = useMemo(() => (a?.nodes ?? []).map((n) => colorKey(n.person, settings.colorBy, n.side, branchNames)), [a, settings.colorBy, branchNames]);
  const legend = useMemo(() => buildLegend(keys), [keys]);
  const legendItems: LegendItem[] = [
    ...legend.entries.map((e) => ({ key: e.key, color: e.color, label: `${labelForKey(e.key, settings.colorBy, t)} (${e.count})` })),
    ...(a?.nodes.some((n) => n.hidden) ? [{ key: "hidden", color: HIDDEN_COLOR, label: t("viz.privatePerson") }] : []),
    ...(settings.showMissing && (a?.missing_slots ?? []).length ? [{ key: "missing", color: "#a8a29e", label: t("viz.notRecorded"), pattern: "dashed" as const }] : []),
  ];
  const controls = (
    <>
      <Field label={t("viz.generations")}>
        {(p) => (
          <Select {...p} value={settings.generations} onChange={(e) => set({ generations: Number(e.target.value) })}>
            {[2, 3, 4, 5, 6, 7, 8].map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label={t("viz.colorBy")}>
        {(p) => (
          <Select {...p} value={settings.colorBy} onChange={(e) => set({ colorBy: e.target.value as ColorBy })}>
            {COLOR_BYS.map((c) => (
              <option key={c} value={c}>
                {t(`viz.colorByOption.${c}`)}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <div className="pb-2">
        <Checkbox label={t("viz.showMissing")} checked={settings.showMissing} onChange={(showMissing) => set({ showMissing })} />
      </div>
    </>
  );
  if (data.isLoading) return <Spinner />;
  if (data.error || !a) return <ErrorAlert error={data.error} />;
  const drawn: Drawn[] = [
    ...a.nodes.map((n) => ({ slot: n.slot, node: n, generation: n.generation })),
    ...(settings.showMissing ? (a.missing_slots ?? []).map((s) => ({ slot: s, node: null, generation: Math.floor(Math.log2(s)) })) : []),
  ];
  const fill = (d: Drawn) => (d.node === null ? MISSING_FILL : d.node.hidden ? HIDDEN_COLOR : legend.color(colorKey(d.node.person, settings.colorBy, d.node.side, branchNames)));
  const label = (d: Drawn) => (d.node === null ? t("viz.notRecorded") : d.node.hidden ? t("viz.privatePerson") : d.node.person?.display_name ?? "");
  const aria = (d: Drawn) =>
    d.node?.person
      ? `${d.node.person.display_name}, ${yearsLabel(d.node.person)}, ${t(`viz.side.${d.node.side}`)}`
      : label(d);
  const choose = (d: Drawn) => d.node?.person && setSelected(d.node.person);
  return (
    <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
      <ChartFrame
        title={t(`viz.chart.${kind}`)}
        summary={a.summary}
        filename={`${kind}-chart`}
        legend={legendItems}
        controls={controls}
        svgRef={svgRef}
        alternative={<AncestryTable a={a} />}
      >
        {kind === "fan" ? (
          <FanSvg svgRef={svgRef} drawn={drawn} generations={a.generations} fill={fill} label={label} aria={aria} onChoose={choose} selected={selected?.id} />
        ) : (
          <PedigreeSvg svgRef={svgRef} drawn={drawn} generations={a.generations} fill={fill} label={label} aria={aria} onChoose={choose} selected={selected?.id} />
        )}
      </ChartFrame>
      <div className="space-y-4">
        {selected && <PersonPanel person={selected} onClose={() => setSelected(null)} />}
        <AnimatedExport chartType={kind} settings={{ root_person_id: rootId, generations: Math.min(settings.generations, kind === "fan" ? 6 : 5), color_by: settings.colorBy }} />
      </div>
    </div>
  );
}

function labelForKey(key: string, colorBy: ColorBy, t: (k: string) => string): string {
  if (key === "__other__") return t("viz.other");
  if (key === "unknown") return t("common.unknown");
  if (colorBy === "side") return t(`viz.side.${key}`);
  if (colorBy === "completeness") return t(`viz.completenessBand.${key}`);
  if (colorBy === "living") return t(`enum.profileStatus.${key}`);
  return key;
}

interface SvgProps {
  svgRef: React.RefObject<SVGSVGElement>;
  drawn: Drawn[];
  generations: number;
  fill: (d: Drawn) => string;
  label: (d: Drawn) => string;
  aria: (d: Drawn) => string;
  onChoose: (d: Drawn) => void;
  selected?: string;
}

function keyActivate(fn: () => void) {
  return (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fn();
    }
  };
}

function FanSvg({ svgRef, drawn, generations, fill, label, aria, onChoose, selected }: SvgProps) {
  const W = 900;
  const H = 500;
  const cx = W / 2;
  const cy = H - 20;
  const rRoot = 60;
  // the semicircle must fit both half the width and the height
  const ring = Math.min(110, (Math.min(W / 2 - 10, H - 40) - rRoot) / generations);
  return (
    <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="group" aria-label="fan">
      {drawn
        .filter((d) => d.slot > 1)
        .map((d) => {
          const g = d.generation;
          const count = 2 ** g;
          const i = d.slot - count;
          const span = Math.PI / count;
          const a0 = Math.PI + i * span;
          const a1 = a0 + span;
          const r0 = rRoot + (g - 1) * ring + 2;
          const r1 = r0 + ring - 2;
          const mid = (a0 + a1) / 2;
          const rl = (r0 + r1) / 2;
          const tx = cx + rl * Math.cos(mid);
          const ty = cy + rl * Math.sin(mid);
          const deg = (mid * 180) / Math.PI;
          const radial = g >= 3;
          const rot = radial ? (deg > 270 || deg < 90 ? deg : deg + 180) : deg + 90;
          const isSel = d.node?.person?.id === selected && !!selected;
          const fs = g <= 2 ? 15 : g === 3 ? 12 : g === 4 ? 10 : 8;
          const max = g <= 2 ? 20 : g === 3 ? 16 : g === 4 ? 14 : 10;
          return (
            <g
              key={d.slot}
              tabIndex={d.node?.person ? 0 : -1}
              role={d.node?.person ? "button" : "img"}
              aria-label={aria(d)}
              onClick={() => onChoose(d)}
              onKeyDown={keyActivate(() => onChoose(d))}
              className={d.node?.person ? "cursor-pointer focus:outline-none [&:focus>path]:stroke-[#1f1a17] [&:focus>path]:stroke-[3]" : ""}
            >
              <path
                d={arcPath(cx, cy, r0, r1, a0, a1)}
                fill={fill(d)}
                fillOpacity={d.node?.person ? 0.88 : 1}
                stroke={isSel ? "#1f1a17" : d.node === null ? "#a8a29e" : "#fff"}
                strokeWidth={isSel ? 3 : 1.5}
                strokeDasharray={d.node === null ? "4 3" : undefined}
              />
              {g <= 6 && (
                <text x={tx} y={ty} transform={`rotate(${rot} ${tx} ${ty})`} textAnchor="middle" dominantBaseline="middle" fontSize={fs} fill={d.node?.person ? "#fff" : "#57534e"} fontWeight={600} pointerEvents="none">
                  {d.node === null ? "?" : truncate(label(d), max)}
                </text>
              )}
            </g>
          );
        })}
      {drawn
        .filter((d) => d.slot === 1)
        .map((d) => (
          <g key="root" tabIndex={0} role="button" aria-label={aria(d)} onClick={() => onChoose(d)} onKeyDown={keyActivate(() => onChoose(d))} className="cursor-pointer focus:outline-none">
            <path d={arcPath(cx, cy, 0, rRoot, Math.PI, 2 * Math.PI)} fill="#9f1239" />
            <text x={cx} y={cy - 28} textAnchor="middle" fontSize={13} fontWeight={700} fill="#fff" pointerEvents="none">
              {truncate(label(d), 14)}
            </text>
            <text x={cx} y={cy - 12} textAnchor="middle" fontSize={11} fill="#fff" pointerEvents="none">
              {d.node?.person ? yearsLabel(d.node.person) : ""}
            </text>
          </g>
        ))}
    </svg>
  );
}

function PedigreeSvg({ svgRef, drawn, generations, fill, label, aria, onChoose, selected }: SvgProps) {
  const cols = generations + 1;
  const W = Math.max(900, cols * 190);
  const rows = 2 ** Math.min(generations, 6);
  const H = Math.max(420, rows * 26);
  const colW = W / cols;
  const boxW = colW - 26;
  const pos = (slot: number) => {
    const g = Math.floor(Math.log2(slot));
    const idx = slot - 2 ** g;
    return { x: 8 + g * colW, y: ((idx + 0.5) * H) / 2 ** g, g };
  };
  const bySlot = new Map(drawn.map((d) => [d.slot, d]));
  return (
    <div className="overflow-x-auto">
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} style={{ minWidth: Math.min(W, 1200) }} className="h-auto w-full" role="group" aria-label="pedigree">
        {drawn
          .filter((d) => d.slot > 1 && bySlot.has(Math.floor(d.slot / 2)))
          .map((d) => {
            const c = pos(Math.floor(d.slot / 2));
            const p = pos(d.slot);
            const sx = c.x + boxW;
            return <path key={`l${d.slot}`} d={`M ${sx} ${c.y} H ${sx + 10} V ${p.y} H ${p.x}`} fill="none" stroke="#c9b79c" strokeWidth={1.5} />;
          })}
        {drawn.map((d) => {
          const { x, y, g } = pos(d.slot);
          const h = g <= 3 ? 44 : g <= 5 ? 22 : 14;
          const isSel = d.node?.person?.id === selected && !!selected;
          return (
            <g
              key={d.slot}
              transform={`translate(${x} ${y - h / 2})`}
              tabIndex={d.node?.person ? 0 : -1}
              role={d.node?.person ? "button" : "img"}
              aria-label={aria(d)}
              onClick={() => onChoose(d)}
              onKeyDown={keyActivate(() => onChoose(d))}
              className={d.node?.person ? "cursor-pointer focus:outline-none [&:focus>rect]:stroke-[3]" : ""}
            >
              <rect
                width={boxW}
                height={h}
                rx={6}
                fill={d.node?.person ? "#fff" : fill(d)}
                stroke={isSel ? "#1f1a17" : d.node?.person ? fill(d) : "#a8a29e"}
                strokeWidth={isSel ? 3 : 2}
                strokeDasharray={d.node === null ? "4 3" : undefined}
              />
              {d.node?.person && <rect width={5} height={h} rx={2} fill={fill(d)} />}
              <text x={10} y={h > 30 ? 18 : h / 2 + 4} fontSize={h > 30 ? 13 : h > 16 ? 11 : 9} fontWeight={600} fill="#1f1a17" pointerEvents="none">
                {truncate(label(d), h > 30 ? 26 : 24)}
              </text>
              {h > 30 && d.node?.person && (
                <text x={10} y={35} fontSize={11} fill="#6b5e55" pointerEvents="none">
                  {truncate([yearsLabel(d.node.person), d.node.person.birth_place?.name].filter(Boolean).join(" · "), 32)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function AncestryTable({ a }: { a: AncestryOut }) {
  const { t } = useTranslation();
  return (
    <table className="w-full text-left">
      <caption className="sr-only">{a.summary}</caption>
      <thead>
        <tr className="border-b border-stone-200">
          <th scope="col" className="py-1 pr-2">#</th>
          <th scope="col" className="py-1 pr-2">{t("viz.col.generation")}</th>
          <th scope="col" className="py-1 pr-2">{t("viz.col.side")}</th>
          <th scope="col" className="py-1 pr-2">{t("viz.col.person")}</th>
          <th scope="col" className="py-1 pr-2">{t("viz.col.life")}</th>
          <th scope="col" className="py-1">{t("viz.col.birthPlace")}</th>
        </tr>
      </thead>
      <tbody>
        {a.nodes.map((n) => (
          <tr key={n.slot} className="border-b border-stone-100">
            <td className="py-1 pr-2">{n.slot}</td>
            <td className="py-1 pr-2">{n.generation}</td>
            <td className="py-1 pr-2">{t(`viz.side.${n.side}`)}</td>
            <td className="py-1 pr-2">{n.hidden ? t("viz.privatePerson") : n.person?.display_name}</td>
            <td className="py-1 pr-2">{n.person ? yearsLabel(n.person) : ""}</td>
            <td className="py-1">{n.person?.birth_place?.name ?? ""}</td>
          </tr>
        ))}
        {(a.missing_slots ?? []).map((s) => (
          <tr key={`m${s}`} className="border-b border-stone-100 text-ink-muted">
            <td className="py-1 pr-2">{s}</td>
            <td className="py-1 pr-2">{Math.floor(Math.log2(s))}</td>
            <td className="py-1 pr-2" />
            <td className="py-1 pr-2" colSpan={3}>
              {t("viz.notRecorded")}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
