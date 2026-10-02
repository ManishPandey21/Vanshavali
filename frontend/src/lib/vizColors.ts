import type { VizPerson } from "../api/types";

/** Colour-blind-aware categorical palette; colour is always paired with a text label. */
export const PALETTE = ["#9a3412", "#1d4ed8", "#047857", "#a16207", "#7e22ce", "#be123c", "#0e7490", "#4d7c0f", "#c2410c"];
export const OTHER_COLOR = "#78716c";
export const HIDDEN_COLOR = "#d6d3d1";
export const MISSING_FILL = "#f5f0e6";

export type ColorBy = "side" | "birthplace" | "village" | "branch" | "completeness" | "living";
export const COLOR_BYS: ColorBy[] = ["side", "birthplace", "village", "branch", "completeness", "living"];

export function colorKey(p: VizPerson | null | undefined, colorBy: ColorBy, side: string, branchNames: Record<string, string> = {}): string | null {
  if (!p) return null;
  switch (colorBy) {
    case "side":
      return side;
    case "birthplace":
      return p.birth_place?.name ?? "unknown";
    case "village":
      return p.village ?? "unknown";
    case "branch":
      return p.branch_ids?.length ? branchNames[p.branch_ids[0]] ?? "unknown" : "unknown";
    case "completeness": {
      const s = p.completeness?.score ?? 0;
      return s >= 0.8 ? "complete" : s >= 0.4 ? "partial" : "sparse";
    }
    case "living":
      return p.profile_status;
  }
}

export interface Legend {
  entries: { key: string; color: string; count: number }[];
  color: (key: string | null) => string;
}

/** The most frequent keys get palette colours; the rest share "other" (never colour alone). */
export function buildLegend(keys: (string | null)[], max = PALETTE.length - 1): Legend {
  const counts = new Map<string, number>();
  for (const k of keys) if (k) counts.set(k, (counts.get(k) ?? 0) + 1);
  const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const top = new Map(sorted.slice(0, max).map(([k], i) => [k, PALETTE[i]]));
  const entries = sorted.slice(0, max).map(([key, count]) => ({ key, color: top.get(key)!, count }));
  const rest = sorted.slice(max).reduce((n, [, c]) => n + c, 0);
  if (rest) entries.push({ key: "__other__", color: OTHER_COLOR, count: rest });
  return { entries, color: (k) => (k ? top.get(k) ?? OTHER_COLOR : HIDDEN_COLOR) };
}

/** "c. 1900" stays "c. 1900", "12 Oct 1950" / "1950-10-12" become "1950" (charts show years). */
export function shortYear(display: string | null | undefined, year: number | null | undefined): string | null {
  if (!display && !year) return null;
  if (!year) return display ?? null;
  const qualifier = display && /^[^\d]/.test(display) ? `${display.split(" ")[0]} ` : "";
  return `${qualifier}${year}`;
}

export function yearsLabel(p: Pick<VizPerson, "birth_display" | "death_display" | "profile_status"> & Partial<Pick<VizPerson, "birth_year" | "death_year">>): string {
  const born = shortYear(p.birth_display, p.birth_year);
  const died = shortYear(p.death_display, p.death_year);
  if (!born && !died) return "";
  if (p.profile_status === "deceased") return `${born ?? "?"}–${died ?? "?"}`;
  return born ? `${born}–` : "";
}
