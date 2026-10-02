import type { ThemeName } from "./types";

export interface Theme {
  background: string;
  surface: string;
  ink: string;
  muted: string;
  accent: string;
  line: string;
  hidden: string;
  missing: string;
  palette: string[];
  fontDisplay: string;
  fontBody: string;
}

// Palettes are distinguishable in light themes; labels always accompany colour (never colour alone).
const BASE_PALETTE = ["#9a3412", "#1d4ed8", "#047857", "#a16207", "#7e22ce", "#be123c", "#0e7490", "#4d7c0f", "#c2410c", "#334155"];

export const THEMES: Record<ThemeName, Theme> = {
  heritage: {
    background: "#fbf6ec",
    surface: "#ffffff",
    ink: "#1f1a17",
    muted: "#6b5e55",
    accent: "#9f1239",
    line: "#c9b79c",
    hidden: "#d6d3d1",
    missing: "#f5f0e6",
    palette: BASE_PALETTE,
    fontDisplay: "Georgia, 'Noto Serif', 'Noto Serif Devanagari', serif",
    fontBody: "'Noto Sans', 'Noto Sans Devanagari', Arial, sans-serif",
  },
  dusk: {
    background: "#1c1917",
    surface: "#292524",
    ink: "#fafaf9",
    muted: "#d6d3d1",
    accent: "#fbbf24",
    line: "#57534e",
    hidden: "#44403c",
    missing: "#1c1917",
    palette: ["#fb923c", "#60a5fa", "#34d399", "#facc15", "#c084fc", "#fb7185", "#22d3ee", "#a3e635", "#fdba74", "#cbd5e1"],
    fontDisplay: "Georgia, 'Noto Serif', 'Noto Serif Devanagari', serif",
    fontBody: "'Noto Sans', 'Noto Sans Devanagari', Arial, sans-serif",
  },
  minimal: {
    background: "#ffffff",
    surface: "#f8fafc",
    ink: "#0f172a",
    muted: "#475569",
    accent: "#0f172a",
    line: "#cbd5e1",
    hidden: "#e2e8f0",
    missing: "#ffffff",
    palette: BASE_PALETTE,
    fontDisplay: "'Noto Sans', 'Noto Sans Devanagari', Arial, sans-serif",
    fontBody: "'Noto Sans', 'Noto Sans Devanagari', Arial, sans-serif",
  },
};

export function themeOf(name: ThemeName | undefined): Theme {
  return THEMES[name ?? "heritage"] ?? THEMES.heritage;
}

export function colorFor(theme: Theme, legendKeys: string[], key: string | null | undefined): string {
  if (!key) return theme.hidden;
  const i = legendKeys.indexOf(key);
  return theme.palette[(i >= 0 ? i : legendKeys.length) % theme.palette.length];
}
