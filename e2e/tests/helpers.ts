import type { Browser, BrowserContext, Page } from "@playwright/test";

export const PASSWORD = "a-long-e2e-passphrase-42";

let counter = 0;
export function uniqueEmail(prefix: string): string {
  counter += 1;
  return `${prefix}-${Date.now()}-${counter}@example.com`;
}

/**
 * Calls the real API with the page context's cookies (session + CSRF double-submit), exactly as
 * the SPA does. Throws with the server's error body on failure unless `allowError` is set.
 */
export async function api<T = unknown>(
  ctx: BrowserContext,
  method: "GET" | "POST" | "PATCH" | "PUT" | "DELETE",
  path: string,
  data?: unknown,
  baseURL = "",
): Promise<T> {
  const csrf = (await ctx.cookies()).find((c) => c.name === "vsh_csrf")?.value ?? "";
  const res = await ctx.request.fetch(`${baseURL}/api/v1${path}`, {
    method,
    data,
    headers: method === "GET" ? {} : { "X-CSRF-Token": csrf },
  });
  if (!res.ok()) throw new Error(`${method} ${path} → ${res.status()} ${await res.text()}`);
  return (await res.json()) as T;
}

export interface Seeded {
  treeId: string;
  userEmail: string;
}

/** Confirms the family-data statement for a tree (ADR-0011) so people can be added to it. */
export async function attest(ctx: BrowserContext, baseURL: string, treeId: string): Promise<void> {
  const stmt = await api<{ version: string; language: string }>(ctx, "GET", "/consent-statements/family_data?lang=en", undefined, baseURL);
  await api(ctx, "POST", `/trees/${treeId}/attestation`, { statement_version: stmt.version, language: stmt.language }, baseURL);
}

/** Registers a fresh user (signed in on this context), creates a tree and confirms the family-data statement for it. */
export async function registerWithTree(ctx: BrowserContext, baseURL: string, treeName: string, displayName = "E2E Owner"): Promise<Seeded> {
  const userEmail = uniqueEmail("owner");
  await api(ctx, "POST", "/auth/register", { email: userEmail, password: PASSWORD, display_name: displayName, preferred_language: "en" }, baseURL);
  const tree = await api<{ id: string }>(ctx, "POST", "/trees", { name: treeName }, baseURL);
  await attest(ctx, baseURL, tree.id);
  return { treeId: tree.id, userEmail };
}

export async function createPerson(
  ctx: BrowserContext,
  baseURL: string,
  treeId: string,
  given: string,
  surname: string,
  extra: Record<string, unknown> = {},
): Promise<{ id: string; display_name: string }> {
  return api(ctx, "POST", `/trees/${treeId}/people`, { names: [{ given_name: given, surname, is_preferred: true }], ...extra }, baseURL);
}

/**
 * Renders printed text to a PNG in the browser (no image libraries needed). Plain black-on-white
 * sans-serif text at a size Tesseract reads reliably.
 */
export async function renderTextPng(browser: Browser, lines: string[], title?: string): Promise<Buffer> {
  const page = await browser.newPage({ viewport: { width: 1400, height: 120 + lines.length * 70 }, deviceScaleFactor: 1 });
  const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  await page.setContent(
    `<html><body style="margin:0;background:#fff;color:#000;font-family:'DejaVu Sans','Liberation Sans',Arial,sans-serif;font-size:34px;line-height:70px;padding:30px 40px">` +
      (title ? `<div style="font-weight:bold">${esc(title)}</div>` : "") +
      lines.map((l) => `<div>${esc(l)}</div>`).join("") +
      `</body></html>`,
  );
  const png = await page.screenshot({ fullPage: true, type: "png" });
  await page.close();
  return png;
}

/** Tiny valid PDF (text only) for documents where OCR is irrelevant. */
export function simplePdf(text: string): Buffer {
  const content = `BT /F1 18 Tf 72 720 Td (${text.replace(/[()\\]/g, "")}) Tj ET`;
  const objs = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    `<< /Length ${content.length} >>\nstream\n${content}\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  let out = "%PDF-1.4\n";
  const offsets: number[] = [];
  objs.forEach((o, i) => {
    offsets.push(out.length);
    out += `${i + 1} 0 obj\n${o}\nendobj\n`;
  });
  const xref = out.length;
  out += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n`;
  for (const off of offsets) out += `${String(off).padStart(10, "0")} 00000 n \n`;
  out += `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(out, "latin1");
}

/** Picks a person in a PersonPicker combobox labelled `label` inside `scope`. */
export async function pickPerson(page: Page, label: string, name: string, scope?: ReturnType<Page["locator"]>) {
  const root = scope ?? page.locator("body");
  await root.getByRole("combobox", { name: label }).fill(name.split(" ")[0]);
  await page.getByRole("option", { name: new RegExp(name) }).first().click();
}

/** RFC 4648 base32 decode (TOTP secrets). */
function base32Decode(s: string): Buffer {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  const clean = s.replace(/=+$/, "").replace(/\s+/g, "").toUpperCase();
  let bits = 0;
  let value = 0;
  const out: number[] = [];
  for (const ch of clean) {
    const idx = alphabet.indexOf(ch);
    if (idx < 0) throw new Error(`invalid base32 character ${ch}`);
    value = (value << 5) | idx;
    bits += 5;
    if (bits >= 8) {
      out.push((value >>> (bits - 8)) & 0xff);
      bits -= 8;
    }
  }
  return Buffer.from(out);
}

/** RFC 6238 TOTP (HMAC-SHA-1, 30 s step, 6 digits) computed with node:crypto. */
export async function totp(secret: string, at = Date.now()): Promise<string> {
  const { createHmac } = await import("node:crypto");
  const counter = Math.floor(at / 1000 / 30);
  const msg = Buffer.alloc(8);
  msg.writeBigUInt64BE(BigInt(counter));
  const h = createHmac("sha1", base32Decode(secret)).update(msg).digest();
  const off = h[h.length - 1] & 0x0f;
  const code = ((h.readUInt32BE(off) & 0x7fffffff) % 1_000_000).toString();
  return code.padStart(6, "0");
}

/** Waits until the current 30-s window has at least `margin` ms left (avoids boundary flakes). */
export async function freshTotpWindow(margin = 5000) {
  const left = 30_000 - (Date.now() % 30_000);
  if (left < margin) await new Promise((r) => setTimeout(r, left + 100));
}
