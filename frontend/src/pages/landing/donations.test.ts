import { describe, expect, it } from "vitest";
import { DONATION_AMOUNTS, parseVoluntaryAmount, safeHostedDonationLink } from "./donations";

describe("voluntary contribution", () => {
  it("keeps the five preset choices", () => {
    expect(DONATION_AMOUNTS).toEqual([10, 50, 100, 1000, 10000]);
  });

  it("accepts whole-rupee voluntary amounts within bounds", () => {
    for (const amount of ["1", "25", "250", "100000"]) {
      expect(parseVoluntaryAmount(amount)).toBe(Number(amount));
    }
  });

  it("rejects empty, fractional, negative, malformed, and oversized amounts", () => {
    for (const amount of ["", "0", "-5", "10.5", "1e3", " 100", "100 ", "1,000", "100001", "Infinity", "abc"]) {
      expect(parseVoluntaryAmount(amount)).toBeNull();
    }
  });

  it("allows only HTTPS hosted checkout links on a recognized provider host", () => {
    expect(safeHostedDonationLink("https://pages.razorpay.com/example")).toBe("https://pages.razorpay.com/example");
    expect(safeHostedDonationLink("https://rzp.io/i/example")).toBe("https://rzp.io/i/example");
    for (const url of [undefined, "", "http://pages.razorpay.com/example", "https://example.com/checkout", "https://pages.razorpay.com.evil.example/"]) {
      expect(safeHostedDonationLink(url)).toBeNull();
    }
  });
});
