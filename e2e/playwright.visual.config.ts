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
 * Builders never update baselines: the factory rejects edits to existing snapshot files, so an
 * intended visual change needs a separately reviewed baseline update.
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
