import { execFileSync } from "node:child_process";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { api, freshTotpWindow, registerVerified, totp, uniqueEmail } from "./helpers";

/**
 * ADR-0026: a system admin (seeded by the dev CLI, temporary password) must turn on two-step
 * sign-in, then adds a gotra in the Super Admin console and publishes it. An ordinary user then
 * finds it in the suggestions without any deployment, and cannot reach the console at all.
 */
const ADMIN_URL = process.env.VSH_E2E_ADMIN_URL ?? "postgresql+psycopg://vanshavali:vanshavali@localhost:5432/postgres";
const DB_URL = ADMIN_URL.replace(/\/[^/]*$/, `/${process.env.VSH_E2E_DB ?? "vsh_e2e"}`);
const TEMPORARY = "e2e-temporary-Adm1n!";
const NEW_PASSWORD = "a-fresh-admin-e2e-passphrase";

function seedSystemAdmin(adminEmail: string) {
  execFileSync("uv", ["run", "python", "-m", "app.cli.seed_demo", "--email", uniqueEmail("demo-owner"), "--admin-email", adminEmail], {
    cwd: "../backend",
    env: { ...process.env, VSH_ENV: "test", VSH_DATABASE_URL: DB_URL, VSH_DEMO_PASSWORD: "e2e-demo-Passw0rd!", VSH_SUPERADMIN_PASSWORD: TEMPORARY },
    stdio: "pipe",
  });
}

/** WCAG 2.2 A/AA: serious or critical axe violations fail (same bar as a11y.spec.ts). */
async function expectAccessible(page: Page, label: string) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"]).analyze();
  const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking.map((v) => `${label}: ${v.id} (${v.nodes.length})`)).toEqual([]);
}

test("a Super Admin publishes a gotra that families then find; ordinary users never see the console", async ({ page, browser, baseURL }) => {
  const adminEmail = uniqueEmail("superadmin");
  seedSystemAdmin(adminEmail);

  // temporary password → new password
  await page.goto("/login");
  await page.getByLabel("Email").fill(adminEmail);
  await page.getByLabel("Password").fill(TEMPORARY);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByLabel("Temporary password").fill(TEMPORARY);
  await page.getByLabel(/^New password/).fill(NEW_PASSWORD);
  await page.getByLabel("Confirm new password").fill(NEW_PASSWORD);
  await page.getByRole("button", { name: "Save new password" }).click();
  await expect(page.getByRole("heading", { name: "Your family trees" })).toBeVisible();

  // the console asks for two-step sign-in first; the API agrees
  await page.getByRole("link", { name: "Master data" }).click();
  await expect(page.getByRole("heading", { name: "Master data management" })).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("Turn on two-step sign-in first");
  const refused = await page.context().request.get("/api/v1/admin/master-data/vocabularies");
  expect(refused.status()).toBe(403);
  expect((await refused.json()).error.code).toBe("admin_mfa_required");

  await page.getByRole("link", { name: "Open account settings" }).click();
  await page.getByRole("button", { name: "Set up two-step verification" }).click();
  const secret = (await page.getByTestId("mfa-secret").innerText()).trim();
  await freshTotpWindow();
  await page.getByLabel("Authentication code").fill(await totp(secret));
  await page.getByRole("button", { name: "Turn on" }).click();
  await expect(page.getByRole("heading", { name: /Two-step verification/ }).getByText("On")).toBeVisible();

  // dashboard → Gotra → Add new, with a live duplicate warning for an existing spelling
  await page.getByRole("link", { name: "Master data" }).click();
  await expect(page.getByText(/no access to any family's tree/)).toBeVisible();
  await expect(page.getByRole("region", { name: "Cultural & heritage" })).toBeVisible();
  await expectAccessible(page, "dashboard");
  await page.getByRole("region", { name: "Cultural & heritage" }).getByRole("link", { name: /^Gotra/ }).click();
  await expect(page.getByRole("table", { name: "Terms in Gotra" })).toBeVisible();
  await expectAccessible(page, "gotra terms");
  await page.getByRole("button", { name: "Add new" }).click();
  const dialog = page.getByRole("dialog", { name: "Add a term" });
  await expectAccessible(page, "term editor");
  await dialog.getByLabel(/English label/).fill("Bhardwaj");
  await expect(dialog.getByText("This may already exist")).toBeVisible();
  await dialog.getByLabel(/English label/).fill("Mudgala");
  await dialog.getByLabel(/Hindi label/).fill("मुद्गल");
  await expect(dialog.getByLabel(/^Code/)).toHaveValue("mudgala");
  await dialog.getByLabel("Aliases and other spellings").fill("Mudgal\nMoudgalya");
  await dialog.getByLabel(/Reason for the change/).fill("Requested by several families; listed in the Pravara-darpana");
  await dialog.getByRole("button", { name: "Publish now" }).click();
  await expect(dialog).toBeHidden();
  await page.getByLabel("Search").fill("मुद्गल");
  const row = page.getByRole("rowheader", { name: /Mudgala · मुद्गल/ });
  await expect(row).toBeVisible();

  // its history records the change, who made it and why
  await page.getByRole("button", { name: "History Mudgala" }).click();
  const history = page.getByRole("dialog", { name: "History of mudgala" });
  await expect(history.getByText("Published")).toBeVisible();
  await expect(history.getByText(/Pravara-darpana/)).toBeVisible();
  await history.getByRole("button", { name: "Close" }).first().click();

  // an ordinary user: the term is suggested at once; the console is 404 and not linked
  const family = await browser.newContext({ baseURL });
  const familyPage = await family.newPage();
  await registerVerified(family, baseURL ?? "", uniqueEmail("family"), "Family Member");
  const found = await api<{ items: { code: string }[] }>(family, "GET", "/vocabularies/gotra?q=moudgalya", undefined, baseURL);
  expect(found.items.map((i) => i.code)).toEqual(["mudgala"]);
  const denied = await family.request.get("/api/v1/admin/master-data/vocabularies");
  expect(denied.status()).toBe(404);
  await familyPage.goto("/admin/master-data");
  await expect(familyPage.getByRole("heading", { name: "Master data management" })).toBeHidden();
  await expect(familyPage.getByRole("link", { name: "Master data" })).toHaveCount(0);
  await family.close();
});
