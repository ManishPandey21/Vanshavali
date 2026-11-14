import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent, type WheelEvent } from "react";
import { useTranslation } from "react-i18next";
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Maximize, Minus, Plus, RotateCcw } from "lucide-react";
import type { GraphOut } from "../../api/types";
import { NODE_H, NODE_W, layoutGraph, neighbour, type Layout } from "../../lib/treeLayout";
import { lifespan } from "../../lib/dates";

const PAN_STEP = 120;
/** Above this many people only what is on screen is drawn (the layout still holds everyone). */
const CULL_ABOVE = 250;
/** Below this zoom a card is a plain box: names are illegible anyway and 10,000 labels are slow. */
const DETAIL_SCALE = 0.3;

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
  layout: givenLayout,
  viewKey,
  centreOn,
  onOpen,
  onSelect,
  selectedId,
  collapsed,
  onToggleCollapse,
  youId,
  heightClass = "h-[65dvh] min-h-[360px]",
  minOpenScale,
}: {
  /** An ancestor or descendant graph, laid out here… */
  graph?: GraphOut;
  /** …or a layout computed by the caller (the complete family, `lib/familyLayout`). */
  layout?: Layout;
  /** With `layout`: the view is re-fitted only when this changes, not each time more people load. */
  viewKey?: string;
  /** With `layout`: bring this node to the middle and focus it (`seq` makes repeats count). */
  centreOn?: { id: string; seq: number } | null;
  onOpen: (personId: string) => void;
  /** When given, a click selects the person (e.g. for a side panel); Enter still opens the profile. */
  onSelect?: (personId: string) => void;
  selectedId?: string | null;
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
}) {
  const { t } = useTranslation();
  const family = !!givenLayout;
  const layout: Layout = useMemo(
    () => givenLayout ?? layoutGraph(graph!, collapsed),
    [givenLayout, graph, collapsed],
  );
  const [size, setSize] = useState({ w: 800, h: 500 });
  const [pendingFocus, setPendingFocus] = useState<string | null>(null);
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
    // a whole family may need to go far smaller than a focused view before everyone fits
    const floor = family ? 0.02 : 0.3;
    // the complete family keeps clear of the toolbar, so the top row and group labels stay readable
    const top = family ? 60 : 16;
    const k = Math.min(1.2, Math.max(floor, Math.min((w - pad) / (layout.width + pad), (h - pad - (top - 16)) / (layout.height + pad))));
    setView({ k, x: (w - layout.width * k) / 2, y: Math.max(top, (h - layout.height * k) / 2) });
  }, [layout.width, layout.height, family]);

  /** The first view: fit everyone, or (when that would be illegible) a readable view around a focus. */
  const open = useCallback(() => {
    const el = containerRef.current;
    const w = el?.clientWidth || 800;
    const h = el?.clientHeight || 500;
    const pad = 32;
    const fitK = Math.min((w - pad) / (layout.width + pad), (h - pad) / (layout.height + pad));
    const focus = layout.nodes.get(youNodeId ?? layout.rootId);
    if (!minOpenScale || fitK >= minOpenScale || !focus) return fit();
    const k = minOpenScale;
    const x = w / 2 - (focus.x + NODE_W / 2) * k;
    // the starting person sits near the top, clear of the zoom toolbar (their descendants fill the
    // view); "You" sits centred
    const y = youNodeId ? h / 2 - (focus.y + NODE_H / 2) * k : 64 - focus.y * k;
    setView({ k, x, y });
  }, [fit, layout, youNodeId, minOpenScale]);

  const openRef = useRef(open);
  openRef.current = open;
  const hasNodes = layout.nodes.size > 0;
  useEffect(() => {
    if (!family) open();
  }, [family, open, graph?.root_id, graph?.direction]);
  // The complete family arrives in pages. Opening the view again on every page would throw the
  // reader around, so it opens once per family and afterwards the starting person is held still.
  useEffect(() => {
    if (family && hasNodes) openRef.current();
  }, [family, viewKey, hasNodes]);
  const anchor = useRef<{ key?: string; id: string; x: number; y: number } | null>(null);
  useEffect(() => {
    if (!family) return;
    const n = layout.nodes.get(layout.rootId);
    const prev = anchor.current;
    if (n && prev && prev.key === viewKey && prev.id === layout.rootId && (prev.x !== n.x || prev.y !== n.y)) {
      setView((v) => ({ ...v, x: v.x + (prev.x - n.x) * v.k, y: v.y + (prev.y - n.y) * v.k }));
    }
    anchor.current = n ? { key: viewKey, id: layout.rootId, x: n.x, y: n.y } : null;
  }, [family, layout, viewKey]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const measure = () => setSize({ w: el.clientWidth || 800, h: el.clientHeight || 500 });
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const centreSeq = centreOn?.seq;
  const centreId = centreOn?.id;
  useEffect(() => {
    if (!centreId) return;
    const n = layout.nodes.get(centreId);
    const el = containerRef.current;
    if (!n || !el) return;
    setView((v) => {
      const k = Math.max(v.k, 0.8);
      return { k, x: el.clientWidth / 2 - (n.x + NODE_W / 2) * k, y: el.clientHeight / 2 - (n.y + NODE_H / 2) * k };
    });
    setFocusId(centreId);
    setPendingFocus(centreId);
    // only when asked again: a growing layout must not keep re-centring
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [centreId, centreSeq]);

  // Draw only what is on screen once the family is large; the margin keeps keyboard neighbours mounted.
  const cull = layout.nodes.size > CULL_ABOVE;
  // only the complete family simplifies its cards; the focused chart keeps names at every zoom
  const detailed = !family || view.k >= DETAIL_SCALE;
  const bounds = useMemo(() => {
    const mx = NODE_W * 2;
    const my = NODE_H * 3;
    return { x0: -view.x / view.k - mx, x1: (size.w - view.x) / view.k + mx, y0: -view.y / view.k - my, y1: (size.h - view.y) / view.k + my };
  }, [view, size]);
  const onScreen = useCallback(
    (x: number, y: number, w = NODE_W, h = NODE_H) => !cull || (x + w >= bounds.x0 && x <= bounds.x1 && y + h >= bounds.y0 && y <= bounds.y1),
    [cull, bounds],
  );
  const shown = useMemo(
    () => [...layout.nodes.values()].filter((n) => n.node.id === focusId || onScreen(n.x, n.y)),
    [layout, onScreen, focusId],
  );
  // focus follows once the node is actually drawn (it may have been off screen a moment ago)
  useEffect(() => {
    if (!pendingFocus) return;
    const el = nodeRefs.current.get(pendingFocus);
    if (!el) return;
    el.focus();
    setPendingFocus(null);
  }, [pendingFocus, shown]);
  const spanOnScreen = (aId: string, bId: string) => {
    const a = layout.nodes.get(aId);
    const b = layout.nodes.get(bId);
    if (!a || !b) return false;
    const x = Math.min(a.x, b.x);
    const y = Math.min(a.y, b.y);
    return onScreen(x, y, Math.abs(a.x - b.x) + NODE_W, Math.abs(a.y - b.y) + NODE_H);
  };

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
        setPendingFocus(target); // it may not be drawn yet when only the visible part is rendered
        ensureVisible(target);
      }
    } else if (e.key === "Home") {
      e.preventDefault();
      setFocusId(layout.rootId);
      setPendingFocus(layout.rootId); // like the arrows: it may be off screen and not drawn yet
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
    if (s.y === tt.y) {
      // a contradictory record put parent and child on one row: an arc above, never a zero-length line
      const top = s.y - 18;
      return `M${s.x + NODE_W / 2},${s.y} C${s.x + NODE_W / 2},${top - 24} ${tt.x + NODE_W / 2},${top - 24} ${tt.x + NODE_W / 2},${tt.y}`;
    }
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
        {family ? (
          <>
            <button type="button" className="rounded p-1.5 hover:bg-parchment-deep" onClick={fit} aria-label={t("treeView.fit")} title={t("treeView.fit")}>
              <Maximize className="size-4" aria-hidden />
            </button>
            <button type="button" className="rounded p-1.5 hover:bg-parchment-deep" onClick={open} aria-label={t("treeView.resetView")} title={t("treeView.resetView")}>
              <RotateCcw className="size-4" aria-hidden />
            </button>
          </>
        ) : (
          <button type="button" className="rounded p-1.5 hover:bg-parchment-deep" onClick={fit} aria-label={t("treeView.fit")}>
            <RotateCcw className="size-4" aria-hidden />
          </button>
        )}
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
            {(layout.groups?.length ?? 0) > 1 &&
              layout.groups!.filter((g) => onScreen(g.x - 16, g.y - 40, g.width + 32, g.height + 56)).map((g) => (
                <g key={`group-${g.index}`} aria-hidden>
                  <rect x={g.x - 16} y={g.y - 16} width={g.width + 32} height={g.height + 32} rx={16} fill="#fffdf8" fillOpacity={0.55} stroke="#c9b79c" strokeDasharray="2 5" />
                  {detailed && (
                    <text x={g.x - 8} y={g.y - 24} fontSize={13} fontWeight={600} fill="#5c4b3b">
                      {t("treeView.groupLabel", { n: g.index + 1, count: g.people })}
                    </text>
                  )}
                </g>
              ))}
            {(layout.links ?? []).filter((l) => spanOnScreen(l.a, l.b)).map((l) => {
              const a = layout.nodes.get(l.a)!;
              const b = layout.nodes.get(l.b)!;
              const x1 = a.x + NODE_W / 2;
              const x2 = b.x + NODE_W / 2;
              const lift = Math.min(a.y, b.y) - 16;
              return (
                <path key={`link-${l.kind}-${l.a}-${l.b}`} d={`M${x1},${a.y} C${x1},${lift} ${x2},${lift} ${x2},${b.y}`} fill="none" stroke="#7a6a55" strokeWidth={1.5} strokeDasharray={l.kind === "sibling" ? "1 4" : "1 7"} strokeLinecap="round" aria-hidden />
              );
            })}
            {layout.couples.filter((c) => spanOnScreen(c.a, c.b)).map((c) => {
              const a = layout.nodes.get(c.a)!;
              const b = layout.nodes.get(c.b)!;
              const left = a.x < b.x ? a : b;
              const right = a.x < b.x ? b : a;
              const y = left.y + NODE_H / 2;
              const divorced = c.type === "divorced_spouse" || c.type === "separated_spouse";
              if (a.y !== b.y) {
                // partners recorded on different rows (a marriage across generations): one curved line
                const y2 = right.y + NODE_H / 2;
                const mx = (left.x + NODE_W + right.x) / 2;
                return (
                  <path key={`${c.a}-${c.b}`} d={`M${left.x + NODE_W},${y} C${mx},${y} ${mx},${y2} ${right.x},${y2}`} fill="none" stroke="#b4441c" strokeWidth={2} strokeDasharray={divorced ? "4 3" : undefined} aria-hidden />
                );
              }
              return (
                <g key={`${c.a}-${c.b}`} aria-hidden>
                  <line x1={left.x + NODE_W} y1={y - 2} x2={right.x} y2={y - 2} stroke="#b4441c" strokeWidth={1.5} strokeDasharray={divorced ? "4 3" : undefined} />
                  <line x1={left.x + NODE_W} y1={y + 2} x2={right.x} y2={y + 2} stroke="#b4441c" strokeWidth={1.5} strokeDasharray={divorced ? "4 3" : undefined} />
                </g>
              );
            })}
            {layout.edges.filter((e) => spanOnScreen(e.source, e.target)).map((e, i) => (
              <path key={`${e.source}-${e.target}-${i}`} d={edgePath(e.source, e.target)} fill="none" stroke="#9c8667" strokeWidth={1.5} strokeDasharray={lineageDash(e.lineage, e.type)} aria-hidden />
            ))}
            {shown.map((n) => {
              const p = n.node.person;
              const hidden = !p;
              const isRoot = !layout.noRootHighlight && n.node.id === layout.rootId;
              const isYou = !!p && !!youId && p.id === youId;
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
                  className="cursor-pointer outline-none [&:focus-visible>rect:first-child]:stroke-[3px] [&:focus-visible>rect:first-child]:stroke-kumkum-700"
                  onFocus={() => setFocusId(n.node.id)}
                  onKeyDown={(e) => onNodeKey(e, n.node.id)}
                  onClick={() => p && (onSelect ?? onOpen)(p.id)}
                >
                  <rect
                    width={NODE_W}
                    height={NODE_H}
                    rx={10}
                    fill={hidden ? "#f5f5f4" : isRoot ? "#fdf3ee" : n.node.partner ? "#fffaf0" : "#ffffff"}
                    stroke={p && selectedId === p.id ? "#d99a0b" : isRoot ? "#9a3412" : hidden ? "#8a7f78" : "#9c8667" /* ≥ 3:1 on white (1.4.11) */}
                    strokeWidth={p && selectedId === p.id ? 3 : isRoot ? 2 : 1}
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
                  {detailed && (
                    <text x={14} y={26} fontSize={14} fontWeight={600} fill={hidden ? "#57534e" : "#231a12"} fontStyle={hidden ? "italic" : undefined}>
                      {p ? truncate(p.display_name, 22) : t("person.privatePerson")}
                    </text>
                  )}
                  {isYou && (
                    <g transform={`translate(${NODE_W - 44},-10)`} aria-hidden>
                      <rect width={40} height={20} rx={10} fill="#9a3412" />
                      <text x={20} y={14} fontSize={11} fontWeight={700} textAnchor="middle" fill="#fff">
                        {t("treeView.you")}
                      </text>
                    </g>
                  )}
                  {p && detailed && (
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
                      transform={`translate(${NODE_W - 28},${graph?.direction === "ancestors" ? 4 : NODE_H - 28})`}
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
        {t(family ? "treeView.keyboardHelpFamily" : "treeView.keyboardHelp")}
      </p>
    </div>
  );
}
