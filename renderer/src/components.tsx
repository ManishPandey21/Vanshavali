import type { ReactNode } from "react";
import { AbsoluteFill, Audio, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { RenderProps } from "./types";
import { themeOf, type Theme } from "./theme";
import { TITLE_FRAMES } from "./timing";

/** Background, branding footer, optional audio slots and the title card around a chart. */
export function Frame({ props, children }: { props: RenderProps; children: (theme: Theme) => ReactNode }) {
  const theme = themeOf(props.theme);
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const chartOpacity = interpolate(frame, [TITLE_FRAMES - 10, TITLE_FRAMES + 5], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const fadeOut = interpolate(frame, [durationInFrames - 12, durationInFrames - 1], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ backgroundColor: theme.background, color: theme.ink, fontFamily: theme.fontBody }}>
      {props.music?.src ? <Audio src={props.music.src} volume={props.music.volume ?? 0.4} /> : null}
      {props.narration?.src ? <Audio src={props.narration.src} volume={props.narration.volume ?? 1} /> : null}
      <AbsoluteFill style={{ opacity: Math.min(chartOpacity, fadeOut) }}>{children(theme)}</AbsoluteFill>
      <TitleCard props={props} theme={theme} />
      <div
        style={{
          position: "absolute",
          bottom: 14,
          left: 24,
          right: 24,
          display: "flex",
          justifyContent: "space-between",
          fontSize: 16,
          color: theme.muted,
          opacity: chartOpacity * fadeOut,
        }}
      >
        <span>{props.branding.footer ?? props.branding.treeName ?? ""}</span>
        <span>Vanshavali · {props.generatedAt.slice(0, 10)}</span>
      </div>
    </AbsoluteFill>
  );
}

function TitleCard({ props, theme }: { props: RenderProps; theme: Theme }) {
  const frame = useCurrentFrame();
  if (frame > TITLE_FRAMES + 5) return null;
  const opacity = interpolate(frame, [0, 12, TITLE_FRAMES - 10, TITLE_FRAMES], [0, 1, 1, 0], { extrapolateRight: "clamp" });
  const rise = interpolate(frame, [0, 18], [24, 0], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", opacity, backgroundColor: theme.background }}>
      <div style={{ transform: `translateY(${rise}px)`, textAlign: "center", padding: 60 }}>
        <div style={{ width: 80, height: 4, background: theme.accent, margin: "0 auto 28px" }} />
        <h1 style={{ fontFamily: theme.fontDisplay, fontSize: 64, margin: 0, color: theme.ink }}>{props.branding.title}</h1>
        {props.branding.subtitle ? <p style={{ fontSize: 30, color: theme.muted, marginTop: 18 }}>{props.branding.subtitle}</p> : null}
        {props.branding.treeName ? <p style={{ fontSize: 22, color: theme.muted, marginTop: 8 }}>{props.branding.treeName}</p> : null}
      </div>
    </AbsoluteFill>
  );
}

type Corner = "top-right" | "top-left" | "bottom-right";

const CORNERS: Record<Corner, Record<string, number>> = {
  "top-right": { top: 24, right: 28 },
  "top-left": { top: 24, left: 28 },
  "bottom-right": { bottom: 48, right: 28 },
};

export function Legend({ theme, entries, colors, corner = "top-right" }: { theme: Theme; entries: { key: string; label: string }[]; colors: (key: string) => string; corner?: Corner }) {
  if (!entries.length) return null;
  return (
    <div style={{ position: "absolute", ...CORNERS[corner], background: theme.surface, border: `1px solid ${theme.line}`, borderRadius: 10, padding: "10px 14px", fontSize: 18, maxWidth: 320 }}>
      {entries.slice(0, 10).map((e) => (
        <div key={e.key} style={{ display: "flex", alignItems: "center", gap: 8, margin: "3px 0" }}>
          <span style={{ width: 14, height: 14, borderRadius: 3, background: colors(e.key), display: "inline-block", flex: "none" }} />
          <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{e.label}</span>
        </div>
      ))}
    </div>
  );
}

export function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}
