import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { api, createPerson, registerVerified, registerWithTree, uniqueEmail } from "./helpers";

/**
 * ADR-0034 in the browser: "Open full tree" shows the whole connected family, and a removed or
 * permanently deleted person leaves no card and no "Private person" placeholder, while a relative
 * who is merely hidden by privacy keeps one.
 *
 * The two scenarios that were first written for draft PR #82 (full tree in both directions; delete
 * needs a reason, survives a failed request and is refused to a viewer) are kept and extended.
 * Set VSH_E2E_SHOTS to a directory to save the "after" screenshots.
 */
const SHOTS = process.env.VSH_E2E_SHOTS;
const shot = async (page: Page, name: string) => {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
};

type Ids = Record<string, string>;
const NAMES = ["Nana", "Nani", "Mama", "Anita", "Ramesh", "Dada", "Son", "Bahu", "Grandkid", "Samdhi"];

/** Three generations with both sides of two marriages, plus two people linked to nobody above. */
async function seedFamily(ctx: BrowserContext, baseURL: string, treeId: string): Promise<Ids> {
  const ids: Ids = {};
  for (const n of [...NAMES, "Stranger", "Other"]) ids[n] = (await createPerson(ctx, baseURL, treeId, n, "Pandey", { profile_status: "deceased" })).id;
  const link = (a: string, b: string, type: string) => api(ctx, "POST", `/trees/${treeId}/relationships`, { person_a_id: ids[a], person_b_id: ids[b], type }, baseURL);
  for (const p of ["Nana", "Nani"]) {
    await link(p, "Anita", "biological_parent");
    await link(p, "Mama", "biological_parent");
  }
  await link("Nana", "Nani", "spouse");
  await link("Anita", "Ramesh", "spouse");
  await link("Dada", "Ramesh", "biological_parent");
  await link("Anita", "Son", "biological_parent");
  await link("Ramesh", "Son", "biological_parent");
  await link("Son", "Bahu", "spouse");
  await link("Samdhi", "Bahu", "biological_parent");
  await link("Son", "Grandkid", "biological_parent");
  await link("Bahu", "Grandkid", "biological_parent");
  await link("Stranger", "Other", "spouse");
  return ids;
}

const chart = (page: Page) => page.getByRole("group", { name: "Family tree chart" });
const card = (page: Page, name: string) => chart(page).getByRole("button", { name: new RegExp(`^${name} Pandey,`) });
const status = (page: Page) => page.getByTestId("family-status");

async function joinAs(owner: BrowserContext, member: BrowserContext, baseURL: string, treeId: string, roles: string[]) {
  const email = uniqueEmail(roles[0].toLowerCase());
  await registerVerified(member, baseURL, email, "Member");
  const invite = await api<{ token: string }>(owner, "POST", `/trees/${treeId}/invitations`, { email, roles }, baseURL);
  await api(member, "POST", `/invitations/${invite.token}/accept`, {}, baseURL);
}

test("Open full tree shows the whole connected family, in both directions and across marriages", async ({ page, context, baseURL }) => {
  const { treeId } = await registerWithTree(context, baseURL!, "Pandey Family Tree");
  const ids = await seedFamily(context, baseURL!, treeId);

  // the focused view, as before: descendants of one person only
  await page.goto(`/t/${treeId}/tree/${ids.Anita}?dir=descendants`);
  await expect(card(page, "Grandkid")).toBeVisible();
  await expect(card(page, "Nana")).toHaveCount(0);

  await page.goto(`/t/${treeId}`);
  await page.getByRole("link", { name: "Open full tree" }).click();
  await expect(page).toHaveURL(/dir=connected/);
  await expect(status(page)).toHaveAttribute("data-status", "complete");
  await expect(status(page)).toContainText("that you are allowed to see: 10 people");
  await expect(status(page)).toContainText("4 generations");
  for (const n of NAMES) await expect(card(page, n)).toBeVisible();
  // linked to nobody in this family: not drawn here, and not joined by an invented line
  await expect(card(page, "Stranger")).toHaveCount(0);
  await expect(chart(page).getByRole("button", { name: /Private person/ })).toHaveCount(0);
  await shot(page, "B1-after-open-full-tree-connected-family");

  // the same family from a different member: the scope follows the person, not a direction
  await page.goto(`/t/${treeId}/tree/${ids.Samdhi}?dir=connected`);
  await expect(status(page)).toContainText("Everyone connected to Samdhi Pandey that you are allowed to see: 10 people");

  // find someone: they are brought to the middle and their details open beside the chart, with
  // focus on the panel heading exactly as when a card is clicked
  await page.getByLabel("Find a person in this view").fill("mama");
  await page.getByRole("list", { name: "Matching people" }).getByRole("button", { name: /Mama Pandey/ }).click();
  await expect(page.getByRole("heading", { name: "Mama Pandey" })).toBeFocused();
  await expect(card(page, "Mama")).toBeInViewport();

  // keyboard: move along the row, return to the starting person
  await card(page, "Mama").focus();
  await page.keyboard.press("ArrowUp"); // to one of Mama's parents on the row above
  await expect(chart(page).locator("[data-node]:focus")).toHaveAttribute("aria-label", /^(Nana|Nani) Pandey,/);
  await page.keyboard.press("Home");
  await expect(card(page, "Samdhi")).toBeFocused();
  for (const control of ["Zoom in", "Zoom out", "Fit to screen", "Reset view", "Move view left"]) {
    await page.getByRole("button", { name: control }).click();
  }
  await page.getByRole("button", { name: "Centre on Samdhi Pandey" }).click();
  await expect(card(page, "Samdhi")).toBeFocused();

  // all groups: the unrelated couple appears as its own group
  await page.getByRole("button", { name: "All groups in this tree" }).click();
  await expect(page).toHaveURL(/scope=all/);
  await expect(status(page)).toContainText("Everyone in this tree that you are allowed to see: 12 people");
  await expect(status(page)).toContainText("2 separate groups");
  await expect(card(page, "Stranger")).toBeVisible();
  await expect(card(page, "Anita")).toBeVisible();
  await shot(page, "B2-after-all-groups");

  // the list alternative names everyone, grouped
  await page.getByRole("button", { name: "List", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Group 1 · 10 people" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Group 2 · 2 people" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Samdhi Pandey" })).toBeVisible();
  const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([]);

  await page.keyboard.press("Tab");
  await page.goto(`/t/${treeId}/tree/${ids.Anita}?dir=connected`);
  await card(page, "Anita").focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(new RegExp(`/people/${ids.Anita}$`));
});

test("a family that needs several pages is never shown as complete until the last page arrives", async ({ page, context, baseURL }) => {
  const { treeId } = await registerWithTree(context, baseURL!, "Paged family");
  await seedFamily(context, baseURL!, treeId);
  const people = await api<{ items: { id: string; display_name: string }[] }>(context, "GET", `/trees/${treeId}/people`, undefined, baseURL!);
  const anita = people.items.find((p) => p.display_name.startsWith("Anita"))!.id;

  // ask the real server for small pages, and hold the last one back
  let failLater = true;
  let requests = 0;
  await page.route("**/api/v1/trees/*/family-graph*", async (route) => {
    const url = new URL(route.request().url());
    requests += 1;
    url.searchParams.set("limit", "4");
    if (url.searchParams.get("cursor") && failLater) {
      await route.fulfill({ status: 422, contentType: "application/json", body: JSON.stringify({ error: { code: "invalid_cursor", message: "Invalid cursor", details: null } }) });
      return;
    }
    await route.continue({ url: url.toString() });
  });
  await page.goto(`/t/${treeId}/tree/${anita}?dir=connected`);
  await expect(status(page)).toHaveAttribute("data-status", "incomplete");
  await expect(status(page)).toContainText("Loading stopped. 4 of 10 people are shown, so this is not the whole family.");
  await expect(page.getByText(/Everyone connected to/)).toHaveCount(0);
  await expect(chart(page).locator("[data-node]")).toHaveCount(4);
  await shot(page, "B3-after-incomplete-state");

  failLater = false;
  await status(page).getByRole("button", { name: "Continue loading" }).click();
  await expect(status(page)).toHaveAttribute("data-status", "complete");
  await expect(status(page)).toContainText("10 people");
  await expect(chart(page).locator("[data-node]")).toHaveCount(10);
  expect(requests).toBeGreaterThanOrEqual(4); // 4 + 4 + 2, plus the refused attempt
});

test("Remove from tree: the person and their placeholder disappear everywhere, and can be restored", async ({ page, context, baseURL }) => {
  const { treeId } = await registerWithTree(context, baseURL!, "Removal family");
  const ids = await seedFamily(context, baseURL!, treeId);

  await page.goto(`/t/${treeId}/people/${ids.Son}`);
  await expect(page.getByRole("button", { name: "Remove from tree" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Delete person" })).toBeVisible();
  await page.getByRole("button", { name: "Remove from tree" }).click();
  const dialog = page.getByRole("dialog", { name: "Remove person from tree?" });
  await expect(dialog).toContainText("Son Pandey");
  await expect(dialog).toContainText("will no longer appear in the tree or its people list");
  await expect(dialog).toContainText("restore the record from Removed people");
  await shot(page, "A0-after-remove-dialog");
  // cancelling changes nothing
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toHaveCount(0);
  await page.goto(`/t/${treeId}/tree/${ids.Anita}?dir=connected`);
  await expect(card(page, "Son")).toBeVisible();

  await page.goto(`/t/${treeId}/people/${ids.Son}`);
  await page.getByRole("button", { name: "Remove from tree" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Remove from tree" }).click();
  await expect(page).toHaveURL(new RegExp(`/t/${treeId}/people$`));
  await expect(page.getByRole("link", { name: /Son Pandey/ })).toHaveCount(0);

  // focused views: no card and no placeholder (this is the screenshot from the report)
  await page.goto(`/t/${treeId}/tree/${ids.Anita}?dir=descendants`);
  await expect(card(page, "Ramesh")).toBeVisible();
  await expect(chart(page).getByRole("button", { name: /Private person|Son Pandey|Grandkid/ })).toHaveCount(0);
  await expect(page.getByText("Private person")).toHaveCount(0);
  await shot(page, "A1-after-removed-person-leaves-no-placeholder");
  await page.goto(`/t/${treeId}/tree/${ids.Anita}?view=family`);
  await expect(page.getByText("Ramesh Pandey").filter({ visible: true }).first()).toBeVisible();
  await expect(page.getByText("Private person")).toHaveCount(0);

  // the full tree: the family has split; nothing joins Grandkid's side to Anita's
  await page.goto(`/t/${treeId}/tree/${ids.Anita}?dir=connected`);
  await expect(status(page)).toContainText("that you are allowed to see: 6 people");
  await expect(card(page, "Grandkid")).toHaveCount(0);
  await expect(chart(page).getByRole("button", { name: /Private person/ })).toHaveCount(0);
  await page.getByRole("button", { name: "All groups in this tree" }).click();
  await expect(status(page)).toContainText("3 separate groups");
  await expect(card(page, "Grandkid")).toBeVisible();
  await expect(chart(page).getByRole("button", { name: /Private person|Son Pandey/ })).toHaveCount(0);
  await shot(page, "A2-after-removed-linking-person-splits-family");

  // overview and the direct link
  await page.goto(`/t/${treeId}`);
  await expect(page.getByRole("link", { name: "Open full tree" })).toBeVisible();
  await expect(page.getByText("Private person")).toHaveCount(0);
  await page.goto(`/t/${treeId}/people/${ids.Son}`);
  await expect(page.getByText(/not found/i).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Son Pandey" })).toHaveCount(0);

  // an admin restores them: the family is whole again
  await page.goto(`/t/${treeId}/admin/restore`);
  await page.getByRole("button", { name: /Restore/ }).first().click();
  await page.goto(`/t/${treeId}/tree/${ids.Anita}?dir=connected`);
  await expect(status(page)).toContainText("that you are allowed to see: 10 people");
  await expect(card(page, "Son")).toBeVisible();
  await expect(card(page, "Grandkid")).toBeVisible();
});

test("a relative hidden by privacy keeps the placeholder; removing them takes it away", async ({ page, browser, context, baseURL }) => {
  const { treeId } = await registerWithTree(context, baseURL!, "Privacy family");
  const ids = await seedFamily(context, baseURL!, treeId);
  await api(context, "PUT", `/trees/${treeId}/people/${ids.Son}/privacy`, { privacy_level: "PRIVATE_TREE_ADMINS" }, baseURL!);
  const viewerCtx = await browser.newContext({ baseURL });
  await joinAs(context, viewerCtx, baseURL!, treeId, ["VIEWER"]);
  const viewer = await viewerCtx.newPage();

  await viewer.goto(`/t/${treeId}/tree/${ids.Anita}?dir=connected`);
  await expect(status(viewer)).toHaveAttribute("data-status", "complete");
  await expect(status(viewer)).toContainText("that you are allowed to see: 9 people");
  await expect(status(viewer)).toContainText("1 private relative shown without a name");
  await expect(chart(viewer).getByRole("button", { name: /^Private person/ })).toHaveCount(1);
  await expect(card(viewer, "Grandkid")).toBeVisible(); // descent continues past the hidden person
  expect(await viewer.content()).not.toContain(ids.Son);
  expect(await viewer.content()).not.toContain("Son Pandey");
  await shot(viewer, "A3-after-genuine-privacy-placeholder-kept");

  // the owner removes the hidden person: now there is nothing to stand in for
  await api(context, "DELETE", `/trees/${treeId}/people/${ids.Son}`, undefined, baseURL!);
  await viewer.reload();
  await expect(status(viewer)).toContainText("that you are allowed to see: 6 people");
  await expect(chart(viewer).getByRole("button", { name: /Private person/ })).toHaveCount(0);
  await viewerCtx.close();
});

test("Delete person: admins only, deliberate, survives a failed request, and is permanent", async ({ page, browser, context, baseURL }) => {
  const { treeId } = await registerWithTree(context, baseURL!, "Deletion family");
  const ids = await seedFamily(context, baseURL!, treeId);

  // a viewer and a contributor: no delete control, and the server refuses a direct request
  for (const roles of [["VIEWER"], ["CONTRIBUTOR"]]) {
    const ctx = await browser.newContext({ baseURL });
    await joinAs(context, ctx, baseURL!, treeId, roles);
    const p = await ctx.newPage();
    await p.goto(`/t/${treeId}/people/${ids.Son}`);
    await expect(p.getByRole("heading", { name: "Son Pandey", level: 1 })).toBeVisible();
    await expect(p.getByRole("button", { name: "Delete person" })).toHaveCount(0);
    await expect(p.getByRole("button", { name: "Remove from tree" })).toHaveCount(roles[0] === "VIEWER" ? 0 : 1);
    const csrf = (await ctx.cookies()).find((c) => c.name === "vsh_csrf")?.value ?? "";
    const denied = await ctx.request.post(`${baseURL}/api/v1/trees/${treeId}/people/${ids.Son}/erase`, { data: { reason: "Not authorised", confirm: true }, headers: { "X-CSRF-Token": csrf } });
    expect(denied.status()).toBe(403);
    await ctx.close();
  }

  await page.goto(`/t/${treeId}/people/${ids.Son}`);
  await page.getByRole("button", { name: "Delete person" }).click();
  const dialog = page.getByRole("dialog", { name: "Permanently delete person?" });
  await expect(dialog).toContainText("This action cannot be undone after permanent deletion.");
  await expect(dialog).toContainText("No one else's record is deleted.");
  const submit = dialog.getByRole("button", { name: "Delete permanently" });
  await expect(submit).toBeDisabled();
  await dialog.getByLabel(/^Reason/).fill("Family asked for this record to be deleted");
  await expect(submit).toBeDisabled(); // a reason alone is not enough
  await dialog.getByLabel(/Type the name/).fill("Son Pandey");
  await expect(submit).toBeEnabled();
  await shot(page, "A4-after-delete-dialog");

  // cancel: nothing happened
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByRole("heading", { name: "Son Pandey", level: 1 })).toBeVisible();

  // a failed request neither navigates away nor pretends to have deleted
  await page.getByRole("button", { name: "Delete person" }).click();
  await dialog.getByLabel(/^Reason/).fill("Family asked for this record to be deleted");
  await dialog.getByLabel(/Type the name/).fill("Son Pandey");
  await page.route(`**/api/v1/trees/${treeId}/people/${ids.Son}/erase`, (route) =>
    route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: { code: "simulated_failure", message: "Simulated failure", details: null } }) }),
  );
  await submit.click();
  await expect(dialog.getByRole("alert")).toContainText("Simulated failure");
  await expect(page).toHaveURL(new RegExp(`/people/${ids.Son}$`));
  await expect(dialog.getByLabel(/^Reason/)).toHaveValue("Family asked for this record to be deleted");
  await page.unroute(`**/api/v1/trees/${treeId}/people/${ids.Son}/erase`);
  expect((await api<{ display_name: string }>(context, "GET", `/trees/${treeId}/people/${ids.Son}`, undefined, baseURL!)).display_name).toBe("Son Pandey");

  await submit.click();
  await expect(page).toHaveURL(new RegExp(`/t/${treeId}/people$`));

  // gone for the owner too: no profile, not restorable, no card, no placeholder, no "Erased person"
  const res = await context.request.get(`${baseURL}/api/v1/trees/${treeId}/people/${ids.Son}`);
  expect(res.status()).toBe(404);
  expect(await api<unknown[]>(context, "GET", `/trees/${treeId}/people/deleted`, undefined, baseURL!)).toEqual([]);
  await page.goto(`/t/${treeId}/tree/${ids.Anita}?dir=connected&scope=all`);
  await expect(status(page)).toHaveAttribute("data-status", "complete");
  await expect(status(page)).toContainText("that you are allowed to see: 11 people");
  await expect(chart(page).getByRole("button", { name: /Private person|Erased person|Son Pandey/ })).toHaveCount(0);
  await expect(card(page, "Grandkid")).toBeVisible(); // nobody else was deleted
  await expect(card(page, "Bahu")).toBeVisible();
  await shot(page, "A5-after-permanent-delete");
  await page.goto(`/t/${treeId}/admin/restore`);
  await expect(page.getByText("No removed people")).toBeVisible();
});
