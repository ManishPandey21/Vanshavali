import { useState } from "react";
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { add, cmp, fmt, frac, parseShare, sum } from "./fractions";
import { checkPartition } from "./partition";
import { renderWithProviders } from "../test/utils";
import { ShareInput } from "../components/property/ShareInput";
import { ulpinError, extraKeyError } from "../pages/tree/property/ParcelsPanel";

describe("exact shares", () => {
  it("adds thirds exactly (no floating point)", () => {
    expect(cmp(sum([frac(1, 3), frac(1, 3), frac(1, 3)]), frac(1))).toBe(0);
    expect(fmt(add(frac(1, 6), frac(1, 3)))).toBe("1/2");
  });

  it("parses a/b and rejects decimals, zero denominators and more than the whole", () => {
    expect(parseShare("1/3")).toMatchObject({ ok: true, numerator: 1, denominator: 3 });
    expect(parseShare(" 2 / 6 ")).toMatchObject({ ok: true, numerator: 2, denominator: 6 });
    expect(parseShare("1")).toMatchObject({ ok: true, numerator: 1, denominator: 1 });
    expect(parseShare("0.33")).toEqual({ ok: false, error: "share.err.decimal" });
    expect(parseShare("1/0")).toEqual({ ok: false, error: "share.err.zeroDen" });
    expect(parseShare("4/3")).toEqual({ ok: false, error: "share.err.overWhole" });
    expect(parseShare("abc")).toEqual({ ok: false, error: "share.err.format" });
    expect(parseShare("")).toEqual({ ok: false, error: "share.err.required" });
  });
});

function ShareHarness() {
  const [v, setV] = useState("");
  return <ShareInput label="Share" value={v} onChange={setV} />;
}

describe("ShareInput", () => {
  it("shows the reduced fraction and a display-only percentage, or a precise error", async () => {
    renderWithProviders(<ShareHarness />, { tree: null });
    const input = screen.getByLabelText("Share");
    await userEvent.type(input, "2/6");
    expect(screen.getByText(/= 1\/3 \(33\.33%, display only\)/)).toBeInTheDocument();
    await userEvent.clear(input);
    await userEvent.type(input, "0.5");
    expect(screen.getByText(/Use a fraction \(1\/3\), not a decimal/)).toBeInTheDocument();
    expect(input).toHaveAttribute("aria-invalid", "true");
  });
});

describe("partition allocation validation", () => {
  const whole = [frac(1)];
  const alloc = (...shares: string[]) => shares.map((share) => ({ holderOk: true, share }));

  it("accepts allocations that add up exactly to the shares ended", () => {
    const c = checkPartition(whole, alloc("1/3", "1/3", "1/3"), false, true);
    expect(c.errors).toEqual([]);
    expect(c.balanced).toBe(true);
    expect(fmt(c.allocated)).toBe("1");
  });

  it("blocks an unbalanced deed unless it is marked partial (then warns)", () => {
    const c = checkPartition(whole, alloc("1/3", "1/3", "1/4"), false, true);
    expect(c.errors).toEqual(["partition.err.unbalanced"]);
    const partial = checkPartition(whole, alloc("1/3", "1/3", "1/4"), true, true);
    expect(partial.errors).toEqual([]);
    expect(partial.warning).toBe("partition.warnPartial");
  });

  it("reports missing holders, bad shares, zero, over-whole, no date and nothing ended", () => {
    expect(checkPartition(whole, [{ holderOk: false, share: "1" }], false, true).errors).toContain("partition.err.holder");
    expect(checkPartition(whole, alloc("x"), false, true).errors).toContain("partition.err.share");
    expect(checkPartition(whole, alloc("0"), false, true).errors).toContain("partition.err.zeroShare");
    expect(checkPartition(whole, alloc("1", "1/2"), true, true).errors).toContain("partition.err.overWhole");
    expect(checkPartition(whole, alloc("1"), false, false).errors).toContain("partition.err.date");
    expect(checkPartition([], alloc("1"), false, true).errors).toContain("partition.err.nothingEnded");
    expect(checkPartition(whole, [], false, true).errors).toContain("partition.err.noAllocations");
  });

  it("handles a half-share being divided between two branches", () => {
    const c = checkPartition([frac(1, 2)], alloc("1/4", "1/4"), false, true);
    expect(c.errors).toEqual([]);
  });
});

describe("parcel identifiers", () => {
  it("validates ULPIN and extra identifier keys like the server", () => {
    expect(ulpinError("")).toBeNull();
    expect(ulpinError("up0912345678ab")).toBeNull();
    expect(ulpinError("UP12ABC")).toBe("property.parcel.ulpinInvalid");
    expect(ulpinError("UP09-12345678A")).toBe("property.parcel.ulpinInvalid");
    expect(extraKeyError("Bhulekh ID")).toBeNull();
    expect(extraKeyError("bad/key")).toBe("property.parcel.extraKeyInvalid");
  });
});
