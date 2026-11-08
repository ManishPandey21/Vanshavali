import { describe, expect, it } from "vitest";
import { describeChain } from "./kinship";

// The regional word matrix (चाचा / ताऊ, मामा…) moved to the backend with the packs
// (backend/tests/test_kinship_packs.py, ADR-0026 §6). Only the literal reading is rendered here.
describe("literal chain reading", () => {
  const age = (chain_index: number, order: "elder" | "younger" | "unknown") => ({
    chain_index,
    person_id: "p",
    relative_to_id: "r",
    order,
    basis: order === "unknown" ? ("unknown" as const) : ("birth_dates" as const),
  });

  it("reads chains in both languages", () => {
    expect(describeChain(["father", "brother"], "en")).toBe("father's brother");
    expect(describeChain(["mother", "brother"], "hi")).toBe("माता के भाई");
    expect(describeChain(["brother", "wife"], "hi")).toBe("भाई की पत्नी");
    expect(describeChain([], "en")).toBe("");
  });

  it("says elder or younger only where the order is known", () => {
    expect(describeChain(["father", "brother"], "en", [age(1, "elder")])).toBe("father's elder brother");
    expect(describeChain(["father", "brother"], "hi", [age(1, "younger")])).toBe("पिता के छोटे भाई");
    expect(describeChain(["father", "brother"], "en", [age(1, "unknown")])).toBe("father's brother");
  });
});
