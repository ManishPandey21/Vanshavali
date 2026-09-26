import { expect, test } from "@playwright/test";
import { api, registerWithTree, renderTextPng, storedZip } from "./helpers";

/**
 * ADR-0013: a MyHeritage-style export (the .ged plus its "…_Photos" folder, zipped) imports the
 * people and links each photo to its person through the normal document pipeline. Nothing mocked.
 */
test("import a GEDCOM zip with its photos folder and find the photo on the person", async ({ page, browser, baseURL }) => {
  const { treeId } = await registerWithTree(page.context(), baseURL!, "Verma parivar");
  const photo = await renderTextPng(browser, ["Kamla Verma, 1962"]);
  const win = "C:\\Users\\someone\\Downloads\\Verma Family Tree_Photos\\";
  const ged = [
    "0 HEAD", "1 GEDC", "2 VERS 5.5.1", "1 CHAR UTF-8", "1 SOUR MYHERITAGE",
    "0 @I1@ INDI", "1 NAME Kamla /Verma/", "1 SEX F", "1 BIRT", "2 DATE 1940",
    "1 OBJE", "2 FORM png", "2 TITL Kamla at the wedding", `2 FILE ${win}P1_kamla.png`,
    "1 OBJE", "2 FORM jpg", `2 FILE ${win}P2_not_exported.jpg`,
    "0 TRLR", "",
  ].join("\r\n");
  const zip = storedZip({ "Verma Family Tree.ged": ged, "Verma Family Tree_Photos/P1_kamla.png": photo });

  await page.goto(`/t/${treeId}/import-export`);
  await expect(page.getByText(/put the .ged file and its photos folder/)).toBeVisible();
  await page.getByLabel("GEDCOM file").setInputFiles({ name: "Verma Family Tree.zip", mimeType: "application/zip", buffer: zip });
  await page.getByRole("button", { name: "Upload & analyse" }).click();

  await expect(page.getByText(/Photos: 1 of 2 found in the zip, for 1 people/)).toBeVisible();
  await page.getByText(/1 photo will be skipped/).click();
  await expect(page.getByText("P2_not_exported.jpg")).toBeVisible();
  await page.getByRole("button", { name: /Import: 1 new/ }).click();
  await expect(page.getByText("1 photo imported and linked to people.")).toBeVisible();

  // the photo is an ordinary, scanned document linked to Kamla
  const people = await api<{ items: { id: string; display_name: string }[] }>(page.context(), "GET", `/trees/${treeId}/people`, undefined, baseURL!);
  const kamla = people.items.find((p) => p.display_name === "Kamla Verma")!;
  const docs = await api<{ items: { title: string; category: string; scan_status: string; links: { target_id: string }[] }[] }>(
    page.context(), "GET", `/trees/${treeId}/documents`, undefined, baseURL!,
  );
  expect(docs.items).toHaveLength(1);
  expect(docs.items[0]).toMatchObject({ title: "Kamla at the wedding", category: "photo", scan_status: "clean" });
  expect(docs.items[0].links.map((l) => l.target_id)).toEqual([kamla.id]);
  await page.goto(`/t/${treeId}/people/${kamla.id}?tab=documents`);
  await expect(page.getByText("Kamla at the wedding")).toBeVisible();
});
