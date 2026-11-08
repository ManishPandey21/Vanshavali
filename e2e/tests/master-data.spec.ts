import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { api, createPerson, registerWithTree } from "./helpers";

/**
 * Master data (ADR-0018) through the real SPA and API: heritage values get suggestions in any
 * script, a chosen value stores its label as typed plus a link to the entry, and a family can add
 * its own kuladevata, which then appears for the next person — and never in another family's tree.
 */
test("gotra suggestions across scripts and the family's own kuladevata", async ({ page, baseURL }) => {
  const ctx = page.context();
  const { treeId } = await registerWithTree(ctx, baseURL!, "Patil parivar");
  const ramesh = await createPerson(ctx, baseURL!, treeId, "Ramesh", "Patil", { sex_at_birth: "male", profile_status: "deceased" });
  const suresh = await createPerson(ctx, baseURL!, treeId, "Suresh", "Patil", { sex_at_birth: "male", profile_status: "deceased" });

  // the shipped packs were loaded by the e2e reset, like the pilot migrate service does
  const vocabularies = await api<{ key: string }[]>(ctx, "GET", "/vocabularies", undefined, baseURL!);
  expect(vocabularies.map((v) => v.key)).toEqual(expect.arrayContaining(["gotra", "kuladevata", "occupation"]));

  await page.goto(`/t/${treeId}/people/${ramesh.id}`);
  await page.getByRole("tab", { name: "Heritage" }).click();

  // gotra: typed in Devanagari, picked from the list
  await page.getByRole("button", { name: "Add heritage fact" }).first().click();
  let dialog = page.getByRole("dialog");
  await dialog.getByLabel("Attribute").selectOption("gotra");
  const value = dialog.getByRole("combobox", { name: "Value" });
  await value.fill("भरद्");
  await dialog.getByRole("option", { name: /Bharadwaja/ }).click();
  await expect(value).toHaveValue("Bharadwaja");
  await expect(dialog.getByText(/Chosen from the list/)).toBeVisible();
  const scan = await new AxeBuilder({ page }).include('[role="dialog"]').withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"]).analyze();
  expect(scan.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([]);
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toBeHidden();

  // kuladevata: not in the (empty) global list, so the family adds its own
  await page.getByRole("button", { name: "Add heritage fact" }).first().click();
  dialog = page.getByRole("dialog");
  await dialog.getByLabel("Attribute").selectOption("kuladevata");
  await dialog.getByRole("combobox", { name: "Value" }).fill("Khandoba");
  await dialog.getByRole("option", { name: /Add “Khandoba” as your family's own entry/ }).click();
  await expect(dialog.getByText(/Chosen from the list/)).toBeVisible();
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toBeHidden();

  const profile = await api<{ attributes: { attribute: string; preferred: { value_text: string; value_json: { vocabulary: string; code: string } } }[] }>(
    ctx,
    "GET",
    `/trees/${treeId}/people/${ramesh.id}/heritage`,
    undefined,
    baseURL!,
  );
  const byAttr = Object.fromEntries(profile.attributes.map((a) => [a.attribute, a.preferred]));
  expect(byAttr.gotra).toMatchObject({ value_text: "Bharadwaja", value_json: { vocabulary: "gotra", code: "bharadwaja" } });
  expect(byAttr.kuladevata.value_text).toBe("Khandoba");
  expect(byAttr.kuladevata.value_json.code).toMatch(/^t:/);

  // the family's entry is offered for the next person (spelt differently), and nothing was inferred
  await page.goto(`/t/${treeId}/people/${suresh.id}`);
  await page.getByRole("tab", { name: "Heritage" }).click();
  await page.getByRole("button", { name: "Add heritage fact" }).first().click();
  dialog = page.getByRole("dialog");
  await dialog.getByLabel("Attribute").selectOption("kuladevata");
  await dialog.getByRole("combobox", { name: "Value" }).fill("khand");
  await expect(dialog.getByRole("option", { name: /Khandoba.*Your family/ })).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  const sureshProfile = await api<{ attributes: unknown[] }>(ctx, "GET", `/trees/${treeId}/people/${suresh.id}/heritage`, undefined, baseURL!);
  expect(sureshProfile.attributes).toEqual([]);

  // another family never sees it
  const other = await api<{ id: string }>(ctx, "POST", "/trees", { name: "Other family" }, baseURL!);
  const otherList = await api<{ items: unknown[] }>(ctx, "GET", `/trees/${other.id}/vocabularies/kuladevata`, undefined, baseURL!);
  expect(otherList.items).toEqual([]);
});
