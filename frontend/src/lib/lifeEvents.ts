import type { EventOut, EventType, LifeEventCategory } from "../api/types";

/** Life-event categories grouped for the picker; each implies a structural type (ADR-0015). */
export const CATEGORY_GROUPS: { id: string; categories: LifeEventCategory[] }[] = [
  { id: "sanskar", categories: ["naming_ceremony", "annaprashan", "mundan", "upanayana", "initiation"] },
  { id: "family", categories: ["birth", "engagement", "marriage", "death", "memorial"] },
  { id: "life", categories: ["education", "graduation", "employment", "retirement", "award", "migration", "property_acquisition", "pilgrimage"] },
  { id: "health", categories: ["illness", "recovery"] },
  { id: "other", categories: ["custom"] },
];

export const CATEGORY_TYPE: Record<LifeEventCategory, EventType> = {
  birth: "birth",
  naming_ceremony: "religious_ceremony",
  annaprashan: "religious_ceremony",
  mundan: "religious_ceremony",
  upanayana: "religious_ceremony",
  initiation: "religious_ceremony",
  education: "education",
  graduation: "education",
  engagement: "other",
  marriage: "marriage",
  migration: "migration",
  employment: "occupation",
  retirement: "occupation",
  award: "other",
  property_acquisition: "other",
  illness: "other",
  recovery: "other",
  pilgrimage: "other",
  death: "death",
  memorial: "memorial",
  custom: "other",
};

type T = (key: string, opts?: Record<string, unknown>) => string;

/** What to call an event: its title, else its category, else its structural type. */
export function eventLabel(e: Pick<EventOut, "title" | "category" | "type">, t: T): string {
  if (e.title) return e.title;
  if (e.category) return t(`enum.lifeEventCategory.${e.category}`);
  return t(`enum.eventType.${e.type}`);
}

export function isImportant(e: Pick<EventOut, "category" | "significance">): boolean {
  return !!e.category || (e.significance ?? "standard") !== "standard";
}

/** Decade bucket for grouped timelines ("1950s"), or null when undated. */
export function decadeOf(year: number | null | undefined): number | null {
  return year ? Math.floor(year / 10) * 10 : null;
}
