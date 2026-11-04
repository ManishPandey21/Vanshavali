// Child-process hygiene for renders (ADR-0017).
//
// When Remotion's browser launch times out it gives up on that Chrome but does not kill it, and the
// still-running child keeps `node render.mjs` alive after the render is done: the smoke test then
// hangs and a render worker leaks a Chrome per retry. These helpers find and kill a process's
// descendants. Linux reads /proc (CI, the render-worker image); elsewhere they are no-ops.
import { readdirSync, readFileSync } from "node:fs";

/** Every descendant pid of `root` (children, grandchildren…), or [] where /proc is unavailable. */
export function descendants(root = process.pid, procRoot = "/proc") {
  let entries;
  try {
    entries = readdirSync(procRoot).filter((d) => /^\d+$/.test(d));
  } catch {
    return [];
  }
  const children = new Map();
  for (const d of entries) {
    try {
      // /proc/<pid>/stat: "pid (comm) state ppid …"; comm may contain spaces and parentheses
      const stat = readFileSync(`${procRoot}/${d}/stat`, "utf8");
      const ppid = Number(stat.slice(stat.lastIndexOf(")") + 2).split(" ")[1]);
      if (!children.has(ppid)) children.set(ppid, []);
      children.get(ppid).push(Number(d));
    } catch {
      // the process exited while we were reading
    }
  }
  const out = [];
  const queue = [...(children.get(root) ?? [])];
  while (queue.length) {
    const pid = queue.shift();
    out.push(pid);
    queue.push(...(children.get(pid) ?? []));
  }
  return out;
}

/** SIGKILL each pid, ignoring ones that are already gone. */
export function killAll(pids) {
  for (const pid of pids) {
    try {
      process.kill(pid, "SIGKILL");
    } catch {
      // already exited
    }
  }
}
