import { expect, test, type Page } from "@playwright/test";

/**
 * Visual regression for the public, data-free screens: the landing page and the sign-in/up forms,
 * in English and in Hindi (Devanagari shaping and font fallback are exactly what unit tests miss).
 * Nothing here depends on database content, so screenshots are deterministic.
 */

async function settle(page: Page) {
  await page.waitForLoadState("networkidle");
  await page.evaluate(() => document.fonts.ready);
}

async function useLanguage(page: Page, lang: "en" | "hi") {
  if (lang === "en") return;
  await page.getByRole("combobox", { name: "Language" }).first().selectOption("hi");
  await expect(page.locator("html")).toHaveAttribute("lang", "hi");
}

for (const lang of ["en", "hi"] as const) {
  test(`landing page (${lang})`, async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await useLanguage(page, lang);
    await settle(page);
    // first screen only: the full landing page is several viewports of imagery (~1.5 MB per baseline)
    await expect(page).toHaveScreenshot(`landing-${lang}.png`);
  });
}

for (const path of ["/login", "/register", "/forgot-password"]) {
  test(`auth form ${path}`, async ({ page }) => {
    await page.goto(path);
    await expect(page.getByRole("button").first()).toBeVisible();
    await settle(page);
    await expect(page).toHaveScreenshot(`${path.slice(1)}.png`, { fullPage: true });
  });
}
