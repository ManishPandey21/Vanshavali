import { describe, expect, it } from "vitest";
import { safeNext } from "./AuthPages";

describe("safeNext (post-login redirect guard)", () => {
  it("keeps same-origin paths with query and hash", () => {
    expect(safeNext("/t/abc/people?q=ram#top")).toBe("/t/abc/people?q=ram#top");
  });

  it.each([
    null,
    "",
    "https://evil.example/",
    "//evil.example/",
    "/\\evil.example/",
    "/\\/evil.example",
    "\\\\evil.example",
    "/%0a//evil.example",
    "/\tevil",
    "javascript:alert(1)",
  ])("never leaves the site for %s", (value) => {
    const out = safeNext(value);
    expect(out.startsWith("/")).toBe(true);
    expect(out.startsWith("//")).toBe(false);
    expect(out).not.toMatch(/\\/);
    expect(new URL(out, window.location.origin).origin).toBe(window.location.origin);
  });

  it("rejects backslash open-redirect variants outright", () => {
    expect(safeNext("/\\evil.example")).toBe("/");
  });
});
