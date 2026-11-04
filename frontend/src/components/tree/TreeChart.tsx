import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent, type WheelEvent } from "react";
import { useTranslation } from "react-i18next";
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Minus, Plus, RotateCcw } from "lucide-react";
import type { GraphOut } from "../../api/types";
import { NODE_H, NODE_W, layoutGraph, neighbour, type Layout } from "../../lib/treeLayout";
import { lifespan } from "../../lib/dates";

const PAN_STEP = 120;
/** Height kept free at the top of the chart for the zoom/pan toolbar, so no card opens beneath it. */
const TOOLBAR_CLEAR = 52;

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
  youId,
  heightClass = "h-[65dvh] min-h-[360px]",
  minOpenScale,
  selectedId,
}: {
  graph: GraphOut;
  onOpen: (personId: string) => void;
  collapsed: ReadonlySet<string>;
  onToggleCollapse: (id: string) => void;
  /** The viewer's own profile in this tree, marked "You" wherever it appears in the chart. */
  youId?: string | null;
  heightClass?: string;
  /**
   * Never open smaller than this scale: a big family first shows a legible part of the tree,
   * centred on the viewer ("You") or the starting person, instead of shrinking every name to a
   * speck. "Fit to screen" still shows everyone.
   */
  minOpenScale?: number;
  /** The person whose details are shown beside the chart, outlined so the link is visible. */
  selectedId?: string | null;
}) {
  const { t } = useTranslation();
  const layout: Layout = useMemo(() => layoutGraph(graph, collapsed), [graph, collapsed]);
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  const [focusId, setFocusId] = useState<string>(layout.rootId);
  const drag = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null);
  const nodeRefs = useRef(new Map<string, SVGGElement>());

  const youNodeId = useMemo(
    () => (youId ? [...layout.nodes.values()].find((n) => n.node.person?.id === youId)?.node.id : undefined),
    [layout, youId],
  );

  const fit = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const w = el.clientWidth || 800;
    const h = el.clientHeight || 500;
    const pad = 32;
    const k = Math.min(1.2, Math.max(0.3, Math.min((w - pad) / (layout.width + pad), (h - pad - TOOLBAR_CLEAR) / (layout.height + pad))));
    setView({ k, x: (w - layout.width * k) / 2, y: Math.max(TOOLBAR_CLEAR, TOOLBAR_CLEAR + (h - TOOLBAR_CLEAR - layout.height * k) / 2) });
  }, [layout.width, layout.height]);

  /** The first view: fit everyone, or (when that would be illegible) a readable view around a focus. */
  const open = useCallback(() => {
    const el = containerRef.current;
    const w = el?.clientWidth || 800;
    const h = el?.clientHeight || 500;
    const pad = 32;
    const fitK = Math.min((w - pad) / (layout.width + pad), (h - pad - TOOLBAR_CLEAR) / (layout.height + pad));
    const focus = layout.nodes.get(youNodeId ?? layout.rootId);
    if (!minOpenScale || fitK >= minOpenScale || !focus) return fit();
    const k = minOpenScale;
    const tw = layout.width * k;
    const th = layout.height * k;
    const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
    // On each axis: centre the whole tree when it fits, otherwise centre the focus person but never
    // scroll past the tree's edge (no empty gutter), and keep the top row clear of the toolbar.
    const x = tw <= w - 32 ? (w - tw) / 2 : clamp(w / 2 - (focus.x + NODE_W / 2) * k, w - tw - 16, 16);
    const y =
      th <= h - TOOLBAR_CLEAR - 16
        ? TOOLBAR_CLEAR + (h - TOOLBAR_CLEAR - 16 - th) / 2
        : youNodeId
          ? clamp(h / 2 - (focus.y + NODE_H / 2) * k, h - th - 16, TOOLBAR_CLEAR)
          : TOOLBAR_CLEAR - focus.y * k; // the starting person at the top, descendants below
    setView({ k, x, y });
  }, [fit, layout, youNodeId, minOpenScale]);

  useEffect(() => {
    open();
  }, [open, graph.root_id, graph.direction]);

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

  const pan = (dx: number, dy: number) => setView((v) => ({ ...v, x: v.x + dx, y: v.y + dy }));

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
      <div className="absolute right-2 top-2 z-10 flex max-w-[calc(100%-1rem)] flex-wrap justify-end gap-1 rounded-lg border border-stone-300 bg-white/95 p-1 shadow-sm">
        <button type="button" className="rounded p-1.5 hover:bg-parchment-deep" onClick={() => zoom(1.2)} aria-label={t("treeView.zoomIn")}>
          <Plus className="size-4" aria-hidden />
        </button>
        <button type="button" className="rounded p-1.5 hover:bg-parchment-deep" onClick={() => zoom(1 / 1.2)} aria-label={t("treeView.zoomOut")}>
          <Minus className="size-4" aria-hidden />
        </button>
        <button type="button" className="rounded p-1.5 hover:bg-parchment-deep" onClick={fit} aria-label={t("treeView.fit")}>
          <RotateCcw className="size-4" aria-hidden />
        </button>
        {/* Single-pointer alternative to drag-panning (WCAG 2.5.7 Dragging Movements). */}
        {(
          [
            ["panLeft", ArrowLeft, 1, 0],
            ["panUp", ArrowUp, 0, 1],
            ["panDown", ArrowDown, 0, -1],
            ["panRight", ArrowRight, -1, 0],
          ] as const
        ).map(([key, Icon, dx, dy]) => (
          <button key={key} type="button" className="rounded p-1.5 hover:bg-parchment-deep" onClick={() => pan(dx * PAN_STEP, dy * PAN_STEP)} aria-label={t(`treeView.${key}`)}>
            <Icon className="size-4" aria-hidden />
          </button>
        ))}
      </div>
      <div
        ref={containerRef}
        className={`${heightClass} w-full cursor-grab touch-none overflow-hidden rounded-xl border border-stone-200 bg-[radial-gradient(circle,_#efe3cc_1px,_transparent_1px)] [background-size:18px_18px] active:cursor-grabbing`}
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
              const isYou = !!p && !!youId && p.id === youId;
              const isSelected = !!p && !!selectedId && p.id === selectedId;
              const years = p ? lifespan(p, t) ?? "" : "";
              // Everything the box shows visually (status bar, minor, lock) is also in the accessible name.
              const extras = p
                ? [
                    p.profile_status !== "unknown" ? t(`enum.profileStatus.${p.profile_status}`) : null,
                    p.is_minor ? t("person.badge.minor") : null,
                    p.is_protected ? t("person.badge.protected") : null,
                  ].filter(Boolean)
                : [];
              const label =
                (p
                  ? t("treeView.nodeLabel", { name: p.display_name, years: years || t("treeView.datesUnknown"), generation: n.node.generation })
                  : t("treeView.hiddenNodeLabel", { generation: n.node.generation })) +
                (n.node.partner ? ` ${t("treeView.partnerNode")}.` : "") +
                (extras.length ? ` ${extras.join(", ")}.` : "") +
                (isYou ? ` ${t("treeView.youLabel")}.` : "");
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
                  aria-current={isSelected ? "true" : undefined}
                  className="cursor-pointer outline-none [&:focus-visible>rect:first-child]:stroke-[3px] [&:focus-visible>rect:first-child]:stroke-kumkum-700"
                  onFocus={() => setFocusId(n.node.id)}
                  onKeyDown={(e) => onNodeKey(e, n.node.id)}
                  onClick={() => p && onOpen(p.id)}
                >
                  <rect
                    width={NODE_W}
                    height={NODE_H}
                    rx={10}
                    fill={hidden ? "#f5f5f4" : isRoot ? "#fdf3ee" : n.node.partner ? "#fffaf0" : "#ffffff"}
                    stroke={isSelected || isRoot ? "#9a3412" : hidden ? "#8a7f78" : "#9c8667" /* ≥ 3:1 on white (1.4.11) */}
                    strokeWidth={isSelected ? 3 : isRoot ? 2 : 1}
                    strokeDasharray={hidden ? "4 3" : undefined}
                  />
                  {/* Status bar: shape as well as colour (WCAG 1.4.1) — solid = living, broken = deceased,
                      outline = unknown. Explained in the legend under the chart. */}
                  {p && p.profile_status === "living" && <rect width={5} height={NODE_H - 16} x={0} y={8} rx={2} fill="#22643a" />}
                  {p && p.profile_status === "deceased" && (
                    <line x1={2.5} y1={8} x2={2.5} y2={NODE_H - 8} stroke="#6b5d4d" strokeWidth={5} strokeDasharray="6 4" />
                  )}
                  {p && p.profile_status !== "living" && p.profile_status !== "deceased" && (
                    <rect width={4} height={NODE_H - 17} x={0.5} y={8.5} rx={2} fill="none" stroke="#8a7a66" />
                  )}
                  <text x={14} y={26} fontSize={14} fontWeight={600} fill={hidden ? "#57534e" : "#231a12"} fontStyle={hidden ? "italic" : undefined}>
                    {p ? truncate(p.display_name, 22) : t("person.privatePerson")}
                  </text>
                  {isYou && (
                    <g transform={`translate(${NODE_W - 44},-10)`} aria-hidden>
                      <rect width={40} height={20} rx={10} fill="#9a3412" />
                      <text x={20} y={14} fontSize={11} fontWeight={700} textAnchor="middle" fill="#fff">
                        {t("treeView.you")}
                      </text>
                    </g>
                  )}
                  {p && (
                    <text x={14} y={46} fontSize={12} fill="#5c4b3b">
                      {years || t("treeView.datesUnknown")}
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
                      transform={`translate(${NODE_W - 28},${graph.direction === "ancestors" ? 4 : NODE_H - 28})`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onToggleCollapse(n.node.id);
                      }}
                      aria-hidden
                    >
                      {/* 24 × 24: minimum pointer target inside the node's own target (WCAG 2.5.8). */}
                      <rect width={24} height={24} rx={12} fill="#fbe3d6" stroke="#b4441c" />
                      <text x={12} y={17} fontSize={15} textAnchor="middle" fill="#7c2d12">
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
      <p className="mt-2 text-xs text-ink-muted">{t("treeView.statusLegend")}</p>
      <p id="tree-kbd-help" className="mt-1 text-xs text-ink-muted">
        {t("treeView.keyboardHelp")}
      </p>
    </div>
  );
}
