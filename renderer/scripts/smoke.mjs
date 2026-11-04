// Real render test: bundle, render every composition's poster and one MP4, check the outputs.
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, statSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { countLaunchRetries } from "./browser.mjs";
import { ROOT } from "./common.mjs";

const node = process.execPath;
execFileSync(node, [path.join(ROOT, "scripts", "bundle.mjs")], { stdio: "inherit" });
// sample props live in TypeScript; the bundle exposes them as the compositions' defaults, so an
// empty-ish payload would not do: build the payloads from the fixture JSON instead
const fixtures = JSON.parse(readFileSync(path.join(ROOT, "fixtures", "samples.json"), "utf8"));
const work = mkdtempSync(path.join(os.tmpdir(), "vsh-render-"));
// Browser launch retries are always reported (not only on failure), so a slow Chrome cold start
// that a retry absorbed stays visible in CI logs instead of passing silently.
let totalRetries = 0;
let renders = 0;
for (const [composition, props] of Object.entries(fixtures)) {
  const dir = mkdtempSync(path.join(work, `${composition}-`));
  const payload = path.join(dir, "payload.json");
  writeFileSync(payload, JSON.stringify({ composition, props }));
  const output = composition === "FanChart" || composition === "EventTimeline" ? "mp4" : "poster";
  const r = spawnSync(node, [path.join(ROOT, "scripts", "render.mjs"), "--payload", payload, "--out-dir", dir, "--output", output], { encoding: "utf8" });
  const retries = countLaunchRetries(r.stderr);
  totalRetries += retries;
  renders += 1;
  console.log(`${composition}: browser launch retries ${retries}`);
  if (r.status !== 0) {
    console.error(r.stderr);
    throw new Error(`${composition}: render failed`);
  }
  const result = JSON.parse(r.stdout.trim().split("\n").at(-1)).result;
  const png = readFileSync(result.poster);
  if (png.subarray(1, 4).toString() !== "PNG" || png.length < 2000) throw new Error(`${composition}: bad poster`);
  if (output === "mp4") {
    const size = statSync(result.video).size;
    const probe = spawnSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", result.video], { encoding: "utf8" });
    const seconds = probe.status === 0 ? Number(probe.stdout.trim()) : NaN;
    const expected = result.durationInFrames / result.fps;
    if (size < 10_000) throw new Error(`${composition}: video too small`);
    if (!Number.isNaN(seconds) && Math.abs(seconds - expected) > 0.5) throw new Error(`${composition}: duration ${seconds} != ${expected}`);
    console.log(`ok ${composition}: poster ${png.length} B, mp4 ${size} B, ${expected.toFixed(1)} s`);
  } else {
    console.log(`ok ${composition}: poster ${png.length} B`);
  }
}
console.log(`browser launch retries: ${totalRetries} across ${renders} renders`);
