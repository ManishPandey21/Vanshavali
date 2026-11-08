import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { api, registerWithTree } from "./helpers";

/**
 * Indian geography reference data (ADR-0019) against the real API, on a phone-sized screen. The
 * database holds the SYNTHETIC fixture (backend/tests/fixtures/geo), loaded by scripts/reset_db.py:
 * snapshot 2026-05 is active, district 9901 is "Prayagraj" (formerly "Allahabad").
 */
test.use({ viewport: { width: 390, height: 844 } });

async function noSeriousAxe(page: Page) {
  const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"]).analyze();
  const blocking = axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
}

async function choose(scope: Page | ReturnType<Page["getByRole"]>, label: string, option: RegExp) {
  await scope.getByRole("combobox", { name: label }).click();
  await scope.getByRole("option", { name: option }).first().click();
}

test("pick a village from the LGD cascade on the Places page and keep it linked", async ({ page, baseURL }) => {
  const ctx = page.context();
  const { treeId } = await registerWithTree(ctx, baseURL!, "Mishra parivar");
  await page.goto(`/t/${treeId}/places`);
  await page.getByRole("button", { name: "New place" }).click();
  const dialog = page.getByRole("dialog");
  const cascade = dialog.getByRole("region", { name: "Local Government Directory" });
  await expect(cascade).toBeVisible();

  await choose(cascade, "State or union territory", /Uttar Pradesh/);
  await choose(cascade, "District", /Prayagraj/);
  // Uttar Pradesh calls its sub-districts tehsils
  await choose(cascade, "Tehsil", /Phulpur/);
  await expect(cascade.getByText("प्रयागराज")).toHaveAttribute("lang", "hi");
  await expect(cascade.getByText(/India Post \(data of 2026-05\)/)).toBeVisible();
  await noSeriousAxe(page);
  await choose(cascade, "Village or town", /^Rampur(?! ?a)/);

  // the pick fills the editable fields and links the code
  await expect(dialog.getByRole("textbox", { name: "Name", exact: true })).toHaveValue("Rampur");
  await expect(dialog.getByText("LGD Village 9900001")).toBeVisible();
  await dialog.getByRole("textbox", { name: "Name", exact: true }).fill("Rampur (Phulpur)"); // the family's spelling wins
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toBeHidden();

  const card = page.getByRole("listitem").filter({ hasText: "Rampur (Phulpur)" });
  await expect(card.getByText("LGD Village 9900001")).toBeVisible();
  await expect(card.getByText(/Prayagraj, Uttar Pradesh, India/)).toBeVisible();

  const places = await api<{ items: { canonical_name: string; lgd_code: string; lgd_level: string; lgd_snapshot_id: string; local_names: { name: string }[] }[] }>(
    ctx,
    "GET",
    `/trees/${treeId}/places`,
    undefined,
    baseURL!,
  );
  const saved = places.items.find((p) => p.canonical_name === "Rampur (Phulpur)")!;
  expect([saved.lgd_code, saved.lgd_level, saved.lgd_snapshot_id]).toEqual(["9900001", "village", "2026-05"]);
  expect(saved.local_names.map((n) => n.name)).toContain("रामपुर");

  // a former district name still finds the district, and says why
  await page.getByRole("button", { name: "New place" }).click();
  await choose(page.getByRole("dialog"), "State or union territory", /Uttar Pradesh/);
  await page.getByRole("dialog").getByRole("combobox", { name: "District" }).fill("Allahabad");
  await expect(page.getByRole("option", { name: /Prayagraj.*also known as Allahabad/ })).toBeVisible();
  await page.getByRole("dialog").getByRole("combobox", { name: "District" }).fill("");
  // a PIN code suggests the district and never picks the village
  await page.getByRole("dialog").getByLabel("PIN code").fill("212402");
  await page.getByRole("button", { name: "Use Prayagraj, Uttar Pradesh" }).click();
  await expect(page.getByRole("dialog").getByRole("group", { name: "District" })).toContainText("Prayagraj");
  await expect(page.getByRole("dialog").getByRole("textbox", { name: "Name", exact: true })).toHaveValue("");
});

test("a new person in a branch is offered the branch's ancestral village, and can find a birth place in Hindi", async ({ page, baseURL }) => {
  const ctx = page.context();
  const { treeId } = await registerWithTree(ctx, baseURL!, "Tiwari parivar");
  const village = await api<{ id: string }>(ctx, "POST", `/trees/${treeId}/places`, { canonical_name: "Sikandra", place_type: "village", lgd_code: "9900004", lgd_level: "village" }, baseURL!);
  const branch = await api<{ id: string }>(ctx, "POST", `/trees/${treeId}/branches`, { name: "Tiwari (Soraon)" }, baseURL!);
  await api(ctx, "POST", `/trees/${treeId}/branches/${branch.id}/heritage`, { attribute: "ancestral_village", place_id: village.id }, baseURL!);

  await page.goto(`/t/${treeId}/people/new`);
  const consent = page.getByRole("checkbox", { name: /I confirm I have their permission/ });
  if (await consent.isVisible().catch(() => false)) {
    await consent.check();
    await page.getByRole("button", { name: "Confirm and continue" }).click();
  }
  await page.getByRole("group", { name: "Name 1" }).getByLabel("Given name").fill("Kamla");
  await page.getByLabel("Living status").selectOption("deceased");

  // nothing is filled until a branch is chosen and the user accepts the offer
  const birthPlace = page.getByRole("combobox", { name: "Place of birth" });
  await expect(birthPlace).toHaveValue("");
  await page.getByLabel("Family branch").selectOption({ label: "Tiwari (Soraon)" });
  const offer = page.getByRole("status").filter({ hasText: "Ancestral village of Tiwari (Soraon)" });
  await expect(offer).toBeVisible();
  await expect(birthPlace).toHaveValue("");
  await noSeriousAxe(page);
  await offer.getByRole("button", { name: "Dismiss" }).click();
  await expect(offer).toBeHidden();

  // find the birth place in the directory by its Hindi name instead
  await page.getByRole("button", { name: "Find in the Local Government Directory" }).first().click();
  await page.getByRole("combobox", { name: "Search all villages and towns" }).fill("रामपुर");
  await page.getByRole("option", { name: /^Rampur रामपुर Phulpur, Prayagraj, Uttar Pradesh/ }).click();
  await expect(page.getByText("Linked to Rampur")).toBeVisible();
  await page.getByRole("button", { name: "Save person" }).click();
  await expect(page.getByRole("heading", { name: "Kamla", level: 1 })).toBeVisible();

  const personId = page.url().split("/people/")[1].split(/[?#]/)[0];
  const branchDetail = await api<{ members: { person: { id: string } | null }[] }>(ctx, "GET", `/trees/${treeId}/branches/${branch.id}`, undefined, baseURL!);
  expect(branchDetail.members.map((m) => m.person?.id)).toContain(personId);
  const places = await api<{ items: { lgd_code: string | null; lgd_level: string | null }[] }>(ctx, "GET", `/trees/${treeId}/places`, undefined, baseURL!);
  expect(places.items.some((p) => p.lgd_code === "9900001" && p.lgd_level === "village")).toBe(true);
});
