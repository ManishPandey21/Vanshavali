// Unit tests for render child-process hygiene (node --test).
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { test } from "node:test";
import { descendants, killAll } from "./procs.mjs";

const linux = existsSync("/proc/self/stat");

test("finds children and grandchildren, and kills them", { skip: !linux && "needs /proc" }, async () => {
  // a shell that starts a grandchild, both long-running
  const child = spawn("sh", ["-c", "sleep 120 & sleep 120"], { stdio: "ignore" });
  await new Promise((r) => setTimeout(r, 300));
  const found = descendants();
  assert.ok(found.includes(child.pid), "direct child found");
  assert.ok(found.length >= 3, "the shell's own children are found too");
  const exited = new Promise((r) => child.on("exit", r));
  killAll(found);
  await exited;
  await new Promise((r) => setTimeout(r, 200));
  assert.deepEqual(descendants().filter((p) => found.includes(p)), []);
});

test("is a no-op without /proc and tolerates processes that are already gone", () => {
  assert.deepEqual(descendants(process.pid, "/no/such/proc"), []);
  killAll([2 ** 22 + 12345]);
});
