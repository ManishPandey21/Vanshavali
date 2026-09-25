import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { jsonResponse, renderWithProviders } from "../../test/utils";
import { LoginPage, RegisterPage } from "./AuthPages";
import { ForgotPasswordPage, ResetPasswordPage, VerifyEmailPage } from "./EmailPages";

const user = { id: "u1", email: "a@example.com", display_name: "A", preferred_language: "en", created_at: "2026-01-01T00:00:00Z", mfa_enabled: false, email_verified: true };
const unauth = () => jsonResponse({ error: { code: "unauthenticated", message: "Authentication required" } }, 401);

type Handler = (body: unknown) => Response;

function setup(route: string, handlers: Record<string, Handler>) {
  const calls: { path: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = String(url).replace(/^.*\/api\/v1/, "").split("?")[0];
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      if (path === "/auth/me") return unauth();
      calls.push({ path, body });
      const h = handlers[path];
      return h ? h(body) : jsonResponse({});
    }),
  );
  renderWithProviders(
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/verify-email/:token" element={<VerifyEmailPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password/:token" element={<ResetPasswordPage />} />
      <Route path="/" element={<p>Trees list</p>} />
      <Route path="/invite/:token" element={<p>Invitation page</p>} />
    </Routes>,
    { tree: null, route },
  );
  return calls;
}

const accepted = () => jsonResponse({ message: "If this email can be registered, we've sent a link to it." }, 202);

describe("registration", () => {
  it("shows a check-your-email state instead of signing in, and can resend", async () => {
    const calls = setup("/register?next=%2Finvite%2Fabc", {
      "/auth/register": accepted,
      "/auth/resend-verification": () => jsonResponse({ message: "ok" }, 202),
    });
    await userEvent.type(await screen.findByLabelText(/^Your name/), "Asha");
    await userEvent.type(screen.getByLabelText(/^Email/), "asha@example.com");
    await userEvent.type(screen.getByLabelText(/^Password/), "a-long-passphrase");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("heading", { name: "Check your email" })).toBeInTheDocument();
    expect(screen.getByText(/If asha@example.com can be registered/)).toBeInTheDocument();
    expect(calls[0]).toEqual({
      path: "/auth/register",
      body: { email: "asha@example.com", password: "a-long-passphrase", display_name: "Asha", preferred_language: "en", next: "/invite/abc" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Send the link again" }));
    expect(await screen.findByText(/we've sent a new link/, { selector: "p" })).toBeInTheDocument();
    expect(calls[1]).toEqual({ path: "/auth/resend-verification", body: { email: "asha@example.com" } });
  });
});

describe("login", () => {
  it("offers to resend the link when the email is not verified", async () => {
    const calls = setup("/login", {
      "/auth/login": () => jsonResponse({ error: { code: "email_not_verified", message: "Please confirm" } }, 403),
      "/auth/resend-verification": () => jsonResponse({ message: "ok" }, 202),
    });
    await userEvent.type(await screen.findByLabelText(/^Email/), "a@example.com");
    await userEvent.type(screen.getByLabelText(/^Password/), "a-long-passphrase");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Please confirm your email address first");
    await userEvent.click(screen.getByRole("button", { name: "Send the link again" }));
    expect(await screen.findByText(/we've sent a new link/)).toBeInTheDocument();
    expect(calls.at(-1)).toEqual({ path: "/auth/resend-verification", body: { email: "a@example.com" } });
  });

  it("links to the forgot-password page", async () => {
    setup("/login", {});
    await userEvent.click(await screen.findByRole("link", { name: "Forgot password?" }));
    expect(await screen.findByRole("heading", { name: "Reset your password" })).toBeInTheDocument();
  });
});

describe("verify email", () => {
  it("sends the token once, signs in and goes to the trees list", async () => {
    const calls = setup("/verify-email/tok-123456789", { "/auth/verify-email": () => jsonResponse(user) });
    expect(await screen.findByText("Trees list")).toBeInTheDocument();
    expect(calls.filter((c) => c.path === "/auth/verify-email")).toEqual([{ path: "/auth/verify-email", body: { token: "tok-123456789" } }]);
  });

  it("continues to a same-site next path, never an external one", async () => {
    setup("/verify-email/tok-123456789?next=%2Finvite%2Fabc", { "/auth/verify-email": () => jsonResponse(user) });
    expect(await screen.findByText("Invitation page")).toBeInTheDocument();
  });

  it("ignores an off-site next path", async () => {
    setup("/verify-email/tok-123456789?next=%2F%2Fevil.example", { "/auth/verify-email": () => jsonResponse(user) });
    expect(await screen.findByText("Trees list")).toBeInTheDocument();
  });

  it("explains an invalid or expired link", async () => {
    setup("/verify-email/used-token-1234", {
      "/auth/verify-email": () => jsonResponse({ error: { code: "token_invalid", message: "This link is invalid" } }, 400),
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("This link is invalid or has expired.");
    expect(screen.getByRole("link", { name: "Back to sign in" })).toBeInTheDocument();
  });
});

describe("password reset", () => {
  it("request always shows the same confirmation", async () => {
    const calls = setup("/forgot-password", { "/auth/password-reset/request": () => jsonResponse({ message: "ok" }, 202) });
    await userEvent.type(await screen.findByLabelText(/^Email/), "who@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(await screen.findByRole("status")).toHaveTextContent("If an account uses who@example.com");
    expect(calls).toEqual([{ path: "/auth/password-reset/request", body: { email: "who@example.com" } }]);
  });

  it("checks the two passwords match, then resets and returns to sign in", async () => {
    const calls = setup("/reset-password/reset-token-123", {
      "/auth/password-reset/confirm": () => jsonResponse({ message: "done" }),
    });
    await userEvent.type(await screen.findByLabelText(/^New password/), "a brand new passphrase");
    await userEvent.type(screen.getByLabelText(/^Confirm new password/), "a different passphrase");
    await userEvent.click(screen.getByRole("button", { name: "Set new password" }));
    expect(await screen.findByText("The passwords don't match.")).toBeInTheDocument();
    expect(calls).toEqual([]);

    await userEvent.clear(screen.getByLabelText(/^Confirm new password/));
    await userEvent.type(screen.getByLabelText(/^Confirm new password/), "a brand new passphrase");
    await userEvent.click(screen.getByRole("button", { name: "Set new password" }));
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Your password has been reset");
    expect(calls).toEqual([{ path: "/auth/password-reset/confirm", body: { token: "reset-token-123", new_password: "a brand new passphrase" } }]);
  });

  it("offers a new link when the reset link is invalid", async () => {
    setup("/reset-password/old-token-1234", {
      "/auth/password-reset/confirm": () => jsonResponse({ error: { code: "token_invalid", message: "invalid" } }, 400),
    });
    await userEvent.type(await screen.findByLabelText(/^New password/), "a brand new passphrase");
    await userEvent.type(screen.getByLabelText(/^Confirm new password/), "a brand new passphrase");
    await userEvent.click(screen.getByRole("button", { name: "Set new password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This link is invalid or has expired.");
    await waitFor(() => expect(screen.getByRole("link", { name: "Request a new reset link" })).toHaveAttribute("href", "/forgot-password"));
  });
});
