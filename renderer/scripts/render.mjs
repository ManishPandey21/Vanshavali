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

const browser = browserExecutable();
// first stderr line only (the API reads the last line as an error code): which browser this run uses
process.stderr.write(`browser=${browser ?? "remotion-headless-shell"}\n`);
const common = {
  serveUrl: BUNDLE_DIR,
  inputProps: payload.props,
  browserExecutable: browser,
  chromiumOptions: CHROMIUM_OPTIONS,
  logLevel: "error",
};
const composition = await selectComposition({ ...common, id: payload.composition });
const posterFrame = Math.min(composition.durationInFrames - 1, Math.round(composition.durationInFrames * 0.72));
const poster = path.join(outDir, "poster.png");
await renderStill({ ...common, composition, output: poster, frame: posterFrame, imageFormat: "png" });
console.log(JSON.stringify({ progress: output === "mp4" ? 0.05 : 1 }));
let video = null;
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
