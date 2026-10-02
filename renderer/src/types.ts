/**
 * Render payloads (ADR-0017). The API builds these as the requesting user (privacy already
 * applied) and the renderer only draws them: it never fetches data itself.
 */

export type ThemeName = "heritage" | "dusk" | "minimal";

export interface Branding {
  title: string;
  subtitle?: string | null;
  treeName?: string | null;
  footer?: string | null;
}

/** Optional narration / music. Absent or null src = silent video. */
export interface AudioSlot {
  src?: string | null;
  volume?: number;
}

export interface PersonCard {
  id: string;
  name: string;
  years?: string | null;
  birthPlace?: string | null;
  village?: string | null;
  living?: boolean;
  completeness?: number | null;
  colorKey?: string | null;
}

export interface LegendEntry {
  key: string;
  label: string;
}

export interface SlotNode {
  slot: number;
  generation: number;
  hidden: boolean;
  person: PersonCard | null;
}

export interface FanPayload {
  kind: "fan";
  generations: number;
  colorBy: string;
  nodes: SlotNode[];
  legend: LegendEntry[];
  missingSlots: number[];
}

export interface PedigreePayload {
  kind: "pedigree";
  generations: number;
  colorBy: string;
  nodes: SlotNode[];
  legend: LegendEntry[];
  missingSlots: number[];
}

export interface TreeNode {
  id: string;
  generation: number;
  hidden: boolean;
  partner: boolean;
  person: PersonCard | null;
}

export interface FamilyTreePayload {
  kind: "family_tree";
  direction: "ancestors" | "descendants";
  rootId: string;
  nodes: TreeNode[];
  edges: { source: string; target: string }[];
  unions: { a: string; b: string }[];
}

export interface LifespanBar {
  name: string;
  start: number;
  end: number | null;
  endKnown: boolean;
  living: boolean;
  colorKey?: string | null;
  events: { year: number; label: string }[];
}

export interface LifespanPayload {
  kind: "lifespan";
  rows: LifespanBar[];
  minYear: number;
  maxYear: number;
  periods: { label: string; startYear: number; endYear: number }[];
  legend: LegendEntry[];
}

export interface TimelinePhoto {
  src: string; // data: URI embedded by the API (only photos the requester may open)
  caption?: string | null;
}

export interface TimelineEvent {
  label: string;
  dateDisplay?: string | null;
  year?: number | null;
  place?: string | null;
  description?: string | null;
  relatives: string[];
  photos: TimelinePhoto[];
}

export interface EventTimelinePayload {
  kind: "event_timeline";
  person: { name: string; years?: string | null };
  events: TimelineEvent[];
}

export type ChartData = FanPayload | PedigreePayload | FamilyTreePayload | LifespanPayload | EventTimelinePayload;

export interface RenderProps {
  [key: string]: unknown;
  theme: ThemeName;
  branding: Branding;
  generatedAt: string;
  locale?: string;
  music?: AudioSlot | null;
  narration?: AudioSlot | null;
  data: ChartData;
}

export const COMPOSITION_IDS = {
  fan: "FanChart",
  pedigree: "PedigreeChart",
  family_tree: "FamilyTree",
  lifespan: "LifespanTimeline",
  event_timeline: "EventTimeline",
} as const;
