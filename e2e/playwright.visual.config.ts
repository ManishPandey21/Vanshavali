import { defineConfig, devices } from "@playwright/test";
import base from "./playwright.config";

/**
 * Visual-regression suite (ADR-0029): screenshot comparison of stable, data-free public screens
 * in English and Hindi, desktop and phone. Same real stack and web servers as the E2E suite.
 *
 * Baselines are committed per platform under visual/__screenshots__/<platform>/ because font
 * rasterisation differs between operating systems. A new host (e.g. the factory on macOS) must
 * record its own baselines once, by a person, during trusted setup:
 *   npx playwright test --config=playwright.visual.config.ts --update-snapshots
 * CI runs this suite in the e2e job against the Linux baselines, so a PR that intentionally
 * changes these screens must update them (and the reviewer looks at the new images). Factory
 * builders never update baselines: the factory rejects edits to existing snapshot files.
 */
export default defineConfig({
  ...base,
  testDir: "./visual",
  snapshotPathTemplate: "{testDir}/__screenshots__/{platform}/{projectName}/{testFilePath}/{arg}{ext}",
  retries: 0,
  use: { ...base.use, contextOptions: { reducedMotion: "reduce" }, locale: "en-IN", timezoneId: "Asia/Kolkata" },
  expect: {
    ...base.expect,
    toHaveScreenshot: { animations: "disabled", caret: "hide", scale: "css", maxDiffPixels: 0 },
  },
  projects: [
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile-chromium", use: { ...devices["Pixel 7"] } },
  ],
});
