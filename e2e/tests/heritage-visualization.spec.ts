import { expect, test } from "@playwright/test";
import { api, attest, createPerson, latestMail, registerVerified, registerWithTree, renderTextPng, uniqueEmail } from "./helpers";

/**
 * Heritage visualization milestone (ADR-0015/0016/0017), through the real SPA and API:
 *  1. add an important life event with a geotag
 *  2. upload a photo to the event
 *  3. set an email reminder (and receive a test reminder)
 *  4. view the event in the person's timeline
 *  5. generate a chart and request an animated export preview
 *  6. a viewer sees the same charts without private people, events or photos
 * Rendering uses the stub renderer unless VSH_E2E_RENDER_BACKEND=remotion (then a real Remotion render).
 */
test("life event with geotag, photo, reminder, timeline, chart export and viewer privacy", async ({ browser, context, page, baseURL }) => {
  test.setTimeout(240_000);
  const { treeId, userEmail } = await registerWithTree(context, baseURL!, "Pandey parivar");
  const soon = new Date(Date.now() + 10 * 86_400_000);
  const mohan = await createPerson(context, baseURL!, treeId, "Mohan", "Pandey", {
    profile_status: "deceased",
    sex_at_birth: "male",
    birth: { date: { precision: "exact", year: 1950, month: soon.getUTCMonth() + 1, day: soon.getUTCDate() } },
  });
  const raju = await createPerson(context, baseURL!, treeId, "Raju", "Pandey", { profile_status: "deceased", sex_at_birth: "male", birth: { date: { precision: "year_only", year: 1978 } } });
  const secret = await createPerson(context, baseURL!, treeId, "Secretmother", "Pandey", { profile_status: "living", sex_at_birth: "female", privacy_level: "PRIVATE_TREE_ADMINS" });
  await api(context, "POST", `/trees/${treeId}/relationships`, { person_a_id: mohan.id, person_b_id: raju.id, type: "biological_parent" }, baseURL!);
  await api(context, "POST", `/trees/${treeId}/relationships`, { person_a_id: secret.id, person_b_id: raju.id, type: "biological_parent" }, baseURL!);
  // a private event (admins only) that the viewer must never see
  const privateEvent = await api<{ id: string }>(context, "POST", `/trees/${treeId}/events`, { category: "illness", title: "Hospital stay", privacy_level: "PRIVATE_TREE_ADMINS", participants: [{ person_id: mohan.id }] }, baseURL!);

  // ---- 1. important life event with a geotag, through the UI
  await page.goto(`/t/${treeId}/people/${mohan.id}?tab=events`);
  await page.getByRole("button", { name: "Add event" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("What happened?").selectOption("pilgrimage");
  await expect(dialog.getByLabel("Event type")).toHaveValue("other");
  await dialog.getByLabel("Title").fill("Kashi yatra");
  await dialog.getByText("Exact location (optional)").click();
  await dialog.getByLabel("Latitude").fill("25.3176");
  await dialog.getByLabel("Longitude").fill("83.0062");
  await dialog.getByLabel("How precise?").selectOption("locality");
  await dialog.getByLabel("How significant?").selectOption("milestone");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toHaveCount(0);
  const card = page.getByRole("article", { name: "Kashi yatra" });
  await expect(card).toContainText("Pilgrimage (yatra)");
  await expect(card).toContainText("Milestone");
  await expect(card).toContainText("25.318° N, 83.006° E");

  // ---- 2. a photo in the event's album (the first becomes the cover)
  await card.getByRole("button", { name: "Photos of Kashi yatra" }).first().click();
  const album = page.getByRole("dialog", { name: "Photos: Kashi yatra" });
  const png = await renderTextPng(browser, ["Dashashwamedh ghat, 1984"]);
  await album.locator("input[type=file]").setInputFiles({ name: "ghat.png", mimeType: "image/png", buffer: png });
  await album.getByLabel("Caption").fill("At the ghats");
  await album.getByLabel("Year taken").fill("1984");
  await album.getByRole("button", { name: "Upload photo" }).click();
  await expect(album.getByRole("list", { name: "Photos" })).toContainText("At the ghats");
  await expect(album.getByRole("list", { name: "Photos" })).toContainText("Cover");
  await expect(album.getByRole("img", { name: "At the ghats" })).toBeVisible();
  await album.getByRole("button", { name: "Close" }).first().click();
  await expect(card).toContainText("1 photo");

  // ---- 3. an email reminder for the birthday, then a test reminder by email
  const birth = page.getByRole("article", { name: "Birth" });
  await birth.getByRole("button", { name: "Set a reminder for Birth" }).click();
  const remDialog = page.getByRole("dialog", { name: "Set a reminder" });
  await expect(remDialog.getByRole("checkbox", { name: /Every year/ })).toBeChecked();
  await remDialog.getByRole("checkbox", { name: "A week before" }).check();
  await remDialog.getByRole("button", { name: "Save" }).click();
  await expect(birth.getByRole("button", { name: "Change the reminder for Birth" })).toContainText("Reminder on");
  await page.goto(`/t/${treeId}/reminders`);
  const upcoming = page.getByRole("region", { name: "Coming up" });
  await expect(upcoming).toContainText("Mohan Pandey's birthday");
  await expect(upcoming).toContainText("in 10 days");
  const mine = page.getByRole("region", { name: "Your reminders" });
  await expect(mine).toContainText("Mohan Pandey's birthday");
  await expect(mine).toContainText("Every year");
  await mine.getByRole("button", { name: "Send me a test" }).click();
  const mail = await latestMail(userEmail, "reminder");
  expect(mail.subject).toContain("[Test] Reminder: Mohan Pandey's birthday");
  await expect(page.getByRole("region", { name: "Delivery history" })).toContainText("Sent");

  // ---- 4. the event in the lifetime timeline (story view)
  await page.goto(`/t/${treeId}/people/${mohan.id}?tab=timeline`);
  await expect(page.getByRole("heading", { name: "The life of Mohan Pandey" })).toBeVisible();
  await expect(page.getByText("Kashi yatra")).toBeVisible();
  await page.getByRole("radio", { name: "Slideshow" }).click();
  await expect(page.getByText(/1 of \d/)).toBeVisible();

  // ---- 5. fan chart with filters, and an animated export preview
  await page.goto(`/t/${treeId}/visualizations?chart=fan&root=${raju.id}`);
  await expect(page.getByText(/Ancestors of Raju Pandey over 5 generations/).first()).toBeVisible();
  await page.getByLabel("Colour by").selectOption("living");
  await expect(page.getByRole("list", { name: "Legend" })).toContainText("Deceased");
  await page.getByRole("button", { name: /Mohan Pandey, 1950–\?, Paternal side/ }).press("Enter");
  await expect(page.getByRole("complementary", { name: "Mohan Pandey" })).toContainText("Deceased");
  await page.getByRole("button", { name: "Create preview" }).click();
  await expect(page.getByRole("img", { name: "Preview of the animated chart" })).toBeVisible({ timeout: 120_000 });
  // map of the geotagged event
  await page.goto(`/t/${treeId}/visualizations?chart=map`);
  await page.getByText(/List of \d+ locations?/).click();
  await expect(page.getByRole("table")).toContainText("Kashi yatra");

  // ---- 6. a viewer: same charts, no private people, events or photos
  const viewerEmail = uniqueEmail("viewer");
  const invite = await api<{ token: string }>(context, "POST", `/trees/${treeId}/invitations`, { email: viewerEmail, roles: ["VIEWER"] }, baseURL!);
  const viewerCtx = await browser.newContext({ baseURL });
  await registerVerified(viewerCtx, baseURL!, viewerEmail, "Viewer Cousin");
  await api(viewerCtx, "POST", `/invitations/${invite.token}/accept`, undefined, baseURL!);
  await attest(viewerCtx, baseURL!, treeId).catch(() => undefined);
  const vpage = await viewerCtx.newPage();
  await vpage.goto(`/t/${treeId}/visualizations?chart=fan&root=${raju.id}`);
  await expect(vpage.getByText(/Ancestors of Raju Pandey/).first()).toBeVisible();
  await expect(vpage.getByRole("list", { name: "Legend" })).toContainText("Private");
  await expect(vpage.getByText("Secretmother")).toHaveCount(0);
  await vpage.goto(`/t/${treeId}/events`);
  await vpage.getByRole("checkbox", { name: "Important events only" }).uncheck();
  await expect(vpage.getByRole("list", { name: "Life events" })).toContainText("Kashi yatra");
  await expect(vpage.getByText("Hospital stay")).toHaveCount(0);
  // the viewer cannot edit the album and the private event's album is a 404 for them
  await vpage.getByRole("button", { name: /1 photo/ }).click();
  await expect(vpage.getByRole("dialog", { name: "Photos: Kashi yatra" })).toContainText("At the ghats");
  await expect(vpage.getByRole("button", { name: "Upload photo" })).toHaveCount(0);
  const denied = await viewerCtx.request.get(`${baseURL}/api/v1/trees/${treeId}/events/${privateEvent.id}/media`);
  expect(denied.status()).toBe(404);
  // and their reminders and exports are their own: the owner's are invisible
  const theirReminders = await api<unknown[]>(viewerCtx, "GET", `/trees/${treeId}/reminders`, undefined, baseURL!);
  expect(theirReminders).toHaveLength(0);
  const theirJobs = await api<unknown[]>(viewerCtx, "GET", `/trees/${treeId}/render-jobs`, undefined, baseURL!);
  expect(theirJobs).toHaveLength(0);
  await viewerCtx.close();
});
