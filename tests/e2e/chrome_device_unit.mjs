// #432: eklentinin köprü kimliği bir kez üretilir, saklanır; ad tarayıcı markasından gelir.
import assert from "node:assert/strict";
import { browserName, deviceIdentity, DEVICE_KEY } from "../../chrome-extension/device.js";

const store = {};
const storage = {
  async get(key) { return key in store ? { [key]: store[key] } : {}; },
  async set(values) { Object.assign(store, values); },
};

assert.equal(browserName([{ brand: "Not A;Brand" }, { brand: "Microsoft Edge" }, { brand: "Chromium" }]), "Edge");
assert.equal(browserName([{ brand: "Google Chrome" }, { brand: "Chromium" }]), "Chrome");
assert.equal(browserName([]), "Chrome");

const first = await deviceIdentity(storage);
assert.match(first.id, /^[a-z]+-[0-9a-f]{18}$/);
assert.deepEqual(store[DEVICE_KEY], first);
const second = await deviceIdentity(storage);
assert.equal(second.id, first.id, "kimlik kalıcı");

store[DEVICE_KEY] = { id: "../kotu" };
assert.notEqual((await deviceIdentity(storage)).id, "../kotu", "geçersiz kimlik yenilenir");
console.log("chrome-device ✓");
