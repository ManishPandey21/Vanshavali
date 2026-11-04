// Render CLI used by the Python render worker (ADR-0017).
//
//   node scripts/render.mjs --payload payload.json --out-dir DIR --output poster|mp4
//
// payload.json = { "composition": "FanChart", "props": RenderProps }. Writes poster.png (always)
// and video.mp4 (output=mp4) into DIR, prints JSON progress lines ({"progress": 0..1}) and finally
// one {"result": {...}} line. Exit code != 0 on failure; the last stderr line is a short error code.
import { renderMedia, renderStill, selectComposition } from "@remotion/renderer";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { openRenderBrowser } from "./browser.mjs";
import { descendants, killAll } from "./procs.mjs";
import { BUNDLE_DIR, CHROMIUM_OPTIONS, browserExecutable } from "./common.mjs";

const ALLOWED = new Set(["FanChart", "PedigreeChart", "FamilyTree", "LifespanTimeline", "EventTimeline"]);

function arg(name) {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? process.argv[i + 1] : undefined;
}

function fail(code) {
  console.error(code);
  process.exit(2);
}

const payloadPath = arg("payload");
const outDir = arg("out-dir");
const output = arg("output") ?? "mp4";
if (!payloadPath || !outDir) fail("usage");
if (!existsSync(path.join(BUNDLE_DIR, "index.html"))) fail("bundle_missing");
const payload = JSON.parse(readFileSync(payloadPath, "utf8"));
if (!ALLOWED.has(payload.composition)) fail("unknown_composition");

let exitCode = 0;
try {
  // one browser for every step (selectComposition, renderStill, renderMedia), opened with a retry
  const browser = await openRenderBrowser();
  const common = {
    serveUrl: BUNDLE_DIR,
    inputProps: payload.props,
    browserExecutable: browserExecutable(),
    chromiumOptions: CHROMIUM_OPTIONS,
    puppeteerInstance: browser,
    logLevel: "error",
  };
  let composition;
  let poster;
  let video = null;
  try {
    composition = await selectComposition({ ...common, id: payload.composition });
    const posterFrame = Math.min(composition.durationInFrames - 1, Math.round(composition.durationInFrames * 0.72));
    poster = path.join(outDir, "poster.png");
    await renderStill({ ...common, composition, output: poster, frame: posterFrame, imageFormat: "png" });
    console.log(JSON.stringify({ progress: output === "mp4" ? 0.05 : 1 }));
    if (output === "mp4") {
      video = path.join(outDir, "video.mp4");
      let last = 0;
      await renderMedia({
        ...common,
        composition,
        codec: "h264",
        outputLocation: video,
        concurrency: Number(process.env.REMOTION_CONCURRENCY ?? 2),
        onProgress: ({ progress }) => {
          if (progress - last >= 0.05 || progress === 1) {
            last = progress;
            console.log(JSON.stringify({ progress: 0.05 + progress * 0.95 }));
          }
        },
      });
    }
  } finally {
    await browser.close({ silent: true });
  }
  console.log(
    JSON.stringify({
      result: {
        poster,
        video,
        width: composition.width,
        height: composition.height,
        fps: composition.fps,
        durationInFrames: composition.durationInFrames,
      },
    }),
  );
} catch (err) {
  console.error(err?.stack ?? String(err));
  exitCode = 1;
}
// Never leave a Chrome behind, and never wait on one: whatever is still running belongs to this
// render (e.g. an abandoned launch), so kill it and exit explicitly (ADR-0017).
killAll(descendants());
process.exit(exitCode);
