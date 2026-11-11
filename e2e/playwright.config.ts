import { defineConfig, devices } from "@playwright/test";

/**
 * Drives the real SPA against the real FastAPI backend.
 * The backend web server resets a dedicated database (`vsh_e2e`: drop → create → alembic upgrade head)
 * before starting, so every run begins from an empty schema. Ports differ from the dev defaults
 * (API 8100, SPA 3100) so a running dev stack is never touched.
 */
const API_PORT = Number(process.env.VSH_E2E_API_PORT ?? 8100);
const WEB_PORT = Number(process.env.VSH_E2E_WEB_PORT ?? 3100);
const ADMIN_URL = process.env.VSH_E2E_ADMIN_URL ?? "postgresql+psycopg://vanshavali:vanshavali@localhost:5432/postgres";
const DB_NAME = process.env.VSH_E2E_DB ?? "vsh_e2e";
const APP_ROLE = process.env.VSH_E2E_APP_ROLE ?? "vsh_app_e2e";
// The backend connects as a non-owner role (password = name, test-only) so row-level security applies.
const DB_URL = ADMIN_URL.replace(/\/[^/]*$/, `/${DB_NAME}`).replace(/\/\/[^@/]*@/, `//${APP_ROLE}:${APP_ROLE}@`);
// The backend writes every email (verification, password reset) here; tests read links from it.
const MAIL_DIR = `${process.cwd()}/.e2e-mail`;

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  timeout: 90_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: [
    {
      command: `rm -rf .e2e-mail && uv run --project ../backend python scripts/reset_db.py && cd ../backend && uv run uvicorn app.main:app --port ${API_PORT}`,
      url: `http://localhost:${API_PORT}/api/v1/health`,
      reuseExistingServer: false,
      timeout: 180_000,
      env: {
        VSH_E2E_ADMIN_URL: ADMIN_URL,
        VSH_E2E_DB: DB_NAME,
        VSH_DATABASE_URL: DB_URL,
        VSH_ENV: "test",
        VSH_PUBLIC_BASE_URL: `http://localhost:${WEB_PORT}`,
        VSH_CORS_ORIGINS: JSON.stringify([`http://localhost:${WEB_PORT}`]),
        VSH_LOGIN_RATE_LIMIT_PER_MINUTE: "1000",
        // every spec registers fresh accounts from 127.0.0.1; a fast host exceeds 20/minute
        VSH_REGISTER_RATE_LIMIT_PER_MINUTE: "1000",
        // ...and verifies each one (POST /auth/verify-email shares the per-IP token limit, 30/minute)
        VSH_TOKEN_RATE_LIMIT_PER_MINUTE: "1000",
        VSH_JOB_MODE: "sync",
        VSH_STORAGE_BACKEND: "local",
        VSH_STORAGE_LOCAL_PATH: `${process.cwd()}/.e2e-storage`,
        VSH_SCANNER: "eicar_test",
        VSH_MAIL_BACKEND: "file",
        VSH_MAIL_FILE_DIR: MAIL_DIR,
        // animated exports: deterministic stub by default; set VSH_E2E_RENDER_BACKEND=remotion (with
        // renderer/ bundled) to render for real (ADR-0017)
        VSH_RENDER_BACKEND: process.env.VSH_E2E_RENDER_BACKEND ?? "stub",
        VSH_RENDERER_DIR: `${process.cwd()}/../renderer`,
      },
      stdout: process.env.CI ? "pipe" : "ignore",
    },
    {
      command: `cd ../frontend && npx vite --port ${WEB_PORT} --strictPort`,
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: { VSH_API_TARGET: `http://localhost:${API_PORT}` },
    },
  ],
});
