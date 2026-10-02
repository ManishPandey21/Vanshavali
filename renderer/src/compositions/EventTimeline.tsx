import { Img, interpolate, useCurrentFrame } from "remotion";
import { Frame, truncate } from "../components";
import { FPS, TITLE_FRAMES } from "../timing";
import type { EventTimelinePayload, RenderProps } from "../types";

const W = 1280;
const PER_EVENT = 4 * FPS;

/** Slideshow of a person's life events: photo (slow zoom), date, place, relatives. */
export function EventTimeline(props: RenderProps) {
  const data = props.data as EventTimelinePayload;
  const frame = useCurrentFrame();
  const local = frame - TITLE_FRAMES;
  const idx = Math.max(0, Math.min(data.events.length - 1, Math.floor(local / PER_EVENT)));
  const t = local - idx * PER_EVENT;
  const ev = data.events[idx];
  const enter = interpolate(t, [0, 14], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const exit = idx < data.events.length - 1 ? interpolate(t, [PER_EVENT - 10, PER_EVENT], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 1;
  const zoom = interpolate(t, [0, PER_EVENT], [1, 1.08]);
  const photo = ev?.photos[0];
  return (
    <Frame props={props}>
      {(theme) => (
        <>
          <div style={{ position: "absolute", top: 26, left: 40, fontFamily: theme.fontDisplay, fontSize: 30, color: theme.ink }}>
            {data.person.name}
            {data.person.years ? <span style={{ color: theme.muted, fontSize: 22, marginLeft: 12 }}>{data.person.years}</span> : null}
          </div>
          {ev ? (
            <div style={{ position: "absolute", top: 90, left: 40, right: 40, bottom: 110, display: "flex", gap: 36, opacity: enter * exit, transform: `translateX(${(1 - enter) * 40}px)` }}>
              {photo ? (
                <div style={{ flex: "0 0 52%", overflow: "hidden", borderRadius: 14, background: theme.surface, border: `1px solid ${theme.line}` }}>
                  <Img src={photo.src} style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${zoom})` }} />
                </div>
              ) : null}
              <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center" }}>
                <div style={{ color: theme.accent, fontSize: 28, fontWeight: 700 }}>{ev.dateDisplay ?? (ev.year ? String(ev.year) : "")}</div>
                <h2 style={{ fontFamily: theme.fontDisplay, fontSize: 48, margin: "8px 0 12px", color: theme.ink }}>{truncate(ev.label, 60)}</h2>
                {ev.place ? <div style={{ fontSize: 24, color: theme.muted }}>📍 {truncate(ev.place, 60)}</div> : null}
                {ev.description ? <p style={{ fontSize: 22, lineHeight: 1.4, color: theme.ink }}>{truncate(ev.description, 220)}</p> : null}
                {ev.relatives.length ? <div style={{ fontSize: 20, color: theme.muted }}>{truncate(ev.relatives.join(", "), 90)}</div> : null}
                {photo?.caption ? <div style={{ fontSize: 18, color: theme.muted, fontStyle: "italic", marginTop: 12 }}>{truncate(photo.caption, 90)}</div> : null}
              </div>
            </div>
          ) : null}
          <svg width={W} height={60} style={{ position: "absolute", bottom: 46, left: 0 }}>
            <line x1={60} x2={W - 60} y1={30} y2={30} stroke={theme.line} strokeWidth={3} />
            {data.events.map((e, i) => {
              const cx = 60 + (data.events.length === 1 ? 0.5 : i / (data.events.length - 1)) * (W - 120);
              const active = i === idx;
              return (
                <g key={i}>
                  <circle cx={cx} cy={30} r={active ? 10 : 6} fill={i <= idx ? theme.accent : theme.surface} stroke={theme.accent} strokeWidth={2} />
                  {e.year && (active || data.events.length <= 12) ? (
                    <text x={cx} y={56} fontSize={13} textAnchor="middle" fill={theme.muted}>
                      {e.year}
                    </text>
                  ) : null}
                </g>
              );
            })}
          </svg>
        </>
      )}
    </Frame>
  );
}
