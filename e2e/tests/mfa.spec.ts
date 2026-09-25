import { expect, test } from "@playwright/test";
import { PASSWORD, freshTotpWindow, totp, uniqueEmail } from "./helpers";

/** Two-step verification: enable with a TOTP code computed in the test, sign out, sign in with a code. */
test("enable two-step verification and sign in with an authenticator code", async ({ page }) => {
  const email = uniqueEmail("mfa");
  await page.goto("/register");
  await page.getByLabel("Your name").fill("MFA Tester");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Start your family tree" })).toBeVisible();

  await page.goto("/account");
  await page.getByRole("button", { name: "Set up two-step verification" }).click();
  const secret = (await page.getByTestId("mfa-secret").innerText()).trim();
  expect(secret).toMatch(/^[A-Z2-7]{16,}=*$/);
  await freshTotpWindow();
  await page.getByLabel("Authentication code").fill(await totp(secret));
  await page.getByRole("button", { name: "Turn on" }).click();
  await expect(page.getByRole("heading", { name: /Two-step verification/ }).getByText("On")).toBeVisible();

  // sign out, then sign in: password first, then the code step
  await page.getByRole("button", { name: "Sign out" }).first().click();
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Two-step verification" })).toBeVisible();

  // a wrong code is refused and keeps us on the code step
  await page.getByLabel("Authentication code").fill("000000");
  await page.getByRole("button", { name: "Verify and sign in" }).click();
  await expect(page.getByRole("alert")).toContainText("That code isn't valid");

  await freshTotpWindow();
  await page.getByLabel("Authentication code").fill(await totp(secret));
  await page.getByRole("button", { name: "Verify and sign in" }).click();
  await expect(page.getByRole("heading", { name: "Your family trees" })).toBeVisible();
});
