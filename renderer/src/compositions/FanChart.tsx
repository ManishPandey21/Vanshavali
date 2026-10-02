import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Frame, Legend, truncate } from "../components";
import { colorFor } from "../theme";
import { FPS, TITLE_FRAMES } from "../timing";
import type { FanPayload, RenderProps, SlotNode } from "../types";

const W = 1280;
const H = 720;

function arcPath(cx: number, cy: number, r0: number, r1: number, a0: number, a1: number): string {
  const p = (r: number, a: number) => `${cx + r * Math.cos(a)} ${cy + r * Math.sin(a)}`;
  const large = a1 - a0 > Math.PI ? 1 : 0;
  return `M ${p(r1, a0)} A ${r1} ${r1} 0 ${large} 1 ${p(r1, a1)} L ${p(r0, a1)} A ${r0} ${r0} 0 ${large} 0 ${p(r0, a0)} Z`;
}

/** Animated fan chart: the root at the centre, each generation's ring sweeping in, outward. */
export function FanChart(props: RenderProps) {
  const data = props.data as FanPayload;
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const gens = Math.max(1, data.generations);
  const cx = W / 2;
  const cy = H - 70;
  const rRoot = 76;
  const ring = Math.min(130, (H - 130 - rRoot) / gens);
  const bySlot = new Map<number, SlotNode>(data.nodes.map((n) => [n.slot, n]));
  const missing = new Set(data.missingSlots);
  const keys = data.legend.map((l) => l.key);
  const perGen = 1.2 * FPS;
  return (
    <Frame props={props}>
      {(theme) => {
        const col = (k: string) => colorFor(theme, keys, k);
        const root = bySlot.get(1);
        const rootIn = spring({ frame: frame - TITLE_FRAMES, fps, config: { damping: 14 } });
        const rings = [];
        for (let g = 1; g <= gens; g++) {
          const start = TITLE_FRAMES + g * perGen * 0.8;
          const sweep = interpolate(frame, [start, start + perGen], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          if (sweep <= 0) continue;
          const count = 2 ** g;
          const span = Math.PI / count;
          const r0 = rRoot + (g - 1) * ring + 4;
          const r1 = r0 + ring - 4;
          for (let i = 0; i < count; i++) {
            const slot = count + i;
            const a0 = Math.PI + i * span;
            const a1 = a0 + span * sweep;
            const node = bySlot.get(slot);
            const isMissing = !node && missing.has(slot);
            if (!node && !isMissing) continue;
            const fill = node?.hidden ? theme.hidden : node?.person ? col(node.person.colorKey ?? "") : theme.missing;
            const mid = (a0 + a0 + span) / 2;
            const rl = (r0 + r1) / 2;
            const tx = cx + rl * Math.cos(mid);
            const ty = cy + rl * Math.sin(mid);
            const deg = (mid * 180) / Math.PI + (g >= 3 ? 0 : 90);
            const label = node?.hidden ? "Private" : node?.person ? node.person.name : isMissing ? "?" : "";
            const fontSize = g <= 2 ? 18 : g === 3 ? 14 : 11;
            rings.push(
              <g key={slot} opacity={sweep}>
                <path
                  d={arcPath(cx, cy, r0, r1, a0, a1)}
                  fill={fill}
                  fillOpacity={node?.person ? 0.85 : 1}
                  stroke={isMissing ? theme.line : theme.background}
                  strokeDasharray={isMissing ? "5 4" : undefined}
                  strokeWidth={2}
                />
                {sweep > 0.9 && label ? (
                  <text
                    x={tx}
                    y={ty}
                    transform={`rotate(${deg > 90 && deg < 270 && g >= 3 ? deg + 180 : deg} ${tx} ${ty})`}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fontSize={fontSize}
                    fill={node?.person ? "#fff" : theme.muted}
                    fontWeight={600}
                  >
                    {truncate(label, g <= 2 ? 22 : g === 3 ? 16 : 12)}
                  </text>
                ) : null}
              </g>,
            );
          }
        }
        return (
          <>
            <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={props.branding.title}>
              {rings}
              <g transform={`translate(${cx} ${cy}) scale(${rootIn})`}>
                <path d={arcPath(0, 0, 0, rRoot, Math.PI, 2 * Math.PI)} fill={theme.accent} />
                <text y={-30} textAnchor="middle" fontSize={15} fontWeight={700} fill="#fff">
                  {truncate(root?.person?.name ?? "", 14)}
                </text>
                <text y={-10} textAnchor="middle" fontSize={13} fill="#fff">
                  {root?.person?.years ?? ""}
                </text>
              </g>
            </svg>
            <Legend theme={theme} entries={data.legend} colors={col} />
          </>
        );
      }}
    </Frame>
  );
}
