import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { api, createPerson, registerWithTree } from "./helpers";

/**
 * Smart Add Relative (ADR-0020), against the real API on a phone-sized screen:
 * "Mama" when no mother is recorded → the mother is added as an unnamed provisional person only
 * after the user chose that and saw the preview; the calculator then finds मामा. Undo removes
 * exactly what was added.
 */
test.use({ viewport: { width: 390, height: 844 } });

/** axe WCAG 2.2 A/AA on the open dialog: no serious or critical violations (same bar as a11y.spec.ts). */
async function axeDialog(page: Page, label: string) {
  const results = await new AxeBuilder({ page })
    .include('[role="dialog"]')
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"])
    .analyze();
  const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect.soft(blocking.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`), `axe on ${label}`).toEqual([]);
}

test("add a Mama through an unknown mother, with preview and the right relationship", async ({ page, baseURL }) => {
  const ctx = page.context();
  const { treeId } = await registerWithTree(ctx, baseURL!, "Verma parivar");
  const me = await createPerson(ctx, baseURL!, treeId, "Aarav", "Verma", { sex_at_birth: "male", profile_status: "living" });

  await page.goto(`/t/${treeId}/people/${me.id}`);
  await page.getByRole("tab", { name: "Family" }).click();
  await page.getByRole("button", { name: "Add a relative" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByText("More relations").click();
  await axeDialog(page, "smart add: choose");
  await dialog.getByRole("button", { name: /Mama · मामा/ }).click();
  await expect(dialog.getByRole("radio", { name: /add the mother as unknown for now/ })).toBeVisible();
  await axeDialog(page, "smart add: step");

  // no mother is recorded: the user must explicitly choose to add her as unknown
  await dialog.getByRole("radio", { name: /add the mother as unknown for now/ }).check();
  await dialog.getByRole("button", { name: "Continue" }).click();
  await expect(dialog.getByLabel("Sex at birth")).toHaveValue("male");
  await dialog.getByLabel("Given name").fill("Mohan");
  await dialog.getByLabel("Surname").fill("Verma");
  await dialog.getByRole("button", { name: "Review" }).click();

  await expect(dialog.getByText(/not known yet — added as an unnamed person/)).toBeVisible();
  await expect(dialog.getByText(/Mohan Verma \(new\)/)).toBeVisible();
  await axeDialog(page, "smart add: preview");
  // nothing has been written before confirming
  const before = await api<{ items: unknown[] }>(ctx, "GET", `/trees/${treeId}/people`, undefined, baseURL!);
  expect(before.items).toHaveLength(1);

  await dialog.getByRole("button", { name: "Confirm and add" }).click();
  await expect(dialog.getByText(/Mohan Verma was added as Aarav Verma's Mama/)).toBeVisible();
  await dialog.getByRole("button", { name: "Close" }).first().click();

  // the provisional mother shows in the family panel, marked to complete
  await expect(page.getByText("To complete").first()).toBeVisible();

  const people = await api<{ items: { id: string; display_name: string }[] }>(ctx, "GET", `/trees/${treeId}/people`, undefined, baseURL!);
  const mohan = people.items.find((p) => p.display_name === "Mohan Verma")!;
  const path = await api<{ label: string; chain: string[] }>(
    ctx,
    "GET",
    `/trees/${treeId}/relationship-path?from=${me.id}&to=${mohan.id}`,
    undefined,
    baseURL!,
  );
  expect(path.label).toBe("uncle");
  expect(path.chain).toEqual(["mother", "brother"]);
});

test("undo removes exactly what Smart Add created", async ({ page, baseURL }) => {
  const ctx = page.context();
  const { treeId } = await registerWithTree(ctx, baseURL!, "Undo parivar");
  const me = await createPerson(ctx, baseURL!, treeId, "Aarav", "Sharma", { sex_at_birth: "male", profile_status: "living" });

  await page.goto(`/t/${treeId}/people/${me.id}`);
  await page.getByRole("tab", { name: "Family" }).click();
  await page.getByRole("button", { name: "Add a relative" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: /^Brother/ }).click();
  await dialog.getByLabel("Given name").fill("Vikram");
  await dialog.getByRole("radio", { name: "Older" }).check();
  await dialog.getByRole("button", { name: "Review" }).click();
  await expect(dialog.getByText(/Recorded as older than Aarav Sharma/)).toBeVisible();
  await dialog.getByRole("button", { name: "Confirm and add" }).click();
  await expect(dialog.getByText(/Vikram was added/)).toBeVisible();
  await dialog.getByRole("button", { name: "Undo" }).click();
  await expect(dialog.getByText(/Undone/)).toBeVisible();

  const people = await api<{ items: { display_name: string }[] }>(ctx, "GET", `/trees/${treeId}/people`, undefined, baseURL!);
  expect(people.items.map((p) => p.display_name)).toEqual(["Aarav Sharma"]);
});
