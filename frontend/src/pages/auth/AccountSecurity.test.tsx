import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../../App";
import { jsonResponse, renderWithProviders } from "../../test/utils";

const base = { id: "u1", email: "pandey@example.com", display_name: "P", preferred_language: "en", created_at: "2026-01-01T00:00:00Z", mfa_enabled: false, email_verified: true };

type Handler = (init?: RequestInit) => Response | Promise<Response>;

function stub(routes: Record<string, Handler>) {
  const calls: { url: string; body?: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      for (const [suffix, h] of Object.entries(routes)) if (url.endsWith(suffix)) return h(init);
      return jsonResponse([]);
    }),
  );
  return calls;
}

const signedOut = () => jsonResponse({ error: { code: "unauthenticated", message: "Authentication required" } }, 401);

afterEach(() => vi.unstubAllGlobals());

describe("Sign in with Google", () => {
  it("hides the button when the server has no Google sign-in", async () => {
    stub({ "/auth/me": signedOut, "/auth/providers": () => jsonResponse({ google: false }) });
    renderWithProviders(<App />, { tree: null, route: "/login" });
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("link", { name: /Continue with Google/ })).not.toBeInTheDocument());
  });

  it("links to the server-side flow, carrying only a same-site next path", async () => {
    stub({ "/auth/me": signedOut, "/auth/providers": () => jsonResponse({ google: true }) });
    renderWithProviders(<App />, { tree: null, route: "/login?next=%2Ft%2Ftree-1" });
    const link = await screen.findByRole("link", { name: /Continue with Google/ });
    expect(link).toHaveAttribute("href", "/api/v1/auth/google/start?next=%2Ft%2Ftree-1");
  });

  it("never forwards an off-site next to the server", async () => {
    stub({ "/auth/me": signedOut, "/auth/providers": () => jsonResponse({ google: true }) });
    renderWithProviders(<App />, { tree: null, route: "/login?next=%2F%2Fevil.example" });
    const link = await screen.findByRole("link", { name: /Continue with Google/ });
    expect(link).toHaveAttribute("href", "/api/v1/auth/google/start?next=%2F");
  });

  it("explains why a Google sign-in came back", async () => {
    stub({ "/auth/me": signedOut, "/auth/providers": () => jsonResponse({ google: true }) });
    renderWithProviders(<App />, { tree: null, route: "/login?oauth_error=mfa_enabled" });
    expect(await screen.findByRole("alert")).toHaveTextContent(/two-step verification/);
  });

  it("shows a generic message for unknown error codes", async () => {
    stub({ "/auth/me": signedOut, "/auth/providers": () => jsonResponse({ google: true }) });
    renderWithProviders(<App />, { tree: null, route: "/login?oauth_error=%3Cscript%3E" });
    expect(await screen.findByRole("alert")).toHaveTextContent("Google sign-in didn't complete. Please try again.");
  });
});

describe("forced password change", () => {
  it("sends a temporary-password account to the change screen from any page", async () => {
    stub({ "/auth/me": () => jsonResponse({ ...base, must_change_password: true }) });
    renderWithProviders(<App />, { tree: null, route: "/t/tree-1/people" });
    expect(await screen.findByRole("heading", { name: "Choose a new password" })).toBeInTheDocument();
    expect(screen.getByText(/pandey@example.com was set up with a temporary password/)).toBeInTheDocument();
  });

  it("checks the new password locally, then posts it and continues", async () => {
    let flagged = true;
    const calls = stub({
      "/auth/me": () => jsonResponse({ ...base, must_change_password: flagged }),
      "/auth/password": () => {
        flagged = false;
        return jsonResponse({ message: "ok" });
      },
    });
    renderWithProviders(<App />, { tree: null, route: "/" });
    await screen.findByRole("heading", { name: "Choose a new password" });
    await userEvent.type(screen.getByLabelText(/^Temporary password/), "temporary-Pa55word!");
    await userEvent.type(screen.getByLabelText(/^New password/), "temporary-Pa55word!");
    await userEvent.type(screen.getByLabelText(/^Confirm new password/), "temporary-Pa55word!");
    await userEvent.click(screen.getByRole("button", { name: "Save new password" }));
    expect(screen.getAllByText("Choose a password different from the temporary one.").length).toBeGreaterThan(0);
    expect(calls.some((c) => c.url.endsWith("/auth/password"))).toBe(false);

    await userEvent.clear(screen.getByLabelText(/^New password/));
    await userEvent.type(screen.getByLabelText(/^New password/), "a-brand-new-passphrase");
    await userEvent.clear(screen.getByLabelText(/^Confirm new password/));
    await userEvent.type(screen.getByLabelText(/^Confirm new password/), "a-brand-new-passphrase");
    await userEvent.click(screen.getByRole("button", { name: "Save new password" }));
    expect(await screen.findByRole("heading", { name: "Your family trees" })).toBeInTheDocument();
    expect(calls.find((c) => c.url.endsWith("/auth/password"))?.body).toEqual({
      current_password: "temporary-Pa55word!",
      new_password: "a-brand-new-passphrase",
    });
  });

  it("leaves ordinary accounts alone", async () => {
    stub({ "/auth/me": () => jsonResponse({ ...base, must_change_password: false }) });
    renderWithProviders(<App />, { tree: null, route: "/change-password" });
    expect(await screen.findByRole("heading", { name: "Your family trees" })).toBeInTheDocument();
  });
});
