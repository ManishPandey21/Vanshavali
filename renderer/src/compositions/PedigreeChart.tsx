import { interpolate, useCurrentFrame } from "remotion";
import { Frame, Legend, truncate } from "../components";
import { colorFor } from "../theme";
import { FPS, TITLE_FRAMES } from "../timing";
import type { PedigreePayload, RenderProps, SlotNode } from "../types";

const W = 1280;
const H = 720;

/** Animated pedigree: the root on the left, each generation's boxes and connectors drawn in turn. */
export function PedigreeChart(props: RenderProps) {
  const data = props.data as PedigreePayload;
  const frame = useCurrentFrame();
  const gens = Math.min(Math.max(1, data.generations), 5); // more than 5 columns do not fit a 720p frame
  const bySlot = new Map<number, SlotNode>(data.nodes.map((n) => [n.slot, n]));
  const missing = new Set(data.missingSlots);
  const keys = data.legend.map((l) => l.key);
  const colW = (W - 120) / (gens + 1);
  const boxW = Math.min(220, colW - 24);
  const top = 80;
  const usable = H - top - 60;
  const pos = (slot: number) => {
    const g = Math.floor(Math.log2(slot));
    const idx = slot - 2 ** g;
    return { x: 40 + g * colW, y: top + ((idx + 0.5) * usable) / 2 ** g, g };
  };
  const perGen = 1.2 * FPS;
  return (
    <Frame props={props}>
      {(theme) => {
        const col = (k: string) => colorFor(theme, keys, k);
        const items = [];
        for (let g = 0; g <= gens; g++) {
          const start = TITLE_FRAMES + g * perGen * 0.8;
          const t = interpolate(frame, [start, start + perGen * 0.7], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          if (t <= 0) continue;
          for (let i = 0; i < 2 ** g; i++) {
            const slot = 2 ** g + i;
            const node = bySlot.get(slot);
            if (!node && !missing.has(slot)) continue;
            const { x, y } = pos(slot);
            const h = g <= 2 ? 64 : g === 3 ? 42 : 24;
            const child = slot > 1 ? pos(Math.floor(slot / 2)) : null;
            if (child) {
              const sx = child.x + boxW;
              const len = Math.abs(x - sx) + Math.abs(y - child.y);
              items.push(
                <path
                  key={`l${slot}`}
                  d={`M ${sx} ${child.y} H ${(sx + x) / 2} V ${y} H ${x}`}
                  fill="none"
                  stroke={theme.line}
                  strokeWidth={2}
                  strokeDasharray={len}
                  strokeDashoffset={len * (1 - t)}
                />,
              );
            }
            const p = node?.person;
            const fill = node?.hidden ? theme.hidden : p ? theme.surface : theme.missing;
            items.push(
              <g key={slot} opacity={t} transform={`translate(${x} ${y - h / 2})`}>
                <rect width={boxW} height={h} rx={8} fill={fill} stroke={p ? col(p.colorKey ?? "") : theme.line} strokeWidth={p ? 3 : 1.5} strokeDasharray={!node ? "5 4" : undefined} />
                {p ? <rect width={6} height={h} rx={3} fill={col(p.colorKey ?? "")} /> : null}
                <text x={14} y={h <= 24 ? h / 2 + 5 : h > 50 ? 24 : 18} fontSize={h <= 24 ? 13 : h > 50 ? 17 : 14} fontWeight={600} fill={theme.ink}>
                  {truncate(node?.hidden ? "Private" : p ? p.name : "Not recorded", h <= 24 ? 24 : 22)}
                </text>
                {p && h > 24 ? (
                  <text x={14} y={h > 50 ? 44 : 36} fontSize={h > 50 ? 14 : 11} fill={theme.muted}>
                    {truncate([p.years, p.birthPlace].filter(Boolean).join(" · "), 28)}
                  </text>
                ) : null}
              </g>,
            );
          }
        }
        return (
          <>
            <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={props.branding.title}>
              {items}
            </svg>
            <Legend theme={theme} entries={data.legend} colors={col} corner="bottom-right" />
          </>
        );
      }}
    </Frame>
  );
}
