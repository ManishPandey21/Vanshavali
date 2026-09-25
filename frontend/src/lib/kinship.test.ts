import { describe, expect, it } from "vitest";
import { describeChain, hindiKinshipTerm, regionalKinshipTerm } from "./kinship";

describe("regional kinship terms", () => {
  it.each([
    [["father", "brother"], "चाचा / ताऊ"],
    [["mother", "brother"], "मामा"],
    [["father", "sister"], "बुआ"],
    [["mother", "sister"], "मौसी"],
    [["father", "father"], "दादा"],
    [["mother", "father"], "नाना"],
    [["father", "mother"], "दादी"],
    [["mother", "mother"], "नानी"],
    [["wife", "father"], "ससुर"],
    [["husband", "mother"], "सास"],
    [["brother", "wife"], "भाभी"],
    [["sister", "son"], "भांजा"],
  ])("%j → %s in Hindi", (chain, term) => {
    expect(hindiKinshipTerm(chain)).toBe(term);
    expect(regionalKinshipTerm(chain, "hi")).toBe(term);
  });

  it("returns null in English (the API label is used) and for unknown chains", () => {
    expect(regionalKinshipTerm(["father", "brother"], "en")).toBeNull();
    expect(hindiKinshipTerm(["parent", "father"])).toBeNull();
    expect(hindiKinshipTerm([])).toBeNull();
  });

  it("describes chains literally in both languages", () => {
    expect(describeChain(["father", "brother"], "en")).toBe("father's brother");
    expect(describeChain(["mother", "brother"], "hi")).toBe("माता के भाई");
  });
});
