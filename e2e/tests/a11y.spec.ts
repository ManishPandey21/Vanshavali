import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";
import { api, createPerson, registerWithTree, renderTextPng, simplePdf } from "./helpers";

/**
 * Accessibility audit (PRS §50, WCAG 2.2 AA; method and findings in docs/accessibility/audit-2026-09.md).
 *
 * 1. Automated: axe-core with the WCAG 2.0/2.1/2.2 A + AA rule tags on every key page (auth, trees,
 *    dashboard, people, every profile tab, add person, tree chart + list, relationship calculator,
 *    documents, property, import/export, admin, account, public pages), in English and in Hindi,
 *    plus a 390×844 mobile viewport for the profile and tree pages. Any serious or critical
 *    violation fails; moderate/minor ones are recorded as test annotations. Each page's heading
 *    outline is checked too (one h1, no skipped levels), since axe's heading-order rule is
 *    best-practice rather than WCAG-tagged.
 * 2. Keyboard-only scripts: skip link, a visible focus indicator at every Tab stop, focus moving to
 *    the new page's heading on navigation, tabs keyboard model, dialog focus trap / Escape / focus
 *    restore, focus to the first invalid field, tree-node arrow navigation with no keyboard trap,
 *    combobox selection.
 * 3. Semantics and adaptation that axe cannot judge: live regions for async results, lang on names
 *    in other scripts, alt text on document previews, table captions/headers, status in words,
 *    reduced motion, reflow at 320 and 640 CSS px.
 *
 * Rules excluded: none. Every page is scanned with the full tag set. Set A11Y_VERBOSE=1 to print
 * every violation (all impacts) and the "needs review" rule ids per page.
 */

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"];
const BLOCKING = new Set(["serious", "critical"]);

interface Seed {
  treeId: string;
  slug: string;
  ramesh: string;
  suresh: string;
  aarav: string;
  documentId: string;
  imageDocumentId: string;
  propertyId: string;
  storage: Awaited<ReturnType<BrowserContext["storageState"]>>;
}

let seed: Seed;

/** Multipart upload through the real API with the context's cookies + CSRF header. */
async function upload(ctx: BrowserContext, baseURL: string, treeId: string, fields: Record<string, string>, file: { name: string; mimeType: string; buffer: Buffer }) {
  const csrf = (await ctx.cookies()).find((c) => c.name === "vsh_csrf")?.value ?? "";
  const res = await ctx.request.post(`${baseURL}/api/v1/trees/${treeId}/documents`, {
    headers: { "X-CSRF-Token": csrf },
    multipart: { ...fields, file },
  });
  if (!res.ok()) throw new Error(`upload → ${res.status()} ${await res.text()}`);
  return (await res.json()) as { id: string };
}

async function seedData(browser: Browser, baseURL: string): Promise<Seed> {
  const ctx = await browser.newContext({ baseURL });
  const { treeId } = await registerWithTree(ctx, baseURL, "Sharma parivar (a11y)");
  const y = (year: number) => ({ precision: "year_only", year });
  const ramesh = await createPerson(ctx, baseURL, treeId, "Ramesh", "Sharma", {
    profile_status: "living",
    sex_at_birth: "male",
    occupation: "Teacher",
    birth: { date: y(1970), place_as_recorded: "Varanasi" },
  });
  // A second name in Devanagari (lang/script metadata must reach the DOM as lang="hi").
  await api(ctx, "POST", `/trees/${treeId}/people/${ramesh.id}/names`, { given_name: "रमेश", surname: "शर्मा", language: "hi", script: "Deva", type: "birth" }, baseURL);
  const relative = (relation: string, given: string, extra: Record<string, unknown>) =>
    api<{ person: { id: string } }>(ctx, "POST", `/trees/${treeId}/people/${ramesh.id}/relatives`, {
      relation,
      new_person: { names: [{ given_name: given, surname: "Sharma", is_preferred: true }], ...extra },
    }, baseURL);
  const suresh = await relative("parent", "Suresh", {
    profile_status: "deceased",
    sex_at_birth: "male",
    privacy_level: "PUBLIC_DECEASED_ONLY",
    birth: { date: y(1940) },
    death: { date: y(2010) },
  });
  await relative("parent", "Kamala", { profile_status: "deceased", sex_at_birth: "female", privacy_level: "PUBLIC_DECEASED_ONLY", birth: { date: y(1945) } });
  await relative("spouse", "Sunita", { profile_status: "living", sex_at_birth: "female" });
  const aarav = await relative("child", "Aarav", { profile_status: "living", sex_at_birth: "male", birth: { date: y(2012) } });

  const pdf = await upload(ctx, baseURL, treeId, { category: "letter", title: "Letter from Kashi", link_target_type: "person", link_target_id: ramesh.id }, { name: "letter.pdf", mimeType: "application/pdf", buffer: simplePdf("Letter from Kashi 1985") });
  const png = await renderTextPng(browser, ["Family photograph caption"], "PHOTO");
  const img = await upload(ctx, baseURL, treeId, { category: "photo", title: "Wedding photograph", link_target_type: "person", link_target_id: ramesh.id }, { name: "photo.png", mimeType: "image/png", buffer: png });

  const property = await api<{ id: string }>(ctx, "POST", `/trees/${treeId}/properties`, { property_type: "agricultural_land", classification: "ancestral", display_name: "Ancestral fields at Bhitari" }, baseURL);
  const parcel = await api<{ id: string }>(ctx, "POST", `/trees/${treeId}/properties/${property.id}/parcels`, { village: "Bhitari", district: "Ghazipur", khasra_or_gata_number: "412", area: "3.5", area_unit: "bigha" }, baseURL);
  const interest = await api<{ id: string }>(ctx, "POST", `/trees/${treeId}/properties/${property.id}/interests`, { holder_type: "person", holder_person_id: suresh.person.id, parcel_id: parcel.id, status: "documented" }, baseURL);
  await api(ctx, "POST", `/trees/${treeId}/properties/${property.id}/events`, {
    type: "inheritance",
    date: y(2010),
    description: "Inherited by the sons",
    ends_interest_ids: [interest.id],
    end_status: "transferred",
    creates_interests: [{ holder_type: "person", holder_person_id: ramesh.id, share_numerator: 1, share_denominator: 1 }],
  }, baseURL);

  const tree = await api<{ slug: string }>(ctx, "PATCH", `/trees/${treeId}`, { public_mode: "DECEASED_ONLY" }, baseURL);
  const storage = await ctx.storageState();
  await ctx.close();
  return { treeId, slug: tree.slug, ramesh: ramesh.id, suresh: suresh.person.id, aarav: aarav.person.id, documentId: pdf.id, imageDocumentId: img.id, propertyId: property.id, storage };
}

/**
 * Waits until the SPA has no spinners (queries settled, lazy chunks loaded) and every finite CSS
 * animation has finished: axe measures colour contrast on what is painted, so an element sampled
 * mid fade-in (e.g. the landing page hero, 600 ms delay) would report a contrast that no user sees.
 */
async function settled(page: Page) {
  await expect(page.locator("main, [role=main]").first()).toBeVisible();
  // The app shell can paint before a lazy route mounts its spinner or page heading. Wait for
  // the route's required heading before auditing, rather than mistaking that shell for a page.
  await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.locator(".animate-spin")).toHaveCount(0, { timeout: 20_000 });
  await page.waitForFunction(
    () =>
      document
        .getAnimations()
        .filter((a) => a.effect?.getComputedTiming().iterations !== Infinity)
        .every((a) => a.playState !== "running" && !a.pending),
    undefined,
    { timeout: 10_000 },
  );
}

/** Runs axe on the current page; serious/critical violations fail (soft, so every page is reported). */
async function audit(page: Page, label: string) {
  await settled(page);
  const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
  const fmt = (v: (typeof results.violations)[number]) =>
    `[${v.impact}] ${v.id}: ${v.help} (${v.helpUrl})\n` + v.nodes.slice(0, 5).map((n) => `    ${n.target.join(" ")} — ${n.failureSummary?.split("\n").slice(1, 2).join("") ?? ""}`).join("\n");
  const blocking = results.violations.filter((v) => BLOCKING.has(v.impact ?? ""));
  const advisory = results.violations.filter((v) => !BLOCKING.has(v.impact ?? ""));
  if (advisory.length) test.info().annotations.push({ type: "a11y-advisory", description: `${label}: ${advisory.map((v) => `${v.impact} ${v.id}`).join(", ")}` });
  if (process.env.A11Y_VERBOSE) {
    console.log(`${label}: ${results.passes.length} rules pass, ${results.violations.length} violated, ${results.incomplete.length} need review (${results.incomplete.map((v) => v.id).join(", ")})`);
    for (const v of results.violations) console.log(`${label} ${fmt(v)}`);
  }
  expect.soft(blocking.map(fmt), `axe serious/critical violations on ${label}`).toEqual([]);
  expect.soft(await outlineProblems(page), `heading outline on ${label}`).toEqual([]);
}

/**
 * Screen-reader heading navigation: exactly one h1 per page and no skipped levels inside <main>
 * (1.3.1 / 2.4.6). axe's heading-order is a best-practice rule outside the WCAG tags, so it is
 * checked here directly.
 */
async function outlineProblems(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const visible = (el: Element) => !!(el as HTMLElement).offsetParent || getComputedStyle(el).position === "fixed";
    const all = [...document.querySelectorAll("h1, h2, h3, h4, h5, h6")].filter((h) => visible(h) && !h.closest("[role=dialog]"));
    const problems: string[] = [];
    const h1s = all.filter((h) => h.tagName === "H1");
    if (h1s.length !== 1) problems.push(`expected one h1, found ${h1s.length}`);
    let prev = 1;
    for (const h of all.filter((x) => x.closest("main"))) {
      const level = Number(h.tagName[1]);
      if (level > prev + 1) problems.push(`h${prev} → h${level} "${h.textContent?.trim().slice(0, 40)}"`);
      prev = level;
    }
    return problems;
  });
}

async function signedIn(browser: Browser, baseURL: string, opts: { lang?: "hi" | "en"; mobile?: boolean } = {}) {
  const ctx = await browser.newContext({
    baseURL,
    storageState: seed.storage,
    viewport: opts.mobile ? { width: 390, height: 844 } : undefined,
    isMobile: opts.mobile,
    hasTouch: opts.mobile,
  });
  const lang = opts.lang ?? "en";
  await ctx.addInitScript((l) => localStorage.setItem("vsh_lang", l), lang);
  return { ctx, page: await ctx.newPage() };
}

test.beforeAll(async ({ browser, baseURL }) => {
  seed = await seedData(browser, baseURL!);
});

const PROFILE_TABS = ["overview", "family", "events", "timeline", "photos", "heritage", "documents", "astrology", "property", "sources", "households", "visualizations", "privacy"];

function treePages(s: Seed): [string, string][] {
  const t = `/t/${s.treeId}`;
  return [
    ["trees list", "/"],
    ["new tree", "/trees/new"],
    ["guided first run", "/welcome"],
    ["account", "/account"],
    ["dashboard", t],
    ["people list", `${t}/people`],
    ["add person", `${t}/people/new`],
    ...PROFILE_TABS.map((tab): [string, string] => [`profile · ${tab}`, `${t}/people/${s.ramesh}?tab=${tab}`]),
    ["tree viewer · chart", `${t}/tree/${s.ramesh}`],
    ["tree viewer · list", `${t}/tree/${s.ramesh}?view=list`],
    ["tree viewer · family", `${t}/tree/${s.ramesh}?view=family`],
    ["tree viewer · descendants list", `${t}/tree/${s.suresh}?view=list&dir=descendants`],
    ["relationship calculator", `${t}/relationship?from=${s.aarav}&to=${s.suresh}`],
    // heritage visualization milestone (ADR-0015/0016/0017)
    ["charts · fan", `${t}/visualizations?chart=fan&root=${s.aarav}`],
    ["charts · relationship web", `${t}/visualizations?chart=graph&root=${s.ramesh}`],
    ["charts · pedigree", `${t}/visualizations?chart=pedigree&root=${s.aarav}`],
    ["charts · family tree", `${t}/visualizations?chart=family&root=${s.suresh}`],
    ["charts · lifespans", `${t}/visualizations?chart=lifespan`],
    ["charts · life story", `${t}/visualizations?chart=events&root=${s.ramesh}`],
    ["charts · map", `${t}/visualizations?chart=map`],
    ["life events", `${t}/events`],
    ["family timeline", `${t}/timeline`],
    ["reminders", `${t}/reminders`],
    ["family calendar", `${t}/calendar`],
    ["search", `${t}/search?q=Ramesh`],
    ["sources", `${t}/sources`],
    ["places", `${t}/places`],
    ["branches", `${t}/branches`],
    ["households", `${t}/households`],
    ["joint family", `${t}/joint-family`],
    ["duplicates", `${t}/duplicates`],
    ["documents list", `${t}/documents`],
    ["document detail (PDF)", `${t}/documents/${s.documentId}`],
    ["document detail (image)", `${t}/documents/${s.imageDocumentId}`],
    ["property list", `${t}/property`],
    ["property detail", `${t}/property/${s.propertyId}`],
    ["property parcels", `${t}/property/${s.propertyId}?tab=parcels`],
    ["property holders", `${t}/property/${s.propertyId}?tab=interests`],
    ["property timeline", `${t}/property/${s.propertyId}?tab=timeline`],
    ["import/export", `${t}/import-export`],
    ["admin members", `${t}/admin/members`],
    ["admin audit", `${t}/admin/audit`],
    ["admin settings", `${t}/admin/settings`],
    ["admin claims", `${t}/admin/claims`],
    ["admin invitations", `${t}/admin/invitations`],
    ["admin restore", `${t}/admin/restore`],
  ];
}

test.describe("axe: WCAG 2.2 A/AA", () => {
  test("public auth pages (login, register, password reset, email verification)", async ({ browser, baseURL }) => {
    for (const lang of ["en", "hi"] as const) {
      const ctx = await browser.newContext({ baseURL });
      await ctx.addInitScript((l) => localStorage.setItem("vsh_lang", l), lang);
      const page = await ctx.newPage();
      await page.goto("/login");
      await audit(page, `login [${lang}]`);
      await page.goto("/register");
      await audit(page, `register [${lang}]`);
      await page.goto("/forgot-password");
      await audit(page, `forgot password [${lang}]`);
      // Token pages in their "link invalid or expired" state (no email round trip needed).
      await page.goto("/reset-password/not-a-real-token");
      await audit(page, `reset password [${lang}]`);
      await page.goto("/verify-email/not-a-real-token");
      await audit(page, `verify email [${lang}]`);
      await ctx.close();
    }
  });

  for (const lang of ["en", "hi"] as const) {
    test(`signed-in pages [${lang}]`, async ({ browser, baseURL }) => {
      test.setTimeout(240_000);
      const { ctx, page } = await signedIn(browser, baseURL!, { lang });
      for (const [label, url] of treePages(seed)) {
        await page.goto(url);
        await audit(page, `${label} [${lang}]`);
      }
      await ctx.close();
    });
  }

  test("public tree pages (signed out)", async ({ browser, baseURL }) => {
    for (const lang of ["en", "hi"] as const) {
      const ctx = await browser.newContext({ baseURL });
      await ctx.addInitScript((l) => localStorage.setItem("vsh_lang", l), lang);
      const page = await ctx.newPage();
      await page.goto("/");
      await audit(page, `landing [${lang}]`);
      await page.goto("/about");
      await audit(page, `about [${lang}]`);
      // a claim link opened while signed out: asks the relative to sign in or create an account
      await page.goto("/claim#not-a-real-claim-token-0000000000000000000");
      await audit(page, `claim link [${lang}]`);
      await page.goto(`/p/${seed.slug}`);
      await audit(page, `public tree [${lang}]`);
      await page.goto(`/p/${seed.slug}/people/${seed.suresh}`);
      await audit(page, `public person [${lang}]`);
      await ctx.close();
    }
  });

  test("mobile 390×844: profile and tree", async ({ browser, baseURL }) => {
    test.setTimeout(180_000);
    const { ctx, page } = await signedIn(browser, baseURL!, { mobile: true });
    const t = `/t/${seed.treeId}`;
    for (const tab of ["overview", "family", "timeline", "documents"]) {
      await page.goto(`${t}/people/${seed.ramesh}?tab=${tab}`);
      await audit(page, `mobile profile · ${tab}`);
    }
    await page.goto(`${t}/tree/${seed.ramesh}`);
    await audit(page, "mobile tree chart");
    await page.goto(`${t}/tree/${seed.ramesh}?view=list`);
    await audit(page, "mobile tree list");
    // Focus Not Obscured (2.4.11): tabbing down a long form never hides the focused control behind
    // the fixed bottom navigation bar.
    await page.goto(`${t}/people/new`);
    await settled(page);
    const navTop = (await page.getByRole("navigation", { name: "Main sections" }).boundingBox())!.y;
    for (let i = 0; i < 45; i++) {
      await page.keyboard.press("Tab");
      const box = await page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        if (!el || el === document.body || el.closest("nav")) return null;
        const r = el.getBoundingClientRect();
        return { top: r.top, name: (el.getAttribute("aria-label") ?? el.textContent ?? "").trim().slice(0, 40) };
      });
      if (box) expect.soft(box.top, `focused "${box.name}" is not hidden under the bottom navigation`).toBeLessThan(navTop);
    }
    // The "More" navigation sheet is a dialog; scan it open.
    await page.goto(t);
    await settled(page);
    await page.getByRole("navigation", { name: "Main sections" }).getByRole("button", { name: "More" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await audit(page, "mobile more-navigation dialog");
    await ctx.close();
  });
});

/** The element that currently has focus, described for assertions. */
async function focused(page: Page) {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el || el === document.body) return { tag: "body", role: "", name: "", inDialog: false, inMain: false, inSvg: false, outline: "", ring: false };
    const cs = getComputedStyle(el);
    const firstRect = el.querySelector("rect");
    return {
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute("role") ?? "",
      name: (el.getAttribute("aria-label") ?? el.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 80),
      inDialog: !!el.closest("[role=dialog]"),
      inMain: !!el.closest("main"),
      inSvg: !!el.closest("svg"),
      outline: `${cs.outlineStyle} ${cs.outlineWidth}`,
      // Visible focus: a real outline, or (SVG tree nodes) a thickened stroke on the node box.
      ring: (cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) >= 2) || (!!firstRect && parseFloat(getComputedStyle(firstRect).strokeWidth) >= 3),
    };
  });
}

async function tabUntil(page: Page, predicate: (f: Awaited<ReturnType<typeof focused>>) => boolean, max = 80, key = "Tab") {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press(key);
    const f = await focused(page);
    if (predicate(f)) return f;
  }
  throw new Error(`focus never reached the target after ${max} × ${key}`);
}

test.describe("keyboard only", () => {
  test("skip link, visible focus on every stop, route change focuses the new heading", async ({ browser, baseURL }) => {
    const { ctx, page } = await signedIn(browser, baseURL!);
    await page.goto(`/t/${seed.treeId}/people/${seed.ramesh}`);
    await settled(page);
    // First Tab: the skip link, visible on focus.
    await page.keyboard.press("Tab");
    const skip = page.getByRole("link", { name: "Skip to main content" });
    await expect(skip).toBeFocused();
    expect((await skip.boundingBox())!.width).toBeGreaterThan(20);
    await page.keyboard.press("Enter");
    await page.keyboard.press("Tab");
    expect((await focused(page)).inMain, "Tab after the skip link lands inside <main>").toBe(true);

    // Every focus stop across the page shows a focus indicator (2.4.7), and none is a trap (2.1.2).
    await page.keyboard.press("Shift+Tab");
    const seen = new Set<string>();
    for (let i = 0; i < 45; i++) {
      await page.keyboard.press("Tab");
      const f = await focused(page);
      if (f.tag === "body") continue;
      expect.soft(f.ring, `visible focus indicator on <${f.tag}> "${f.name}" (${f.outline})`).toBe(true);
      seen.add(`${f.tag}:${f.name}`);
    }
    expect(seen.size, "Tab moves through many distinct controls (no trap)").toBeGreaterThan(20);

    // In-app navigation by keyboard moves focus to the new page's h1 and retitles the document.
    await page.getByRole("navigation", { name: "Tree navigation" }).getByRole("link", { name: "People", exact: true }).focus();
    await page.keyboard.press("Enter");
    const h1 = page.getByRole("heading", { level: 1, name: "People" });
    await expect(h1).toBeFocused();
    await expect(page).toHaveTitle(/^People · /);
    await ctx.close();
  });

  test("tabs: arrow keys, Home/End, roving tabindex", async ({ browser, baseURL }) => {
    const { ctx, page } = await signedIn(browser, baseURL!);
    await page.goto(`/t/${seed.treeId}/people/${seed.ramesh}`);
    await settled(page);
    await tabUntil(page, (f) => f.role === "tab" && f.name === "Overview");
    await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("tab", { name: "Family" })).toBeFocused();
    await expect(page.getByRole("tab", { name: "Family" })).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("End");
    await expect(page.getByRole("tab", { name: "Privacy" })).toBeFocused();
    await page.keyboard.press("Home");
    await expect(page.getByRole("tab", { name: "Overview" })).toBeFocused();
    // Only the selected tab is in the Tab sequence; the next Tab goes to the panel.
    await page.keyboard.press("Tab");
    await expect(page.getByRole("tabpanel")).toBeFocused();
    await ctx.close();
  });

  test("dialog: focus moves in, Tab is trapped, Escape closes, focus returns to the opener", async ({ browser, baseURL }) => {
    const { ctx, page } = await signedIn(browser, baseURL!);
    await page.goto(`/t/${seed.treeId}/people/${seed.ramesh}?tab=family`);
    await settled(page);
    const opener = page.getByRole("button", { name: "Add parent" });
    await tabUntil(page, (f) => f.name === "Add parent");
    await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    expect((await focused(page)).inDialog, "focus moved into the dialog").toBe(true);
    for (let i = 0; i < 60; i++) {
      await page.keyboard.press("Tab");
      expect((await focused(page)).inDialog, `Tab #${i + 1} stays inside the dialog`).toBe(true);
    }
    for (let i = 0; i < 10; i++) {
      await page.keyboard.press("Shift+Tab");
      expect((await focused(page)).inDialog, `Shift+Tab #${i + 1} stays inside the dialog`).toBe(true);
    }
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(opener).toBeFocused();

    // A failed submit moves focus to the first invalid field, which is described by its error.
    await page.keyboard.press("Enter");
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "Add parent" }).click();
    const given = dialog.getByRole("group", { name: "Name 1" }).getByLabel("Given name");
    await expect(given).toBeFocused();
    await expect(given).toHaveAttribute("aria-invalid", "true");
    await expect(given).toHaveAccessibleDescription(/Enter at least a given name/);
    await page.keyboard.press("Escape");
    await expect(opener).toBeFocused();
    await ctx.close();
  });

  test("tree chart: arrow keys between relatives, Home, Enter opens, Tab leaves (no trap)", async ({ browser, baseURL }) => {
    const { ctx, page } = await signedIn(browser, baseURL!);
    await page.goto(`/t/${seed.treeId}/tree/${seed.ramesh}`);
    await settled(page);
    const root = await tabUntil(page, (f) => f.inSvg);
    expect(root.name).toMatch(/^Ramesh Sharma, 1970.*Living/);
    expect(root.ring, "focused tree node shows a focus indicator").toBe(true);
    await page.keyboard.press("ArrowUp");
    const parent = await focused(page);
    expect(parent.name).toMatch(/(Suresh|Kamala) Sharma/);
    expect(parent.name, "status is in the node name, not only its colour").toContain("Deceased");
    await page.keyboard.press(parent.name.startsWith("Suresh") ? "ArrowRight" : "ArrowLeft");
    const other = await focused(page);
    expect(other.name).toMatch(/(Suresh|Kamala) Sharma/);
    expect(other.name).not.toBe(parent.name);
    await page.keyboard.press("Home");
    expect((await focused(page)).name).toMatch(/^Ramesh Sharma/);
    // One Tab stop for the whole chart (roving tabindex): Tab leaves it, Shift+Tab comes back.
    await page.keyboard.press("Tab");
    expect((await focused(page)).inSvg).toBe(false);
    await page.keyboard.press("Shift+Tab");
    expect((await focused(page)).name).toMatch(/^Ramesh Sharma/);
    // Pointer users can pan without dragging (2.5.7): the view moves with a button press.
    const transform = () => page.locator("svg[role=group] > g").first().getAttribute("transform");
    const before = await transform();
    await page.getByRole("button", { name: "Move view left" }).click();
    expect(await transform()).not.toBe(before);
    await page.getByRole("button", { name: /^Ramesh Sharma/ }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { level: 1, name: "Ramesh Sharma" })).toBeFocused();
    await ctx.close();
  });

  test("person picker and relationship result: keyboard selection, announced results", async ({ browser, baseURL }) => {
    const { ctx, page } = await signedIn(browser, baseURL!);
    await page.goto(`/t/${seed.treeId}/relationship?from=${seed.aarav}`);
    await settled(page);
    const input = page.getByRole("combobox", { name: "Relative" });
    await input.focus();
    await page.keyboard.type("Suresh");
    await expect(page.getByRole("status").filter({ hasText: /^1 result$/ })).toHaveCount(1);
    await page.keyboard.press("ArrowDown");
    await expect(input).toHaveAttribute("aria-activedescendant", /opt-0/);
    await page.keyboard.press("Enter");
    // The input is replaced by the chosen person; focus follows to its "clear" button.
    await expect(page.getByRole("button", { name: /Suresh Sharma/ })).toBeFocused();
    await expect(page.getByRole("status").filter({ hasText: /grandfather/ })).toHaveCount(1);
    await page.keyboard.press("Enter");
    await expect(page.getByRole("combobox", { name: "Relative" })).toBeFocused();
    await ctx.close();
  });
});

test.describe("semantics and adaptation", () => {
  test("landmarks, table semantics, lang on other-script names, preview alt text, status in words", async ({ browser, baseURL }) => {
    const { ctx, page } = await signedIn(browser, baseURL!);
    const t = `/t/${seed.treeId}`;
    await page.goto(`${t}/people/${seed.ramesh}`);
    await settled(page);
    await expect(page.getByRole("main")).toHaveCount(1);
    await expect(page.getByRole("navigation", { name: "Tree navigation" })).toHaveCount(1);
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    // The Devanagari name is marked up as Hindi so a screen reader switches voice (3.1.2).
    await expect(page.locator('[lang="hi"]', { hasText: "रमेश शर्मा" }).first()).toBeVisible();
    await expect(page.getByText("Living", { exact: true }).first()).toBeVisible();

    await page.goto(`${t}/admin/members`);
    await settled(page);
    const table = page.getByRole("table");
    await expect(table).toHaveCount(1);
    await expect(table.locator("caption")).toHaveCount(1);
    expect(await table.getByRole("columnheader").count()).toBeGreaterThan(1);

    await page.goto(`${t}/documents/${seed.imageDocumentId}`);
    await settled(page);
    const img = page.getByRole("img", { name: /Wedding photograph/ });
    await expect(img).toBeVisible({ timeout: 20_000 });

    await page.goto(`${t}/tree/${seed.suresh}?view=list&dir=descendants`);
    await settled(page);
    await expect(page.getByRole("heading", { level: 2, name: "Starting person" })).toBeVisible();
    await expect(page.getByRole("main").getByText("· Deceased").first()).toBeVisible();

    // UI in Hindi: <html lang> follows the language.
    await page.getByLabel("Language").first().selectOption("hi");
    await expect(page.locator("html")).toHaveAttribute("lang", "hi");
    await ctx.close();
  });

  test("text fields have a 3:1 boundary (1.4.11 Non-text Contrast)", async ({ browser, baseURL }) => {
    const { ctx, page } = await signedIn(browser, baseURL!);
    await page.goto(`/t/${seed.treeId}/people/new`);
    await settled(page);
    const ratio = await page.getByRole("group", { name: "Name 1" }).getByLabel("Given name").evaluate((el) => {
      const rgb = (c: string) => c.match(/\d+(\.\d+)?/g)!.slice(0, 3).map(Number);
      const lum = (c: string) => {
        const [r, g, b] = rgb(c).map((v) => {
          const x = v / 255;
          return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
        });
        return 0.2126 * r + 0.7152 * g + 0.0722 * b;
      };
      const cs = getComputedStyle(el);
      const [a, b] = [lum(cs.borderTopColor), lum(cs.backgroundColor)].sort((x, y) => y - x);
      return (a + 0.05) / (b + 0.05);
    });
    expect(ratio).toBeGreaterThanOrEqual(3);
    await ctx.close();
  });

  test("reduced motion stops animations", async ({ browser, baseURL }) => {
    const ctx = await browser.newContext({ baseURL, storageState: seed.storage, reducedMotion: "reduce" });
    const page = await ctx.newPage();
    await page.goto(`/t/${seed.treeId}`);
    await settled(page);
    const style = await page.evaluate(() => {
      const el = document.createElement("div");
      el.className = "animate-spin";
      document.body.appendChild(el);
      const cs = getComputedStyle(el);
      return { count: cs.animationIterationCount, duration: parseFloat(cs.animationDuration) };
    });
    expect(style.count).toBe("1");
    expect(style.duration).toBeLessThan(0.01);
    await ctx.close();
  });

  test("reflow at 320 CSS px (= 400% zoom) and 640 px (= 200% zoom): no horizontal page scroll", async ({ browser, baseURL }) => {
    test.setTimeout(180_000);
    const t = `/t/${seed.treeId}`;
    const pages = [
      t,
      `${t}/people`,
      `${t}/people/new`,
      ...["overview", "family", "timeline", "documents", "astrology", "privacy"].map((tab) => `${t}/people/${seed.ramesh}?tab=${tab}`),
      `${t}/tree/${seed.ramesh}?view=list`,
      `${t}/relationship?from=${seed.aarav}&to=${seed.suresh}`,
      `${t}/documents`,
      `${t}/documents/${seed.documentId}`,
      `${t}/property/${seed.propertyId}?tab=timeline`,
      `${t}/admin/members`,
      `${t}/admin/audit`,
      `/p/${seed.slug}/people/${seed.suresh}`,
    ];
    for (const width of [320, 640]) {
      const ctx = await browser.newContext({ baseURL, storageState: seed.storage, viewport: { width, height: 720 } });
      const page = await ctx.newPage();
      for (const url of pages) {
        await page.goto(url);
        await settled(page);
        const overflow = await page.evaluate(() => {
          const doc = document.documentElement;
          if (doc.scrollWidth <= doc.clientWidth + 1) return null;
          // Name the widest offenders to make a failure actionable.
          const clipped = (el: HTMLElement) => {
            for (let a = el.parentElement; a && a !== doc; a = a.parentElement) if (/(auto|scroll|hidden|clip)/.test(getComputedStyle(a).overflowX)) return true;
            return false;
          };
          const wide = [...document.querySelectorAll<HTMLElement>("body *")]
            .filter((el) => el.getBoundingClientRect().right > doc.clientWidth + 1 && !clipped(el))
            .slice(-3)
            .map((el) => `${el.tagName.toLowerCase()}.${String(el.className).split(" ").slice(0, 3).join(".")}`);
          return `${doc.scrollWidth}px: ${wide.join(", ")}`;
        });
        expect.soft(overflow, `horizontal scroll at ${width}px on ${url}`).toBeNull();
      }
      await ctx.close();
    }
  });
});
