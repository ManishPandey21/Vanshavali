import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { api, createPerson, registerWithTree } from "./helpers";

/**
 * Age-aware kinship terms (ADR-0020 §5) through the real SPA and API: with no birth dates the
 * calculator shows both words and asks whether the uncle is older or younger than the *father*;
 * the family's answer is recorded and the term becomes ताऊ.
 */
test("Tau or Chacha: the family's answer decides the term", async ({ page, baseURL }) => {
  const ctx = page.context();
  const { treeId } = await registerWithTree(ctx, baseURL!, "Sharma parivar");
  const dada = await createPerson(ctx, baseURL!, treeId, "Shyam", "Sharma", { sex_at_birth: "male", profile_status: "deceased" });
  const father = await createPerson(ctx, baseURL!, treeId, "Ramesh", "Sharma", { sex_at_birth: "male", profile_status: "deceased" });
  const uncle = await createPerson(ctx, baseURL!, treeId, "Suresh", "Sharma", { sex_at_birth: "male", profile_status: "deceased" });
  const me = await createPerson(ctx, baseURL!, treeId, "Aarav", "Sharma", { sex_at_birth: "male", profile_status: "living" });
  for (const child of [father, uncle]) {
    await api(ctx, "POST", `/trees/${treeId}/relationships`, { person_a_id: dada.id, person_b_id: child.id, type: "biological_parent" }, baseURL!);
  }
  await api(ctx, "POST", `/trees/${treeId}/relationships`, { person_a_id: father.id, person_b_id: me.id, type: "biological_parent" }, baseURL!);

  await page.goto(`/t/${treeId}/relationship?from=${me.id}&to=${uncle.id}`);
  const question = page.getByRole("group", { name: "Is Suresh Sharma older or younger than Ramesh Sharma?" });
  await expect(question).toBeVisible();
  const scan = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"]).analyze();
  expect(scan.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([]);

  await question.getByRole("button", { name: "Older than Ramesh Sharma" }).click();
  await expect(question).toBeHidden();
  await expect(page.getByText("father's elder brother")).toBeVisible();
  await expect(page.getByText(/confirmed by the family/)).toBeVisible();

  // in Hindi the term is now ताऊ, not "चाचा / ताऊ"
  await page.getByLabel("Language").first().selectOption("hi");
  await expect(page.getByRole("heading", { name: /ताऊ/ })).toBeVisible();
  await expect(page.getByText("चाचा / ताऊ")).toHaveCount(0);

  const path = await api<{ age_orders: { order: string; basis: string; relative_to_id: string }[] }>(
    ctx,
    "GET",
    `/trees/${treeId}/relationship-path?from=${me.id}&to=${uncle.id}`,
    undefined,
    baseURL!,
  );
  expect(path.age_orders).toEqual([expect.objectContaining({ order: "elder", basis: "family_confirmed", relative_to_id: father.id })]);
});
