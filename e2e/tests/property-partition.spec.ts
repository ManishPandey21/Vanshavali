import { expect, test } from "@playwright/test";
import { createPerson, pickPerson, registerWithTree, simplePdf } from "./helpers";

/**
 * Critical flow 3: Create Property → Add Parcel → Link Ancestor (interest held by a deceased
 * person) → Upload Partition Deed → Record Partition among 3 holders → View History.
 */
test("property: parcel, ancestor's holding, partition deed, partition among three heirs", async ({ page, context, baseURL }) => {
  const { treeId } = await registerWithTree(context, baseURL!, "Tiwari khandan");
  await createPerson(context, baseURL!, treeId, "Shivnath", "Tiwari", { profile_status: "deceased", sex_at_birth: "male" });
  for (const n of ["Ramnath", "Somnath", "Kashinath"]) await createPerson(context, baseURL!, treeId, n, "Tiwari", { profile_status: "living", sex_at_birth: "male" });

  // ---- create property (legal notice always visible)
  await page.goto(`/t/${treeId}/property`);
  await expect(page.getByRole("note").first()).toContainText("not a legal title opinion");
  await page.getByRole("button", { name: "New property" }).click();
  let dialog = page.getByRole("dialog");
  await dialog.getByLabel(/^Name/).fill("Ancestral fields at Bhitari");
  await dialog.getByLabel("Classification").selectOption("ancestral");
  await dialog.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { name: "Ancestral fields at Bhitari", level: 1 })).toBeVisible();
  await expect(page.getByRole("note").first()).toContainText("not a legal title opinion");

  // ---- parcel with Indian identifiers; ULPIN is validated before saving
  await page.getByRole("tab", { name: /Parcels/ }).click();
  await page.getByRole("button", { name: "Add parcel" }).click();
  dialog = page.getByRole("dialog");
  await dialog.getByLabel("Village", { exact: true }).fill("Bhitari");
  await dialog.getByLabel("District", { exact: true }).fill("Ghazipur");
  await dialog.getByLabel("Khasra / gata no.").fill("412");
  await dialog.getByLabel("ULPIN").fill("UP12ABC");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog.getByText("ULPIN must be exactly 14 letters or digits.")).toBeVisible();
  await dialog.getByLabel("ULPIN").fill("UP0912345678AB");
  await dialog.getByLabel("Area", { exact: true }).fill("3.5");
  await dialog.getByLabel("Unit", { exact: true }).selectOption("bigha");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByText("UP0912345678AB")).toBeVisible();

  // ---- the deceased ancestor holds the whole property (documented)
  await page.getByRole("tab", { name: "Holders & shares" }).click();
  await page.getByRole("button", { name: "Add holder" }).click();
  dialog = page.getByRole("dialog");
  await pickPerson(page, "Holder", "Shivnath Tiwari", dialog);
  await dialog.getByLabel("Share").fill("1");
  await dialog.getByLabel("Status").selectOption("documented");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toBeHidden();
  const holders = page.getByRole("tabpanel");
  await expect(holders.getByRole("link", { name: "Shivnath Tiwari" })).toBeVisible();
  await expect(holders.getByText("Deceased")).toBeVisible();

  // ---- upload the partition deed (vault category, linked to the property)
  await page.getByRole("tab", { name: /Documents/ }).click();
  await page.getByRole("button", { name: "Upload document" }).click();
  dialog = page.getByRole("dialog");
  await dialog.getByLabel("Category").selectOption("partition_deed");
  await dialog.getByLabel(/^File/).setInputFiles({ name: "partition-deed-1990.pdf", mimeType: "application/pdf", buffer: simplePdf("Partition deed 1990 Bhitari") });
  await dialog.getByLabel(/^Title/).fill("Partition deed 1990");
  await dialog.getByRole("button", { name: "Upload document" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("link", { name: "Partition deed 1990" })).toBeVisible();

  // ---- partition wizard: 1/3 each to three heirs, deed linked
  await page.getByRole("tab", { name: "Timeline" }).click();
  await page.getByRole("button", { name: "Record partition" }).click();
  dialog = page.getByRole("dialog");
  const date = dialog.getByRole("group", { name: "Date of partition" });
  await date.getByLabel("How precise is this date?").selectOption("year_only");
  await date.getByLabel(/^Year/).fill("1990");
  await dialog.getByLabel("Registration number").fill("GZP/1990/77");
  await dialog.getByRole("button", { name: "Next" }).click();
  await expect(dialog.getByText("Total being divided")).toContainText("1");
  await dialog.getByRole("button", { name: "Next" }).click();

  const heirs = ["Ramnath Tiwari", "Somnath Tiwari", "Kashinath Tiwari"];
  for (let i = 0; i < heirs.length; i++) {
    if (i > 0) await dialog.getByRole("button", { name: "Add holder" }).click();
    const alloc = dialog.getByRole("group", { name: `Allocation ${i + 1}` });
    await pickPerson(page, "Holder", heirs[i], alloc);
    await alloc.getByLabel("Share").fill(i < 2 ? "1/3" : "1/4");
  }
  // 1/3 + 1/3 + 1/4 ≠ 1: blocked with an exact explanation, not a rounding guess.
  await expect(dialog.getByText(/must add up exactly/)).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Next" })).toBeDisabled();
  await dialog.getByRole("group", { name: "Allocation 3" }).getByLabel("Share").fill("1/3");
  await expect(dialog.getByText("Allocated 1 of 1")).toBeVisible();
  await dialog.getByRole("button", { name: "Next" }).click();
  await dialog.getByLabel(/Partition deed 1990/).check();
  await dialog.getByRole("button", { name: "Record partition" }).click();
  await expect(dialog).toBeHidden();

  // ---- history: the partition event, who it moved from/to, and the linked deed
  const partition = page.getByRole("article", { name: "Partition" });
  await expect(partition).toBeVisible();
  await expect(partition).toContainText("1990");
  await expect(partition).toContainText("Reg. no. GZP/1990/77");
  await expect(partition.getByRole("link", { name: "Shivnath Tiwari" })).toBeVisible();
  for (const h of heirs) await expect(partition.getByRole("link", { name: h })).toBeVisible();
  await expect(partition.getByRole("link", { name: "Partition deed 1990" })).toBeVisible();

  // holders-at-date: before the partition the ancestor held it
  await page.getByLabel("Who held it on").fill("1985-06-01");
  await expect(page.getByRole("heading", { name: /Holders on 1985-06-01/ })).toBeVisible();

  // current holders: three exact thirds
  await page.getByRole("tab", { name: "Holders & shares" }).click();
  const current = page.getByRole("tabpanel");
  for (const h of heirs) await expect(current.getByRole("link", { name: h })).toBeVisible();
  await expect(current.getByText("1/3", { exact: true })).toHaveCount(3);
});
