import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent, type WheelEvent } from "react";
import { useTranslation } from "react-i18next";
import { Minus, Plus, RotateCcw } from "lucide-react";
import type { GraphOut } from "../../api/types";
import { NODE_H, NODE_W, layoutGraph, neighbour, type Layout } from "../../lib/treeLayout";

function truncate(s: string, n: number) {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

/**
 * SVG generation-row chart with pan (drag), zoom (wheel / buttons), collapse/expand per node and
 * roving-focus keyboard navigation: arrows move between people, Enter opens the profile,
 * Space toggles collapse.
 */
export function TreeChart({
  graph,
  onOpen,
  collapsed,
  onToggleCollapse,
}: {
  graph: GraphOut;
  onOpen: (personId: string) => void;
  collapsed: ReadonlySet<string>;
  onToggleCollapse: (id: string) => void;
}) {
  const { t } = useTranslation();
  const layout: Layout = useMemo(() => layoutGraph(graph, collapsed), [graph, collapsed]);
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  const [focusId, setFocusId] = useState<string>(layout.rootId);
  const drag = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null);
  const nodeRefs = useRef(new Map<string, SVGGElement>());

  const fit = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const w = el.clientWidth || 800;
    const h = el.clientHeight || 500;
    const pad = 32;
    const k = Math.min(1.2, Math.max(0.3, Math.min((w - pad) / (layout.width + pad), (h - pad) / (layout.height + pad))));
    setView({ k, x: (w - layout.width * k) / 2, y: Math.max(16, (h - layout.height * k) / 2) });
  }, [layout.width, layout.height]);

  useEffect(() => {
    fit();
  }, [fit, graph.root_id, graph.direction]);

  useEffect(() => {
    if (!layout.nodes.has(focusId)) setFocusId(layout.rootId);
  }, [layout, focusId]);

  const zoom = (factor: number, cx?: number, cy?: number) => {
    setView((v) => {
      const k = Math.min(2.5, Math.max(0.2, v.k * factor));
      const el = containerRef.current;
      const px = cx ?? (el ? el.clientWidth / 2 : 0);
      const py = cy ?? (el ? el.clientHeight / 2 : 0);
      return { k, x: px - ((px - v.x) * k) / v.k, y: py - ((py - v.y) * k) / v.k };
    });
  };

  const onWheel = (e: WheelEvent) => {
    if (!e.ctrlKey && !e.metaKey) return; // plain wheel scrolls the page; ctrl/⌘ + wheel zooms
    e.preventDefault();
    const rect = containerRef.current!.getBoundingClientRect();
    zoom(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - rect.left, e.clientY - rect.top);
  };
  const onPointerDown = (e: PointerEvent) => {
    if ((e.target as Element).closest("[data-node]")) return;
    drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y };
    (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
  };
  const onPointerMove = (e: PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    setView((v) => ({ ...v, x: d.vx + e.clientX - d.x, y: d.vy + e.clientY - d.y }));
  };
  const onPointerUp = () => {
    drag.current = null;
  };

  /** Keep the focused node visible when moving with the keyboard. */
  const ensureVisible = (id: string) => {
    const n = layout.nodes.get(id);
    const el = containerRef.current;
    if (!n || !el) return;
    setView((v) => {
      const sx = n.x * v.k + v.x;
      const sy = n.y * v.k + v.y;
      let { x, y } = v;
      if (sx < 8) x += 8 - sx;
      if (sx + NODE_W * v.k > el.clientWidth - 8) x -= sx + NODE_W * v.k - (el.clientWidth - 8);
      if (sy < 8) y += 8 - sy;
      if (sy + NODE_H * v.k > el.clientHeight - 8) y -= sy + NODE_H * v.k - (el.clientHeight - 8);
      return { ...v, x, y };
    });
  };

  const onNodeKey = (e: KeyboardEvent, id: string) => {
    const n = layout.nodes.get(id)!;
    if (e.key === "Enter") {
      e.preventDefault();
      if (n.node.person) onOpen(n.node.person.id);
    } else if (e.key === " ") {
      e.preventDefault();
      if (n.children.length) onToggleCollapse(id);
    } else if (e.key === "ArrowUp" || e.key === "ArrowDown" || e.key === "ArrowLeft" || e.key === "ArrowRight") {
      e.preventDefault();
      const target = neighbour(layout, id, e.key);
      if (target) {
        setFocusId(target);
        nodeRefs.current.get(target)?.focus();
        ensureVisible(target);
      }
    } else if (e.key === "Home") {
      e.preventDefault();
      setFocusId(layout.rootId);
      nodeRefs.current.get(layout.rootId)?.focus();
      ensureVisible(layout.rootId);
    }
  };

  const edgePath = (sourceId: string, targetId: string) => {
    const s = layout.nodes.get(sourceId)!;
    const tt = layout.nodes.get(targetId)!;
    // parent (source) → child (target); connect bottom of the upper box to top of the lower box
    const upper = s.y < tt.y ? s : tt;
    const lower = s.y < tt.y ? tt : s;
    const x1 = upper.x + NODE_W / 2;
    const y1 = upper.y + NODE_H;
    const x2 = lower.x + NODE_W / 2;
    const y2 = lower.y;
    const my = (y1 + y2) / 2;
    return `M${x1},${y1} V${my} H${x2} V${y2}`;
  };

  const lineageDash = (lineage?: string | null, type?: string) =>
    type === "adoptive_parent" || lineage === "legal" ? "6 4" : type === "step_parent" || lineage === "social" ? "2 4" : lineage === "ritual" ? "8 3 2 3" : undefined;

  return (
    <div className="relative">
      <div className="absolute right-2 top-2 z-10 flex gap-1 rounded-lg border border-stone-300 bg-white/95 p-1 shadow-sm">
        <button type="button" className="rounded p-1.5 hover:bg-parchment-deep" onClick={() => zoom(1.2)} aria-label={t("treeView.zoomIn")}>
          <Plus className="size-4" aria-hidden />
        </button>
        <button type="button" className="rounded p-1.5 hover:bg-parchment-deep" onClick={() => zoom(1 / 1.2)} aria-label={t("treeView.zoomOut")}>
          <Minus className="size-4" aria-hidden />
        </button>
        <button type="button" className="rounded p-1.5 hover:bg-parchment-deep" onClick={fit} aria-label={t("treeView.fit")}>
          <RotateCcw className="size-4" aria-hidden />
        </button>
      </div>
      <div
        ref={containerRef}
        className="h-[65dvh] min-h-[360px] w-full cursor-grab touch-none overflow-hidden rounded-xl border border-stone-200 bg-[radial-gradient(circle,_#efe3cc_1px,_transparent_1px)] [background-size:18px_18px] active:cursor-grabbing"
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <svg ref={svgRef} width="100%" height="100%" role="group" aria-label={t("treeView.chartLabel")} aria-describedby="tree-kbd-help">
          <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
            {layout.couples.map((c) => {
              const a = layout.nodes.get(c.a)!;
              const b = layout.nodes.get(c.b)!;
              const left = a.x < b.x ? a : b;
              const right = a.x < b.x ? b : a;
              const y = left.y + NODE_H / 2;
              const divorced = c.type === "divorced_spouse" || c.type === "separated_spouse";
              return (
                <g key={`${c.a}-${c.b}`} aria-hidden>
                  <line x1={left.x + NODE_W} y1={y - 2} x2={right.x} y2={y - 2} stroke="#b4441c" strokeWidth={1.5} strokeDasharray={divorced ? "4 3" : undefined} />
                  <line x1={left.x + NODE_W} y1={y + 2} x2={right.x} y2={y + 2} stroke="#b4441c" strokeWidth={1.5} strokeDasharray={divorced ? "4 3" : undefined} />
                </g>
              );
            })}
            {layout.edges.map((e, i) => (
              <path key={`${e.source}-${e.target}-${i}`} d={edgePath(e.source, e.target)} fill="none" stroke="#9c8667" strokeWidth={1.5} strokeDasharray={lineageDash(e.lineage, e.type)} aria-hidden />
            ))}
            {[...layout.nodes.values()].map((n) => {
              const p = n.node.person;
              const hidden = !p;
              const isRoot = n.node.id === layout.rootId;
              const years = p ? `${p.birth_year ?? "?"}–${p.death_year ?? (p.profile_status === "living" ? "" : "?")}` : "";
              const label = p
                ? t("treeView.nodeLabel", { name: p.display_name, years, generation: n.node.generation })
                : t("treeView.hiddenNodeLabel", { generation: n.node.generation });
              return (
                <g
                  key={n.node.id}
                  data-node
                  ref={(el) => {
                    if (el) nodeRefs.current.set(n.node.id, el);
                    else nodeRefs.current.delete(n.node.id);
                  }}
                  transform={`translate(${n.x},${n.y})`}
                  tabIndex={focusId === n.node.id ? 0 : -1}
                  role="button"
                  aria-label={label}
                  aria-expanded={n.children.length ? !n.collapsed : undefined}
                  className="cursor-pointer outline-none [&:focus-visible>rect:first-child]:stroke-[3px] [&:focus-visible>rect:first-child]:stroke-kumkum-700"
                  onFocus={() => setFocusId(n.node.id)}
                  onKeyDown={(e) => onNodeKey(e, n.node.id)}
                  onClick={() => p && onOpen(p.id)}
                >
                  <rect
                    width={NODE_W}
                    height={NODE_H}
                    rx={10}
                    fill={hidden ? "#f5f5f4" : isRoot ? "#fdf3ee" : "#ffffff"}
                    stroke={isRoot ? "#9a3412" : hidden ? "#a8a29e" : "#d6c7ad"}
                    strokeWidth={isRoot ? 2 : 1}
                    strokeDasharray={hidden ? "4 3" : undefined}
                  />
                  {p && <rect width={5} height={NODE_H - 16} x={0} y={8} rx={2} fill={p.profile_status === "living" ? "#22643a" : p.profile_status === "deceased" ? "#8a7a66" : "#c9b89c"} />}
                  <text x={14} y={26} fontSize={14} fontWeight={600} fill={hidden ? "#57534e" : "#231a12"} fontStyle={hidden ? "italic" : undefined}>
                    {p ? truncate(p.display_name, 22) : t("person.privatePerson")}
                  </text>
                  {p && (
                    <text x={14} y={46} fontSize={12} fill="#5c4b3b">
                      {years !== "?–?" && years !== "?–" ? years : t("treeView.datesUnknown")}
                      {p.is_minor ? ` · ${t("person.badge.minor")}` : ""}
                      {p.is_protected ? " · 🔒" : ""}
                    </text>
                  )}
                  {n.collapsed && n.hiddenDescendants > 0 && (
                    <text x={14} y={61} fontSize={10} fill="#9a3412">
                      {t("treeView.collapsedCount", { count: n.hiddenDescendants })}
                    </text>
                  )}
                  {n.children.length > 0 && (
                    <g
                      transform={`translate(${NODE_W - 22},${graph.direction === "ancestors" ? 4 : NODE_H - 22})`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onToggleCollapse(n.node.id);
                      }}
                      aria-hidden
                    >
                      <rect width={18} height={18} rx={9} fill="#fbe3d6" stroke="#b4441c" />
                      <text x={9} y={13} fontSize={13} textAnchor="middle" fill="#7c2d12">
                        {n.collapsed ? "+" : "−"}
                      </text>
                    </g>
                  )}
                </g>
              );
            })}
          </g>
        </svg>
      </div>
      <p id="tree-kbd-help" className="mt-2 text-xs text-ink-muted">
        {t("treeView.keyboardHelp")}
      </p>
    </div>
  );
}
