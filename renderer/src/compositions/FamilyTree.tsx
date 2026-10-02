import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { Frame, truncate } from "../components";
import { FPS, OUTRO_SECONDS, TITLE_FRAMES } from "../timing";
import type { FamilyTreePayload, RenderProps, TreeNode } from "../types";

const W = 1280;
const H = 720;

interface Placed {
  node: TreeNode;
  x: number;
  y: number;
  order: number;
}

/** Tidy layout: a node and its partners form a unit; a unit is as wide as its descendants. */
export function layoutTree(data: FamilyTreePayload): Placed[] {
  const byId = new Map(data.nodes.map((n) => [n.id, n]));
  const up = data.direction === "ancestors";
  const next = new Map<string, string[]>();
  for (const e of data.edges) {
    const from = up ? e.target : e.source;
    const to = up ? e.source : e.target;
    next.set(from, [...(next.get(from) ?? []), to]);
  }
  const partners = new Map<string, string[]>();
  for (const u of data.unions) {
    for (const [a, b] of [[u.a, u.b], [u.b, u.a]]) {
      if (byId.get(b)?.partner) partners.set(a, [...(partners.get(a) ?? []), b]);
    }
  }
  const seen = new Set<string>();
  const widths = new Map<string, number>();
  const kids = new Map<string, string[]>();
  const width = (id: string): number => {
    seen.add(id);
    const unit = [id, ...(partners.get(id) ?? [])];
    unit.forEach((u) => seen.add(u));
    const children = unit.flatMap((u) => next.get(u) ?? []).filter((c, i, arr) => byId.has(c) && arr.indexOf(c) === i && !seen.has(c));
    children.forEach((c) => seen.add(c));
    kids.set(id, children);
    const w = Math.max(unit.length, children.reduce((s, c) => s + width(c), 0));
    widths.set(id, w);
    return w;
  };
  const total = width(data.rootId);
  const gens = data.nodes.map((n) => n.generation);
  const minG = Math.min(...gens, 0);
  const maxG = Math.max(...gens, 0);
  const rows = maxG - minG + 1;
  const unitW = Math.min(170, (W - 80) / Math.max(1, total));
  const offset = (W - total * unitW) / 2;
  const rowH = Math.min(140, (H - 140) / Math.max(1, rows));
  const out: Placed[] = [];
  let order = 0;
  const queue: [string, number][] = [[data.rootId, offset]];
  while (queue.length) {
    const [id, left] = queue.shift()!;
    const n = byId.get(id);
    if (!n) continue;
    const w = widths.get(id) ?? 1;
    const unit = [id, ...(partners.get(id) ?? [])];
    const unitLeft = left + ((w - unit.length) * unitW) / 2;
    unit.forEach((u, i) => {
      const un = byId.get(u);
      if (un) out.push({ node: un, x: unitLeft + i * unitW, y: 70 + (un.generation - minG) * rowH, order: order++ });
    });
    let cursor = left;
    for (const c of kids.get(id) ?? []) {
      queue.push([c, cursor]);
      cursor += (widths.get(c) ?? 1) * unitW;
    }
  }
  return out;
}

export function cardWidth(placed: Placed[]): number {
  const xs = [...new Set(placed.map((p) => p.x))].sort((a, b) => a - b);
  const gap = xs.length > 1 ? Math.min(...xs.slice(1).map((x, i) => x - xs[i])) : 170;
  return Math.max(60, Math.min(160, gap - 10));
}

export function FamilyTree(props: RenderProps) {
  const data = props.data as FamilyTreePayload;
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const placed = layoutTree(data);
  const at = new Map(placed.map((p) => [p.node.id, p]));
  const span = durationInFrames - TITLE_FRAMES - OUTRO_SECONDS * FPS - 20;
  const step = span / Math.max(1, placed.length);
  const cardW = cardWidth(placed) + 10;
  return (
    <Frame props={props}>
      {(theme) => (
        <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={props.branding.title}>
          {data.edges.map((e) => {
            const a = at.get(e.source);
            const b = at.get(e.target);
            if (!a || !b) return null;
            const t = interpolate(frame, [TITLE_FRAMES + Math.max(a.order, b.order) * step, TITLE_FRAMES + Math.max(a.order, b.order) * step + 12], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
            const x1 = a.x + cardW / 2;
            const x2 = b.x + cardW / 2;
            const y1 = a.y + 50;
            const y2 = b.y;
            const midY = (y1 + y2) / 2;
            return <path key={`${e.source}-${e.target}`} d={`M ${x1} ${y1} V ${midY} H ${x2} V ${y2}`} fill="none" stroke={theme.line} strokeWidth={2} opacity={t} />;
          })}
          {data.unions.map((u) => {
            const a = at.get(u.a);
            const b = at.get(u.b);
            if (!a || !b) return null;
            const t = interpolate(frame, [TITLE_FRAMES + Math.max(a.order, b.order) * step, TITLE_FRAMES + Math.max(a.order, b.order) * step + 12], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
            const [l, r] = a.x < b.x ? [a, b] : [b, a];
            return <line key={`u-${u.a}-${u.b}`} x1={l.x + cardW - 10} x2={r.x} y1={l.y + 25} y2={r.y + 25} stroke={theme.accent} strokeWidth={2} opacity={t} />;
          })}
          {placed.map((p) => {
            const start = TITLE_FRAMES + p.order * step;
            const t = interpolate(frame, [start, start + 12], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
            const isRoot = p.node.id === data.rootId;
            const name = p.node.hidden ? "Private" : p.node.person?.name ?? "";
            return (
              <g key={p.node.id} opacity={t} transform={`translate(${p.x} ${p.y + (1 - t) * 12})`}>
                <rect width={cardW - 10} height={50} rx={8} fill={p.node.hidden ? theme.hidden : theme.surface} stroke={isRoot ? theme.accent : theme.line} strokeWidth={isRoot ? 3 : 1.5} />
                <text x={8} y={21} fontSize={cardW < 110 ? 11 : 14} fontWeight={600} fill={theme.ink}>
                  {truncate(name, cardW < 110 ? 12 : 18)}
                </text>
                <text x={8} y={39} fontSize={11} fill={theme.muted}>
                  {p.node.person?.years ?? ""}
                </text>
              </g>
            );
          })}
        </svg>
      )}
    </Frame>
  );
}
