// Unit tests for the launch retry (node --test).
import assert from "node:assert/strict";
import { test } from "node:test";
import { countLaunchRetries, isLaunchTimeout, openWithRetry } from "./browser.mjs";

const timeout = () => new Error("Timed out after 25000 ms while trying to connect to the browser! Chrome logged the following: …");

test("a launch timeout is retried and the next attempt's browser is returned", async () => {
  let calls = 0;
  const retries = [];
  const browser = await openWithRetry(
    async () => {
      calls += 1;
      if (calls === 1) throw timeout();
      return "browser";
    },
    { onRetry: (i) => retries.push(i) },
  );
  assert.equal(browser, "browser");
  assert.equal(calls, 2);
  assert.deepEqual(retries, [1]);
});

test("gives up after the last attempt with the original error", async () => {
  let calls = 0;
  await assert.rejects(
    openWithRetry(async () => {
      calls += 1;
      throw timeout();
    }, { attempts: 3 }),
    /Timed out after 25000 ms/,
  );
  assert.equal(calls, 3);
});

test("any other error is not retried", async () => {
  let calls = 0;
  await assert.rejects(
    openWithRetry(async () => {
      calls += 1;
      throw new Error("Failed to launch the browser process: missing libnss3");
    }),
    /missing libnss3/,
  );
  assert.equal(calls, 1);
});

test("isLaunchTimeout matches only Remotion's connect timeout", () => {
  assert.equal(isLaunchTimeout(timeout()), true);
  assert.equal(isLaunchTimeout(new Error("delayRender() timeout")), false);
  assert.equal(isLaunchTimeout(undefined), false);
});

test("countLaunchRetries counts only the retry marker lines", () => {
  assert.equal(countLaunchRetries(""), 0);
  assert.equal(countLaunchRetries(undefined), 0);
  assert.equal(countLaunchRetries("browser_launch_retry_1\nbrowser_launch_retry_2\n"), 2);
  assert.equal(countLaunchRetries("some warning\nbrowser_launch_retry_1\nnot browser_launch_retry_9 here"), 1);
});

test("each timed-out attempt is cleaned up before the next one starts", async () => {
  const events = [];
  let calls = 0;
  await openWithRetry(
    async () => {
      calls += 1;
      events.push(`open${calls}`);
      if (calls < 3) throw timeout();
      return "browser";
    },
    { beforeAttempt: (i) => events.push(`before${i}`), afterTimeout: (i) => events.push(`cleanup${i}`) },
  );
  assert.deepEqual(events, ["before1", "open1", "cleanup1", "before2", "open2", "cleanup2", "before3", "open3"]);
});

test("the last timed-out attempt is cleaned up too; other errors need no cleanup", async () => {
  const cleaned = [];
  await assert.rejects(openWithRetry(async () => { throw timeout(); }, { attempts: 2, afterTimeout: (i) => cleaned.push(i) }));
  assert.deepEqual(cleaned, [1, 2]);
  cleaned.length = 0;
  await assert.rejects(openWithRetry(async () => { throw new Error("boom"); }, { afterTimeout: (i) => cleaned.push(i) }));
  assert.deepEqual(cleaned, []);
});
