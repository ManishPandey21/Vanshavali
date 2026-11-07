import assert from "node:assert/strict";
import { test } from "node:test";
import { compositorPackages, findFfprobe } from "./ffprobe.mjs";

const resolverFor = (installed) => (spec) => {
  const pkg = spec.replace(/\/package\.json$/, "");
  if (!installed.includes(pkg)) throw new Error(`Cannot find module '${spec}'`);
  return `/nm/${pkg}/package.json`;
};

test("platform packages", () => {
  assert.deepEqual(compositorPackages("linux", "x64"), ["@remotion/compositor-linux-x64-gnu", "@remotion/compositor-linux-x64-musl"]);
  assert.deepEqual(compositorPackages("darwin", "arm64"), ["@remotion/compositor-darwin-arm64"]);
  assert.deepEqual(compositorPackages("win32", "x64"), ["@remotion/compositor-win32-x64-msvc"]);
  assert.deepEqual(compositorPackages("aix", "ppc64"), []);
});

test("prefers $FFPROBE, then Remotion's bundled ffprobe, then PATH", () => {
  const base = { platform: "linux", arch: "x64", exists: () => true };
  const all = resolverFor(["@remotion/compositor-linux-x64-gnu"]);
  assert.equal(findFfprobe({ ...base, env: { FFPROBE: "/opt/ff/ffprobe" }, resolve: all, works: () => true }), "/opt/ff/ffprobe");
  assert.equal(
    findFfprobe({ ...base, env: {}, resolve: all, works: () => true }),
    "/nm/@remotion/compositor-linux-x64-gnu/ffprobe",
  );
  // musl build when the gnu one is absent
  const musl = resolverFor(["@remotion/compositor-linux-x64-musl"]);
  assert.equal(findFfprobe({ ...base, env: {}, resolve: musl, works: () => true }), "/nm/@remotion/compositor-linux-x64-musl/ffprobe");
  // bundled binary that does not run → system ffprobe
  assert.equal(findFfprobe({ ...base, env: {}, resolve: all, works: (b) => b === "ffprobe" }), "ffprobe");
});

test("returns null when nothing runs, so the caller can fail loudly", () => {
  const none = resolverFor([]);
  assert.equal(findFfprobe({ platform: "linux", arch: "x64", env: {}, resolve: none, exists: () => false, works: () => false }), null);
  // an explicit $FFPROBE that does not run is not silently replaced
  assert.equal(findFfprobe({ platform: "linux", arch: "x64", env: { FFPROBE: "/nope" }, resolve: none, works: (b) => b === "ffprobe" }), null);
});

test("finds a working ffprobe in this checkout (Remotion's bundled build)", () => {
  const bin = findFfprobe();
  assert.ok(bin, "no ffprobe found: run npm ci in renderer/");
});
