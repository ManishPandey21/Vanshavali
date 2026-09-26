import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
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

afterEach(() => vi.unstubAllGlobals());

describe("landing page", () => {
  it("is what a signed-out visitor sees at the home page, with a way to start and to sign in", async () => {
    const calls = stubApi(false);
    renderWithProviders(<App />, { tree: null, route: "/" });
    expect(await screen.findByRole("heading", { level: 1, name: /Preserving the threads of tradition/ })).toBeInTheDocument();
    expect(screen.getAllByText("॥ वसुधैव कुटुम्बकम् ॥").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /Begin your family tree/ })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
    expect(screen.getByText(/for preserving Indian family heritage/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Tambool offering/ })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /tree viewer in Hindi/ })).toHaveAttribute("src", "/landing/tree-viewer-hi.png");
    // Static page: it asks only who is signed in, never for family data.
    expect(calls.every((u) => u.endsWith("/auth/me"))).toBe(true);
  });

  it("does not replace the signed-in home page", async () => {
    stubApi(true);
    renderWithProviders(<App />, { tree: null, route: "/" });
    expect(await screen.findByRole("heading", { name: "Your family trees" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1, name: /Preserving the threads/ })).not.toBeInTheDocument();
  });

  it("stays reachable at /about when signed in, pointing back to the user's trees", async () => {
    stubApi(true);
    renderWithProviders(<App />, { tree: null, route: "/about" });
    expect(await screen.findByRole("heading", { level: 1, name: /Preserving the threads/ })).toBeInTheDocument();
    expect((await screen.findAllByRole("link", { name: /Go to my family trees/ }))[0]).toHaveAttribute("href", "/");
    expect(screen.queryByRole("link", { name: "Sign in" })).not.toBeInTheDocument();
  });

  it("still sends signed-out visitors of private pages to sign in", async () => {
    stubApi(false);
    renderWithProviders(<App />, { tree: null, route: "/account" });
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
  });
});
