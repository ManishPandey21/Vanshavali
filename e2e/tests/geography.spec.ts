import { execFileSync } from "node:child_process";
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { registerWithTree } from "./helpers";

/**
 * ADR-0019: an operator stages the synthetic LGD and India Post fixtures with the real CLI, they
 * are approved and activated, and a family member then links places to the directory in the
 * browser: by a Hindi search, step by step (state → district → tehsil → village) and PIN first.
 * The fixtures are fictional (backend/tests/fixtures/geo); no official data is committed.
 */
const ADMIN_URL = process.env.VSH_E2E_ADMIN_URL ?? "postgresql+psycopg://vanshavali:vanshavali@localhost:5432/postgres";
const DB_URL = ADMIN_URL.replace(/\/[^/]*$/, `/${process.env.VSH_E2E_DB ?? "vsh_e2e"}`);
const ENV = { ...process.env, VSH_ENV: "test", VSH_DATABASE_URL: DB_URL };

function cli(args: string[]): string {
  return execFileSync("uv", ["run", "python", "-m", "app.cli.geo", ...args], { cwd: "../backend", env: ENV, stdio: "pipe" }).toString();
}

/** Stage → approve → activate. The approval is done directly as test setup (no second admin in e2e). */
function goLive(source: "lgd" | "india_post", file: string, label: string) {
  const out = cli(["stage", "--source", source, "--label", label, "--file", `tests/fixtures/geo/${file}`, "--licence", "Synthetic test data", "--attribution", "Vanshavali test fixtures"]);
  const id = /\(id ([0-9a-f-]{36})\)/.exec(out)?.[1];
  if (!id) throw new Error(`staging failed: ${out}`);
  execFileSync(
    "uv",
    ["run", "python", "-c", `from sqlalchemy import text; from app.core.db import get_sessionmaker; s=get_sessionmaker()(); s.execute(text("UPDATE geo_snapshot SET status='approved' WHERE id=:i"), {"i": "${id}"}); s.commit()`],
    { cwd: "../backend", env: ENV, stdio: "pipe" },
  );
  cli(["activate", "--snapshot", id, "--reason", "e2e setup", "--operator", "playwright"]);
}

test.beforeAll(() => {
  const label = `e2e-${Date.now()}`;
  goLive("lgd", "lgd_v1.csv", label);
  goLive("india_post", "post_v1.csv", label);
});

test("link family places to the official directory by search, step by step and PIN", async ({ page, context, baseURL }) => {
  const { treeId } = await registerWithTree(context, baseURL ?? "", "Geography family");
  await page.goto(`/t/${treeId}/places`);

  // 1. Hindi search → the village, with district and state filled in; the name is suggested once
  await page.getByRole("button", { name: "New place" }).first().click();
  let dialog = page.getByRole("dialog", { name: "New place" });
  const search = dialog.getByRole("combobox", { name: /Search a village/ });
  await search.fill("बाबत");
  await dialog.getByRole("option", { name: /Babatpur/ }).click();
  await expect(dialog.getByRole("status").filter({ hasText: "Linked to: Babatpur" })).toContainText("Pindra, Varanasi, Uttar Pradesh");
  await expect(dialog.getByRole("textbox", { name: "Name", exact: true })).toHaveValue("Babatpur");
  await expect(dialog.getByRole("textbox", { name: "District", exact: true })).toHaveValue("Varanasi");
  await expect(dialog.getByRole("textbox", { name: "State", exact: true })).toHaveValue("Uttar Pradesh");
  await expect(dialog.getByText(/Source: Vanshavali test fixtures/)).toBeVisible();
  // WCAG 2.2 A/AA: no serious or critical violations in the place dialog with the directory open
  const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"]).analyze();
  expect(axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([]);
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByText("LGD: 9100001")).toBeVisible();

  // 2. step by step, keeping the family's own name for the place
  await page.getByRole("button", { name: "New place" }).first().click();
  dialog = page.getByRole("dialog", { name: "New place" });
  await dialog.getByRole("textbox", { name: "Name", exact: true }).fill("Our old house lane, Shivpur");
  await dialog.getByText("Or choose step by step").click();
  await dialog.getByRole("combobox", { name: "State / UT" }).selectOption({ label: "Uttar Pradesh · उत्तर प्रदेश" });
  await dialog.getByRole("combobox", { name: "District", exact: true }).selectOption({ label: "Varanasi · वाराणसी" });
  await dialog.getByRole("combobox", { name: "Tehsil", exact: true }).selectOption({ label: "Varanasi Sadar · वाराणसी सदर" });
  await dialog.getByRole("combobox", { name: "Village or town" }).click();
  await dialog.getByRole("option", { name: /Shivpur/ }).click();
  await expect(dialog.getByRole("textbox", { name: "Name", exact: true })).toHaveValue("Our old house lane, Shivpur");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByText("LGD: 9100003")).toBeVisible();

  // 3. PIN first: the PIN suggests places, it never picks one by itself
  await page.getByRole("button", { name: "New place" }).first().click();
  dialog = page.getByRole("dialog", { name: "New place" });
  await dialog.getByLabel("PIN code").fill("221006");
  await expect(dialog.getByText("A PIN can cover several villages, so choose the one you mean.")).toBeVisible();
  await expect(dialog.getByRole("status").filter({ hasText: "Linked to" })).toHaveCount(0);
  await dialog.getByRole("button", { name: /^Phulpur/ }).first().click();
  await expect(dialog.getByRole("textbox", { name: "Name", exact: true })).toHaveValue("Phulpur");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("LGD: 9100002")).toBeVisible();

  // a pre-1947 place stays free text, with no directory link
  await page.getByRole("button", { name: "New place" }).first().click();
  dialog = page.getByRole("dialog", { name: "New place" });
  await dialog.getByRole("textbox", { name: "Name", exact: true }).fill("Lyallpur (pre-1947)");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByText("Lyallpur (pre-1947)")).toBeVisible();
});
