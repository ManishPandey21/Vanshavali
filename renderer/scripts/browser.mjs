// One shared Chromium per render, opened with a retry (ADR-0017).
//
// Remotion gives Chrome a fixed 25 s to accept the DevTools connection. A cold first start (fresh
// headless-shell download, font cache built on first use, a busy CI runner) can exceed that, which
// made the renderer smoke test fail intermittently with "Timed out after 25000 ms while trying to
// connect to the browser". Opening the browser once per render (instead of once each in
// selectComposition, renderStill and renderMedia) and retrying only that launch timeout fixes it.
import { openBrowser } from "@remotion/renderer";
import { CHROMIUM_OPTIONS, browserExecutable } from "./common.mjs";

const LAUNCH_TIMEOUT = /Timed out after \d+ ?ms while trying to connect to the browser/;

/** True for Remotion's browser-launch timeout, the only failure worth retrying. */
export function isLaunchTimeout(err) {
  return LAUNCH_TIMEOUT.test(String(err?.message ?? err));
}

/**
 * Calls `open()` up to `attempts` times, retrying only a launch timeout; any other error, or the
 * last timeout, is thrown. `open` is injectable for tests.
 */
export async function openWithRetry(open, { attempts = 3, onRetry = () => {} } = {}) {
  for (let i = 1; ; i++) {
    try {
      return await open();
    } catch (err) {
      if (i >= attempts || !isLaunchTimeout(err)) throw err;
      onRetry(i, err);
    }
  }
}

/** How many launch retries a render reported: its `browser_launch_retry_N` lines on stderr. */
export function countLaunchRetries(stderr) {
  return String(stderr ?? "")
    .split("\n")
    .filter((line) => /^browser_launch_retry_\d+$/.test(line.trim())).length;
}

/** The Chromium every render step shares; close it with `browser.close({ silent: true })`. */
export function openRenderBrowser() {
  return openWithRetry(
    () => openBrowser("chrome", { browserExecutable: browserExecutable(), chromiumOptions: CHROMIUM_OPTIONS, logLevel: "error" }),
    // stderr, short and content-free: the render worker reads only the last line as an error code
    { onRetry: (i) => console.error(`browser_launch_retry_${i}`) },
  );
}
