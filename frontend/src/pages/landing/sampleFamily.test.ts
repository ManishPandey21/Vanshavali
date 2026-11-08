import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";
import { layoutGraph } from "../../lib/treeLayout";
import { SAMPLE_PEOPLE, VIEWER_ID, sampleGraph } from "./sampleFamily";

describe("landing sample family", () => {
  const graph = sampleGraph(false);

  it("shows a member's view: years only for the departed and for the viewer themself", () => {
    for (const n of graph.nodes) {
      const p = n.person;
      if (!p) continue;
      if (p.profile_status === "living" && p.id !== VIEWER_ID) {
        expect(p.birth_date, p.display_name).toBeNull();
        expect(p.is_protected, p.display_name).toBe(true);
      }
    }
    expect(graph.nodes.find((n) => n.id === VIEWER_ID)?.person?.birth_year).toBe(1998);
    // the departed carry a story; the living never do
    for (const p of SAMPLE_PEOPLE) expect(!!p.story, p.en).toBe(p.status === "deceased");
  });

  it("includes one private relative as an anonymous placeholder", () => {
    const hidden = graph.nodes.filter((n) => !n.person);
    expect(hidden).toHaveLength(1);
    expect(hidden[0]).toMatchObject({ hidden: true });
  });

  it("is a graph the real tree layout can place, with every couple side by side", () => {
    const layout = layoutGraph(graph);
    expect(layout.nodes.size).toBe(graph.nodes.length);
    expect(layout.couples).toHaveLength(3);
    expect(layout.rootId).toBe("sample-suresh");
  });

  it("names everyone's relation to Aarav with the server's Hindi word for that chain", () => {
    // the static sample must say what the app itself would say (ADR-0026 §6 packs)
    const pack = JSON.parse(
      readFileSync(path.resolve(process.cwd(), "../backend/app/modules/kinship/packs/kinship-hi-north.json"), "utf8"),
    ) as { terms: Record<string, { term: string }> };
    for (const p of SAMPLE_PEOPLE.filter((x) => x.id !== VIEWER_ID)) {
      expect(p.term, p.en).toBe(pack.terms[p.kin.join(".")]?.term);
    }
    expect(SAMPLE_PEOPLE.find((p) => p.id === "sample-suresh")!.term).toBe("दादा");
  });

  it("uses Devanagari names on the Hindi page", () => {
    expect(sampleGraph(true).nodes.find((n) => n.id === VIEWER_ID)?.person?.display_name).toBe("आरव शर्मा");
  });
});
