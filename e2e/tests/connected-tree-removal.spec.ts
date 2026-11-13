import { expect, test } from "@playwright/test";
import { api, createPerson, registerWithTree } from "./helpers";

/** The exact overview → complete chart → remove regression from a family tree. */
test("open full tree includes both directions; removal leaves no private placeholder", async ({ page, context, baseURL }) => {
  const { treeId } = await registerWithTree(context, baseURL!, "Connected test family");
  const ancestor = await createPerson(context, baseURL!, treeId, "Ancestor", "Family", { profile_status: "deceased" });
  const middle = await createPerson(context, baseURL!, treeId, "Middle", "Family", { profile_status: "deceased" });
  const grandchild = await createPerson(context, baseURL!, treeId, "Grandchild", "Family", { profile_status: "deceased" });
  const side = await createPerson(context, baseURL!, treeId, "Side", "Family", { profile_status: "deceased" });

  for (const [parent, child] of [[ancestor, middle], [middle, grandchild], [ancestor, side]]) {
    await api(context, "POST", `/trees/${treeId}/relationships`, {
      person_a_id: parent.id, person_b_id: child.id, type: "biological_parent",
    }, baseURL!);
  }

  await page.goto(`/t/${treeId}`);
  await expect(page.getByRole("link", { name: "Open full tree" })).toBeVisible();
  await page.getByRole("link", { name: "Open full tree" }).click();
  await expect(page).toHaveURL(/dir=connected/);
  const chart = page.getByRole("group", { name: "Family tree chart" });
  for (const name of ["Ancestor Family", "Middle Family", "Grandchild Family", "Side Family"]) {
    await expect(chart.getByRole("button", { name: new RegExp(name) })).toBeVisible();
  }

  await page.goto(`/t/${treeId}/people/${middle.id}`);
  await page.getByRole("button", { name: "Remove", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Remove Middle Family");
  await dialog.getByRole("button", { name: "Remove", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/t/${treeId}/people$`));

  await page.goto(`/t/${treeId}`);
  const overview = page.getByRole("group", { name: "Family tree chart" });
  await expect(overview.getByRole("button", { name: /Ancestor Family/ })).toBeVisible();
  await expect(overview.getByRole("button", { name: /Side Family/ })).toBeVisible();
  await expect(overview.getByRole("button", { name: /Middle Family|Grandchild Family|Private person/ })).toHaveCount(0);
  await page.getByRole("link", { name: "Open full tree" }).click();
  const full = page.getByRole("group", { name: "Family tree chart" });
  await expect(full.getByRole("button", { name: /Middle Family|Grandchild Family|Private person/ })).toHaveCount(0);
});
