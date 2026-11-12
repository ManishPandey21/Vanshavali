// Which ffprobe the smoke test uses to check an MP4's duration.
//
// Remotion ships its own FFmpeg build (ffmpeg + ffprobe) in a platform package such as
// @remotion/compositor-linux-x64-gnu, pinned by package-lock.json. Using it means CI needs no
// system ffmpeg from the Ubuntu mirror (whose stalls cancelled CI jobs, Nov 2026), and the
// duration check runs against the same FFmpeg that encoded the video.
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

/** Remotion compositor packages that can carry an ffprobe for this platform, most likely first. */
export function compositorPackages(platform = process.platform, arch = process.arch) {
  if (platform === "linux") return [`@remotion/compositor-linux-${arch}-gnu`, `@remotion/compositor-linux-${arch}-musl`];
  if (platform === "darwin") return [`@remotion/compositor-darwin-${arch}`];
  if (platform === "win32") return [`@remotion/compositor-win32-${arch}-msvc`];
  return [];
}

const runs = (bin) => spawnSync(bin, ["-version"], { encoding: "utf8" }).status === 0;

/**
 * The ffprobe to use: $FFPROBE if set, else Remotion's bundled one, else `ffprobe` on PATH.
 * Returns null when none runs; the caller decides whether that is fatal (the smoke test: yes).
 */
export function findFfprobe({
  env = process.env,
  platform = process.platform,
  arch = process.arch,
  resolve = createRequire(import.meta.url).resolve,
  exists = existsSync,
  works = runs,
} = {}) {
  if (env.FFPROBE) return works(env.FFPROBE) ? env.FFPROBE : null;
  const exe = platform === "win32" ? "ffprobe.exe" : "ffprobe";
  for (const pkg of compositorPackages(platform, arch)) {
    let dir;
    try {
      dir = path.dirname(resolve(`${pkg}/package.json`));
    } catch {
      continue; // not installed for this platform
    }
    const bin = path.join(dir, exe);
    if (exists(bin) && works(bin)) return bin;
  }
  return works("ffprobe") ? "ffprobe" : null;
}

/** Duration in seconds of a media file, or throw (never a silent NaN). */
export function probeDuration(ffprobe, file) {
  const r = spawnSync(ffprobe, ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", file], { encoding: "utf8" });
  const seconds = Number(r.stdout?.trim());
  if (r.status !== 0 || !Number.isFinite(seconds)) {
    throw new Error(`ffprobe could not read the duration of ${file}: ${(r.stderr || r.error?.message || "").trim()}`);
  }
  return seconds;
}
