import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { jsonResponse, renderWithProviders } from "../../test/utils";
import { LoginPage } from "./AuthPages";

const user = { id: "u1", email: "a@example.com", display_name: "A", preferred_language: "en", created_at: "2026-01-01T00:00:00Z", mfa_enabled: true };

function setup(responses: Response[]) {
  const logins: unknown[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/me")) return jsonResponse({ error: { code: "unauthenticated", message: "Authentication required" } }, 401);
      if (url.endsWith("/auth/login")) {
        logins.push(JSON.parse(String(init?.body)));
        return responses.shift()!;
      }
      return jsonResponse([]);
    }),
  );
  renderWithProviders(
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<p>Home page</p>} />
    </Routes>,
    { tree: null, route: "/login" },
  );
  return logins;
}

describe("login with two-step verification", () => {
  it("asks for the code on mfa_required and resends the login with mfa_code", async () => {
    const logins = setup([
      jsonResponse({ error: { code: "mfa_required", message: "Enter the 6-digit code" } }, 401),
      jsonResponse(user),
    ]);
    await userEvent.type(await screen.findByLabelText(/^Email/), "a@example.com");
    await userEvent.type(screen.getByLabelText(/^Password/), "correct-horse-battery");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    const code = await screen.findByLabelText(/^Authentication code/);
    expect(screen.getByRole("heading", { name: "Two-step verification" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument(); // mfa_required is a step, not an error
    await userEvent.type(code, "123 456");
    await userEvent.click(screen.getByRole("button", { name: "Verify and sign in" }));
    expect(await screen.findByText("Home page")).toBeInTheDocument();
    expect(logins).toEqual([
      { email: "a@example.com", password: "correct-horse-battery" },
      { email: "a@example.com", password: "correct-horse-battery", mfa_code: "123456" },
    ]);
  });

  it("shows a clear error for mfa_invalid and stays on the code step", async () => {
    setup([
      jsonResponse({ error: { code: "mfa_required", message: "Enter the code" } }, 401),
      jsonResponse({ error: { code: "mfa_invalid", message: "Invalid authentication code" } }, 401),
    ]);
    await userEvent.type(await screen.findByLabelText(/^Email/), "a@example.com");
    await userEvent.type(screen.getByLabelText(/^Password/), "correct-horse-battery");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await userEvent.type(await screen.findByLabelText(/^Authentication code/), "000000");
    await userEvent.click(screen.getByRole("button", { name: "Verify and sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That code isn't valid");
    expect(screen.getByLabelText(/^Authentication code/)).toBeInTheDocument();
  });

  it("keeps the verify button disabled until at least 6 digits are entered", async () => {
    setup([jsonResponse({ error: { code: "mfa_required", message: "Enter the code" } }, 401)]);
    await userEvent.type(await screen.findByLabelText(/^Email/), "a@example.com");
    await userEvent.type(screen.getByLabelText(/^Password/), "pw-pw-pw-pw-pw");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await userEvent.type(await screen.findByLabelText(/^Authentication code/), "123");
    await waitFor(() => expect(screen.getByRole("button", { name: "Verify and sign in" })).toBeDisabled());
  });
});
