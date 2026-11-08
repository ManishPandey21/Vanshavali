import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { api, createPerson, pickPerson, registerWithTree } from "./helpers";

/**
 * Cultural depth (ADR-0026) against the real stack, on a phone-sized screen: relationship words
 * from the server's packs and the family's own words, the traditions archive, and the heritage
 * editor's new attributes with pravara suggestions that are never filled in.
 */
test.use({ viewport: { width: 390, height: 844 } });

async function noSeriousAxe(page: Page) {
  const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"]).analyze();
  const blocking = axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
}

async function family(page: Page, baseURL: string) {
  const owner = page.context();
  const { treeId } = await registerWithTree(owner, baseURL, "Sharma parivar", "Dadaji");
  const dada = await createPerson(owner, baseURL, treeId, "Ram", "Sharma", { profile_status: "deceased", sex_at_birth: "male" });
  const father = await createPerson(owner, baseURL, treeId, "Ramesh", "Sharma", {
    profile_status: "deceased",
    sex_at_birth: "male",
    birth: { date: { precision: "year_only", year: 1960 } },
  });
  const uncle = await createPerson(owner, baseURL, treeId, "Suresh", "Sharma", {
    profile_status: "deceased",
    sex_at_birth: "male",
    birth: { date: { precision: "year_only", year: 1952 } },
  });
  const me = await createPerson(owner, baseURL, treeId, "Aarav", "Sharma", { profile_status: "deceased", sex_at_birth: "male" });
  for (const child of [father, uncle]) {
    await api(owner, "POST", `/trees/${treeId}/relationships`, { person_a_id: dada.id, person_b_id: child.id, type: "biological_parent" }, baseURL);
  }
  await api(owner, "POST", `/trees/${treeId}/relationships`, { person_a_id: father.id, person_b_id: me.id, type: "biological_parent" }, baseURL);
  return { treeId, dada, father, uncle, me };
}

test("relationship words come from the family's chosen language, and the family's own word comes first", async ({ page, baseURL }) => {
  const f = await family(page, baseURL!);
  const path = `/t/${f.treeId}/relationship?from=${f.me.id}&to=${f.uncle.id}`;
  // English by default: the English label
  await page.goto(path);
  await expect(page.getByRole("heading", { level: 2, name: /uncle/ })).toBeVisible();

  // the tree's default words: Hindi (North), not yet reviewed by a native speaker, says so
  await page.goto(`/t/${f.treeId}/admin/settings`);
  await page.getByLabel("Default relationship words").selectOption("hi|north");
  await page.getByRole("region", { name: "Relationship words in this family" }).getByRole("button", { name: "Save" }).first().click();
  await expect(page.getByText("Saved").first()).toBeVisible();
  await page.goto(path);
  await expect(page.getByRole("heading", { level: 2, name: /ताऊ/ })).toBeVisible(); // the uncle is older than the father
  await expect(page.getByText("not yet reviewed")).toBeVisible();
  await expect(page.getByText("tau", { exact: true })).toBeVisible();
  await noSeriousAxe(page);

  // the family's own word for an elder paternal uncle
  await page.goto(`/t/${f.treeId}/admin/settings`);
  const form = page.getByRole("form", { name: "Add a family word" });
  await form.getByLabel("Step 1").selectOption("father");
  await form.getByLabel("Step 2").selectOption("brother");
  await form.getByLabel("Only when the relative is").selectOption("elder");
  await form.getByLabel("Your family's word").fill("बड़े बाबूजी");
  await expect(form.getByText("father's brother (elder)")).toBeVisible();
  await noSeriousAxe(page);
  await form.getByRole("button", { name: "Save word" }).click();
  await expect(page.getByRole("button", { name: "Remove the family word बड़े बाबूजी" })).toBeVisible();
  await page.goto(path);
  await expect(page.getByRole("heading", { level: 2, name: /बड़े बाबूजी/ })).toBeVisible();
  await expect(page.getByText("Your family's word")).toBeVisible();
  await expect(page.getByText("ताऊ")).toBeVisible();

  // a reader's own choice wins over the tree's: English again
  await page.goto("/account");
  await page.getByLabel("Relationship words in").selectOption({ label: "English" });
  await page.getByRole("region", { name: "Relationship words" }).getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved").first()).toBeVisible();
  await page.goto(path);
  await expect(page.getByRole("heading", { level: 2, name: /uncle/ })).toBeVisible();
});

test("a family tradition is written, linked to a person, found by search in any script, and kept private", async ({ page, baseURL }) => {
  const f = await family(page, baseURL!);
  await page.goto(`/t/${f.treeId}/traditions`);
  await expect(page.getByRole("heading", { level: 1, name: "Family traditions" })).toBeVisible();
  await page.getByRole("button", { name: "Add a tradition" }).click();
  const dialog = page.getByRole("dialog", { name: "Add a family tradition" });
  await dialog.getByLabel("Kind").selectOption("song");
  await dialog.getByLabel("Language").selectOption("hi");
  await dialog.getByLabel("Title").fill("होली के गीत");
  await dialog.getByLabel("Text", { exact: false }).fill("फागुन आयो रे\n\n- पहली पंक्ति\n- **दूसरी** पंक्ति");
  await pickPerson(page, "Add a person", "Ram Sharma", dialog);
  await expect(dialog.getByRole("button", { name: "Remove Ram Sharma" })).toBeVisible();
  await noSeriousAxe(page);
  await dialog.getByRole("button", { name: "Save" }).click();

  await expect(page.getByRole("heading", { level: 1, name: "होली के गीत" })).toBeVisible();
  await expect(page.getByRole("listitem").filter({ hasText: "दूसरी पंक्ति" }).locator("strong")).toHaveText("दूसरी");
  await expect(page.getByRole("link", { name: "Ram Sharma" })).toBeVisible();
  await noSeriousAxe(page);

  // found by a romanised search, and on the person's profile
  await page.goto(`/t/${f.treeId}/traditions`);
  await page.getByLabel("Search titles and text").fill("holi");
  await expect(page.getByRole("link", { name: "होली के गीत" })).toBeVisible();
  await page.goto(`/t/${f.treeId}/people/${f.dada.id}`);
  await expect(page.getByRole("heading", { name: "Family traditions" })).toBeVisible();
  await expect(page.getByRole("link", { name: "होली के गीत" })).toBeVisible();

  // never on the public (deceased-only) tree
  await api(page.context(), "PATCH", `/trees/${f.treeId}`, { public_mode: "DECEASED_ONLY" }, baseURL!);
  const tree = await api<{ slug: string }>(page.context(), "GET", `/trees/${f.treeId}`, undefined, baseURL!);
  const publicView = await page.request.get(`${baseURL}/api/v1/public/trees/${tree.slug}/traditions`);
  expect(publicView.status()).toBe(404);
});

test("heritage: devak, family languages and pravara suggestions that are never filled in", async ({ page, baseURL }) => {
  const f = await family(page, baseURL!);
  await page.goto(`/t/${f.treeId}/people/${f.dada.id}`);
  await page.getByRole("tab", { name: "Heritage" }).click();
  await page.getByRole("button", { name: "+ Devak" }).click();
  let dialog = page.getByRole("dialog", { name: "Add a heritage fact" });
  await dialog.getByRole("combobox", { name: "Value" }).fill("Panchpallav");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Panchpallav")).toBeVisible();

  // pravara: no gotra recorded from the list yet, so nothing is suggested; it stays free text
  await page.getByRole("button", { name: "+ Pravara" }).click();
  dialog = page.getByRole("dialog", { name: "Add a heritage fact" });
  await expect(dialog.getByText(/Record the gotra from the list first/)).toBeVisible();
  await noSeriousAxe(page);
  await dialog.getByRole("button", { name: "Cancel" }).click();

  await page.getByRole("button", { name: "+ Gotra" }).click();
  dialog = page.getByRole("dialog", { name: "Add a heritage fact" });
  await dialog.getByRole("combobox", { name: "Value" }).fill("Kashyap");
  await page.getByRole("option", { name: /Kashyapa/ }).first().click();
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Kashyapa").first()).toBeVisible();
  // the gotra never fills in a pravara
  await expect(page.getByRole("button", { name: "+ Pravara" })).toBeVisible();
  await page.getByRole("button", { name: "+ Pravara" }).click();
  dialog = page.getByRole("dialog", { name: "Add a heritage fact" });
  // shipped links are draft until sourced and reviewed: the note, and no suggestions yet
  await expect(dialog.getByText(/traditions differ/)).toBeVisible();
  await expect(dialog.getByText(/No reviewed pravara links for this gotra yet/)).toBeVisible();
  await expect(dialog.getByRole("combobox", { name: "Value" })).toHaveValue("");
  await noSeriousAxe(page);
});
