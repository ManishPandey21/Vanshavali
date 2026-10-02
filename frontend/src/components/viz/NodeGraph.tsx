import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Minus, Plus, RotateCcw } from "lucide-react";
import type { GraphEdgeOut, GraphNodeOut, NeighbourhoodOut } from "../../api/types";
import { fetchNeighbourhood } from "../../api/hooks/viz";
import { useBranches } from "../../api/hooks/family";
import { useTreeCtx } from "../../lib/tree-context";
import { buildLegend, HIDDEN_COLOR, yearsLabel } from "../../lib/vizColors";
import { Button } from "../ui/Button";
import { ErrorAlert, Spinner } from "../ui/feedback";
import { Checkbox, Field, Select } from "../ui/form";
import { ChartFrame } from "./ChartFrame";
import { PersonPanel } from "./PersonPanel";

export interface SimNode {
  id: string;
  data: GraphNodeOut;
  x: number;
  y: number;
  vx: number;
  vy: number;
  pinned: boolean;
}

type GroupBy = "none" | "branch" | "household" | "village" | "living";
const GROUPS: GroupBy[] = ["none", "branch", "household", "village", "living"];
const W = 960;
const H = 600;

/** Merge a neighbourhood payload into the graph; new nodes start next to the node they hang off. */
export function mergeGraph(nodes: Map<string, SimNode>, edges: Map<string, GraphEdgeOut>, g: NeighbourhoodOut, anchor?: { x: number; y: number }) {
  const cx = anchor?.x ?? W / 2;
  const cy = anchor?.y ?? H / 2;
  g.nodes.forEach((n, i) => {
    const existing = nodes.get(n.id);
    if (existing) {
      // a fuller view of a known node (e.g. expandable flag) replaces the old data
      existing.data = { ...n, expandable: n.expandable && existing.data.expandable !== false ? n.expandable : n.expandable };
      return;
    }
    const angle = (i / Math.max(1, g.nodes.length)) * Math.PI * 2;
    nodes.set(n.id, { id: n.id, data: n, x: cx + Math.cos(angle) * 60, y: cy + Math.sin(angle) * 60, vx: 0, vy: 0, pinned: false });
  });
  for (const e of g.edges) edges.set(`${e.source}|${e.target}|${e.kind}`, e);
}

/** A few hundred iterations of a simple force layout (repulsion, springs, gravity). */
export function layout(nodes: Map<string, SimNode>, edges: Map<string, GraphEdgeOut>, iterations = 180) {
  const list = [...nodes.values()];
  const index = new Map(list.map((n, i) => [n.id, i]));
  for (let it = 0; it < iterations; it++) {
    const cool = 1 - it / iterations;
    for (let i = 0; i < list.length; i++) {
      const a = list[i];
      for (let j = i + 1; j < list.length; j++) {
        const b = list[j];
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        let d2 = dx * dx + dy * dy;
        if (d2 < 0.01) {
          dx = Math.random() - 0.5;
          dy = Math.random() - 0.5;
          d2 = 0.5;
        }
        const f = 900 / d2;
        a.vx += dx * f;
        a.vy += dy * f;
        b.vx -= dx * f;
        b.vy -= dy * f;
      }
    }
    for (const e of edges.values()) {
      const ia = index.get(e.source);
      const ib = index.get(e.target);
      if (ia === undefined || ib === undefined) continue;
      const a = list[ia];
      const b = list[ib];
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 1;
      const rest = e.kind === "union" ? 70 : 110;
      const k = (d - rest) * 0.04;
      a.vx += (dx / d) * k;
      a.vy += (dy / d) * k;
      b.vx -= (dx / d) * k;
      b.vy -= (dy / d) * k;
      if (e.kind === "parent") {
        // parents sit above children
        a.vy -= 0.3;
        b.vy += 0.3;
      }
    }
    for (const n of list) {
      n.vx += (W / 2 - n.x) * 0.01;
      n.vy += (H / 2 - n.y) * 0.01;
      if (!n.pinned) {
        n.x += Math.max(-20, Math.min(20, n.vx * cool));
        n.y += Math.max(-20, Math.min(20, n.vy * cool));
      }
      n.vx *= 0.5;
      n.vy *= 0.5;
    }
  }
}

/** A view transform that fits every node inside the canvas (with room for labels). */
export function fitView(nodes: Iterable<SimNode>): { x: number; y: number; k: number } {
  const list = [...nodes];
  if (!list.length) return { x: 0, y: 0, k: 1 };
  const xs = list.map((n) => n.x);
  const ys = list.map((n) => n.y);
  const minX = Math.min(...xs) - 70;
  const maxX = Math.max(...xs) + 70;
  const minY = Math.min(...ys) - 40;
  const maxY = Math.max(...ys) + 50;
  const k = Math.max(0.3, Math.min(1.6, W / (maxX - minX), H / (maxY - minY)));
  return { x: (W - (maxX - minX) * k) / 2 - minX * k, y: (H - (maxY - minY) * k) / 2 - minY * k, k };
}

/** Shortest path over the loaded edges (any relationship), for "how is this person connected?". */
export function pathBetween(edges: GraphEdgeOut[], from: string, to: string): string[] {
  const adj = new Map<string, string[]>();
  for (const e of edges) {
    adj.set(e.source, [...(adj.get(e.source) ?? []), e.target]);
    adj.set(e.target, [...(adj.get(e.target) ?? []), e.source]);
  }
  const prev = new Map<string, string | null>([[from, null]]);
  const queue = [from];
  while (queue.length) {
    const cur = queue.shift()!;
    if (cur === to) break;
    for (const n of adj.get(cur) ?? []) {
      if (!prev.has(n)) {
        prev.set(n, cur);
        queue.push(n);
      }
    }
  }
  if (!prev.has(to)) return [];
  const path: string[] = [];
  for (let c: string | null = to; c !== null; c = prev.get(c) ?? null) path.unshift(c);
  return path;
}

export function NodeGraph({ rootId }: { rootId: string }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const branches = useBranches(treeId);
  const branchNames = useMemo(() => Object.fromEntries((branches.data ?? []).map((b) => [b.id, b.name])), [branches.data]);
  const nodes = useRef(new Map<string, SimNode>());
  const edges = useRef(new Map<string, GraphEdgeOut>());
  const [, setVersion] = useState(0);
  const redraw = () => setVersion((v) => v + 1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [groupBy, setGroupBy] = useState<GroupBy>("living");
  const [branchFilter, setBranchFilter] = useState("");
  const [villageFilter, setVillageFilter] = useState("");
  const [withEvents, setWithEvents] = useState(false);
  const [path, setPath] = useState<string[]>([]);
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  const svgRef = useRef<SVGSVGElement>(null);
  const drag = useRef<{ id: string | null; sx: number; sy: number; ox: number; oy: number } | null>(null);

  const load = useCallback(
    async (id: string, radius: number, anchor?: { x: number; y: number }) => {
      setLoading(true);
      setError(null);
      try {
        const g = await fetchNeighbourhood(treeId, id, radius);
        mergeGraph(nodes.current, edges.current, g, anchor);
        // the node we expanded is now fully loaded at radius 1
        const n = nodes.current.get(id);
        if (n && anchor) n.data = { ...n.data, expandable: false };
        layout(nodes.current, edges.current);
        setView(fitView(nodes.current.values()));
        redraw();
      } catch (e) {
        setError(e);
      } finally {
        setLoading(false);
      }
    },
    [treeId],
  );

  useEffect(() => {
    nodes.current = new Map();
    edges.current = new Map();
    setSelected(null);
    setPath([]);
    setView({ x: 0, y: 0, k: 1 });
    void load(rootId, 2);
  }, [rootId, load]);

  const list = [...nodes.current.values()];
  const edgeList = [...edges.current.values()];
  const group = (n: SimNode): string | null => {
    const p = n.data.person;
    if (!p) return null;
    if (groupBy === "branch") return p.branch_ids?.[0] ? branchNames[p.branch_ids[0]] ?? "unknown" : "unknown";
    if (groupBy === "household") return n.data.household_ids?.[0] ? `#${n.data.household_ids[0].slice(0, 4)}` : "unknown";
    if (groupBy === "village") return p.village ?? "unknown";
    if (groupBy === "living") return p.profile_status;
    return "all";
  };
  const legend = buildLegend(list.map(group));
  const villages = [...new Set(list.map((n) => n.data.person?.village).filter(Boolean))] as string[];
  const matches = (n: SimNode) => {
    const p = n.data.person;
    if (!p) return !branchFilter && !villageFilter && !withEvents;
    if (branchFilter && !(p.branch_ids ?? []).includes(branchFilter)) return false;
    if (villageFilter && p.village !== villageFilter) return false;
    if (withEvents && !(p.event_count ?? 0)) return false;
    return true;
  };
  const onPath = new Set(path);
  const pathEdge = (e: GraphEdgeOut) => {
    const i = path.indexOf(e.source);
    return i >= 0 && (path[i + 1] === e.target || path[i - 1] === e.target);
  };
  const sel = selected ? nodes.current.get(selected) : null;

  const toLocal = (clientX: number, clientY: number) => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    const sx = ((clientX - rect.left) / rect.width) * W;
    const sy = ((clientY - rect.top) / rect.height) * H;
    return { x: (sx - view.x) / view.k, y: (sy - view.y) / view.k };
  };
  const zoom = (factor: number) => setView((v) => ({ ...v, k: Math.max(0.3, Math.min(3, v.k * factor)) }));

  const controls = (
    <>
      <Field label={t("viz.groupBy")}>
        {(p) => (
          <Select {...p} value={groupBy} onChange={(e) => setGroupBy(e.target.value as GroupBy)}>
            {GROUPS.map((g) => (
              <option key={g} value={g}>
                {t(`viz.groupOption.${g}`)}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label={t("viz.filterBranch")}>
        {(p) => (
          <Select {...p} value={branchFilter} onChange={(e) => setBranchFilter(e.target.value)}>
            <option value="">{t("viz.all")}</option>
            {(branches.data ?? []).map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label={t("viz.filterVillage")}>
        {(p) => (
          <Select {...p} value={villageFilter} onChange={(e) => setVillageFilter(e.target.value)}>
            <option value="">{t("viz.all")}</option>
            {villages.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <div className="pb-2">
        <Checkbox label={t("viz.withEvents")} checked={withEvents} onChange={setWithEvents} />
      </div>
    </>
  );

  return (
    <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
      <ChartFrame
        title={t("viz.chart.graph")}
        summary={t("viz.graphSummary", { count: list.filter((n) => n.data.person).length, edges: edgeList.length })}
        filename="family-graph"
        svgRef={svgRef}
        controls={controls}
        legend={groupBy === "none" ? [] : legend.entries.map((e) => ({ key: e.key, color: e.color, label: e.key === "__other__" ? t("viz.other") : e.key === "unknown" ? t("common.unknown") : groupBy === "living" ? t(`enum.profileStatus.${e.key}`) : e.key }))}
        alternative={<GraphList nodes={list} edges={edgeList} />}
      >
        <div className="relative">
          <div className="no-print absolute right-2 top-2 z-10 flex gap-1">
            <Button size="sm" variant="secondary" onClick={() => zoom(1.25)} aria-label={t("viz.zoomIn")} icon={<Plus className="size-4" aria-hidden />} />
            <Button size="sm" variant="secondary" onClick={() => zoom(0.8)} aria-label={t("viz.zoomOut")} icon={<Minus className="size-4" aria-hidden />} />
            <Button size="sm" variant="secondary" onClick={() => setView(fitView(nodes.current.values()))} aria-label={t("viz.resetView")} icon={<RotateCcw className="size-4" aria-hidden />} />
          </div>
          {loading && list.length === 0 && <Spinner />}
          <svg
            ref={svgRef}
            viewBox={`0 0 ${W} ${H}`}
            className="h-auto w-full touch-none select-none"
            role="group"
            aria-label={t("viz.chart.graph")}
            onWheel={(e) => zoom(e.deltaY < 0 ? 1.1 : 0.9)}
            onPointerDown={(e) => {
              if (e.target === svgRef.current) drag.current = { id: null, sx: e.clientX, sy: e.clientY, ox: view.x, oy: view.y };
            }}
            onPointerMove={(e) => {
              const d = drag.current;
              if (!d) return;
              if (d.id) {
                const n = nodes.current.get(d.id);
                if (n) {
                  const p = toLocal(e.clientX, e.clientY);
                  n.x = p.x;
                  n.y = p.y;
                  n.pinned = true;
                  redraw();
                }
              } else {
                const rect = svgRef.current!.getBoundingClientRect();
                setView((v) => ({ ...v, x: d.ox + ((e.clientX - d.sx) / rect.width) * W, y: d.oy + ((e.clientY - d.sy) / rect.height) * H }));
              }
            }}
            onPointerUp={() => (drag.current = null)}
            onPointerLeave={() => (drag.current = null)}
          >
            <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
              {edgeList.map((e) => {
                const a = nodes.current.get(e.source);
                const b = nodes.current.get(e.target);
                if (!a || !b) return null;
                const hot = pathEdge(e);
                return (
                  <line
                    key={`${e.source}|${e.target}|${e.kind}`}
                    x1={a.x}
                    y1={a.y}
                    x2={b.x}
                    y2={b.y}
                    stroke={hot ? "#9f1239" : e.kind === "union" ? "#a16207" : "#c9b79c"}
                    strokeWidth={hot ? 4 : e.kind === "union" ? 2.5 : 1.5}
                    strokeDasharray={e.kind === "sibling" || e.kind === "other" ? "4 3" : undefined}
                  />
                );
              })}
              {list.map((n) => {
                const p = n.data.person;
                const dim = !matches(n);
                const color = n.data.hidden ? HIDDEN_COLOR : groupBy === "none" ? "#9f1239" : legend.color(group(n));
                const isRoot = n.id === rootId;
                const isSel = n.id === selected;
                const initials = p ? p.display_name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("") : "?";
                return (
                  <g
                    key={n.id}
                    transform={`translate(${n.x} ${n.y})`}
                    opacity={dim ? 0.25 : 1}
                    tabIndex={p ? 0 : -1}
                    role={p ? "button" : "img"}
                    aria-label={p ? `${p.display_name}${yearsLabel(p) ? `, ${yearsLabel(p)}` : ""}${n.data.expandable ? `, ${t("viz.hasMoreRelatives")}` : ""}` : t("viz.privatePerson")}
                    className={p ? "cursor-pointer focus:outline-none [&:focus>circle.sel]:stroke-[#1f1a17]" : ""}
                    onPointerDown={(e) => {
                      e.stopPropagation();
                      drag.current = { id: n.id, sx: e.clientX, sy: e.clientY, ox: 0, oy: 0 };
                    }}
                    onClick={() => p && setSelected(n.id)}
                    onDoubleClick={() => p && n.data.expandable && void load(n.id, 1, { x: n.x, y: n.y })}
                    onKeyDown={(e) => {
                      if (!p) return;
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setSelected(n.id);
                      }
                      if ((e.key === "e" || e.key === "+") && n.data.expandable) void load(n.id, 1, { x: n.x, y: n.y });
                    }}
                  >
                    <circle className="sel" r={isRoot ? 24 : 19} fill="transparent" stroke={isSel || onPath.has(n.id) ? "#1f1a17" : "transparent"} strokeWidth={3} />
                    <circle r={isRoot ? 20 : 15} fill={color} stroke="#fff" strokeWidth={2} />
                    <text textAnchor="middle" dy={4} fontSize={isRoot ? 12 : 10} fontWeight={700} fill="#fff" pointerEvents="none">
                      {initials}
                    </text>
                    {n.data.expandable && <circle cx={13} cy={-13} r={6} fill="#fff" stroke={color} strokeWidth={2} />}
                    {n.data.expandable && (
                      <text x={13} y={-10} textAnchor="middle" fontSize={10} fontWeight={700} fill={color} pointerEvents="none">
                        +
                      </text>
                    )}
                    <text y={isRoot ? 36 : 30} textAnchor="middle" fontSize={11} fill="#1f1a17" pointerEvents="none">
                      {p ? (p.display_name.length > 18 ? `${p.display_name.slice(0, 17)}…` : p.display_name) : t("viz.privatePerson")}
                    </text>
                  </g>
                );
              })}
            </g>
          </svg>
          <p className="no-print px-3 pb-2 text-xs text-ink-muted">{t("viz.graphHelp")}</p>
        </div>
      </ChartFrame>
      <div className="space-y-3">
        <ErrorAlert error={error} />
        {sel?.data.person && (
          <PersonPanel
            person={sel.data.person}
            onClose={() => setSelected(null)}
            extra={
              <div className="flex flex-wrap gap-2">
                {sel.data.expandable && (
                  <Button size="sm" loading={loading} onClick={() => void load(sel.id, 1, { x: sel.x, y: sel.y })}>
                    {t("viz.expand")}
                  </Button>
                )}
                {sel.id !== rootId && (
                  <Button size="sm" variant="secondary" onClick={() => setPath(pathBetween(edgeList, rootId, sel.id))}>
                    {t("viz.showPath")}
                  </Button>
                )}
                {path.length > 0 && (
                  <Button size="sm" variant="ghost" onClick={() => setPath([])}>
                    {t("viz.clearPath")}
                  </Button>
                )}
              </div>
            }
          />
        )}
        {path.length > 0 && (
          <p className="text-sm" role="status">
            {t("viz.pathSteps", { count: path.length - 1 })}: {path.map((id) => nodes.current.get(id)?.data.person?.display_name ?? t("viz.privatePerson")).join(" → ")}
          </p>
        )}
      </div>
    </div>
  );
}

function GraphList({ nodes, edges }: { nodes: SimNode[]; edges: GraphEdgeOut[] }) {
  const { t } = useTranslation();
  const name = (id: string) => nodes.find((n) => n.id === id)?.data.person?.display_name ?? t("viz.privatePerson");
  return (
    <ul className="space-y-1">
      {edges.map((e) => (
        <li key={`${e.source}|${e.target}|${e.kind}`}>
          {name(e.source)} — {t(`viz.edge.${e.kind}`)} — {name(e.target)}
        </li>
      ))}
    </ul>
  );
}
