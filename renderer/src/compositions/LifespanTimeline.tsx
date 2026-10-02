import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { Frame, Legend, truncate } from "../components";
import { colorFor } from "../theme";
import { FPS, OUTRO_SECONDS, TITLE_FRAMES } from "../timing";
import type { LifespanPayload, RenderProps } from "../types";

const W = 1280;
const H = 720;

/** A time cursor sweeps across the years; each life grows as the cursor passes through it. */
export function LifespanTimeline(props: RenderProps) {
  const data = props.data as LifespanPayload;
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const nowYear = new Date(props.generatedAt).getFullYear() || new Date().getFullYear();
  const lo = Math.floor((data.minYear - 5) / 10) * 10;
  const hi = Math.max(data.maxYear, nowYear) + 2;
  const left = 230;
  const right = W - 40;
  const top = 120;
  const rows = data.rows.slice(0, 40);
  const rowH = Math.min(40, (H - top - 60) / Math.max(1, rows.length));
  const x = (y: number) => left + ((y - lo) / (hi - lo)) * (right - left);
  const end = durationInFrames - OUTRO_SECONDS * FPS;
  const cursor = interpolate(frame, [TITLE_FRAMES, end], [lo, hi], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const keys = data.legend.map((l) => l.key);
  const ticks: number[] = [];
  for (let y = lo; y <= hi; y += hi - lo > 150 ? 25 : 10) ticks.push(y);
  return (
    <Frame props={props}>
      {(theme) => {
        const col = (k: string) => colorFor(theme, keys, k);
        return (
          <>
            <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={props.branding.title}>
              {data.periods
                .filter((p) => p.endYear >= lo && p.startYear <= hi)
                .map((p, i) => (
                  <g key={p.label}>
                    <rect x={x(Math.max(lo, p.startYear))} y={top - 30} width={Math.max(2, x(Math.min(hi, p.endYear)) - x(Math.max(lo, p.startYear)))} height={H - top} fill={theme.accent} opacity={i % 2 ? 0.05 : 0.09} />
                    <text x={x(Math.max(lo, p.startYear)) + 4} y={top - 14} fontSize={13} fill={theme.muted}>
                      {truncate(p.label, 26)}
                    </text>
                  </g>
                ))}
              {ticks.map((t) => (
                <g key={t}>
                  <line x1={x(t)} x2={x(t)} y1={top - 4} y2={H - 50} stroke={theme.line} strokeWidth={1} opacity={0.6} />
                  <text x={x(t)} y={H - 32} fontSize={14} textAnchor="middle" fill={theme.muted}>
                    {t}
                  </text>
                </g>
              ))}
              {rows.map((r, i) => {
                const y = top + i * rowH;
                const stop = r.end ?? nowYear;
                const shown = Math.min(stop, cursor);
                const visible = cursor >= r.start;
                return (
                  <g key={`${r.name}-${i}`} opacity={visible ? 1 : 0.25}>
                    <text x={left - 10} y={y + rowH * 0.7} fontSize={Math.min(15, rowH * 0.7)} textAnchor="end" fill={theme.ink}>
                      {truncate(r.name, 26)}
                    </text>
                    {visible ? (
                      <rect x={x(r.start)} y={y + 3} width={Math.max(2, x(shown) - x(r.start))} height={rowH - 6} rx={4} fill={col(r.colorKey ?? "")} opacity={r.living ? 0.6 : 0.85} />
                    ) : null}
                    {visible && !r.endKnown && !r.living ? <text x={x(shown) + 4} y={y + rowH * 0.7} fontSize={12} fill={theme.muted}>?</text> : null}
                    {r.events
                      .filter((e) => e.year <= cursor)
                      .map((e) => (
                        <circle key={`${e.year}-${e.label}`} cx={x(e.year)} cy={y + rowH / 2} r={Math.min(5, rowH / 3)} fill={theme.surface} stroke={theme.ink} strokeWidth={1.5} />
                      ))}
                  </g>
                );
              })}
              <line x1={x(cursor)} x2={x(cursor)} y1={top - 30} y2={H - 50} stroke={theme.accent} strokeWidth={3} />
              <text x={x(cursor)} y={top - 36} fontSize={22} fontWeight={700} textAnchor="middle" fill={theme.accent}>
                {Math.round(cursor)}
              </text>
            </svg>
            <Legend theme={theme} entries={data.legend} colors={col} corner="top-left" />
          </>
        );
      }}
    </Frame>
  );
}
