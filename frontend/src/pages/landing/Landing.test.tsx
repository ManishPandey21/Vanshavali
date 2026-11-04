import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../../App";
import i18n from "../../i18n";
import { jsonResponse, renderWithProviders } from "../../test/utils";

const user = { id: "u1", email: "a@example.com", display_name: "A", preferred_language: "en", created_at: "2026-01-01T00:00:00Z", mfa_enabled: false };

function stubApi(signedIn: boolean) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      calls.push(url);
      if (url.endsWith("/auth/me")) {
        return signedIn ? jsonResponse(user) : jsonResponse({ error: { code: "unauthenticated", message: "Authentication required" } }, 401);
      }
      return jsonResponse([]);
    }),
  );
  return calls;
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
});

describe("landing page", () => {
  it("is what a signed-out visitor sees at the home page, with a way to start and to sign in", async () => {
    const calls = stubApi(false);
    renderWithProviders(<App />, { tree: null, route: "/" });
    expect(await screen.findByRole("heading", { level: 1, name: /Preserving the Threads of Tradition/ })).toBeInTheDocument();
    expect(screen.getAllByText("॥ वसुधैव कुटुम्बकम् ॥").length).toBeGreaterThan(0);
    for (const link of screen.getAllByRole("link", { name: /Begin your family tree/ })) expect(link).toHaveAttribute("href", "/login");
    expect(screen.getAllByRole("link", { name: "Sign in" })[0]).toHaveAttribute("href", "/login");
    expect(screen.getByText(/for preserving Indian family heritage/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Tambool offering/ })).toBeInTheDocument();
    // without IntersectionObserver (jsdom) the family tree shows finished, kinship included
    expect(screen.getByRole("img", { name: /family tree growing generation by generation/ })).toBeInTheDocument();
    expect(screen.getByText("Suresh is Aarav's दादा (dādā) — his father's father")).toBeInTheDocument();
    // Static page: it asks only who is signed in, never for family data.
    expect(calls.every((u) => u.endsWith("/auth/me"))).toBe(true);
  });

  it("does not replace the signed-in home page", async () => {
    stubApi(true);
    renderWithProviders(<App />, { tree: null, route: "/" });
    expect(await screen.findByRole("heading", { name: "Your family trees" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1, name: /Preserving the threads/i })).not.toBeInTheDocument();
  });

  it("stays reachable at /about when signed in, pointing back to the user's trees", async () => {
    stubApi(true);
    renderWithProviders(<App />, { tree: null, route: "/about" });
    expect(await screen.findByRole("heading", { level: 1, name: /Preserving the threads/i })).toBeInTheDocument();
    expect((await screen.findAllByRole("link", { name: /Go to my family trees/ }))[0]).toHaveAttribute("href", "/");
    expect(screen.queryByRole("link", { name: "Sign in" })).not.toBeInTheDocument();
  });

  it("still sends signed-out visitors of private pages to sign in", async () => {
    stubApi(false);
    renderWithProviders(<App />, { tree: null, route: "/account" });
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
  });

  it("lets a visitor plant three generations before signing up, keeping the names in this tab only", async () => {
    const calls = stubApi(false);
    renderWithProviders(<App />, { tree: null, route: "/" });
    expect(await screen.findByRole("link", { name: /Try it now/ })).toHaveAttribute("href", "#plant");
    const preview = screen.getByRole("list", { name: "Preview of your family tree" });
    expect(screen.getByText(/Start with your own name/)).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText(/Your name/), "Aarav Sharma");
    expect(screen.getByLabelText(/Your father's name/)).toHaveAttribute("placeholder", "e.g. Ramesh Sharma");
    await userEvent.type(screen.getByLabelText(/Your father's name/), "Ramesh Sharma");
    await userEvent.type(screen.getByLabelText(/Your mother's name/), "Sunita Sharma");
    await userEvent.type(screen.getByLabelText(/Your grandfather's name/), "Suresh Sharma");

    for (const name of ["Aarav Sharma", "Ramesh Sharma", "Sunita Sharma", "Suresh Sharma"]) expect(within(preview).getByText(name)).toBeInTheDocument();
    expect(screen.getByText("The Sharma family")).toBeInTheDocument();
    expect(screen.getByText("Three generations of Sharma — your vanshavali has begun.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Save my family tree/ })).toHaveAttribute("href", "/register");
    expect(JSON.parse(window.sessionStorage.getItem("vsh.treeDraft") ?? "{}")).toMatchObject({ self: "Aarav Sharma", grandfather: "Suresh Sharma" });
    // typing names sends nothing anywhere
    expect(calls.every((u) => u.endsWith("/auth/me"))).toBe(true);

    await userEvent.click(screen.getByRole("button", { name: "Clear names" }));
    expect(window.sessionStorage.getItem("vsh.treeDraft")).toBeNull();
    expect(within(preview).queryByText("Aarav Sharma")).not.toBeInTheDocument();
  });

  it("explains how to begin in three steps, each leading somewhere real", async () => {
    stubApi(false);
    renderWithProviders(<App />, { tree: null, route: "/" });
    const how = await screen.findByRole("region", { name: /Your family's story, in three simple steps/ });
    const steps = within(how).getAllByRole("listitem");
    expect(steps.map((li) => within(li).getByRole("heading", { level: 3 }).textContent)).toEqual([
      "Plant the seed",
      "Gather the elders' memories",
      "Invite the family",
    ]);
    // each step's action goes to something that exists: the planter on this page, sign-in, the privacy section
    expect(within(steps[0]!).getByRole("link", { name: /Plant your tree now/ })).toHaveAttribute("href", "#plant");
    expect(within(steps[1]!).getByRole("link", { name: /Begin your family tree/ })).toHaveAttribute("href", "/login");
    expect(within(steps[2]!).getByRole("link", { name: /How we keep it private/ })).toHaveAttribute("href", "#trust");
    expect(document.getElementById("plant")).not.toBeNull();
    expect(document.getElementById("trust")).not.toBeNull();
  });

  it("states the four privacy promises the server enforces, with a way to start", async () => {
    stubApi(false);
    renderWithProviders(<App />, { tree: null, route: "/" });
    const trust = await screen.findByRole("region", { name: /Your family's trust, kept with care/ });
    expect(within(trust).getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual([
      "Private and invite-only",
      "Living relatives protected",
      "You decide who sees what",
      "Your records stay yours",
    ]);
    expect(within(trust).getByText(/shown only to tree admins/)).toBeInTheDocument();
    expect(within(trust).getByText(/marked public one by one/)).toBeInTheDocument();
    expect(within(trust).getByRole("link", { name: /Begin your family tree/ })).toHaveAttribute("href", "/login");
    // the footer can jump to both new sections (the header row is kept to its five links)
    expect(screen.getAllByRole("link", { name: "How it works" })[0]).toHaveAttribute("href", "#how");
    expect(screen.getAllByRole("link", { name: "Privacy" })[0]).toHaveAttribute("href", "#trust");
  });

  it("renders the new sections in Hindi without repeating the trust word", async () => {
    stubApi(false);
    await i18n.changeLanguage("hi");
    try {
      renderWithProviders(<App />, { tree: null, route: "/" });
      expect(await screen.findByRole("region", { name: /आपके परिवार की कहानी/ })).toBeInTheDocument();
      const trust = screen.getByRole("region", { name: /आपके परिवार का भरोसा/ });
      expect(within(trust).getByText("विश्वास से सुरक्षित")).toBeInTheDocument();
      expect(within(trust).queryByText("॥ विश्वास ॥")).not.toBeInTheDocument();
    } finally {
      await i18n.changeLanguage("en");
    }
  });

  it("lets a visitor explore the sample family in the real tree viewer, without any family data from the server", async () => {
    const calls = stubApi(false);
    renderWithProviders(<App />, { tree: null, route: "/" });
    const watch = await screen.findByRole("button", { name: "Watch it grow" });
    expect(watch).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getByRole("button", { name: "Explore it yourself" }));
    expect(screen.getByRole("button", { name: "Explore it yourself" })).toHaveAttribute("aria-pressed", "true");

    const chart = screen.getByRole("group", { name: "Family tree chart" });
    expect(within(chart).getByRole("button", { name: /^Private person/ })).toBeInTheDocument();
    expect(within(chart).getByRole("button", { name: /^Aarav Sharma.*This is you\.$/ })).toBeInTheDocument();

    const panel = screen.getByRole("region", { name: "About the person you chose" });
    expect(within(panel).getByText(/see who they are to Aarav Sharma/)).toBeInTheDocument();
    await userEvent.click(within(chart).getByRole("button", { name: /^Suresh Sharma/ }));
    expect(within(chart).getByRole("button", { name: /^Suresh Sharma/ })).toHaveAttribute("aria-current", "true");
    expect(within(panel).getByText("दादा")).toBeInTheDocument();
    expect(within(panel).getByText("(father's father)")).toBeInTheDocument();
    expect(within(panel).getByText(/bahi of births and marriages/)).toBeInTheDocument();

    await userEvent.click(within(chart).getByRole("button", { name: /^Mahesh Sharma/ }));
    expect(within(panel).getByText("चाचा / ताऊ")).toBeInTheDocument();
    expect(within(panel).getByText(/visible only to tree admins/)).toBeInTheDocument();
    expect(within(panel).getByRole("link", { name: /Begin your family tree/ })).toHaveAttribute("href", "/login");
    // fictional and static: exploring asks the server for nothing
    expect(calls.every((u) => u.endsWith("/auth/me"))).toBe(true);
  });
});
