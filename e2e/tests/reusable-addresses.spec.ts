import { expect, test } from "@playwright/test";
import { api, createPerson, registerWithTree } from "./helpers";

/** Real-stack coverage for the reusable-address source picker, link/copy modes and explicit adoption. */
test("reuse a family address by link or copy and explicitly adopt a corrected version", async ({
  page,
  baseURL,
}) => {
  const ctx = page.context();
  const { treeId } = await registerWithTree(ctx, baseURL!, "Reusable address family");
  const person = await createPerson(ctx, baseURL!, treeId, "Lakshmi", "Iyer", {
    profile_status: "deceased",
  });
  const family = await api<{ id: string; revision: number }>(
    ctx,
    "POST",
    `/trees/${treeId}/family-addresses`,
    {
      label: "Iyer ancestral house",
      privacy_level: "TREE_MEMBERS",
      snapshot: {
        street: "12 Agraharam Street",
        locality: "Palakkad",
        district: "Palakkad",
        state: "Kerala",
        country_code: "IN",
        postal_code: "678001",
      },
    },
    baseURL!,
  );

  await page.goto(`/t/${treeId}/people/${person.id}?tab=addresses`);
  await page.getByRole("button", { name: "Reuse address" }).click();
  let dialog = page.getByRole("dialog", { name: "Reuse a family address" });
  await dialog.getByLabel("Address source").selectOption({ label: "Iyer ancestral house" });
  await expect(dialog.getByText("12 Agraharam Street")).toBeVisible();
  await dialog.getByLabel("Reuse as").selectOption("link");
  await dialog.getByRole("button", { name: "Use address" }).click();
  await expect(page.getByText("Linked · v1")).toBeVisible();
  await expect(page.getByText("12 Agraharam Street")).toBeVisible();

  await page.getByRole("button", { name: "Reuse address" }).click();
  dialog = page.getByRole("dialog", { name: "Reuse a family address" });
  await dialog.getByLabel("Address source").selectOption({ label: "Iyer ancestral house" });
  await dialog.getByLabel("Reuse as").selectOption("copy");
  await dialog.getByRole("button", { name: "Use address" }).click();
  await expect(page.getByText("Copied")).toBeVisible();

  await api(
    ctx,
    "POST",
    `/trees/${treeId}/family-addresses/${family.id}/versions`,
    {
      revision: family.revision,
      reason: "House number corrected",
      snapshot: {
        street: "14 Agraharam Street",
        locality: "Palakkad",
        district: "Palakkad",
        state: "Kerala",
        country_code: "IN",
        postal_code: "678001",
      },
    },
    baseURL!,
  );
  await page.reload();
  await expect(page.getByText(/Shared address version 2 is available/)).toBeVisible();
  await expect(page.getByText("12 Agraharam Street")).toHaveCount(2);
  await page.getByRole("button", { name: "Review update" }).click();
  const adoption = page.getByRole("dialog", { name: "Adopt the shared address update?" });
  await expect(adoption).toContainText("version 1");
  await expect(adoption).toContainText("version 2");
  await adoption.getByRole("button", { name: "Adopt version" }).click();
  await expect(page.getByText("Linked · v2")).toBeVisible();
  await expect(page.getByText("14 Agraharam Street")).toBeVisible();
  await expect(page.getByText(/Shared address version 2 is available/)).toHaveCount(0);
  // The independent copy remains pinned to the original snapshot.
  await expect(page.getByText("12 Agraharam Street")).toHaveCount(1);
});
