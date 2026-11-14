import { describe, expect, it } from "vitest";
import type { FamilyGraphEdge, FamilyGraphLink, FamilyGraphNode } from "../api/types";
import { layoutFamily } from "./familyLayout";
import { NODE_H, NODE_W, ROW_H, neighbour } from "./treeLayout";

const node = (id: string, generation: number, component = 0, hidden = false): FamilyGraphNode => ({
  id,
  generation,
  component,
  hidden,
  person: hidden ? null : { id, display_name: id, profile_status: "deceased", sex_at_birth: null },
});
const parent = (source: string, target: string): FamilyGraphEdge => ({ source, target, type: "biological_parent", lineage: "biological" });
const union = (a: string, b: string, type: FamilyGraphLink["type"] = "spouse"): FamilyGraphLink => ({ a, b, kind: "union", type });

/** Both sides of two marriages, a second marriage, a hidden relative and an explicit sibling. */
const family = {
  nodes: [
    node("Anita", 0),
    node("Ramesh", 0),
    node("Sita", 0),
    node("Mama", 0),
    node("Samdhi", 0),
    node("Nana", -1),
    node("Nani", -1),
    node("Dada", -1),
    node("Son", 1),
    node("Bahu", 1),
    node("Half", 1),
    node("Saala", 1),
    node("hidden-0-12", 1, 0, true),
    node("Grandkid", 2),
  ],
  edges: [
    parent("Nana", "Anita"),
    parent("Nani", "Anita"),
    parent("Nana", "Mama"),
    parent("Nani", "Mama"),
    parent("Dada", "Ramesh"),
    parent("Anita", "Son"),
    parent("Ramesh", "Son"),
    parent("Ramesh", "Half"),
    parent("Sita", "Half"),
    parent("Samdhi", "Bahu"),
    parent("Son", "Grandkid"),
    parent("Bahu", "Grandkid"),
    parent("Anita", "hidden-0-12"),
  ],
  links: [
    union("Nana", "Nani"),
    union("Anita", "Ramesh"),
    union("Ramesh", "Sita", "divorced_spouse"),
    union("Son", "Bahu"),
    { a: "Bahu", b: "Saala", kind: "sibling", type: "sibling" } as FamilyGraphLink,
  ],
  rootId: "Anita",
};

function overlaps(layout: ReturnType<typeof layoutFamily>) {
  const all = [...layout.nodes.values()];
  return all.some((a) => all.some((b) => a !== b && a.y === b.y && Math.abs(a.x - b.x) < NODE_W));
}

describe("complete family layout", () => {
  it("places every returned person exactly once, with nobody overlapping", () => {
    const l = layoutFamily(family);
    expect(l.nodes.size).toBe(family.nodes.length);
    expect(overlaps(l)).toBe(false);
    expect(l.rootId).toBe("Anita");
    expect(l.noRootHighlight).toBe(false);
  });

  it("keeps partners side by side on one row, including a second marriage", () => {
    const l = layoutFamily(family);
    const at = (id: string) => l.nodes.get(id)!;
    for (const [a, b] of [
      ["Nana", "Nani"],
      ["Anita", "Ramesh"],
      ["Son", "Bahu"],
    ]) {
      expect(at(a).y).toBe(at(b).y);
      expect(Math.abs(at(a).x - at(b).x)).toBeLessThanOrEqual(NODE_W + 24);
    }
    expect(at("Sita").y).toBe(at("Ramesh").y);
    expect(l.couples).toHaveLength(4);
  });

  it("puts each generation on its own row: ancestors above, descendants below", () => {
    const l = layoutFamily(family);
    const y = (id: string) => l.nodes.get(id)!.y;
    expect(y("Nana")).toBe(0);
    expect(y("Anita")).toBe(ROW_H);
    expect(y("Son")).toBe(ROW_H * 2);
    expect(y("Grandkid")).toBe(ROW_H * 3);
    expect(y("Samdhi")).toBe(y("Anita")); // an in-law's parent is one row above the in-law
    for (const e of l.edges) expect(l.nodes.get(e.source)!.y).toBeLessThan(l.nodes.get(e.target)!.y);
    expect(l.height).toBe(ROW_H * 3 + NODE_H);
  });

  it("keeps a hidden relative as an unnamed card and draws the sibling link", () => {
    const l = layoutFamily(family);
    expect(l.nodes.get("hidden-0-12")!.node.person).toBeNull();
    expect(l.links).toEqual([{ a: "Bahu", b: "Saala", kind: "sibling" }]);
  });

  it("never draws a line to someone the server did not return", () => {
    // the server leaves a removed person out entirely; an edge that still named them is dropped
    const l = layoutFamily({ ...family, edges: [...family.edges, parent("Removed", "Grandkid")], links: [...family.links, union("Removed", "Mama")] });
    expect(l.nodes.has("Removed")).toBe(false);
    expect(l.edges.some((e) => e.source === "Removed")).toBe(false);
    expect(l.couples.some((c) => c.a === "Removed")).toBe(false);
  });

  it("lays disconnected groups apart and never joins them", () => {
    const l = layoutFamily({
      nodes: [...family.nodes, node("Stranger", 0, 1), node("Other", 0, 1), node("Loner", 0, 2)],
      edges: [...family.edges, parent("Anita", "Stranger")], // a cross-group edge must be ignored
      links: [...family.links, union("Stranger", "Other")],
      rootId: null,
    });
    expect(l.groups).toHaveLength(3);
    expect(l.groups!.map((g) => g.people)).toEqual([13, 2, 1]);
    expect(l.noRootHighlight).toBe(true);
    expect(l.edges.some((e) => e.target === "Stranger")).toBe(false);
    const [a, b, c] = l.groups!;
    const apart = (p: typeof a, q: typeof a) => p.x + p.width <= q.x || q.x + q.width <= p.x || p.y + p.height <= q.y || q.y + q.height <= p.y;
    expect(apart(a, b) && apart(a, c) && apart(b, c)).toBe(true);
    expect(overlaps(l)).toBe(false);
  });

  it("supports keyboard movement along a row and between rows", () => {
    const l = layoutFamily(family);
    const row = [...l.nodes.values()].filter((n) => n.y === l.nodes.get("Anita")!.y).sort((a, b) => a.x - b.x).map((n) => n.node.id);
    const i = row.indexOf("Anita");
    expect(neighbour(l, "Anita", "ArrowRight")).toBe(row[i + 1]);
    expect(neighbour(l, row[0], "ArrowLeft")).toBeNull();
    expect(["Nana", "Nani", "Dada"]).toContain(neighbour(l, "Anita", "ArrowUp"));
    expect(neighbour(l, "Grandkid", "ArrowDown")).toBeNull();
  });

  it("lays out a 5,000-person family quickly and without overlap", () => {
    const nodes: FamilyGraphNode[] = [];
    const edges: FamilyGraphEdge[] = [];
    let level = ["g0-0"];
    nodes.push(node("g0-0", 0));
    for (let g = 1; nodes.length < 5000; g++) {
      const next: string[] = [];
      for (const p of level) {
        for (let k = 0; k < 3 && nodes.length < 5000; k++) {
          const id = `g${g}-${next.length}`;
          nodes.push(node(id, g));
          edges.push(parent(p, id));
          next.push(id);
        }
      }
      level = next;
    }
    const started = performance.now();
    const l = layoutFamily({ nodes, edges, links: [], rootId: "g0-0" });
    expect(performance.now() - started).toBeLessThan(3000);
    expect(l.nodes.size).toBe(5000);
    const byRow = new Map<number, number[]>();
    for (const n of l.nodes.values()) byRow.set(n.y, [...(byRow.get(n.y) ?? []), n.x]);
    for (const xs of byRow.values()) {
      xs.sort((a, b) => a - b);
      for (let i = 1; i < xs.length; i++) expect(xs[i] - xs[i - 1]).toBeGreaterThanOrEqual(NODE_W);
    }
  });
});
