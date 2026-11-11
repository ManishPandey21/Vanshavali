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
 * CI runs this suite in the e2e job against its own set (visual/__screenshots__/ci-ubuntu-24.04),
 * so a PR that intentionally changes these screens must update both sets: the local one with
 * --update-snapshots, the CI one from the "visual-regression-diffs" artifact of the failed run
 * (copy each *-actual.png over the baseline of the same name). Reviewers look at the new images.
 * Factory builders never update baselines: the factory rejects edits to existing snapshot files.
 */
// Which baseline set to compare against. Font rasterisation differs between machines even on the same
// OS (CI's runner vs a developer's Linux box differ by a few anti-aliased glyph pixels), so CI keeps
// its own set (VSH_VISUAL_BASELINES=ci-ubuntu-24.04, rendered by CI itself) and every other host
// uses one per platform. Tolerances stay at zero either way.
const baselines = process.env.VSH_VISUAL_BASELINES ?? "{platform}";
if (!/^[a-z0-9.{}-]+$/.test(baselines)) throw new Error("VSH_VISUAL_BASELINES must be a simple name");

export default defineConfig({
  ...base,
  testDir: "./visual",
  snapshotPathTemplate: `{testDir}/__screenshots__/${baselines}/{projectName}/{testFilePath}/{arg}{ext}`,
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
