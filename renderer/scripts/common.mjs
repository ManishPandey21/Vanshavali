// Shared helpers for the renderer CLI scripts.
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
export const BUNDLE_DIR = path.join(ROOT, "build", "bundle");

/** Chromium to drive: REMOTION_BROWSER_EXECUTABLE, else Playwright's headless shell if present,
 *  else null (Remotion then downloads its own pinned Chrome Headless Shell on first use, as the
 *  render-worker image does with `npx remotion browser ensure`).
 *
 *  Never a system Chromium (/usr/bin/chromium, /usr/bin/chromium-browser): what those are depends
 *  on the host (a snap stub on Ubuntu, a different build on each CI runner image), and picking them
 *  up made the smoke render time out connecting to the browser on runner image ubuntu24/20261101. */
export function browserExecutable() {
  if (process.env.REMOTION_BROWSER_EXECUTABLE) return process.env.REMOTION_BROWSER_EXECUTABLE;
  const playwrightShell = "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell";
  return existsSync(playwrightShell) ? playwrightShell : null;
}

export const CHROMIUM_OPTIONS = { gl: "swangle", disableWebSecurity: false, ignoreCertificateErrors: false };
