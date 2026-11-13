import { describe, expect, it } from "vitest";
import type { GraphOut, PersonSummary } from "../api/types";
import { layoutGraph } from "./treeLayout";

function person(id: string): PersonSummary {
  return { id, display_name: id, profile_status: "deceased", sex_at_birth: null } as PersonSummary;
}

function connectedGraph(): GraphOut {
  return {
    root_id: "child",
    direction: "connected",
    depth: 25,
    truncated: false,
    nodes: [
      { id: "child", person: person("child"), generation: 0 },
      { id: "father", person: person("father"), generation: -1 },
      { id: "mother", person: person("mother"), generation: -1 },
      { id: "sibling", person: person("sibling"), generation: 0 },
      { id: "grandchild", person: person("grandchild"), generation: 1 },
      { id: "hidden-5", person: null, hidden: true, generation: -2 },
    ],
    edges: [
      { source: "father", target: "child", type: "biological_parent" },
      { source: "mother", target: "child", type: "biological_parent" },
      { source: "father", target: "sibling", type: "biological_parent" },
      { source: "child", target: "grandchild", type: "biological_parent" },
      { source: "hidden-5", target: "father", type: "biological_parent" },
    ],
    unions: [{ id: "union-1", a: "father", b: "mother", type: "spouse" }],
  };
}

describe("complete connected family layout", () => {
  it("positions every returned ancestor, descendant, sibling and hidden node", () => {
    const graph = connectedGraph();
    const layout = layoutGraph(graph);
    expect(layout.nodes.size).toBe(graph.nodes.length);
    expect([...layout.nodes.keys()].sort()).toEqual(graph.nodes.map((n) => n.id).sort());
    expect(layout.nodes.get("father")!.y).toBeLessThan(layout.nodes.get("child")!.y);
    expect(layout.nodes.get("grandchild")!.y).toBeGreaterThan(layout.nodes.get("child")!.y);
    expect(layout.edges.length).toBe(graph.edges.length);
    expect(layout.rootId).toBe("child");
    expect(layout.couples).toHaveLength(1);
  });

  it("never invents a missing person or collapses visible relatives in connected mode", () => {
    const graph = connectedGraph();
    graph.nodes = graph.nodes.filter((node) => node.id !== "hidden-5");
    graph.edges = graph.edges.filter((edge) => edge.source !== "hidden-5");
    const layout = layoutGraph(graph, new Set(["father"]));
    expect([...layout.nodes.keys()].sort()).toEqual(graph.nodes.map((n) => n.id).sort());
    expect(layout.nodes.has("hidden-5")).toBe(false);
    expect(layout.nodes.has("sibling")).toBe(true);
  });
});
