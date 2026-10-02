import { describe, expect, it } from "vitest";
import { CATEGORY_GROUPS, CATEGORY_TYPE, decadeOf, eventLabel, isImportant } from "./lifeEvents";

const t = (k: string) => `T:${k}`;

describe("life events", () => {
  it("covers every category exactly once in the picker", () => {
    const all = CATEGORY_GROUPS.flatMap((g) => g.categories);
    expect(new Set(all).size).toBe(all.length);
    expect(all.sort()).toEqual(Object.keys(CATEGORY_TYPE).sort());
  });

  it("labels by title, then category, then type", () => {
    expect(eventLabel({ title: "Mundan at Vindhyachal", category: "mundan", type: "religious_ceremony" }, t)).toBe("Mundan at Vindhyachal");
    expect(eventLabel({ title: null, category: "mundan", type: "religious_ceremony" }, t)).toBe("T:enum.lifeEventCategory.mundan");
    expect(eventLabel({ title: null, category: null, type: "residence" }, t)).toBe("T:enum.eventType.residence");
  });

  it("marks important events and buckets decades", () => {
    expect(isImportant({ category: null, significance: "standard" })).toBe(false);
    expect(isImportant({ category: null, significance: "milestone" })).toBe(true);
    expect(isImportant({ category: "award", significance: "standard" })).toBe(true);
    expect(decadeOf(1947)).toBe(1940);
    expect(decadeOf(null)).toBeNull();
  });
});
