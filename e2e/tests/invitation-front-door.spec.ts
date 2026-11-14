import { expect, test } from "@playwright/test";
import { api, createPerson, pickPerson, registerVerified, registerWithTree, uniqueEmail } from "./helpers";

/**
 * Phase F: the unified front door keeps the bearer-link claim flow distinct from membership
 * invitations, shares no family data, and reports only backend-observed outcomes.
 */
test("create and review a profile-claim invitation from the invitation front door", async ({ page, browser, baseURL }) => {
  const owner = page.context();
  const { treeId } = await registerWithTree(owner, baseURL!, "Front door family", "Asha Iyer");
  await createPerson(owner, baseURL!, treeId, "Meera", "Iyer", { profile_status: "living" });

  await page.goto(`/t/${treeId}/admin/invitations`);
  await expect(page.getByRole("heading", { name: "Invite family member" })).toBeVisible();
  await page.getByRole("button", { name: /Invite to claim a profile/ }).click();
  await pickPerson(page, "Relative's profile", "Meera Iyer");
  await page.getByRole("button", { name: "Create a private link for Meera Iyer" }).click();

  const whatsapp = page.getByRole("link", { name: /Share on WhatsApp/ });
  const telegram = page.getByRole("link", { name: /Share on Telegram/ });
  await expect(whatsapp).toBeVisible();
  await expect(telegram).toBeVisible();
  const whatsappHref = (await whatsapp.getAttribute("href"))!;
  const message = decodeURIComponent(whatsappHref.slice("https://wa.me/?text=".length));
  expect(message).not.toContain("Meera");
  expect(message).not.toContain("Front door family");
  const claimUrl = message.match(/https?:\/\/\S+\/claim#[\w-]+/)![0];
  const telegramUrl = new URL((await telegram.getAttribute("href"))!);
  expect(telegramUrl.origin + telegramUrl.pathname).toBe("https://t.me/share/url");
  expect(telegramUrl.searchParams.get("url")).toBe(claimUrl);

  const history = page.getByRole("listitem", { name: "Profile invitation for Meera Iyer" });
  await expect(history.getByText("Created")).toBeVisible();
  await expect(page.getByText("Sent", { exact: true })).toHaveCount(0);

  const relative = await browser.newContext({ baseURL });
  const relativeEmail = uniqueEmail("claim-relative");
  await registerVerified(relative, baseURL!, relativeEmail, "Meera Iyer");
  const token = claimUrl.split("#")[1];
  const statement = await api<{ version: string; language: string }>(
    relative,
    "GET",
    "/consent-statements/profile_claim?lang=en",
    undefined,
    baseURL!,
  );
  await api(
    relative,
    "POST",
    `/claim-invites/${token}/accept`,
    { consent_version: statement.version, language: statement.language, confirm_adult: true },
    baseURL!,
  );

  await page.reload();
  await expect(page.getByRole("listitem", { name: "Profile invitation for Meera Iyer" }).getByText("Claim requested")).toBeVisible();
  const claims = await api<Array<{ id: string }>>(owner, "GET", `/trees/${treeId}/claims`, undefined, baseURL!);
  await api(owner, "POST", `/trees/${treeId}/claims/${claims[0]!.id}/approve`, {}, baseURL!);
  await page.reload();
  await expect(page.getByRole("listitem", { name: "Profile invitation for Meera Iyer" }).getByText("Accepted")).toBeVisible();
  await relative.close();
});
