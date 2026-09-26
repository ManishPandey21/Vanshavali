import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";
import { uniqueEmail } from "./helpers";

/**
 * ADR-0012: an account created with a temporary password (dev/demo CLI) must choose a new one
 * before it can do anything else, in the browser as well as at the API.
 */
const ADMIN_URL = process.env.VSH_E2E_ADMIN_URL ?? "postgresql+psycopg://vanshavali:vanshavali@localhost:5432/postgres";
const DB_URL = ADMIN_URL.replace(/\/[^/]*$/, `/${process.env.VSH_E2E_DB ?? "vsh_e2e"}`);
const TEMPORARY = "e2e-temporary-Pa55!";

function createDemoAccount(email: string) {
  execFileSync("uv", ["run", "python", "-m", "app.cli.create_demo_account", "--email", email, "--name", "Demo Pandey"], {
    cwd: "../backend",
    env: { ...process.env, VSH_ENV: "test", VSH_DATABASE_URL: DB_URL, VSH_DEMO_ACCOUNT_PASSWORD: TEMPORARY },
    stdio: "pipe",
  });
}

test("a temporary password must be replaced before the app opens", async ({ page, context }) => {
  const email = uniqueEmail("demo");
  createDemoAccount(email);

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(TEMPORARY);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Choose a new password" })).toBeVisible();

  // every other page leads back here, and the API itself refuses
  await page.goto("/trees/new");
  await expect(page.getByRole("heading", { name: "Choose a new password" })).toBeVisible();
  const refused = await context.request.get("/api/v1/trees");
  expect(refused.status()).toBe(403);
  expect((await refused.json()).error.code).toBe("password_change_required");

  await page.getByLabel("Temporary password").fill(TEMPORARY);
  await page.getByLabel(/^New password/).fill("a-fresh-e2e-passphrase");
  await page.getByLabel("Confirm new password").fill("a-fresh-e2e-passphrase");
  await page.getByRole("button", { name: "Save new password" }).click();
  await expect(page.getByRole("heading", { name: "Your family trees" })).toBeVisible();
  expect((await context.request.get("/api/v1/trees")).status()).toBe(200);
});
