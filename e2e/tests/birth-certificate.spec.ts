import { expect, test } from "@playwright/test";
import { api, createPerson, registerWithTree, renderTextPng } from "./helpers";

/**
 * Critical flow 2: Upload Birth Certificate → Process (OCR, job mode sync) → Review Extracted
 * Values → Accept / Reject fields. An accepted date becomes a new birth claim visible in the
 * timeline; a rejected field changes nothing.
 */
test("birth certificate: upload, OCR, review, accept and reject", async ({ page, context, browser, baseURL }) => {
  const { treeId } = await registerWithTree(context, baseURL!, "Certificate family");
  const person = await createPerson(context, baseURL!, treeId, "Ravi", "Kumar", { profile_status: "living", sex_at_birth: "male" });

  const png = await renderTextPng(
    browser,
    [
      "Name: Ravi Kumar",
      "Sex: Male",
      "Date of Birth: 12/03/1985",
      "Place of Birth: Kanpur",
      "Father's Name: Suresh Kumar",
      "Mother's Name: Sunita Devi",
      "Registration No: KNP-1985-00421",
    ],
    "CERTIFICATE OF BIRTH",
  );

  await page.goto(`/t/${treeId}/people/${person.id}?tab=documents`);
  await page.getByRole("button", { name: "Upload birth certificate" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("Category")).toHaveValue("birth_certificate");
  await expect(dialog.getByText(/Will be linked to Ravi Kumar/)).toBeVisible();
  await dialog.getByLabel(/^File/).setInputFiles({ name: "birth-certificate.png", mimeType: "image/png", buffer: png });
  await dialog.getByLabel(/^Title/).fill("Birth certificate of Ravi");
  await dialog.getByRole("button", { name: "Upload document" }).click();

  // Document detail: vault storage, pipeline finished (sync jobs), proposals listed.
  await expect(page.getByRole("heading", { name: "Birth certificate of Ravi", level: 1 })).toBeVisible();
  await expect(page.getByText("Vault", { exact: true })).toBeVisible();
  const dob = page.getByRole("listitem", { name: "Date of birth" });
  await expect(dob).toBeVisible({ timeout: 60_000 });
  await expect(dob).toContainText("1985");
  await expect(dob).toContainText("Extracted");
  const place = page.getByRole("listitem", { name: "Place of birth" });
  await expect(place).toContainText("Kanpur");

  // OCR text panel (permitted for the owner) shows the machine-read text with its caveat.
  await page.getByRole("tab", { name: "OCR text" }).click();
  await expect(page.getByText(/may contain errors/)).toBeVisible();
  await expect(page.getByText(/Registration No/).first()).toBeVisible();
  await page.getByRole("tab", { name: /Extracted values/ }).click();

  // Accept the date, reject the place.
  await dob.getByRole("button", { name: "Accept Date of birth" }).click();
  await expect(dob).toContainText("Source-verified");
  await place.getByRole("button", { name: "Reject Place of birth" }).click();
  await expect(place).toContainText("Rejected");
  await expect(place.getByRole("button", { name: /Accept/ })).toHaveCount(0);

  // The accepted date is a new birth claim in the timeline; the rejected place was not applied.
  await page.goto(`/t/${treeId}/people/${person.id}?tab=timeline`);
  const birth = page.getByRole("article", { name: "Birth" });
  await expect(birth).toBeVisible();
  await expect(birth).toContainText("12 March 1985");
  await expect(birth).not.toContainText("Kanpur");
  await expect(birth).toContainText(/1 source/);

  // API cross-check: exactly one birth event, no place from the rejected proposal.
  const events = await api<{ type: string; place_as_recorded: string | null; place_name: string | null }[]>(context, "GET", `/trees/${treeId}/people/${person.id}/events`, undefined, baseURL!);
  const births = events.filter((e) => e.type === "birth");
  expect(births).toHaveLength(1);
  expect(births[0].place_as_recorded ?? births[0].place_name ?? "").not.toContain("Kanpur");
});
