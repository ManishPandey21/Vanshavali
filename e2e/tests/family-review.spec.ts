import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { api, attest, createPerson, registerVerified, registerWithTree, uniqueEmail } from "./helpers";

/**
 * Change proposals and family review (ADR-0021) against the real stack, on a phone-sized screen:
 * a contributor's edit waits for review, the owner approves it from a notification, the person's
 * history records who proposed and who reviewed it, and duplicates are suggested at entry.
 */
test.use({ viewport: { width: 390, height: 844 } });

async function noSeriousAxe(page: Page) {
  const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"]).analyze();
  const blocking = axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
}

test("a contributor's change waits for the family's review, then is applied", async ({ page, browser, baseURL }) => {
  const owner = page.context();
  const { treeId } = await registerWithTree(owner, baseURL!, "Sharma parivar", "Dadaji");
  const kamla = await createPerson(owner, baseURL!, treeId, "Kamla", "Sharma", { profile_status: "deceased", sex_at_birth: "female" });
  await api(owner, "PUT", `/trees/${treeId}/review-policy`, { review_policy: "all" }, baseURL!);

  // a contributor joins
  const cousinCtx = await browser.newContext({ baseURL, viewport: { width: 390, height: 844 } });
  const cousinEmail = uniqueEmail("cousin");
  await registerVerified(cousinCtx, baseURL!, cousinEmail, "Cousin Ravi");
  const invite = await api<{ token: string }>(owner, "POST", `/trees/${treeId}/invitations`, { email: cousinEmail, roles: ["CONTRIBUTOR"] }, baseURL!);
  await api(cousinCtx, "POST", `/invitations/${invite.token}/accept`, {}, baseURL!);
  await attest(cousinCtx, baseURL!, treeId);

  // the contributor corrects a name: the family reviews such changes, so it becomes a proposal
  const cousin = await cousinCtx.newPage();
  await cousin.goto(`/t/${treeId}/people/${kamla.id}`);
  await cousin.getByRole("button", { name: /Edit name Kamla Sharma/ }).click();
  const nameDialog = cousin.getByRole("dialog", { name: "Edit name" });
  await nameDialog.getByLabel("Given name").fill("Kamala");
  await nameDialog.getByRole("button", { name: "Save" }).click();
  const propose = cousin.getByRole("dialog", { name: "Send this change for review" });
  await expect(propose).toBeVisible();
  await expect(propose.getByText("Given name: Kamala")).toBeVisible();
  await propose.getByLabel(/Why this change is right/).fill("Her school certificate spells it Kamala");
  await noSeriousAxe(cousin);
  await propose.getByRole("button", { name: "Send for review" }).click();
  await expect(propose.getByText(/Sent for review/)).toBeVisible();
  // nothing changed yet
  const before = await api<{ names: { given_name: string }[] }>(owner, "GET", `/trees/${treeId}/people/${kamla.id}`, undefined, baseURL!);
  expect(before.names.map((n) => n.given_name)).toEqual(["Kamla"]);

  // the owner is notified and approves
  await page.goto(`/t/${treeId}`);
  await page.getByRole("button", { name: "Notifications, 1 unread" }).first().click();
  await page.getByRole("link", { name: /Cousin Ravi proposed 1 change\(s\) to Kamla Sharma/ }).click();
  await expect(page.getByRole("heading", { level: 1, name: "1 change to Kamla Sharma" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Kamala" })).toBeVisible();
  await noSeriousAxe(page);
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("Accepted")).toBeVisible();

  // applied, family-confirmed, and in the history with both people named
  await page.goto(`/t/${treeId}/people/${kamla.id}`);
  await expect(page.getByText("Family-confirmed")).toBeVisible();
  await page.getByRole("tab", { name: "History" }).click();
  // the name and the display name that follows it: both proposed by the cousin, reviewed by Dadaji
  await expect(page.getByText(/Cousin Ravi · reviewed by Dadaji/).first()).toBeVisible();
  await noSeriousAxe(page);
  await cousinCtx.close();
});

test("adding someone who is already in the tree is noticed before saving", async ({ page, baseURL }) => {
  const owner = page.context();
  const { treeId } = await registerWithTree(owner, baseURL!, "Verma parivar");
  await createPerson(owner, baseURL!, treeId, "Shanti", "Verma", { profile_status: "deceased", sex_at_birth: "female" });
  await page.goto(`/t/${treeId}/people/new`);
  const consent = page.getByRole("checkbox", { name: /I confirm I have their permission/ });
  if (await consent.isVisible().catch(() => false)) {
    await consent.check();
    await page.getByRole("button", { name: "Confirm and continue" }).click();
  }
  const name1 = page.getByRole("group", { name: "Name 1" });
  await name1.getByLabel("Given name").fill("Shanti");
  await name1.getByLabel("Surname / family name").fill("Verma");
  const panel = page.getByRole("status").filter({ hasText: "Already in the tree?" });
  await expect(panel).toBeVisible();
  await expect(panel.getByRole("link", { name: "Shanti Verma" })).toBeVisible();
  await expect(panel.getByText("same name")).toBeVisible();
  await noSeriousAxe(page);
  await panel.getByRole("button", { name: "This is someone else" }).click();
  await expect(panel).toBeHidden();
});
