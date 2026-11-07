import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { api, registerWithTree } from "./helpers";

/**
 * Name transliteration suggestions (ADR-0025), against the real API on a phone-sized screen: the
 * typed name stays as typed; accepting the Devanagari suggestion adds a separate name that the
 * server records as calculated and confirmed by the user.
 */
test.use({ viewport: { width: 390, height: 844 } });

test("suggest a name in Devanagari and keep it as a separate, confirmed name", async ({ page, baseURL }) => {
  const ctx = page.context();
  const { treeId } = await registerWithTree(ctx, baseURL!, "Sharma parivar");
  await page.goto(`/t/${treeId}/people/new`);
  const consent = page.getByRole("checkbox", { name: /I confirm I have their permission/ });
  if (await consent.isVisible().catch(() => false)) {
    await consent.check();
    await page.getByRole("button", { name: "Confirm and continue" }).click();
  }
  const name1 = page.getByRole("group", { name: "Name 1" });
  await name1.getByLabel("Given name").fill("Sunita");
  await name1.getByLabel("Surname / family name").fill("Sharma");

  // the suggestion appears under the name, announced politely, without changing what was typed
  const suggestion = name1.getByRole("status");
  await expect(suggestion.getByText("In Devanagari:")).toBeVisible();
  await expect(suggestion.getByText("सुनीता शर्मा")).toHaveAttribute("lang", "hi");
  await expect(name1.getByLabel("Given name")).toHaveValue("Sunita");

  const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"]).analyze();
  const blocking = axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);

  await suggestion.getByRole("button", { name: /Add as another name: सुनीता शर्मा/ }).click();
  const name2 = page.getByRole("group", { name: "Name 2" });
  await expect(name2.getByLabel("Given name")).toHaveValue("सुनीता");
  await expect(name2.getByText("Spelling suggested, confirmed by you")).toBeVisible();
  await page.getByLabel("Living status").selectOption("deceased");
  await page.getByRole("button", { name: "Save person" }).click();

  await expect(page.getByRole("heading", { name: "Sunita Sharma", level: 1 })).toBeVisible();
  await expect(page.getByText("सुनीता शर्मा").first()).toBeVisible();

  const personId = page.url().split("/people/")[1].split(/[?#]/)[0];
  const person = await api<{ names: { given_name: string; is_preferred: boolean; provenance: { origin: string; algorithm_or_model: string | null } }[] }>(
    ctx,
    "GET",
    `/trees/${treeId}/people/${personId}`,
    undefined,
    baseURL!,
  );
  const typed = person.names.find((n) => n.given_name === "Sunita")!;
  const suggested = person.names.find((n) => n.given_name === "सुनीता")!;
  expect(typed.is_preferred).toBe(true);
  expect(typed.provenance.origin).toBe("manual");
  expect(suggested.is_preferred).toBe(false);
  expect(suggested.provenance.origin).toBe("calculation");
  expect(suggested.provenance.algorithm_or_model).toContain("vanshavali-translit");
});
