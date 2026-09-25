/**
 * Layered ("generation rows") layout for ancestor / descendant graphs from the API.
 *
 * The API returns a DAG (people can appear via several lines — pedigree collapse). We derive a
 * spanning tree from the root by BFS (first discovery wins) for positioning, then draw every API
 * edge. Subtree widths are computed bottom-up and each node is centred over its layout children
 * (a simplified tidy-tree). Nothing is fetched or invented here: only nodes the API returned are laid out.
 */
import type { GraphEdge, GraphNode, GraphOut } from "../api/types";

export const NODE_W = 184;
export const NODE_H = 68;
export const H_GAP = 24;
export const ROW_H = 132;

export interface LaidOutNode {
  node: GraphNode;
  x: number; // left
  y: number; // top
  children: string[]; // layout children (next generation away from root)
  hiddenDescendants: number; // count collapsed away
  collapsed: boolean;
}

export interface Layout {
  nodes: Map<string, LaidOutNode>;
  edges: GraphEdge[];
  couples: { a: string; b: string; type: string }[];
  width: number;
  height: number;
  rows: Map<number, string[]>; // generation -> node ids ordered left→right
  rootId: string;
}

function sexRank(n: GraphNode | undefined): number {
  const s = n?.person?.sex_at_birth;
  // presentation only: a stable order so parents don't swap sides between renders
  return s === "male" ? 0 : s === "female" ? 1 : n?.hidden ? 3 : 2;
}

export function layoutGraph(graph: GraphOut, collapsed: ReadonlySet<string> = new Set()): Layout {
  const direction = graph.direction === "ancestors" ? "ancestors" : "descendants";
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const rootId = String(graph.root_id);
  // adjacency away from the root
  const next = new Map<string, string[]>();
  for (const e of graph.edges) {
    const from = direction === "ancestors" ? e.target : e.source;
    const to = direction === "ancestors" ? e.source : e.target;
    if (!byId.has(from) || !byId.has(to)) continue;
    const list = next.get(from) ?? [];
    if (!list.includes(to)) list.push(to);
    next.set(from, list);
  }
  for (const [k, list] of next) next.set(k, [...list].sort((a, b) => sexRank(byId.get(a)) - sexRank(byId.get(b)) || (byId.get(a)?.person?.birth_year ?? 9999) - (byId.get(b)?.person?.birth_year ?? 9999)));

  // BFS spanning tree
  const layoutChildren = new Map<string, string[]>();
  const seen = new Set<string>([rootId]);
  const queue = [rootId];
  while (queue.length) {
    const cur = queue.shift()!;
    const kids: string[] = [];
    for (const n of next.get(cur) ?? []) {
      if (seen.has(n)) continue;
      seen.add(n);
      kids.push(n);
      queue.push(n);
    }
    layoutChildren.set(cur, kids);
  }

  // In-law partners (node.partner) are not in the lineage; draw each beside the spouse it is
  // united with, as one couple unit whose children are centred beneath the pair.
  const partnersOf = new Map<string, string[]>();
  const attached = new Set<string>();
  for (const u of graph.unions ?? []) {
    const a = String(u.a);
    const b = String(u.b);
    const na = byId.get(a);
    const nb = byId.get(b);
    if (!na || !nb) continue;
    const [member, partner] = nb.partner && !na.partner ? [a, b] : na.partner && !nb.partner ? [b, a] : [null, null];
    if (!member || !partner || attached.has(partner) || !seen.has(member)) continue;
    attached.add(partner);
    partnersOf.set(member, [...(partnersOf.get(member) ?? []), partner]);
  }
  const unitW = (id: string) => {
    const k = partnersOf.get(id)?.length ?? 0;
    return NODE_W * (1 + k) + H_GAP * k;
  };

  const countBelow = (id: string): number => (layoutChildren.get(id) ?? []).reduce((s, c) => s + 1 + countBelow(c), 0);

  // subtree widths (collapsed nodes count as leaves)
  const width = new Map<string, number>();
  const measure = (id: string): number => {
    const kids = collapsed.has(id) ? [] : layoutChildren.get(id) ?? [];
    const own = unitW(id);
    const w = kids.length ? Math.max(own, kids.reduce((s, k) => s + measure(k), 0) + H_GAP * (kids.length - 1)) : own;
    width.set(id, w);
    return w;
  };
  measure(rootId);

  const out = new Map<string, LaidOutNode>();
  const rows = new Map<number, string[]>();
  const place = (id: string, left: number, depth: number) => {
    const w = width.get(id) ?? NODE_W;
    const isCollapsed = collapsed.has(id);
    const kids = isCollapsed ? [] : layoutChildren.get(id) ?? [];
    const node = byId.get(id)!;
    const x = left + (w - unitW(id)) / 2;
    out.set(id, {
      node,
      x,
      y: depth,
      children: layoutChildren.get(id) ?? [],
      collapsed: isCollapsed,
      hiddenDescendants: isCollapsed ? countBelow(id) : 0,
    });
    const gen = node.generation;
    rows.set(gen, [...(rows.get(gen) ?? []), id]);
    (partnersOf.get(id) ?? []).forEach((pid, i) => {
      out.set(pid, { node: byId.get(pid)!, x: x + (NODE_W + H_GAP) * (i + 1), y: depth, children: [], collapsed: false, hiddenDescendants: 0 });
      rows.set(gen, [...(rows.get(gen) ?? []), pid]);
    });
    let cursor = left;
    for (const k of kids) {
      place(k, cursor, depth + 1);
      cursor += (width.get(k) ?? NODE_W) + H_GAP;
    }
  };
  place(rootId, 0, 0);

  const maxDepth = Math.max(0, ...[...out.values()].map((n) => n.y));
  // ancestors grow upward: root at the bottom
  for (const n of out.values()) {
    const level = direction === "ancestors" ? maxDepth - n.y : n.y;
    n.y = level * ROW_H;
  }
  for (const [g, ids] of rows) rows.set(g, [...ids].sort((a, b) => out.get(a)!.x - out.get(b)!.x));

  const edges = graph.edges.filter((e) => out.has(e.source) && out.has(e.target));
  const couples = (graph.unions ?? [])
    .map((u) => ({ a: String(u.a), b: String(u.b), type: String(u.type ?? "spouse") }))
    .filter((c) => out.has(c.a) && out.has(c.b) && out.get(c.a)!.y === out.get(c.b)!.y);

  return {
    nodes: out,
    edges,
    couples,
    width: Math.max(width.get(rootId) ?? NODE_W, ...[...out.values()].map((n) => n.x + NODE_W)),
    height: (maxDepth + 1) * ROW_H - (ROW_H - NODE_H),
    rows,
    rootId,
  };
}

/** Keyboard navigation target: nearest node in the adjacent row (Up/Down) or the neighbour in the row (Left/Right). */
export function neighbour(layout: Layout, fromId: string, key: "ArrowUp" | "ArrowDown" | "ArrowLeft" | "ArrowRight"): string | null {
  const from = layout.nodes.get(fromId);
  if (!from) return null;
  const gen = from.node.generation;
  const row = layout.rows.get(gen) ?? [];
  if (key === "ArrowLeft" || key === "ArrowRight") {
    const i = row.indexOf(fromId);
    const j = key === "ArrowLeft" ? i - 1 : i + 1;
    return row[j] ?? null;
  }
  // Up = visually above (smaller y). Ancestor rows have more negative generations.
  const targetY = key === "ArrowUp" ? from.y - ROW_H : from.y + ROW_H;
  const candidates = [...layout.nodes.values()].filter((n) => n.y === targetY);
  if (!candidates.length) return null;
  const cx = from.x;
  candidates.sort((a, b) => Math.abs(a.x - cx) - Math.abs(b.x - cx));
  return candidates[0].node.id;
}
