import { expect, test } from "@playwright/test";
import { PASSWORD, openVerificationLink, uniqueEmail } from "./helpers";

/**
 * ADR-0011: register → guided onboarding (privacy notice, tree, yourself + parents behind the
 * family-data consent) → share a claim link via WhatsApp → the relative opens it, signs up, gives
 * their own consent → the admin approves → the relative sees the tree. Nothing is mocked.
 */
test("onboard a family and bring a relative in through a WhatsApp claim link", async ({ page, browser, baseURL }) => {
  // ---- register, verify the email, and land on the guided first run
  const ownerEmail = uniqueEmail("onboard");
  await page.goto("/register");
  await page.getByLabel("Your name").fill("Asha Iyer");
  await page.getByLabel("Email").fill(ownerEmail);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();
  await openVerificationLink(page, ownerEmail);
  await expect(page.getByRole("heading", { name: "Start your family tree" })).toBeVisible();
  await expect(page.getByText("Your tree is private.")).toBeVisible();
  await page.getByRole("button", { name: "I understand, continue" }).click();

  await page.getByLabel("Tree name").fill("Iyer parivar");
  await page.getByRole("button", { name: "Create my private tree" }).click();

  // ---- add yourself and your father; the consent box must be ticked first
  await expect(page.getByRole("heading", { name: "Add your family" })).toBeVisible();
  await expect(page.getByRole("group", { name: "You" }).getByLabel("Given name")).toHaveValue("Asha");
  await page.getByRole("group", { name: "Father" }).getByLabel("Given name").fill("Ravi");
  const consent = page.getByRole("checkbox", { name: "I agree to add my family members' names to this private tree, and I confirm I have their permission to do so." });
  await expect(consent).not.toBeChecked();
  await page.getByRole("button", { name: "Save and continue" }).click();
  await expect(page.getByText("Please tick the box to continue.")).toBeVisible();
  await consent.check();
  await page.getByRole("button", { name: "Save and continue" }).click();

  // ---- invite the father over WhatsApp
  await expect(page.getByRole("heading", { name: "Invite relatives" })).toBeVisible();
  await page.getByRole("button", { name: "Create a private link for Ravi Iyer" }).click();
  const whatsapp = page.getByRole("link", { name: /Share on WhatsApp/ });
  await expect(whatsapp).toBeVisible();
  const href = (await whatsapp.getAttribute("href"))!;
  expect(href.startsWith("https://wa.me/?text=")).toBe(true);
  const message = decodeURIComponent(href.slice("https://wa.me/?text=".length));
  // the message carries the link only: no names or tree details travel through WhatsApp
  expect(message).not.toContain("Ravi");
  expect(message).not.toContain("Iyer parivar");
  const link = message.match(/https?:\/\/\S+\/claim#[\w-]+/)![0];
  expect(new URL(link).pathname).toBe("/claim");
  await page.getByRole("button", { name: "Go to my tree" }).click();
  await expect(page.getByRole("heading", { name: "Iyer parivar" })).toBeVisible();
  const treeUrl = page.url();

  // ---- the relative opens the link in their own browser and signs up from it
  const relCtx = await browser.newContext({ baseURL });
  const rel = await relCtx.newPage();
  await rel.goto(link.replace(/^https?:\/\/[^/]+/, ""));
  await rel.getByRole("link", { name: "Create account" }).click();
  const relEmail = uniqueEmail("relative");
  await rel.getByLabel("Your name").fill("Ravi Iyer");
  await rel.getByLabel("Email").fill(relEmail);
  await rel.getByLabel("Password").fill(PASSWORD);
  await rel.getByRole("button", { name: "Create account" }).click();
  await expect(rel.getByRole("heading", { name: "Check your email" })).toBeVisible();
  // the verification email carries the claim page in its fragment, so the token never reaches a server
  await openVerificationLink(rel, relEmail);
  await expect(rel).toHaveURL(/\/claim#[\w-]+$/);

  // back on the claim page (the fragment survived sign-up and verification), with a plain-language notice
  await expect(rel.getByText("Asha Iyer added you as “Ravi Iyer” in the private family tree “Iyer parivar”.")).toBeVisible();
  await rel.getByRole("checkbox", { name: /This profile is about me/ }).check();
  await rel.getByRole("checkbox", { name: /I am 18 or older/ }).check();
  await rel.getByRole("button", { name: "Claim my profile" }).click();
  await expect(rel.getByText(/Your request was sent to the tree admins/).first()).toBeVisible();

  // a pending claim shows nothing of the tree
  await rel.goto("/");
  await expect(rel.getByRole("heading", { name: "Your family trees" })).toBeVisible();
  await expect(rel.getByRole("link", { name: /Iyer parivar/ })).toHaveCount(0);

  // ---- the owner sees who is asking, and approves
  await page.goto(`${treeUrl}/admin/claims`);
  await expect(page.getByText("Requested by Ravi Iyer")).toBeVisible();
  await expect(page.getByText(/Came through an invite link/)).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("Approved")).toBeVisible();

  // ---- now the relative is in, linked to their own profile
  await rel.goto("/");
  await rel.getByRole("link", { name: /Iyer parivar/ }).click();
  await expect(rel.getByRole("heading", { name: "Iyer parivar" })).toBeVisible();
  await relCtx.close();
});
