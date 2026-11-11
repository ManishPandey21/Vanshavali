import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { createPerson, registerWithTree } from "./helpers";

/**
 * The family calendar (ADR-0022) against the real stack on a phone-sized screen. The lunar engine
 * is switched off here (as it is by default until its licence review and golden tables are done),
 * so this checks what a family sees today: tithi dates kept as written, the calendar by date with a
 * plain reason for the missing tithi days, and a private feed that leaves names out by default.
 */
test.use({ viewport: { width: 390, height: 844 } });

async function noSeriousAxe(page: Page) {
  const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"]).analyze();
  const blocking = axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
}

test("tithi dates, the family calendar and a private calendar feed", async ({ page, baseURL }) => {
  const ctx = page.context();
  const { treeId } = await registerWithTree(ctx, baseURL!, "Mishra parivar", "Mishra");
  const soon = new Date(Date.now() + 20 * 86_400_000);
  const person = await createPerson(ctx, baseURL!, treeId, "Kamla", "Mishra", {
    sex_at_birth: "female",
    birth: {
      date: {
        precision: "exact",
        year: 1950,
        month: soon.getMonth() + 1,
        day: soon.getDate(),
        lunar: { masa: "bhadrapada", paksha: "krishna", tithi: 8, month_convention: "purnimanta" },
      },
    },
  });

  // the tithi is shown as the family wrote it, next to the Gregorian date
  await page.goto(`/t/${treeId}/people/${person.id}`);
  await expect(page.getByText(/Bhadrapada Krishna Ashtami/).first()).toBeVisible();

  // tree settings: the month system and city, with the engine still switched off
  await page.goto(`/t/${treeId}/admin/settings`);
  const card = page.getByRole("region", { name: "Family calendar" });
  await expect(card.getByText("Tithi days are switched off on this site for now.")).toBeVisible();
  await card.getByLabel("Month system").selectOption("purnimanta");
  await card.getByLabel("Observance city").selectOption("varanasi");
  await card.getByRole("button", { name: "Save" }).click();
  await expect(card.getByText("Saved", { exact: true }).last()).toBeVisible();

  // the calendar: the birthday by date, and why there is no tithi day
  await page.goto(`/t/${treeId}/calendar`);
  await expect(page.getByRole("heading", { level: 1, name: "Family calendar" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Kamla Mishra/ })).toBeVisible();
  await expect(page.getByText("By date").first()).toBeVisible();
  await expect(page.getByText(/calendar engine has not been switched on/)).toBeVisible();
  await noSeriousAxe(page);

  // a private feed: names stay out unless chosen, and the link is shown once
  await page.getByRole("button", { name: "Make a calendar link" }).click();
  const link = page.getByLabel("Your calendar link");
  await expect(link).toBeVisible();
  const url = await link.inputValue();
  expect(url).toMatch(/\/api\/v1\/calendar-feeds\/[\w-]+\.ics$/);
  await noSeriousAxe(page);
  const ics = await page.request.get(url.replace(/^https?:\/\/[^/]+/, baseURL!));
  expect(ics.status()).toBe(200);
  const text = await ics.text();
  expect(text).toContain("BEGIN:VCALENDAR");
  expect(text).not.toContain("Kamla");

  // a revoked link stops working; reloading never shows it again
  await page.reload();
  await expect(page.getByLabel("Your calendar link")).toHaveCount(0);
  await page.getByRole("button", { name: "Turn off the link" }).click();
  await expect(page.getByRole("button", { name: "Make a calendar link" })).toBeVisible();
  expect((await page.request.get(url.replace(/^https?:\/\/[^/]+/, baseURL!))).status()).toBe(404);
});
