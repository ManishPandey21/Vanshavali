import { describe, expect, it } from "vitest";
import en from "./locales/en.json";
import hi from "./locales/hi.json";
import { PRIVACY_LEVELS } from "../components/person/PersonForm";
import { EVENT_TYPES } from "../pages/tree/person/EventDialog";
import { HERITAGE_ATTRIBUTES } from "../components/heritage/HeritageProfile";
import { FIELD_GROUPS } from "../pages/tree/person/PrivacyTab";
import { DATE_PRECISIONS, TIME_PRECISIONS, TIME_SOURCES } from "../lib/dates";

type Tree = { [k: string]: string | Tree };
const flat = (o: Tree, pre = ""): string[] => Object.entries(o).flatMap(([k, v]) => (typeof v === "object" ? flat(v, `${pre}${k}.`) : [`${pre}${k}`]));

describe("translations", () => {
  it("Hindi has exactly the same keys as English", () => {
    const e = new Set(flat(en as Tree));
    const h = new Set(flat(hi as Tree));
    expect([...e].filter((k) => !h.has(k))).toEqual([]);
    expect([...h].filter((k) => !e.has(k))).toEqual([]);
  });

  it("every enum value used in the UI has a label", () => {
    const keys = new Set(flat(en as Tree));
    const need = [
      ...PRIVACY_LEVELS.map((v) => `enum.privacy.${v}`),
      ...PRIVACY_LEVELS.map((v) => `enum.privacyHint.${v}`),
      ...EVENT_TYPES.map((v) => `enum.eventType.${v}`),
      ...HERITAGE_ATTRIBUTES.map((v) => `enum.heritage.${v}`),
      ...FIELD_GROUPS.map((v) => `enum.fieldGroup.${v}`),
      ...DATE_PRECISIONS.map((v) => `enum.datePrecision.${v}`),
      ...TIME_PRECISIONS.map((v) => `enum.timePrecision.${v}`),
      ...TIME_SOURCES.map((v) => `enum.timeSource.${v}`),
    ];
    expect(need.filter((k) => !keys.has(k))).toEqual([]);
  });
});
