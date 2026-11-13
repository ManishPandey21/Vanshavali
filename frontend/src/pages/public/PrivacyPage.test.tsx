import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../../App";
import en from "../../i18n/locales/en.json";
import hi from "../../i18n/locales/hi.json";
import { jsonResponse, renderWithProviders } from "../../test/utils";
import { PRIVACY_SECTIONS, privacyContactEmail, privacyNoticeKeys } from "./PrivacyPage";

type Tree = { [k: string]: string | Tree };
const lookup = (o: Tree, key: string): unknown => key.split(".").reduce<unknown>((v, part) => (v as Tree | undefined)?.[part], o);

function stubSignedOut() {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      calls.push(url);
      if (url.endsWith("/auth/me")) return jsonResponse({ error: { code: "unauthenticated", message: "Authentication required" } }, 401);
      if (url.endsWith("/public/site-impact")) return jsonResponse({ family_trees: 0, unique_visitors_30d: null });
      return jsonResponse([]);
    }),
  );
  return calls;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("privacy notice", () => {
  it("has every key it reads, as non-empty text, in English and Hindi", () => {
    for (const key of privacyNoticeKeys()) {
      expect(typeof lookup(en as Tree, key), `en ${key}`).toBe("string");
      expect(typeof lookup(hi as Tree, key), `hi ${key}`).toBe("string");
      expect((lookup(hi as Tree, key) as string).trim(), `hi ${key}`).not.toBe("");
    }
  });

  it("names every cookie and browser-storage key the app actually uses", () => {
    const storage = JSON.stringify(en.privacyNotice.sections.storage);
    for (const name of ["vsh_session", "vsh_csrf", "vsh_impact_visitor", "vsh_lang", "vsh_recent_", "vsh.treeDraft"]) {
      expect(storage).toContain(name);
    }
  });

  it("is public: a signed-out visitor reads it at /privacy, with a contents list and every section", async () => {
    const calls = stubSignedOut();
    renderWithProviders(<App />, { tree: null, route: "/privacy" });
    expect(await screen.findByRole("heading", { level: 1, name: "Privacy notice" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Welcome back" })).not.toBeInTheDocument();
    const contents = screen.getByRole("navigation", { name: "On this page" });
    expect(within(contents).getAllByRole("link")).toHaveLength(PRIVACY_SECTIONS.length + 1);
    for (const s of PRIVACY_SECTIONS) {
      expect(screen.getByRole("heading", { level: 2, name: en.privacyNotice.sections[s.id as keyof typeof en.privacyNotice.sections].title })).toBeInTheDocument();
    }
    // No contact address configured in tests: point to the support contact, never invent one.
    expect(screen.getByText(/use the support contact you were given/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /@/ })).not.toBeInTheDocument();
    // A static page: it asks only who is signed in.
    expect(calls.every((u) => u.endsWith("/auth/me"))).toBe(true);
  });

  it("is linked from the landing page footer", async () => {
    stubSignedOut();
    renderWithProviders(<App />, { tree: null, route: "/" });
    const footer = (await screen.findByText(/for preserving Indian family heritage/)).closest("footer")!;
    expect(within(footer).getByRole("link", { name: "Privacy notice" })).toHaveAttribute("href", "/privacy");
    await userEvent.click(within(footer).getByRole("link", { name: "Privacy notice" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Privacy notice" })).toBeInTheDocument();
  });

  it.each([
    ["/login", "Welcome back"],
    ["/register", null],
  ])("is linked from the sign-in and register screens (%s)", async (route, heading) => {
    stubSignedOut();
    renderWithProviders(<App />, { tree: null, route });
    if (heading) await screen.findByRole("heading", { name: heading });
    const link = await screen.findByRole("link", { name: "Privacy notice" });
    expect(link).toHaveAttribute("href", "/privacy");
    await userEvent.click(link);
    expect(await screen.findByRole("heading", { level: 1, name: "Privacy notice" })).toBeInTheDocument();
  });

  it("links the configured contact address", async () => {
    vi.stubEnv("VITE_PRIVACY_CONTACT_EMAIL", "privacy@example.org");
    stubSignedOut();
    renderWithProviders(<App />, { tree: null, route: "/privacy" });
    const link = await screen.findByRole("link", { name: "privacy@example.org" });
    expect(link).toHaveAttribute("href", "mailto:privacy@example.org");
    expect(link.closest("p")).toHaveTextContent("For any privacy question or request, write to privacy@example.org.");
  });

  it("accepts only a plain email address as the configured contact", () => {
    expect(privacyContactEmail(undefined)).toBeNull();
    expect(privacyContactEmail("")).toBeNull();
    expect(privacyContactEmail("privacy@example.org")).toBe("privacy@example.org");
    expect(privacyContactEmail("  privacy@example.org ")).toBe("privacy@example.org");
    for (const bad of ["javascript:alert(1)", "not an email", "a@b", "x@y.zz?subject=<b>", "a@b.cc?cc=other@example.org", "\"x\"@y.zz", "a b@c.dd"]) {
      expect(privacyContactEmail(bad)).toBeNull();
    }
  });
});
