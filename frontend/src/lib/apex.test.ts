import { describe, expect, it } from "vitest";
import type { BranchOut, GraphOut, PersonSummary } from "../api/types";
import { pickFounder, pickSeed, pickTopAncestor } from "./apex";

const person = (id: string, extra: Partial<PersonSummary> = {}): PersonSummary =>
  ({ id, display_name: id, profile_status: "deceased", sex_at_birth: null, ...extra }) as PersonSummary;
const branch = (id: string, founder: string | null, extra: Partial<BranchOut> = {}): BranchOut =>
  ({ id, name: id, description: null, founder_person_id: founder, parent_branch_id: null, descent_rule: "bilateral", created_at: "", ...extra }) as BranchOut;

describe("pickFounder", () => {
  it("takes the founder of the largest top-level branch the viewer can see", () => {
    const visible = new Set(["a", "b", "c"]);
    expect(pickFounder([branch("small", "a", { member_count: 3 }), branch("big", "b", { member_count: 9 })], visible)).toBe("b");
    // sub-branches never define the family's elder
    expect(pickFounder([branch("sub", "c", { member_count: 99, parent_branch_id: "small" }), branch("small", "a", { member_count: 1 })], visible)).toBe("a");
  });

  it("never picks a founder the viewer cannot see, or a branch without one", () => {
    expect(pickFounder([branch("x", "hidden", { member_count: 50 }), branch("y", null)], new Set(["a"]))).toBeNull();
  });
});

describe("pickSeed", () => {
  const people = [person("young", { birth_year: 1990 }), person("old", { birth_year: 1931 }), person("undated")];
  it("starts from the viewer's own profile when it is visible", () => {
    expect(pickSeed(people, "young")).toBe("young");
  });
  it("otherwise starts from the earliest-born, with undated people last", () => {
    expect(pickSeed(people, "not-visible")).toBe("old");
    expect(pickSeed([person("b"), person("a")], null)).toBe("a"); // stable by name
    expect(pickSeed([], null)).toBeNull();
  });
});

describe("pickTopAncestor", () => {
  const graph = (nodes: GraphOut["nodes"]): GraphOut => ({ root_id: "me", direction: "ancestors", depth: 25, truncated: false, nodes, edges: [] });
  it("climbs to the most distant visible generation, preferring the paternal line", () => {
    const g = graph([
      { id: "me", person: person("me"), generation: 0 },
      { id: "dad", person: person("dad", { sex_at_birth: "male" }), generation: -1 },
      { id: "nani", person: person("nani", { sex_at_birth: "female", birth_year: 1900 }), generation: -2 },
      { id: "dada", person: person("dada", { sex_at_birth: "male" }), generation: -2 },
    ]);
    expect(pickTopAncestor(g)).toBe("dada");
  });
  it("skips hidden ancestors and partners, and falls back to the root", () => {
    const g = graph([
      { id: "me", person: person("me"), generation: 0 },
      { id: "secret", person: null, hidden: true, generation: -3 },
      { id: "step", person: person("step"), generation: -1, partner: true },
    ]);
    expect(pickTopAncestor(g)).toBe("me");
  });
});
