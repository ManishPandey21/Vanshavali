import type { GraphOut, PersonSummary } from "../../api/types";

/**
 * The landing page's explorable sample: the fictional Sharma family (the same people as the
 * animated tree and the demo seed), shaped exactly like a `/descendants` response so the real
 * TreeChart can draw it. Nothing here is fetched; nobody in it is real.
 *
 * The visitor explores "as Aarav", an ordinary member, so the sample shows what the privacy rules
 * show a member: years and stories for relatives who have passed away, no birth dates for the
 * living (only tree admins see those), Aarav's own years on his own profile, and a relative who
 * keeps their profile private as an anonymous placeholder.
 */

export const VIEWER_ID = "sample-aarav";

export interface SamplePerson {
  id: string;
  en: string;
  hi: string;
  sex: "male" | "female";
  status: "living" | "deceased";
  born?: { year: number; circa?: boolean };
  died?: { year: number; circa?: boolean };
  minor?: boolean;
  /** Kinship chain from Aarav to this person, in the words lib/kinship understands. */
  kin: string[];
  /**
   * The Hindi relationship word for that chain. The app takes these words from the server's
   * reviewed packs (ADR-0026 §6); this static, request-free sample copies them from
   * backend/app/modules/kinship/packs/kinship-hi-north.json (a test keeps the two in step).
   */
  term?: string;
  /** A one-line story for relatives who have passed away (never for the living). */
  story?: { en: string; hi: string };
}

export const SAMPLE_PEOPLE: SamplePerson[] = [
  {
    id: "sample-suresh",
    en: "Suresh Sharma",
    hi: "सुरेश शर्मा",
    sex: "male",
    status: "deceased",
    born: { year: 1938 },
    died: { year: 2011 },
    kin: ["father", "father"], term: "दादा",
    story: {
      en: "Kept the family bahi of births and marriages for fifty years.",
      hi: "पचास वर्षों तक परिवार की जन्म और विवाह की बही संभाली।",
    },
  },
  {
    id: "sample-kamala",
    en: "Kamala Sharma",
    hi: "कमला शर्मा",
    sex: "female",
    status: "deceased",
    born: { year: 1942, circa: true },
    died: { year: 2019 },
    kin: ["father", "mother"], term: "दादी",
    story: {
      en: "Remembered every recipe, and every relative's birthday.",
      hi: "हर व्यंजन और हर संबंधी का जन्मदिन उन्हें याद रहता था।",
    },
  },
  { id: "sample-ramesh", en: "Ramesh Sharma", hi: "रमेश शर्मा", sex: "male", status: "living", kin: ["father"], term: "पिता" },
  { id: "sample-sunita", en: "Sunita Sharma", hi: "सुनीता शर्मा", sex: "female", status: "living", kin: ["mother"], term: "माता" },
  { id: "sample-mahesh", en: "Mahesh Sharma", hi: "महेश शर्मा", sex: "male", status: "living", kin: ["father", "brother"], term: "चाचा / ताऊ" },
  { id: "sample-geeta", en: "Geeta Sharma", hi: "गीता शर्मा", sex: "female", status: "living", kin: ["father", "brother", "wife"], term: "चाची / ताई" },
  { id: VIEWER_ID, en: "Aarav Sharma", hi: "आरव शर्मा", sex: "male", status: "living", born: { year: 1998 }, kin: [] },
  { id: "sample-anaya", en: "Anaya Sharma", hi: "अनया शर्मा", sex: "female", status: "living", minor: true, kin: ["sister"], term: "बहन" },
  { id: "sample-kabir", en: "Kabir Sharma", hi: "कबीर शर्मा", sex: "male", status: "living", minor: true, kin: ["father", "brother", "son"], term: "चचेरा भाई" },
];

const PRIVATE_ID = "sample-private";

/** Generation (0 = Suresh) and the blood-line parent each person hangs from; partners marry in. */
const PLACE: Record<string, { generation: number; parent?: string; partnerOf?: string }> = {
  "sample-suresh": { generation: 0 },
  "sample-kamala": { generation: 0, partnerOf: "sample-suresh" },
  "sample-ramesh": { generation: 1, parent: "sample-suresh" },
  "sample-sunita": { generation: 1, partnerOf: "sample-ramesh" },
  "sample-mahesh": { generation: 1, parent: "sample-suresh" },
  "sample-geeta": { generation: 1, partnerOf: "sample-mahesh" },
  [VIEWER_ID]: { generation: 2, parent: "sample-ramesh" },
  "sample-anaya": { generation: 2, parent: "sample-ramesh" },
  "sample-kabir": { generation: 2, parent: "sample-mahesh" },
};

function summary(p: SamplePerson, hindi: boolean): PersonSummary {
  const date = (d?: { year: number; circa?: boolean }) => (d ? { precision: d.circa ? "circa" : "exact", year: d.year, calendar: "gregorian" } : null);
  const living = p.status === "living";
  return {
    id: p.id,
    display_name: hindi ? p.hi : p.en,
    profile_status: p.status,
    sex_at_birth: p.sex,
    birth_year: p.born?.year ?? null,
    death_year: p.died?.year ?? null,
    birth_date: date(p.born),
    death_date: date(p.died),
    is_minor: !!p.minor,
    // living relatives are protected; Aarav sees his own profile as himself
    is_protected: living && p.id !== VIEWER_ID,
  } as PersonSummary;
}

/** The sample as the `/descendants` graph the tree viewer draws, in the page's language. */
export function sampleGraph(hindi: boolean): GraphOut {
  const nodes: GraphOut["nodes"] = SAMPLE_PEOPLE.map((p) => ({
    id: p.id,
    person: summary(p, hindi),
    generation: PLACE[p.id]!.generation,
    partner: !!PLACE[p.id]!.partnerOf,
  }));
  nodes.push({ id: PRIVATE_ID, person: null, hidden: true, generation: 2 });
  const edges = [
    ...SAMPLE_PEOPLE.filter((p) => PLACE[p.id]!.parent).map((p) => ({ source: PLACE[p.id]!.parent!, target: p.id, type: "biological_parent" })),
    { source: "sample-mahesh", target: PRIVATE_ID, type: "biological_parent" },
  ] as GraphOut["edges"];
  const unions = SAMPLE_PEOPLE.filter((p) => PLACE[p.id]!.partnerOf).map((p) => ({ a: PLACE[p.id]!.partnerOf!, b: p.id, type: "spouse" }));
  return { root_id: "sample-suresh", direction: "descendants", depth: 2, truncated: false, nodes, edges, unions } as GraphOut;
}
