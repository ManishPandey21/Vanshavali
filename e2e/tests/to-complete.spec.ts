import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { api, createPerson, registerWithTree } from "./helpers";

/**
 * "To complete" (ADR-0020 §8, issues #32/#33), against the real API on a phone-sized screen: a
 * provisional mother added by Smart Add is listed with what is missing, leaves the headline branch
 * count, and moves from "needs a name" to "not yet verified" once named.
 */
test.use({ viewport: { width: 390, height: 844 } });

test("provisional people are listed to complete and left out of headline counts", async ({ page, baseURL }) => {
  const ctx = page.context();
  const { treeId } = await registerWithTree(ctx, baseURL!, "Verma parivar");
  const branch = await api<{ id: string }>(ctx, "POST", `/trees/${treeId}/branches`, { name: "Verma" }, baseURL!);
  const me = await createPerson(ctx, baseURL!, treeId, "Aarav", "Verma", { profile_status: "deceased", branch_ids: [branch.id] });
  const added = await api<{ person: { id: string }; created_people: { id: string }[] }>(
    ctx,
    "POST",
    `/trees/${treeId}/people/${me.id}/smart-add`,
    { term: "mama", choices: ["new"], new_person: { profile_status: "deceased", names: [{ given_name: "Mohan", surname: "Verma", is_preferred: true }] } },
    baseURL!,
  );
  const mother = added.created_people.find((p) => p.id !== added.person.id)!;
  await api(ctx, "POST", `/trees/${treeId}/branches/${branch.id}/members`, { person_ids: [mother.id] }, baseURL!);

  // headline branch count: Aarav only; the admin count shows the one to complete
  await page.goto(`/t/${treeId}/branches`);
  await expect(page.getByText("1 member", { exact: true })).toBeVisible();
  await expect(page.getByText("1 to complete")).toBeVisible();

  await page.goto(`/t/${treeId}/people`);
  const toggle = page.getByRole("button", { name: "To complete" });
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
  await expect(page).toHaveURL(/view=to-complete/);
  await expect(page.getByText(/only you and the tree admins can see them/)).toBeVisible();
  await expect(page.getByText("Aarav Verma")).toHaveCount(0);
  await expect(page.getByText("No name yet.")).toBeVisible();

  const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"]).analyze();
  const blocking = axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);

  // the action goes to the profile, where a name can be added
  await page.getByRole("link", { name: /Add their name/ }).click();
  await expect(page).toHaveURL(new RegExp(`/people/${mother.id}\\?tab=overview`));

  await api(ctx, "POST", `/trees/${treeId}/people/${mother.id}/names`, { given_name: "Sunita", surname: "Verma" }, baseURL!);
  await page.goto(`/t/${treeId}/people?view=to-complete`);
  await expect(page.getByText(/no supporting evidence yet/)).toBeVisible();
  await expect(page.getByRole("link", { name: /Review relationship evidence/ })).toHaveAttribute("href", `/t/${treeId}/people/${mother.id}?tab=family`);
});
