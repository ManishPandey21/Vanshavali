import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { api, createPerson, registerVerified, registerWithTree, uniqueEmail } from "./helpers";

/** Same bar as a11y.spec.ts: no serious or critical WCAG 2.2 A/AA violations. */
async function axe(page: Page, label: string) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"]).analyze();
  const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => `${v.id}: ${v.help}`);
  expect.soft(blocking, `axe serious/critical violations on ${label}`).toEqual([]);
}

/**
 * ADR-0011: whoever opens a claim link can say "this isn't me" (the link is cancelled, nothing
 * changes) or "this is me, remove me" (the profile is hidden at once; an admin erases it).
 * Real API, real browser; nothing is mocked.
 */
test("a relative can decline a link or ask to be removed, and the admin erases the profile", async ({ page, browser, baseURL }) => {
  const { treeId } = await registerWithTree(page.context(), baseURL!, "Nair tharavad");
  const meera = await createPerson(page.context(), baseURL!, treeId, "Meera", "Nair", { profile_status: "living", occupation: "Teacher" });
  const invite = () => api<{ url: string }>(page.context(), "POST", `/trees/${treeId}/people/${meera.id}/claim-invites`, { offered_role: "VIEWER" }, baseURL!);
  const pathOf = (url: string) => url.replace(/^https?:\/\/[^/]+/, "");

  // ---- a wrong recipient: "this isn't me"
  const wrongCtx = await browser.newContext({ baseURL });
  await registerVerified(wrongCtx, baseURL!, uniqueEmail("wrong"), "Wrong Number");
  const wrong = await wrongCtx.newPage();
  await wrong.goto(pathOf((await invite()).url));
  await expect(wrong.getByRole("button", { name: "This isn't me" })).toBeVisible();
  await axe(wrong, "claim page");
  await wrong.getByRole("button", { name: "This isn't me" }).click();
  await wrong.getByRole("dialog").getByRole("button", { name: "Yes, cancel this link" }).click();
  await expect(wrong.getByText(/This link no longer works, and nothing about you was added/).first()).toBeVisible();
  await wrongCtx.close();

  // ---- the real Meera: "this is me, remove me"
  const relCtx = await browser.newContext({ baseURL });
  await registerVerified(relCtx, baseURL!, uniqueEmail("meera"), "Meera Nair");
  const rel = await relCtx.newPage();
  await rel.goto(pathOf((await invite()).url));
  await expect(rel.getByText(/added you as “Meera Nair”/)).toBeVisible();
  await rel.getByRole("button", { name: "This is me, but remove me" }).click();
  const dialog = rel.getByRole("dialog", { name: "Remove me from this tree" });
  await expect(dialog).toBeVisible();
  await axe(rel, "remove-me dialog");
  await dialog.getByRole("checkbox", { name: /I am “Meera Nair”/ }).check();
  await dialog.getByRole("button", { name: "Hide my profile and ask for removal" }).click();
  await expect(rel.getByText(/Your profile is now hidden from everyone except the tree admins/).first()).toBeVisible();
  await relCtx.close();

  // ---- the owner reviews the request and erases the profile
  await page.goto(`/t/${treeId}/admin/claims`);
  await expect(page.getByText("Removal request")).toBeVisible();
  await expect(page.getByText("Requested by Meera Nair")).toBeVisible();
  await axe(page, "claims queue with a removal request");
  await page.getByRole("button", { name: "Erase profile" }).click();
  await page.getByRole("dialog", { name: "Erase this profile permanently?" }).getByRole("button", { name: "Erase profile" }).click();
  await expect(page.getByText("Approved")).toBeVisible();

  // ADR-0034: a permanently deleted profile is gone for everyone, the owner included: no profile,
  // no "Erased person" entry in the list, and nothing to restore.
  const after = await page.context().request.get(`${baseURL}/api/v1/trees/${treeId}/people/${meera.id}`);
  expect(after.status()).toBe(404);
  const people = await api<{ items: { id: string; display_name: string }[] }>(page.context(), "GET", `/trees/${treeId}/people`, undefined, baseURL!);
  expect(people.items.some((p) => p.id === meera.id || p.display_name === "Erased person")).toBe(false);
});
