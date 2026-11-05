import { describe, expect, it } from "vitest";
import { describeChain, hindiKinshipTerm, regionalKinshipTerm, resolveKinship } from "./kinship";

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

describe("age-aware Hindi kinship (ADR-0020 §5)", () => {
  const age = (chain_index: number, order: "elder" | "younger" | "unknown", basis: "family_confirmed" | "birth_dates" | "unknown" = order === "unknown" ? "unknown" : "birth_dates") => ({
    chain_index,
    person_id: "p",
    relative_to_id: "r",
    order,
    basis,
  });

  it.each([
    [["father", "brother"], 1, "ताऊ", "चाचा", "चाचा / ताऊ"],
    [["father", "brother", "wife"], 1, "ताई", "चाची", "चाची / ताई"],
    [["husband", "brother"], 1, "जेठ", "देवर", "देवर / जेठ"],
    [["husband", "brother", "wife"], 1, "जेठानी", "देवरानी", "देवरानी / जेठानी"],
    [["wife", "brother"], 1, "भाई साहब", "साला", "साला / भाई साहब"],
    [["brother"], 0, "भैया", "भाई", "भाई"],
    [["sister"], 0, "दीदी", "बहन", "बहन"],
    [["sister", "husband"], 0, "जीजा", "बहनोई", "जीजा"],
  ] as const)("%j: elder → %s… uses the order of chain word %i", (chain, index, elder, younger, unknown) => {
    expect(resolveKinship(chain, [age(index, "elder")], "hi").term).toBe(elder);
    expect(resolveKinship(chain, [age(index, "younger", "family_confirmed")], "hi")).toMatchObject({ term: younger, basis: "family_confirmed", ageQuestion: null });
    const open = resolveKinship(chain, [age(index, "unknown")], "hi");
    expect(open.term).toBe(unknown);
    expect(open.ageQuestion).toEqual({ personId: "p", relativeToId: "r" });
    // no age data at all (e.g. a hidden relative on the path): both words, and no question
    expect(resolveKinship(chain, [], "hi")).toMatchObject({ term: unknown, ageQuestion: null });
  });

  it("uses the order of the right word, not any sibling word in the chain", () => {
    // father's brother: only word 1 matters; an order on word 0 (none here) must not decide it
    expect(resolveKinship(["father", "brother"], [age(0, "elder")], "hi").term).toBe("चाचा / ताऊ");
  });

  it("terms that do not depend on age ignore age orders", () => {
    expect(resolveKinship(["mother", "brother"], [age(1, "elder")], "hi").term).toBe("मामा");
    expect(resolveKinship(["mother", "sister"], [age(1, "younger")], "hi").term).toBe("मौसी");
    expect(resolveKinship(["son", "wife", "father"], [], "hi").term).toBe("समधी");
    expect(resolveKinship(["husband", "sister", "husband"], [], "hi").term).toBe("ननदोई");
  });

  it("English keeps the API label but still asks the open question and describes known age", () => {
    const r = resolveKinship(["father", "brother"], [age(1, "unknown")], "en");
    expect(r.term).toBeNull();
    expect(r.ageQuestion).toEqual({ personId: "p", relativeToId: "r" });
    expect(describeChain(["father", "brother"], "en", [age(1, "elder")])).toBe("father's elder brother");
    expect(describeChain(["father", "brother"], "hi", [age(1, "younger")])).toBe("पिता के छोटे भाई");
    expect(describeChain(["father", "brother"], "en", [age(1, "unknown")])).toBe("father's brother");
  });

  it("reports the basis in English too (regression: it was only set for Hindi)", () => {
    expect(resolveKinship(["father", "brother"], [age(1, "elder", "family_confirmed")], "en")).toMatchObject({ term: null, basis: "family_confirmed" });
    expect(resolveKinship(["father", "brother"], [{ ...age(1, "younger", "family_confirmed"), dates_disagree: true }], "en").dates_disagree).toBe(true);
  });

  it("flags a family answer that the visible birth dates contradict", () => {
    const r = resolveKinship(["father", "brother"], [{ ...age(1, "younger", "family_confirmed"), dates_disagree: true }], "hi");
    expect(r).toMatchObject({ term: "चाचा", dates_disagree: true });
  });
});
