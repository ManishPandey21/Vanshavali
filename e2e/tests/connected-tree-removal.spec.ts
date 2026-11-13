import { expect, test } from "@playwright/test";
import { api, createPerson, registerWithTree, registerVerified, uniqueEmail } from "./helpers";

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

test("permanent delete requires a reason, preserves failure recovery, and denies a viewer", async ({ browser, page, context, baseURL }) => {
  const { treeId } = await registerWithTree(context, baseURL!, "Deletion protection");
  const target = await createPerson(context, baseURL!, treeId, "DeleteCandidate", "Pandey", { profile_status: "deceased" });

  await page.goto(`/t/${treeId}/people/${target.id}`);
  await page.getByRole("button", { name: "Delete permanently" }).click();
  const confirmation = page.getByRole("dialog");
  await expect(confirmation).toBeVisible();
  const eraseAction = confirmation.getByRole("button", { name: "Delete permanently" });
  await expect(eraseAction).toBeDisabled();
  await confirmation.getByLabel("Reason for permanent deletion").fill("No");
  await expect(eraseAction).toBeDisabled();
  await confirmation.getByLabel("Reason for permanent deletion").fill("Remove duplicate profile");
  await expect(eraseAction).toBeEnabled();

  // A failing API must not navigate away or misreport success, and the reason
  // must remain available for a correction/retry.
  await page.route(`**/api/v1/trees/${treeId}/people/${target.id}/erase`, async (route) => {
    await route.fulfill({
      status: 500, contentType: "application/json",
      body: JSON.stringify({ error: { code: "simulated_failure", message: "Simulated erasure failure" } }),
    });
  });
  await eraseAction.click();
  await expect(confirmation.getByRole("alert")).toContainText("Simulated erasure failure");
  await expect(page).toHaveURL(new RegExp(`/people/${target.id}$`));
  await expect(confirmation.getByLabel("Reason for permanent deletion")).toHaveValue("Remove duplicate profile");
  await page.unroute(`**/api/v1/trees/${treeId}/people/${target.id}/erase`);

  // A genuine viewer has read access but must not see delete controls or
  // succeed in an API-level erasure, even with their own valid CSRF token.
  const viewerCtx = await browser.newContext({ baseURL });
  const email = uniqueEmail("eraserviewer");
  await registerVerified(viewerCtx, baseURL!, email);
  const invite = await api<{ token: string }>(
    context, "POST", `/trees/${treeId}/invitations`,
    { email, roles: ["VIEWER"] }, baseURL!,
  );
  await api(viewerCtx, "POST", `/invitations/${invite.token}/accept`, {}, baseURL!);
  const viewerPage = await viewerCtx.newPage();
  await viewerPage.goto(`/t/${treeId}/people/${target.id}`);
  await expect(viewerPage.getByRole("heading", { name: "DeleteCandidate Pandey" })).toBeVisible();
  await expect(viewerPage.getByRole("button", { name: "Delete permanently" })).toHaveCount(0);
  const viewerCsrf = (await viewerCtx.cookies()).find((cookie) => cookie.name === "vsh_csrf")?.value ?? "";
  const denied = await viewerCtx.request.post(
    `${baseURL}/api/v1/trees/${treeId}/people/${target.id}/erase`, {
      data: { reason: "Not authorized", confirm: true },
      headers: { "X-CSRF-Token": viewerCsrf },
    },
  );
  expect(denied.status()).toBe(403);
  await viewerCtx.close();

  // Retrying after removing the simulated failure must use the server's
  // real irreversible erasure path, not a client-side optimistic state.
  await eraseAction.click();
  await expect(page).toHaveURL(new RegExp(`/t/${treeId}/people$`));
  const archive = await api<{ display_name: string }>(
    context, "GET", `/trees/${treeId}/people/${target.id}`, undefined, baseURL!,
  );
  expect(archive.display_name).toBe("Erased person");
  const listed = await api<{ items: { id: string }[] }>(
    context, "GET", `/trees/${treeId}/people`, undefined, baseURL!,
  );
  expect(listed.items.map((p) => p.id)).not.toContain(target.id);
});
