import { expect, test, type Browser, type BrowserContext } from "@playwright/test";
import { api, registerVerified, registerWithTree, renderTextPng, uniqueEmail } from "./helpers";

/**
 * ADR-0027: Visibility & Sharing. A contributor uploads a photo, shares it with one selected member
 * (view only), and the system enforces that choice in the browser and on every route: the selected
 * member sees it but cannot download the original; a family admin and another member get "not found"
 * even with the document's URL; narrowing it back to "Only me" removes the member's access.
 */
async function join(browser: Browser, baseURL: string, owner: BrowserContext, treeId: string, name: string, roles: string[]) {
  const ctx = await browser.newContext({ baseURL });
  const email = uniqueEmail(name.toLowerCase().replace(/\s+/g, "-"));
  await registerVerified(ctx, baseURL, email, name);
  const invite = await api<{ token: string }>(owner, "POST", `/trees/${treeId}/invitations`, { email, roles }, baseURL);
  await api(ctx, "POST", `/invitations/${invite.token}/accept`, undefined, baseURL);
  const stmt = await api<{ version: string; language: string }>(ctx, "GET", "/consent-statements/family_data?lang=en", undefined, baseURL);
  await api(ctx, "POST", `/trees/${treeId}/attestation`, { statement_version: stmt.version, language: stmt.language }, baseURL);
  return ctx;
}

async function status(ctx: BrowserContext, baseURL: string, path: string, method: "GET" | "POST" = "GET"): Promise<number> {
  const csrf = (await ctx.cookies()).find((c) => c.name === "vsh_csrf")?.value ?? "";
  const res = await ctx.request.fetch(`${baseURL}/api/v1${path}`, { method, headers: method === "GET" ? {} : { "X-CSRF-Token": csrf } });
  return res.status();
}

test("a photo shared with selected members is seen only by them, everywhere", async ({ browser, context, baseURL }) => {
  const base = baseURL!;
  const { treeId } = await registerWithTree(context, base, "Mishra parivar", "Tree Owner");
  const uploader = await join(browser, base, context, treeId, "Uploader Didi", ["CONTRIBUTOR"]);
  const asha = await join(browser, base, context, treeId, "Asha Mishra", ["VIEWER"]);
  const ravi = await join(browser, base, context, treeId, "Ravi Mishra", ["VIEWER"]);
  const admin = await join(browser, base, context, treeId, "Family Admin", ["FAMILY_ADMIN"]);
  const png = await renderTextPng(browser, ["Nani at the Kashi ghat, 1962"]);

  // ---- the uploader chooses "Selected members" → Asha (view only) in the upload dialog
  const page = await uploader.newPage();
  await page.goto(`/t/${treeId}/documents`);
  await page.getByRole("button", { name: "Upload document" }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(/^File/).setInputFiles({ name: "nani.png", mimeType: "image/png", buffer: png });
  await dialog.getByLabel(/^Title/).fill("Nani at the ghat");
  await expect(dialog.getByRole("radio", { name: "All family members" })).toBeVisible();
  await dialog.getByRole("radio", { name: "Selected members" }).check();
  await dialog.getByLabel("Search family members by name").fill("Asha");
  const list = dialog.getByRole("list", { name: "Family members to share with" });
  await expect(list.getByText("Ravi Mishra")).toHaveCount(0);
  await list.getByRole("listitem").filter({ hasText: "Asha Mishra" }).getByRole("checkbox", { name: "Can view" }).check();
  await dialog.getByRole("button", { name: "Upload document" }).click();
  await expect(page.getByRole("heading", { name: "Nani at the ghat", level: 1 })).toBeVisible({ timeout: 60_000 });
  const docId = page.url().split("/documents/")[1].split(/[?#/]/)[0];

  // the sharing panel lists exactly who has access
  const panel = page.getByRole("region", { name: /Visibility & sharing/ });
  await expect(panel.getByText("Selected members", { exact: true }).first()).toBeVisible();
  const who = panel.getByTestId("sharing-audience");
  await expect(who.getByText(/Uploader Didi · Owner/)).toBeVisible();
  await expect(who.getByText(/Asha Mishra · Selected/)).toBeVisible();
  await expect(who.getByText(/Family Admin/)).toHaveCount(0);
  await expect(who.getByText(/Tree Owner/)).toHaveCount(0);

  // ---- Asha sees the photo but has no download
  const ashaPage = await asha.newPage();
  await ashaPage.goto(`/t/${treeId}/documents/${docId}`);
  await expect(ashaPage.getByRole("heading", { name: "Nani at the ghat", level: 1 })).toBeVisible();
  await expect(ashaPage.getByRole("button", { name: "Download" })).toHaveCount(0);
  expect(await status(asha, base, `/trees/${treeId}/documents/${docId}/download-url?variant=original`, "POST")).toBe(403);

  // ---- the family admin, the tree owner and Ravi cannot reach it by URL, list or API
  for (const ctx of [admin, context, ravi]) {
    const p = await ctx.newPage();
    await p.goto(`/t/${treeId}/documents/${docId}`);
    await expect(p.getByRole("heading", { name: "Nani at the ghat" })).toHaveCount(0);
    await expect(p.getByText(/not found/i).first()).toBeVisible();
    expect(await status(ctx, base, `/trees/${treeId}/documents/${docId}`)).toBe(404);
    expect(await status(ctx, base, `/trees/${treeId}/documents/${docId}/download-url?variant=thumbnail`, "POST")).toBe(404);
    const listed = await api<{ items: { id: string }[] }>(ctx, "GET", `/trees/${treeId}/documents`, undefined, base);
    expect(listed.items.map((d) => d.id)).not.toContain(docId);
    await p.close();
  }

  // ---- narrowing back to "Only me" takes effect at once
  await panel.getByRole("radio", { name: "Only me" }).check();
  await panel.getByRole("button", { name: "Save sharing" }).click();
  await expect(panel.getByText("Sharing updated.")).toBeAttached();
  expect(await status(asha, base, `/trees/${treeId}/documents/${docId}`)).toBe(404);

  // ---- sharing with all family members asks for confirmation first
  await panel.getByRole("radio", { name: "All family members" }).check();
  await expect(who.getByText(/Ravi Mishra · Family member/)).toBeVisible();
  await panel.getByRole("button", { name: "Save sharing" }).click();
  const confirm = page.getByRole("dialog", { name: "Share more widely?" });
  await expect(confirm.getByText(/more people will be able to see/)).toBeVisible();
  await confirm.getByRole("button", { name: "Yes, share" }).click();
  await expect(confirm).toHaveCount(0);
  expect(await status(ravi, base, `/trees/${treeId}/documents/${docId}`)).toBe(200);
});

test("a family tradition kept for Only me, then shared with one member", async ({ browser, context, baseURL }) => {
  const base = baseURL!;
  const { treeId } = await registerWithTree(context, base, "Tiwari parivar", "Tree Owner");
  const author = await join(browser, base, context, treeId, "Author Bua", ["CONTRIBUTOR"]);
  const asha = await join(browser, base, context, treeId, "Asha Tiwari", ["VIEWER"]);
  const admin = await join(browser, base, context, treeId, "Family Admin", ["FAMILY_ADMIN"]);

  const page = await author.newPage();
  await page.goto(`/t/${treeId}/traditions`);
  await page.getByRole("button", { name: "Add a tradition" }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(/^Title/).fill("Nani's teej songs");
  await dialog.getByRole("radio", { name: "Only me" }).check();
  await expect(dialog.getByRole("checkbox", { name: "Can download" })).toHaveCount(0);
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("heading", { name: "Nani's teej songs", level: 1 })).toBeVisible();
  const entryId = page.url().split("/traditions/")[1].split(/[?#/]/)[0];

  // the tree owner and a family admin cannot reach it by URL, list or API
  for (const ctx of [context, admin, asha]) {
    expect(await status(ctx, base, `/trees/${treeId}/traditions/${entryId}`)).toBe(404);
    const listed = await api<{ items: { id: string }[] }>(ctx, "GET", `/trees/${treeId}/traditions`, undefined, base);
    expect(listed.items.map((e) => e.id)).not.toContain(entryId);
  }

  // the author shares it with Asha; widening asks for confirmation first
  const panel = page.getByRole("region", { name: /Visibility & sharing/ });
  await panel.getByRole("radio", { name: "Selected members" }).check();
  await panel.getByRole("list", { name: "Family members to share with" }).getByRole("listitem").filter({ hasText: "Asha Tiwari" }).getByRole("checkbox", { name: "Can view" }).check();
  await expect(panel.getByTestId("sharing-audience").getByText(/Asha Tiwari · Selected/)).toBeVisible();
  await panel.getByRole("button", { name: "Save sharing" }).click();
  const confirm = page.getByRole("dialog", { name: "Share more widely?" });
  await confirm.getByRole("button", { name: "Yes, share" }).click();
  await expect(confirm).toHaveCount(0);
  expect(await status(asha, base, `/trees/${treeId}/traditions/${entryId}`)).toBe(200);
  expect(await status(admin, base, `/trees/${treeId}/traditions/${entryId}`)).toBe(404);
});
