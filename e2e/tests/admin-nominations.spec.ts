import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { api, attest, registerVerified, registerWithTree, uniqueEmail } from "./helpers";

/**
 * Family Admin nominations (ADR-0006 amendment of 9 Nov 2026) against the real stack, on a
 * phone-sized screen: a family admin nominates a cousin, the cousin accepts from a notification,
 * and only the owner's approval makes the cousin a family admin.
 */
test.use({ viewport: { width: 390, height: 844 } });

async function noSeriousAxe(page: Page) {
  const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"]).analyze();
  const blocking = axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
}

async function join(owner: BrowserContext, ctx: BrowserContext, baseURL: string, treeId: string, name: string, roles: string[]) {
  const email = uniqueEmail(name.toLowerCase().replace(/\W+/g, "-"));
  await registerVerified(ctx, baseURL, email, name);
  const invite = await api<{ token: string }>(owner, "POST", `/trees/${treeId}/invitations`, { email, roles }, baseURL);
  await api(ctx, "POST", `/invitations/${invite.token}/accept`, {}, baseURL);
  await attest(ctx, baseURL, treeId);
}

async function rolesOf(owner: BrowserContext, baseURL: string, treeId: string, name: string): Promise<string[]> {
  const members = await api<{ display_name: string; roles: string[] }[]>(owner, "GET", `/trees/${treeId}/members`, undefined, baseURL);
  return members.find((m) => m.display_name === name)!.roles;
}

test("nominate → accept → approve: the role changes only after the owner approves", async ({ page, browser, baseURL }) => {
  const owner = page.context();
  const { treeId } = await registerWithTree(owner, baseURL!, "Mishra parivar", "Dadaji");
  const adminCtx = await browser.newContext({ baseURL, viewport: { width: 390, height: 844 } });
  const cousinCtx = await browser.newContext({ baseURL, viewport: { width: 390, height: 844 } });
  await join(owner, adminCtx, baseURL!, treeId, "Asha Mishra", ["FAMILY_ADMIN"]);
  await join(owner, cousinCtx, baseURL!, treeId, "Ravi Mishra", ["CONTRIBUTOR"]);

  // the family admin nominates the cousin, with a reason
  const admin = await adminCtx.newPage();
  await admin.goto(`/t/${treeId}/admin/members`);
  await admin.getByRole("button", { name: "Nominate Ravi Mishra for family admin" }).click();
  const dialog = admin.getByRole("dialog", { name: "Nominate Ravi Mishra for family admin" });
  await dialog.getByLabel(/Why this member/).fill("Ravi keeps the Varanasi records and knows every branch");
  await noSeriousAxe(admin);
  await dialog.getByRole("button", { name: "Nominate" }).click();
  await expect(admin.getByRole("listitem", { name: "Nomination of Ravi Mishra" })).toBeVisible();
  expect(await rolesOf(owner, baseURL!, treeId, "Ravi Mishra")).toEqual(["CONTRIBUTOR"]);

  // the cousin is told, sees who nominated them and why, and accepts
  const cousin = await cousinCtx.newPage();
  await cousin.goto(`/t/${treeId}`);
  await cousin.getByRole("button", { name: "Notifications, 1 unread" }).first().click();
  await cousin.getByRole("link", { name: "Asha Mishra nominated you to be a family admin." }).click();
  const mine = cousin.getByRole("listitem", { name: "Nomination of Ravi Mishra" });
  await expect(mine.getByText("Asha Mishra nominated you to be a family admin")).toBeVisible();
  await expect(mine.getByText("Ravi keeps the Varanasi records and knows every branch")).toBeVisible();
  await noSeriousAxe(cousin);
  await mine.getByRole("button", { name: "Accept nomination" }).click();
  await expect(cousin.getByText("You accepted the nomination. An owner will decide.")).toBeVisible();
  expect(await rolesOf(owner, baseURL!, treeId, "Ravi Mishra")).toEqual(["CONTRIBUTOR"]);

  // the family admin who nominated cannot approve; the owner does
  await admin.reload();
  await expect(admin.getByRole("listitem", { name: "Nomination of Ravi Mishra" }).getByRole("button", { name: "Approve", exact: true })).toHaveCount(0);
  await page.goto(`/t/${treeId}/admin/members`);
  const item = page.getByRole("listitem", { name: "Nomination of Ravi Mishra" });
  await expect(item.getByText("Accepted by the nominee")).toBeVisible();
  await item.getByRole("button", { name: "Approve", exact: true }).click();
  const approve = page.getByRole("dialog", { name: "Make Ravi Mishra a family admin?" });
  await noSeriousAxe(page);
  await approve.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText("Ravi Mishra is now a family admin.")).toBeVisible();
  expect(await rolesOf(owner, baseURL!, treeId, "Ravi Mishra")).toEqual(["CONTRIBUTOR", "FAMILY_ADMIN"]);

  // every step is in the audit log
  const audit = await api<{ items: { action: string }[] }>(owner, "GET", `/trees/${treeId}/audit?action=admin_nomination.`, undefined, baseURL!);
  expect(audit.items.map((e) => e.action).reverse()).toEqual(["admin_nomination.created", "admin_nomination.accepted_by_nominee", "admin_nomination.approved"]);
  await adminCtx.close();
  await cousinCtx.close();
});
