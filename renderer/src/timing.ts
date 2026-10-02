import type { ChartData } from "./types";

export const FPS = 30;
export const TITLE_SECONDS = 2.5;
export const OUTRO_SECONDS = 2;
export const MAX_SECONDS = 120;

/** Seconds of chart animation (after the title card) for a payload. */
export function chartSeconds(data: ChartData): number {
  switch (data.kind) {
    case "fan":
    case "pedigree":
      return 1.2 * Math.max(1, data.generations) + 2;
    case "family_tree":
      return Math.min(40, 4 + 0.25 * data.nodes.length);
    case "lifespan":
      return Math.min(40, 6 + 0.08 * data.rows.length);
    case "event_timeline":
      return Math.max(4, 4 * data.events.length);
  }
}

export function totalFrames(data: ChartData): number {
  const seconds = Math.min(MAX_SECONDS, TITLE_SECONDS + chartSeconds(data) + OUTRO_SECONDS);
  return Math.round(seconds * FPS);
}

export const TITLE_FRAMES = Math.round(TITLE_SECONDS * FPS);
