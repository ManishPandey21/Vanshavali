import { expect, test } from "@playwright/test";
import { PASSWORD, api, createPerson, openVerificationLink, registerWithTree, uniqueEmail } from "./helpers";

/**
 * Critical flow 4: Viewer Attempts Unauthorized Change. A second user joins via an invitation link
 * as VIEWER; the UI offers no edit controls, and a direct API write made with the viewer's own
 * cookies + CSRF header is refused (403) — the server is the authority — with data unchanged.
 */
test("viewer sees no edit controls and a direct PATCH is refused", async ({ browser, context, baseURL }) => {
  const { treeId } = await registerWithTree(context, baseURL!, "Joshi parivar");
  const person = await createPerson(context, baseURL!, treeId, "Gopal", "Joshi", { profile_status: "deceased", sex_at_birth: "male" });
  const viewerEmail = uniqueEmail("viewer");
  const invite = await api<{ invite_url: string; token: string }>(context, "POST", `/trees/${treeId}/invitations`, { email: viewerEmail, roles: ["VIEWER"] }, baseURL!);
  const invitePath = new URL(invite.invite_url).pathname;

  // ---- the viewer, in a separate browser context, registers through the UI via the invite link
  const viewerCtx = await browser.newContext({ baseURL });
  const page = await viewerCtx.newPage();
  await page.goto(invitePath);
  await expect(page).toHaveURL(/\/login\?next=/);
  await page.getByRole("link", { name: "Create account" }).click();
  await page.getByLabel("Your name").fill("Viewer Cousin");
  await page.getByLabel("Email").fill(viewerEmail);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();
  // the verification link carries the invitation as #next=, so opening it continues to the invite
  await openVerificationLink(page, viewerEmail);
  await expect(page.getByRole("heading", { name: "Family tree invitation" })).toBeVisible();
  await expect(page.getByText("Viewer", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Join this family tree" }).click();
  await expect(page.getByRole("heading", { name: "Joshi parivar" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Add person" })).toHaveCount(0);

  // ---- profile: readable, but no edit controls anywhere
  await page.goto(`/t/${treeId}/people/${person.id}`);
  await expect(page.getByRole("heading", { name: "Gopal Joshi", level: 1 })).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit details" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Add name" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Remove" })).toHaveCount(0);
  await page.getByRole("tab", { name: "Family" }).click();
  await expect(page.getByRole("button", { name: "Add parent" })).toHaveCount(0);
  await page.getByRole("tab", { name: "Timeline" }).click();
  await expect(page.getByRole("button", { name: "Add event" })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "Privacy" })).toHaveCount(0);

  // ---- a hand-crafted write with the viewer's session and a valid CSRF header is refused
  const result = await page.evaluate(
    async ({ treeId, personId }) => {
      const csrf = document.cookie.split("; ").find((c) => c.startsWith("vsh_csrf="))?.split("=")[1] ?? "";
      const res = await fetch(`/api/v1/trees/${treeId}/people/${personId}`, {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": decodeURIComponent(csrf) },
        body: JSON.stringify({ preferred_display_name: "Hacked Name", occupation: "tampered" }),
      });
      return { status: res.status, body: await res.json(), hadCsrf: csrf.length > 0 };
    },
    { treeId, personId: person.id },
  );
  expect(result.hadCsrf).toBe(true);
  expect(result.status).toBe(403);
  expect(result.body.error.code).toBe("forbidden");

  // ---- unchanged, as seen by both the owner (API) and the viewer (UI)
  const after = await api<{ display_name: string; occupation: string | null }>(context, "GET", `/trees/${treeId}/people/${person.id}`, undefined, baseURL!);
  expect(after.display_name).toBe("Gopal Joshi");
  expect(after.occupation).toBeNull();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Gopal Joshi", level: 1 })).toBeVisible();
  await viewerCtx.close();
});
