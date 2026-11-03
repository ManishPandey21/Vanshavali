import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../../App";
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
});
