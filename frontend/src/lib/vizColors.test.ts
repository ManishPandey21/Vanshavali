import { describe, expect, it } from "vitest";
import type { VizPerson } from "../api/types";
import { buildLegend, colorKey, HIDDEN_COLOR, OTHER_COLOR, yearsLabel } from "./vizColors";

const person = (over: Partial<VizPerson> = {}): VizPerson => ({
  id: "p",
  display_name: "Mohan",
  profile_status: "deceased",
  birth_display: "1955",
  death_display: "2015",
  branch_ids: ["b1"],
  birth_place: { name: "Bhadohi" },
  village: "Bhadohi",
  completeness: { score: 0.5, missing: ["sources"] },
  ...over,
});

describe("chart colour keys", () => {
  it("derives keys for every colour mode", () => {
    const p = person();
    expect(colorKey(p, "side", "paternal")).toBe("paternal");
    expect(colorKey(p, "birthplace", "x")).toBe("Bhadohi");
    expect(colorKey(p, "branch", "x", { b1: "Iyers of Bhadohi" })).toBe("Iyers of Bhadohi");
    expect(colorKey(p, "completeness", "x")).toBe("partial");
    expect(colorKey(p, "living", "x")).toBe("deceased");
    expect(colorKey(person({ birth_place: null }), "birthplace", "x")).toBe("unknown");
    expect(colorKey(null, "side", "self")).toBeNull();
  });

  it("gives frequent keys colours and groups the rest", () => {
    const legend = buildLegend(["a", "a", "b", "c", null], 2);
    expect(legend.entries.map((e) => e.key)).toEqual(["a", "b", "__other__"]);
    expect(legend.color("c")).toBe(OTHER_COLOR);
    expect(legend.color(null)).toBe(HIDDEN_COLOR);
    expect(legend.color("a")).not.toBe(legend.color("b"));
  });

  it("formats lifespans", () => {
    expect(yearsLabel(person())).toBe("1955–2015");
    expect(yearsLabel(person({ profile_status: "living", death_display: null }))).toBe("1955–");
  });
});
