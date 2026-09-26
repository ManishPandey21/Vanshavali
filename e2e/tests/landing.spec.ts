import { expect, test } from "@playwright/test";
import { PASSWORD, openVerificationLink, uniqueEmail } from "./helpers";

/**
 * Public landing page: a signed-out visitor to "/" sees it (in English or Hindi), can start a tree
 * from it, and once signed in "/about" still shows the page and leads back to their trees.
 */
test("signed-out visitors land on the heritage page and can begin a tree from it", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: /Preserving the threads of tradition/ })).toBeVisible();
  await expect(page.getByText("॥ वसुधैव कुटुम्बकम् ॥").first()).toBeVisible();
  await expect(page.getByText(/for preserving Indian family heritage/)).toBeVisible();

  await page.getByRole("combobox", { name: "Language" }).first().selectOption("hi");
  await expect(page.getByRole("heading", { level: 1, name: /परंपरा के धागों को सहेजते हुए/ })).toBeVisible();
  await page.getByRole("combobox", { name: "भाषा" }).first().selectOption("en");

  await page.getByRole("link", { name: /Begin your family tree/ }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.getByRole("link", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/register$/);
  const email = uniqueEmail("landing");
  await page.getByLabel("Your name").fill("Landing Visitor");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();
  await openVerificationLink(page, email);
  await expect(page.getByRole("heading", { name: "Start your family tree" })).toBeVisible();

  await page.goto("/about");
  await page.getByRole("link", { name: /Go to my family trees/ }).first().click();
  await expect(page.getByRole("heading", { name: "Your family trees" })).toBeVisible();
});
