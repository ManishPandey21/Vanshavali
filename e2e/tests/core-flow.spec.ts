import { expect, test, type Locator } from "@playwright/test";

/**
 * Critical flow 1 (docs/architecture/README.md): register → create tree → add person →
 * add parents → add spouse → add child (in a union) → view the tree → relationship in Hindi.
 * Runs against the real API; nothing is mocked.
 */

const stamp = Date.now();
const email = `e2e-${stamp}@example.com`;
const password = "a-long-e2e-passphrase-42";

async function fillNewPerson(scope: Locator, given: string, surname: string, sex?: string) {
  const name1 = scope.getByRole("group", { name: "Name 1" });
  await name1.getByLabel("Given name").fill(given);
  await name1.getByLabel("Surname / family name").fill(surname);
  if (sex) await scope.getByLabel("Sex at birth").selectOption({ label: sex });
}

test("register, build a small family and view it", async ({ page }) => {
  // ---- register
  await page.goto("/register");
  await page.getByLabel("Your name").fill("E2E Tester");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Your family trees" })).toBeVisible();

  // ---- create tree
  await page.getByRole("link", { name: "New family tree" }).first().click();
  await page.getByLabel("Tree name").fill("Sharma parivar");
  await page.getByRole("button", { name: "New family tree" }).click();
  await expect(page.getByRole("heading", { name: "Sharma parivar" })).toBeVisible();

  // ---- add person with a Devanagari name and an approximate, verbally recalled birth time
  await page.getByRole("link", { name: "Add person" }).first().click();
  await expect(page.getByRole("heading", { name: "Add a person" })).toBeVisible();
  const form = page.locator("form");
  await fillNewPerson(form, "Ramesh", "Sharma", "Male");
  await page.getByRole("button", { name: /Add another name/ }).click();
  const name2 = page.getByRole("group", { name: "Name 2" });
  await name2.getByLabel("Given name").fill("रमेश");
  await name2.getByLabel("Surname / family name").fill("शर्मा");
  await page.getByLabel("Living status").selectOption("living");
  const dob = page.getByRole("group", { name: "Date of birth" });
  await dob.getByLabel("Day").fill("12");
  await dob.getByLabel("Month").selectOption({ label: "March" });
  await dob.getByLabel("Year").fill("1970");
  const tob = page.getByRole("group", { name: "Time of birth" });
  await tob.getByLabel("Time (24-hour)").fill("06:30");
  await tob.getByLabel("Where does this time come from?").selectOption("verbal");
  // "Exact" must be unavailable for a verbal time
  await expect(tob.getByRole("option", { name: "Exact" })).toBeDisabled();
  await page.getByRole("button", { name: "Save person" }).click();

  await expect(page.getByRole("heading", { name: "Ramesh Sharma", level: 1 })).toBeVisible();
  await expect(page.getByText("रमेश शर्मा").first()).toBeVisible();
  await expect(page.getByText(/about 06:30/)).toBeVisible();
  const profileUrl = page.url();

  // ---- family: parents
  await page.getByRole("tab", { name: "Family" }).click();
  for (const [given, sex] of [
    ["Suresh", "Male"],
    ["Kamala", "Female"],
  ] as const) {
    await page.getByRole("button", { name: "Add parent" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await fillNewPerson(dialog, given, "Sharma", sex);
    await dialog.getByRole("button", { name: "Add parent" }).click();
    await expect(dialog).toBeHidden();
    await expect(page.getByRole("link", { name: new RegExp(`${given} Sharma`) })).toBeVisible();
  }

  // ---- spouse
  await page.getByRole("button", { name: "Add spouse" }).click();
  let dialog = page.getByRole("dialog");
  await fillNewPerson(dialog, "Sunita", "Sharma", "Female");
  const marriage = dialog.getByRole("group", { name: "Date of marriage / start of union" });
  await marriage.getByLabel("How precise is this date?").selectOption("year_only");
  await expect(marriage.getByLabel("Day")).toHaveCount(0);
  await marriage.getByLabel("Year").fill("1995");
  await dialog.getByRole("button", { name: "Add spouse" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("link", { name: /Sunita Sharma/ })).toBeVisible();

  // ---- child in that union
  await page.getByRole("button", { name: "Add child" }).first().click();
  dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("Which union?")).toContainText("With Sunita Sharma");
  await fillNewPerson(dialog, "Aarav", "Sharma", "Male");
  await dialog.getByRole("button", { name: "Add child" }).click();
  await expect(dialog).toBeHidden();
  const union = page.getByRole("article", { name: /Union 1/ });
  await expect(union.getByRole("link", { name: /Aarav Sharma/ })).toBeVisible();

  // ---- tree view (ancestors), list alternative, keyboard navigation
  await page.getByRole("link", { name: "View in tree" }).click();
  await expect(page.getByRole("heading", { name: "Family tree of Ramesh Sharma" })).toBeVisible();
  const root = page.getByRole("button", { name: /Ramesh Sharma, 1970/ });
  await expect(root).toBeVisible();
  await expect(page.getByRole("button", { name: /Suresh Sharma/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Kamala Sharma/ })).toBeVisible();
  await root.focus();
  await page.keyboard.press("ArrowUp");
  await expect(page.getByRole("button", { name: /(Suresh|Kamala) Sharma/ }).first()).toBeFocused();

  await page.getByRole("button", { name: "List" }).click();
  await expect(page.getByRole("heading", { name: "1 generation up" })).toBeVisible();
  await page.getByRole("button", { name: "Descendants" }).click();
  await expect(page.getByRole("link", { name: "Aarav Sharma" })).toBeVisible();

  // ---- relationship calculator in Hindi: Aarav → Suresh = दादा
  await page.goto(profileUrl);
  await page.getByRole("tab", { name: "Family" }).click();
  await page.getByRole("link", { name: /Aarav Sharma/ }).click();
  await expect(page.getByRole("heading", { name: "Aarav Sharma", level: 1 })).toBeVisible();
  await page.getByRole("main").getByRole("link", { name: "How are we related?" }).click();
  await page.getByLabel("Relative").fill("Suresh");
  await page.getByRole("option", { name: /Suresh Sharma/ }).click();
  await expect(page.locator("#rel-result")).toContainText("grandfather");
  await page.getByLabel("Language").first().selectOption("hi");
  await expect(page.locator("#rel-result")).toContainText("दादा");
});
