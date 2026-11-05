import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { runInNewContext } from "node:vm";
import { listen } from "@tauri-apps/api/event";

// Exercise the generated script from the actual locked Rust dependency together
// with the actual JS API: registration eval may land after listen() resolves.
const appRoot = fileURLToPath(new URL("../", import.meta.url));
const lock = readFileSync(join(appRoot, "src-tauri/Cargo.lock"), "utf8").replaceAll("\r\n", "\n");
const version = lock.match(/\[\[package\]\]\nname = "tauri"\nversion = "([^"]+)"/)?.[1];
assert.ok(version, "the locked Tauri runtime must be identifiable");
const registry = join(process.env.CARGO_HOME || join(homedir(), ".cargo"), "registry/src");
const sources = readdirSync(registry).flatMap((index) => {
  const source = join(registry, index, `tauri-${version}`, "src/event/mod.rs");
  try { return [readFileSync(source, "utf8")]; } catch (error) {
    if (error.code === "ENOENT") return [];
    throw error;
  }
});
assert.equal(sources.length, 1, "fetch the locked Tauri crate before this regression test");
const body = sources[0].split("pub(crate) fn unlisten_js_script(")[1]
  ?.split("pub(crate) fn event_initialization_script(")[0];
const template = body?.match(/format!\(\s*"([\s\S]*?)",\s*\)/)?.[1];
assert.ok(template, "the regression must execute Tauri's generated unlisten script");
const script = template.replaceAll("{listeners_object_name}", "testListeners")
  .replaceAll("{event_arg}", "event").replaceAll("{event_id_arg}", "eventId")
  .replaceAll("{{", "{").replaceAll("}}", "}");

test("immediate cleanup still removes the backend subscription before its registration eval lands", async () => {
  const previousWindow = globalThis.window;
  const callbacks = new Map();
  const subscriptions = new Set();
  const removedCallbacks = [];
  const event = "fusion-test-event";
  const existingId = 8;
  const pendingId = 9;
  const registry = { [event]: { [existingId]: { handlerId: 80 } } };
  const native = {
    transformCallback(handler) { callbacks.set(90, handler); return 90; },
    unregisterCallback(id) { removedCallbacks.push(id); callbacks.delete(id); },
    async invoke(command, args) {
      if (command === "plugin:event|listen") {
        subscriptions.add(pendingId);
        return pendingId;
      }
      assert.equal(command, "plugin:event|unlisten");
      assert.equal(args.event, event);
      subscriptions.delete(args.eventId);
    },
  };
  const bridge = {
    __TAURI_INTERNALS__: native,
    __TAURI_EVENT_PLUGIN_INTERNALS__: {
      unregisterListener(event, eventId) {
        runInNewContext(script, { window: bridge, event, eventId });
      },
    },
    testListeners: registry,
  };
  globalThis.window = bridge;
  try {
    let deliveries = 0;
    const stop = await listen(event, () => { deliveries++; });
    await stop();
    assert.equal(subscriptions.has(pendingId), false);
    // The already queued registration eval may still arrive, but future backend
    // event delivery must no longer select the removed listener.
    registry[event][pendingId] = { handlerId: 90 };
    for (const id of subscriptions) callbacks.get(registry[event][id].handlerId)?.({ event, id });
    assert.equal(deliveries, 0);
    assert.deepEqual(removedCallbacks, []);
    assert.equal(registry[event][existingId].handlerId, 80);
  } finally {
    if (previousWindow === undefined) delete globalThis.window;
    else globalThis.window = previousWindow;
  }
});

test("registered cleanup removes only its own JS callback and backend subscription", async () => {
  const previousWindow = globalThis.window;
  const removedCallbacks = [];
  const removedSubscriptions = [];
  const bridge = {
    testListeners: { "fusion-test-event": { 8: { handlerId: 80 }, 9: { handlerId: 90 } } },
    __TAURI_INTERNALS__: {
      transformCallback() { return 90; },
      unregisterCallback(id) { removedCallbacks.push(id); },
      async invoke(command, args) {
        if (command === "plugin:event|listen") return 9;
        assert.equal(command, "plugin:event|unlisten");
        removedSubscriptions.push(args.eventId);
      },
    },
    __TAURI_EVENT_PLUGIN_INTERNALS__: {
      unregisterListener(event, eventId) {
        runInNewContext(script, { window: bridge, event, eventId });
      },
    },
  };
  globalThis.window = bridge;
  try {
    const stop = await listen("fusion-test-event", () => undefined);
    await stop();
    assert.deepEqual(removedCallbacks, [90]);
    assert.deepEqual(removedSubscriptions, [9]);
    assert.equal(bridge.testListeners["fusion-test-event"][8].handlerId, 80);
  } finally {
    if (previousWindow === undefined) delete globalThis.window;
    else globalThis.window = previousWindow;
  }
});
