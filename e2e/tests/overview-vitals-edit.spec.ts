import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { api, createPerson, registerWithTree } from "./helpers";

/**
 * U02: birth and death are edited from the Overview "Life details" card through the existing
 * event editor. Real API, nothing mocked.
 */

const vitals = (page: Page) => page.getByRole("region", { name: "Life details" });

async function saveYearOnly(page: Page, year: string) {
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("How precise is this date?").selectOption({ label: "Year only" });
  await dialog.getByLabel("Year").fill(year);
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
}

test("add a year-only birth from Overview, then edit it; change survives reload", async ({ context, page, baseURL }) => {
  const { treeId } = await registerWithTree(context, baseURL!, "Vitals parivar");
  const person = await createPerson(context, baseURL!, treeId, "Mohan", "Verma", { sex_at_birth: "male" });
  await page.goto(`/t/${treeId}/people/${person.id}`);
  await expect(vitals(page)).toBeVisible();

  await vitals(page).getByRole("button", { name: "Add birth" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await saveYearOnly(page, "1950");
  await expect(vitals(page).getByText("1950")).toBeVisible();
  await expect(vitals(page).getByRole("button", { name: "Add birth" })).toHaveCount(0);

  await vitals(page).getByRole("button", { name: "Edit date of birth" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("Year")).toHaveValue("1950");
  await saveYearOnly(page, "1951");
  await expect(vitals(page).getByText("1951")).toBeVisible();

  await page.reload();
  await expect(vitals(page).getByText("1951")).toBeVisible();
  await expect(vitals(page).getByText("1950")).toHaveCount(0);
});

test("Cancel changes nothing", async ({ context, page, baseURL }) => {
  const { treeId } = await registerWithTree(context, baseURL!, "Cancel parivar");
  const person = await createPerson(context, baseURL!, treeId, "Sita", "Verma", { sex_at_birth: "female" });
  await page.goto(`/t/${treeId}/people/${person.id}`);
  await vitals(page).getByRole("button", { name: "Add birth" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(vitals(page).getByRole("button", { name: "Add birth" })).toBeVisible();
});

test("time and birthplace edits preserve the date and unknown zone after reload", async ({ context, page, baseURL }) => {
  const { treeId } = await registerWithTree(context, baseURL!, "Birth details");
  const person = await createPerson(context, baseURL!, treeId, "सीता", "वर्मा", {
    birth: { date: { precision: "year_only", year: 1950 } },
  });
  await page.goto(`/t/${treeId}/people/${person.id}`);
  await vitals(page).getByRole("button", { name: "Edit birth time" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("Time zone", { exact: true })).toHaveValue("");
  await expect(dialog.getByLabel("Year", { exact: true })).toHaveCount(0);
  await dialog.getByLabel("Time (24-hour)").fill("04:12:34");
  await dialog.getByLabel("UTC offset (minutes)").fill("330");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toHaveCount(0);
  await vitals(page).getByRole("button", { name: "Edit birthplace" }).click();
  await dialog.getByRole("combobox", { name: "Place", exact: true }).fill("पुराना गाँव, कानपुर");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toHaveCount(0);
  await page.reload();
  await expect(vitals(page).getByText("पुराना गाँव, कानपुर")).toBeVisible();
  await expect(vitals(page).getByText("1950")).toBeVisible();
  const events = await api<Array<{ date: { year: number }; time: { value: string }; timezone_id: string | null; utc_offset_minutes: number }>>(context, "GET", `/trees/${treeId}/people/${person.id}/events`, undefined, baseURL);
  expect(events[0].date.year).toBe(1950);
  expect(events[0].time.value).toBe("04:12:34");
  expect(events[0].timezone_id).toBeNull();
  expect(events[0].utc_offset_minutes).toBe(330);
});

for (const size of [
  { name: "desktop", width: 1280, height: 800 },
  { name: "390 px", width: 390, height: 844 },
]) {
  test(`Overview actions pass axe and have 44 px targets at ${size.name}`, async ({ context, page, baseURL }) => {
    const { treeId } = await registerWithTree(context, baseURL!, "Axe parivar");
    const person = await createPerson(context, baseURL!, treeId, "Gopal", "Verma", { profile_status: "deceased", sex_at_birth: "male" });
    await page.setViewportSize({ width: size.width, height: size.height });
    await page.goto(`/t/${treeId}/people/${person.id}`);
    const add = vitals(page).getByRole("button", { name: "Add death" });
    await expect(add).toBeVisible();
    await expect(page.locator(".animate-spin")).toHaveCount(0);
    for (const name of ["Add birth", "Add death"]) {
      const box = await vitals(page).getByRole("button", { name }).boundingBox();
      expect(box!.height).toBeGreaterThanOrEqual(44);
      expect(box!.width).toBeGreaterThanOrEqual(44);
    }
    await add.focus();
    await expect(add).toBeFocused();
    const results = await new AxeBuilder({ page })
      .include('section[aria-labelledby="ov-vitals"]')
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"])
      .analyze();
    expect(results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? "")).map((v) => v.id)).toEqual([]);
  });
}
