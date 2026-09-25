import { expect, test } from "@playwright/test";
import { PASSWORD, latestMail, linkPath, openVerificationLink, registerWithTree, uniqueEmail } from "./helpers";

/**
 * Account recovery (ADR-0005): "Forgot password?" → generic confirmation → emailed single-use link →
 * new password → every existing session is signed out → sign in with the new password. Also: an
 * unverified account is told to confirm its email on sign-in and can get a fresh link.
 */
test("reset a forgotten password from the emailed link", async ({ browser, context, baseURL }) => {
  const { userEmail } = await registerWithTree(context, baseURL!, "Reset parivar");
  const newPassword = "a-new-e2e-passphrase-77";

  const page = await (await browser.newContext({ baseURL })).newPage();
  await page.goto("/login");
  await page.getByRole("link", { name: "Forgot password?" }).click();
  await expect(page.getByRole("heading", { name: "Reset your password" })).toBeVisible();
  await page.getByLabel("Email").fill(userEmail);
  await page.getByRole("button", { name: "Send reset link" }).click();
  await expect(page.getByRole("status")).toContainText(`If an account uses ${userEmail}`);

  // an unknown address gets exactly the same answer
  await page.goto("/forgot-password");
  await page.getByLabel("Email").fill(uniqueEmail("nobody"));
  await page.getByRole("button", { name: "Send reset link" }).click();
  await expect(page.getByRole("status")).toContainText("we've sent it a password reset link");

  const resetPath = linkPath(await latestMail(userEmail, "password_reset"), "reset-password");
  await page.goto(resetPath);
  await expect(page.getByRole("heading", { name: "Choose a new password" })).toBeVisible();
  await page.getByRole("textbox", { name: "New password", exact: true }).fill(newPassword);
  await page.getByLabel("Confirm new password").fill("something else entirely");
  await page.getByRole("button", { name: "Set new password" }).click();
  await expect(page.getByText("The passwords don't match.")).toBeVisible();
  await page.getByLabel("Confirm new password").fill(newPassword);
  await page.getByRole("button", { name: "Set new password" }).click();
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "Your password has been reset" })).toBeVisible();

  // the owner's original session (the `context` fixture) was revoked
  const me = await context.request.get(`${baseURL}/api/v1/auth/me`);
  expect(me.status()).toBe(401);

  // old password no longer works; the new one does
  await page.getByLabel("Email").fill(userEmail);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toContainText("don't match an account");
  await page.getByLabel("Password").fill(newPassword);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Your family trees" })).toBeVisible();
  await expect(page.getByText("Reset parivar")).toBeVisible();

  // the link is single use
  await page.goto(resetPath);
  await page.getByRole("textbox", { name: "New password", exact: true }).fill("yet-another-passphrase");
  await page.getByLabel("Confirm new password").fill("yet-another-passphrase");
  await page.getByRole("button", { name: "Set new password" }).click();
  await expect(page.getByRole("alert")).toContainText("This link is invalid or has expired.");
});

test("an unverified account is asked to confirm its email and can resend the link", async ({ page }) => {
  const email = uniqueEmail("unverified");
  await page.goto("/register");
  await page.getByLabel("Your name").fill("Late Verifier");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();
  const first = linkPath(await latestMail(email, "verify_email"), "verify-email");

  await page.getByRole("link", { name: "Back to sign in" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toContainText("Please confirm your email address first");
  await page.getByRole("button", { name: "Send the link again" }).click();
  await expect(page.getByText("we've sent a new link")).toBeVisible();

  // the new link replaced the first one
  await expect.poll(async () => linkPath(await latestMail(email, "verify_email"), "verify-email")).not.toBe(first);
  await openVerificationLink(page, email);
  await expect(page.getByRole("heading", { name: "Your family trees" })).toBeVisible();
});
