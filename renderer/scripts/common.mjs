// Shared helpers for the renderer CLI scripts.
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
export const BUNDLE_DIR = path.join(ROOT, "build", "bundle");

/** Chromium to drive: REMOTION_BROWSER_EXECUTABLE, else Playwright's headless shell if present,
 *  else null (Remotion then downloads its own Chrome Headless Shell on first use). */
export function browserExecutable() {
  if (process.env.REMOTION_BROWSER_EXECUTABLE) return process.env.REMOTION_BROWSER_EXECUTABLE;
  for (const p of [
    "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
  ]) {
    if (existsSync(p)) return p;
  }
  return null;
}

export const CHROMIUM_OPTIONS = { gl: "swangle", disableWebSecurity: false, ignoreCertificateErrors: false };
