import type { RenderProps } from "./types";

// Fictional sample data (studio previews and the smoke test). Never real people.
const base = {
  theme: "heritage" as const,
  generatedAt: "2026-10-02T00:00:00Z",
  branding: { title: "The Sharma family", subtitle: "Five generations", treeName: "Sample tree", footer: "Sample data" },
};

const card = (id: string, name: string, years: string, colorKey: string) => ({ id, name, years, colorKey, birthPlace: colorKey });
const slotNodes = [
  { slot: 1, generation: 0, hidden: false, person: card("1", "Arjun Sharma", "1990–", "Varanasi") },
  { slot: 2, generation: 1, hidden: false, person: card("2", "Ravi Sharma", "1958–2019", "Varanasi") },
  { slot: 3, generation: 1, hidden: false, person: card("3", "Meera Sharma", "1962–", "Prayagraj") },
  { slot: 4, generation: 2, hidden: false, person: card("4", "Shankar Sharma", "1930–1999", "Bhadohi") },
  { slot: 5, generation: 2, hidden: false, person: card("5", "Kamla Devi", "1935–2010", "Bhadohi") },
  { slot: 6, generation: 2, hidden: true, person: null },
  { slot: 8, generation: 3, hidden: false, person: card("8", "Gopal Sharma", "c. 1900–1960", "Bhadohi") },
];
const legend = [
  { key: "Varanasi", label: "Varanasi" },
  { key: "Prayagraj", label: "Prayagraj" },
  { key: "Bhadohi", label: "Bhadohi" },
];

export const SAMPLE_PROPS: Record<string, RenderProps> = {
  fan: { ...base, data: { kind: "fan", generations: 3, colorBy: "birthplace", nodes: slotNodes, legend, missingSlots: [7, 9, 10, 11] } },
  pedigree: { ...base, data: { kind: "pedigree", generations: 3, colorBy: "birthplace", nodes: slotNodes, legend, missingSlots: [7, 9, 10, 11] } },
  family_tree: {
    ...base,
    data: {
      kind: "family_tree",
      direction: "descendants",
      rootId: "g",
      nodes: [
        { id: "g", generation: 0, hidden: false, partner: false, person: card("g", "Gopal Sharma", "c. 1900–1960", "") },
        { id: "w", generation: 0, hidden: false, partner: true, person: card("w", "Parvati", "1905–1970", "") },
        { id: "s", generation: 1, hidden: false, partner: false, person: card("s", "Shankar", "1930–1999", "") },
        { id: "d", generation: 1, hidden: false, partner: false, person: card("d", "Lakshmi", "1933–", "") },
        { id: "r", generation: 2, hidden: false, partner: false, person: card("r", "Ravi", "1958–2019", "") },
      ],
      edges: [
        { source: "g", target: "s" },
        { source: "g", target: "d" },
        { source: "s", target: "r" },
      ],
      unions: [{ a: "g", b: "w" }],
    },
  },
  lifespan: {
    ...base,
    data: {
      kind: "lifespan",
      minYear: 1900,
      maxYear: 2026,
      legend: [{ key: "deceased", label: "Deceased" }, { key: "living", label: "Living" }],
      periods: [{ label: "British Raj", startYear: 1858, endYear: 1947 }, { label: "Republic of India", startYear: 1950, endYear: 2026 }],
      rows: [
        { name: "Gopal Sharma", start: 1900, end: 1960, endKnown: true, living: false, colorKey: "deceased", events: [{ year: 1925, label: "Marriage" }] },
        { name: "Shankar Sharma", start: 1930, end: 1999, endKnown: true, living: false, colorKey: "deceased", events: [{ year: 1947, label: "Migration" }] },
        { name: "Ravi Sharma", start: 1958, end: 2019, endKnown: true, living: false, colorKey: "deceased", events: [] },
        { name: "Arjun Sharma", start: 1990, end: null, endKnown: true, living: true, colorKey: "living", events: [] },
      ],
    },
  },
  event_timeline: {
    ...base,
    data: {
      kind: "event_timeline",
      person: { name: "Shankar Sharma", years: "1930–1999" },
      events: [
        { label: "Birth", dateDisplay: "1930", year: 1930, place: "Bhadohi", relatives: [], photos: [] },
        { label: "Moved to Varanasi", dateDisplay: "1947", year: 1947, place: "Varanasi", description: "Opened a cloth shop near the ghats.", relatives: [], photos: [] },
        { label: "Marriage", dateDisplay: "12 Feb 1955", year: 1955, place: "Prayagraj", relatives: ["Kamla Devi"], photos: [] },
      ],
    },
  },
};
