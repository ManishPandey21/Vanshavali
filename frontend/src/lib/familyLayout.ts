/**
 * Layout for the complete family graph (ADR-0034): several families joined by marriages, ancestors
 * and descendants of the same person, and disconnected groups side by side.
 *
 * The server decides who is in the graph and on which row (`generation`); nothing is fetched,
 * inferred or joined here. This file only chooses horizontal positions:
 *
 * 1. People are grouped into *blocks*: a person with their partners on the same row. A block is
 *    rigid, so a couple is always side by side.
 * 2. Blocks are ordered by a walk down from each founder (block, then each child's block), so
 *    siblings stay together under their parents.
 * 3. A few relaxation sweeps pull each block under its parents and over its children without ever
 *    changing the order or letting two cards overlap.
 * 4. Each connected group is laid out on its own and the groups are packed onto shelves. No line is
 *    ever drawn between two groups.
 */
import type { FamilyGraphEdge, FamilyGraphLink, FamilyGraphNode } from "../api/types";
import { H_GAP, NODE_H, NODE_W, ROW_H, type LaidOutNode, type Layout } from "./treeLayout";

const STEP = NODE_W + H_GAP;
const GROUP_GAP_X = 96;
const GROUP_GAP_Y = 112;
const SWEEPS = 6;

export interface FamilyGraphData {
  nodes: readonly FamilyGraphNode[];
  edges: readonly FamilyGraphEdge[];
  links: readonly FamilyGraphLink[];
  rootId?: string | null;
}

interface Block {
  ids: string[];
  gen: number;
  x: number;
}

function byAgeThenId(a: FamilyGraphNode, b: FamilyGraphNode) {
  return (a.person?.birth_year ?? 9999) - (b.person?.birth_year ?? 9999) || a.id.localeCompare(b.id);
}

function layoutGroup(
  nodes: FamilyGraphNode[],
  edges: readonly FamilyGraphEdge[],
  links: readonly FamilyGraphLink[],
): { pos: Map<string, { x: number; y: number }>; width: number; height: number } {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const children = new Map<string, string[]>();
  const parents = new Map<string, string[]>();
  for (const e of edges) {
    if (!byId.has(e.source) || !byId.has(e.target)) continue;
    children.set(e.source, [...(children.get(e.source) ?? []), e.target]);
    parents.set(e.target, [...(parents.get(e.target) ?? []), e.source]);
  }
  const partners = new Map<string, string[]>();
  const siblings = new Map<string, string[]>();
  for (const l of links) {
    if (!byId.has(l.a) || !byId.has(l.b) || l.kind === "other") continue;
    const m = l.kind === "union" ? partners : siblings;
    m.set(l.a, [...(m.get(l.a) ?? []), l.b]);
    m.set(l.b, [...(m.get(l.b) ?? []), l.a]);
  }
  const gen = (id: string) => byId.get(id)!.generation;
  const sorted = (ids: readonly string[]) => [...new Set(ids)].sort((a, b) => byAgeThenId(byId.get(a)!, byId.get(b)!));

  // 1 + 2: blocks, in walk order per row
  const rows = new Map<number, Block[]>();
  const blockOf = new Map<string, Block>();
  const startBlock = (first: string): Block => {
    const ids = [first];
    const block: Block = { ids, gen: gen(first), x: 0 };
    blockOf.set(first, block);
    for (let i = 0; i < ids.length; i++) {
      for (const p of sorted(partners.get(ids[i]) ?? [])) {
        if (blockOf.has(p) || gen(p) !== block.gen) continue;
        blockOf.set(p, block);
        ids.push(p);
      }
    }
    rows.set(block.gen, [...(rows.get(block.gen) ?? []), block]);
    return block;
  };
  const walk = (start: string) => {
    // explicit stack: a family can be many generations deep and very wide
    const stack = [start];
    while (stack.length) {
      const id = stack.pop()!;
      if (blockOf.has(id)) continue;
      const block = startBlock(id);
      const next: string[] = [];
      for (const m of block.ids) next.push(...sorted(siblings.get(m) ?? []));
      const kids: string[] = [];
      for (const m of block.ids) kids.push(...(children.get(m) ?? []));
      next.push(...sorted(kids));
      for (let i = next.length - 1; i >= 0; i--) if (!blockOf.has(next[i])) stack.push(next[i]);
    }
  };
  const size = new Map<string, number>();
  const founders = nodes.filter((n) => !(parents.get(n.id) ?? []).length);
  const descendants = (id: string): number => {
    // cheap proxy for "main line first": direct children + grandchildren
    if (size.has(id)) return size.get(id)!;
    const kids = children.get(id) ?? [];
    const v = kids.length + kids.reduce((s, k) => s + (children.get(k) ?? []).length, 0);
    size.set(id, v);
    return v;
  };
  founders.sort((a, b) => a.generation - b.generation || descendants(b.id) - descendants(a.id) || byAgeThenId(a, b));
  for (const f of founders) walk(f.id);
  for (const n of [...nodes].sort((a, b) => a.generation - b.generation || byAgeThenId(a, b))) walk(n.id); // cycles

  // 3: horizontal positions
  const gens = [...rows.keys()].sort((a, b) => a - b);
  const width = (b: Block) => b.ids.length * STEP - H_GAP;
  for (const g of gens) {
    let x = 0;
    for (const b of rows.get(g)!) {
      b.x = x;
      x += width(b) + H_GAP;
    }
  }
  const centre = (id: string) => {
    const b = blockOf.get(id)!;
    return b.x + b.ids.indexOf(id) * STEP + NODE_W / 2;
  };
  const settle = (row: Block[], wanted: (number | null)[]) => {
    // keep the order, never overlap: average of a left-packed and a right-packed pass
    const want = wanted.map((w, i) => w ?? row[i].x);
    const left: number[] = [];
    for (let i = 0; i < row.length; i++) left[i] = i ? Math.max(want[i], left[i - 1] + width(row[i - 1]) + H_GAP) : want[i];
    const right: number[] = [];
    for (let i = row.length - 1; i >= 0; i--)
      right[i] = i < row.length - 1 ? Math.min(want[i], right[i + 1] - width(row[i]) - H_GAP) : want[i];
    for (let i = 0; i < row.length; i++) row[i].x = (left[i] + right[i]) / 2;
    for (let i = 1; i < row.length; i++) row[i].x = Math.max(row[i].x, row[i - 1].x + width(row[i - 1]) + H_GAP);
  };
  const pull = (b: Block, towards: Map<string, string[]>): number | null => {
    let sum = 0;
    let n = 0;
    b.ids.forEach((id, i) => {
      for (const other of towards.get(id) ?? []) {
        if (!blockOf.has(other)) continue;
        sum += centre(other) - i * STEP - NODE_W / 2;
        n += 1;
      }
    });
    return n ? sum / n : null;
  };
  for (let s = 0; s < SWEEPS; s++) {
    for (const g of [...gens].reverse()) settle(rows.get(g)!, rows.get(g)!.map((b) => pull(b, children)));
    for (const g of gens) settle(rows.get(g)!, rows.get(g)!.map((b) => pull(b, parents)));
  }

  let minX = Infinity;
  let maxX = -Infinity;
  for (const g of gens)
    for (const b of rows.get(g)!) {
      minX = Math.min(minX, b.x);
      maxX = Math.max(maxX, b.x + width(b));
    }
  const pos = new Map<string, { x: number; y: number }>();
  const top = gens[0] ?? 0;
  for (const g of gens)
    for (const b of rows.get(g)!) b.ids.forEach((id, i) => pos.set(id, { x: b.x - minX + i * STEP, y: (g - top) * ROW_H }));
  return { pos, width: Math.max(NODE_W, maxX - minX), height: (gens.length ? gens[gens.length - 1] - top : 0) * ROW_H + NODE_H };
}

export function layoutFamily(data: FamilyGraphData): Layout {
  const groups = new Map<number, FamilyGraphNode[]>();
  for (const n of data.nodes) groups.set(n.component, [...(groups.get(n.component) ?? []), n]);
  const groupOf = new Map(data.nodes.map((n) => [n.id, n.component]));
  const edgesBy = new Map<number, FamilyGraphEdge[]>();
  for (const e of data.edges) {
    const g = groupOf.get(e.source);
    if (g === undefined || g !== groupOf.get(e.target)) continue; // never across groups
    edgesBy.set(g, [...(edgesBy.get(g) ?? []), e]);
  }
  const linksBy = new Map<number, FamilyGraphLink[]>();
  for (const l of data.links) {
    const g = groupOf.get(l.a);
    if (g === undefined || g !== groupOf.get(l.b)) continue;
    linksBy.set(g, [...(linksBy.get(g) ?? []), l]);
  }

  const out = new Map<string, LaidOutNode>();
  const boxes: NonNullable<Layout["groups"]> = [];
  const order = [...groups.keys()].sort((a, b) => a - b);
  const laid = order.map((g) => ({ g, ...layoutGroup(groups.get(g)!, edgesBy.get(g) ?? [], linksBy.get(g) ?? []) }));
  // 4: shelves as wide as the largest group (at least a few cards), so loners do not form a column
  const shelfWidth = Math.max(STEP * 5, ...laid.map((l) => l.width));
  let x = 0;
  let y = 0;
  let shelfHeight = 0;
  let totalWidth = 0;
  for (const l of laid) {
    if (x > 0 && x + l.width > shelfWidth) {
      x = 0;
      y += shelfHeight + GROUP_GAP_Y;
      shelfHeight = 0;
    }
    for (const n of groups.get(l.g)!) {
      const p = l.pos.get(n.id)!;
      out.set(n.id, { node: n, x: x + p.x, y: y + p.y, children: [], hiddenDescendants: 0, collapsed: false });
    }
    boxes.push({ index: l.g, x, y, width: l.width, height: l.height, people: groups.get(l.g)!.filter((n) => n.person).length });
    totalWidth = Math.max(totalWidth, x + l.width);
    shelfHeight = Math.max(shelfHeight, l.height);
    x += l.width + GROUP_GAP_X;
  }

  const rows = new Map<number, string[]>();
  for (const n of out.values()) rows.set(n.y, [...(rows.get(n.y) ?? []), n.node.id]);
  for (const [k, ids] of rows) rows.set(k, ids.sort((a, b) => out.get(a)!.x - out.get(b)!.x));

  const has = (id: string) => out.has(id);
  const rootId = data.rootId && out.has(data.rootId) ? data.rootId : (data.nodes[0]?.id ?? "");
  return {
    nodes: out,
    edges: data.edges.filter((e) => has(e.source) && has(e.target) && groupOf.get(e.source) === groupOf.get(e.target)),
    couples: data.links
      .filter((l) => l.kind === "union" && has(l.a) && has(l.b) && groupOf.get(l.a) === groupOf.get(l.b))
      .map((l) => ({ a: l.a, b: l.b, type: l.type })),
    links: data.links
      .filter((l) => l.kind !== "union" && has(l.a) && has(l.b) && groupOf.get(l.a) === groupOf.get(l.b))
      .map((l) => ({ a: l.a, b: l.b, kind: l.kind })),
    groups: boxes,
    width: Math.max(NODE_W, totalWidth),
    height: y + shelfHeight,
    rows,
    rootId,
    noRootHighlight: !(data.rootId && out.has(data.rootId)),
  };
}
