import { describe, expect, it } from "vitest";
import { abbreviateSurname, fitFanLabel, GLYPH_EM } from "./fanLabel";

const width = (l: { text: string; fontSize: number }) => [...l.text].length * GLYPH_EM * l.fontSize;

describe("fan-chart labels", () => {
  it("keeps a short name whole at the largest size", () => {
    expect(fitFanLabel("Asha Iyer", { length: 200, thickness: 90, maxFont: 15, minFont: 10 })).toEqual({ text: "Asha Iyer", fontSize: 15 });
  });

  it("shrinks a long name before shortening it", () => {
    const l = fitFanLabel("Ram Prasad Pandey", { length: 110, thickness: 80, maxFont: 12, minFont: 9 });
    expect(l.text).toBe("Ram Prasad Pandey");
    expect(l.fontSize).toBeLessThan(12);
    expect(width(l)).toBeLessThanOrEqual(110);
  });

  it("abbreviates the surname, then truncates with an ellipsis, never exceeding the space", () => {
    const abbreviated = fitFanLabel("Hari Shankar Tiwari", { length: 90, thickness: 80, maxFont: 12, minFont: 9 });
    expect(abbreviated.text).toBe("Hari Shankar T.");
    expect(width(abbreviated)).toBeLessThanOrEqual(90);
    const cut = fitFanLabel("Venkataraman Subramaniam Iyer", { length: 66, thickness: 80, maxFont: 12, minFont: 9 });
    expect(cut.text.endsWith("…")).toBe(true);
    expect(cut.fontSize).toBe(9);
    expect(width(cut)).toBeLessThanOrEqual(66);
  });

  it("caps the size by a narrow sector's thickness and drops the label when nothing readable fits", () => {
    const narrow = fitFanLabel("Mohan Pandey", { length: 70, thickness: 11, maxFont: 10, minFont: 7 });
    expect(narrow.fontSize).toBeLessThanOrEqual(8);
    expect(width(narrow)).toBeLessThanOrEqual(70);
    expect(fitFanLabel("Mohan Pandey", { length: 70, thickness: 6, maxFont: 10, minFont: 7 })).toEqual({ text: "", fontSize: 0 });
    expect(fitFanLabel("Mohan Pandey", { length: 8, thickness: 40, maxFont: 10, minFont: 7 })).toEqual({ text: "", fontSize: 0 });
  });

  it("counts Indic text by code point and abbreviates by the first one", () => {
    const l = fitFanLabel("रामप्रसाद पाण्डेय", { length: 60, thickness: 40, maxFont: 12, minFont: 9 });
    expect(width(l)).toBeLessThanOrEqual(60);
    expect(abbreviateSurname("रामप्रसाद पाण्डेय")).toBe("रामप्रसाद पा."); // पा, not प
    const cut = fitFanLabel("रामप्रसाद पाण्डेय", { length: 30, thickness: 40, maxFont: 12, minFont: 9 });
    // cut between clusters: "रा" keeps its vowel sign and the conjunct "प्र" is not split
    expect(cut.text).toBe("राम…");
    expect(width(cut)).toBeLessThanOrEqual(30);
    expect(abbreviateSurname("Mohan")).toBe("Mohan");
  });
});
