import { describe, expect, it } from "vitest";
import i18n from "../i18n";
import { formatDate, formatTime, isTimeCombinationAllowed, normalizeDate, validateDate, validateTime } from "./dates";

const t = i18n.getFixedT("en");

describe("genealogical dates", () => {
  it("requires day and month for exact dates", () => {
    expect(validateDate({ calendar: "gregorian", precision: "exact", year: 1950, month: 3 }).day).toBe("date.err.exactNeedsDay");
    expect(validateDate({ calendar: "gregorian", precision: "exact", year: 1950, day: 3 }).month).toBe("date.err.exactNeedsMonth");
    expect(validateDate({ calendar: "gregorian", precision: "exact", year: 1950, month: 3, day: 3 })).toEqual({});
  });

  it("rejects impossible Gregorian days and parts not allowed by precision", () => {
    expect(validateDate({ calendar: "gregorian", precision: "exact", year: 1951, month: 2, day: 29 }).day).toBe("date.err.invalidDay");
    expect(validateDate({ calendar: "gregorian", precision: "year_only", year: 1951, month: 2 }).month).toBe("date.err.yearOnlyNoParts");
    expect(validateDate({ calendar: "gregorian", precision: "range", year: 1951 }).end_year).toBe("date.err.endYearRequired");
    expect(validateDate({ calendar: "gregorian", precision: "unknown" })).toEqual({});
  });

  it("normalises away parts a precision does not allow", () => {
    expect(normalizeDate({ calendar: "gregorian", precision: "year_only", year: 1900, month: 4, day: 2 })).toEqual({ calendar: "gregorian", precision: "year_only", year: 1900 });
  });

  it("always shows qualifiers and the calendar", () => {
    expect(formatDate({ calendar: "gregorian", precision: "circa", year: 1900 }, t)).toBe("c. 1900");
    expect(formatDate({ calendar: "vikram_samvat", precision: "day_unknown", year: 2001, month: 1 }, t)).toBe("Chaitra 2001 (Vikram Samvat)");
    expect(formatDate({ calendar: "gregorian", precision: "range", year: 1900, end_year: 1905 }, t)).toBe("between 1900 and 1905");
  });
});

describe("genealogical times", () => {
  it("never labels an approximate time as exact", () => {
    for (const precision of ["approximate", "family_recollection", "document_recorded"] as const) {
      const text = formatTime({ value: "06:30", precision, source: "verbal" }, t)!;
      expect(text).not.toMatch(/exact/i);
      expect(text).toMatch(/06:30/);
    }
    expect(formatTime({ value: "06:30", precision: "approximate", source: "verbal" }, t)).toMatch(/^about 06:30/);
  });

  it("disallows exact + verbal/approximate/unknown source", () => {
    expect(isTimeCombinationAllowed("exact", "verbal")).toBe(false);
    expect(isTimeCombinationAllowed("exact", "approximate")).toBe(false);
    expect(isTimeCombinationAllowed("exact", "unknown")).toBe(false);
    expect(isTimeCombinationAllowed("exact", "birth_certificate")).toBe(true);
    expect(validateTime({ value: "06:30", precision: "exact", source: "verbal" })).toBe("time.err.exactNotAllowed");
    expect(validateTime({ value: null, precision: "approximate", source: "verbal" })).toBe("time.err.valueRequired");
  });
});
