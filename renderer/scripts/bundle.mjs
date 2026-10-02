// Pre-bundle the compositions once (webpack) so each render starts in seconds.
import { bundle } from "@remotion/bundler";
import path from "node:path";
import { BUNDLE_DIR, ROOT } from "./common.mjs";

const out = await bundle({ entryPoint: path.join(ROOT, "src", "index.ts"), outDir: BUNDLE_DIR, enableCaching: false });
console.log(JSON.stringify({ bundle: out }));
