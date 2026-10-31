// Eklenti çekirdeğinin (core.js) tarayıcı API'sine dokunan parçaları Node'da, sahte
// `chrome` nesnesiyle: izleyici kaydı, sekme grubu, yeni pencere. Kullanım: node chrome_core_unit.mjs
import assert from "node:assert/strict";
import { MONITOR_SCRIPT_ID, execute, registerMonitor } from "../../chrome-extension/core.js";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// --- Sahte Chrome -----------------------------------------------------------------------------
const state = {
  origins: [],
  registered: new Map(), // id → kayıt
  local: {},
  tabs: new Map(),
  grouped: [],
  registerErrors: [],
};
globalThis.chrome = {
  permissions: {
    getAll: async () => ({ origins: [...state.origins] }),
    contains: async ({ origins }) => origins.every((o) => state.origins.includes(o) || state.origins.includes("<all_urls>")),
  },
  storage: {
    local: { get: async (key) => ({ [key]: state.local[key] }), set: async (items) => Object.assign(state.local, items) },
    session: { get: async () => ({}), set: async () => undefined, remove: async () => undefined },
  },
  scripting: {
    getRegisteredContentScripts: async ({ ids }) => {
      await sleep(20); // gerçek API asenkron; eşzamanlı çağrılar burada kesişir
      return ids.filter((id) => state.registered.has(id)).map((id) => state.registered.get(id));
    },
    unregisterContentScripts: async ({ ids }) => { await sleep(5); ids.forEach((id) => state.registered.delete(id)); },
    registerContentScripts: async (scripts) => {
      await sleep(5);
      for (const script of scripts) {
        if (state.registered.has(script.id)) {
          const error = new Error(`Duplicate script ID '${script.id}'`);
          state.registerErrors.push(error);
          throw error;
        }
        state.registered.set(script.id, script);
      }
    },
  },
  tabs: {
    get: async (id) => { const tab = state.tabs.get(id); if (!tab) throw new Error("No tab with id"); return tab; },
    group: async ({ tabIds }) => { state.grouped.push([...tabIds]); return 77; },
  },
  tabGroups: { update: async () => undefined },
  windows: { create: async () => ({ id: 3, tabs: [] }) },
};

// --- İzleyici kaydı: <all_urls> izleyiciyi her siteye kurmaz --------------------------------------
// Ölçüldü (31 Ekim, bağımsız inceleme): ekran görüntüsü için verilen <all_urls> izni izleyiciyi
// her sitede, her çerçevede kalıcı kuruyordu; "yalnız izinli site" tasarımı pratikte bozuluyordu.
state.origins = ["<all_urls>"];
assert.deepEqual(await registerMonitor(), { registered: false });
state.origins = ["<all_urls>", "https://ornek.test/*", "http://127.0.0.1/*"];
const only = await registerMonitor();
assert.deepEqual(only.origins, ["https://ornek.test/*"]);
assert.deepEqual(state.registered.get(MONITOR_SCRIPT_ID).matches, ["https://ornek.test/*"]);

// --- İzleyici kaydı eşzamanlı çağrıda serileşir -----------------------------------------------------
// Ölçüldü (31 Ekim): getRegistered → unregister → register atomik değildi; iki izin ardışık
// gelince ikinci kayıt "Duplicate script ID" ile düşüyor, hata yutuluyor ve ikinci site
// izleyicisiz kalıyordu.
state.registered.clear();
state.registerErrors.length = 0;
state.origins = ["https://a.test/*"];
const first = registerMonitor();
state.origins = ["https://a.test/*", "https://b.test/*"];
const second = registerMonitor();
const [resultA, resultB] = await Promise.all([first, second]);
assert.equal(state.registerErrors.length, 0, "eşzamanlı kayıt Duplicate script ID üretmemeli");
// İlk çağrı zincir yüzünden izinleri bir mikro görev sonra okur; her iki sonuç da kayıtlıdır.
assert.equal(resultA.registered, true);
assert.deepEqual(resultB.origins, ["https://a.test/*", "https://b.test/*"]);
assert.deepEqual(state.registered.get(MONITOR_SCRIPT_ID).matches, ["https://a.test/*", "https://b.test/*"]);

// --- Sekme grubu yalnız http(s) sekmeleri alır -----------------------------------------------------
state.tabs.set(5, { id: 5, url: "chrome://settings/", windowId: 1 });
state.tabs.set(6, { id: 6, url: "https://a.test/x", windowId: 1 });
state.tabs.set(7, { id: 7, url: "https://b.test/y", windowId: 1 });
await assert.rejects(execute({ islem: "tab_group", veri: { ids: [6, 5] } }), /http\(s\)/);
await assert.rejects(execute({ islem: "tab_group", veri: { ids: [6, 999] } }), /http\(s\)/);
assert.deepEqual(state.grouped, [], "geçersiz id'li istek hiçbir sekmeyi gruplamamalı");
const grouped = await execute({ islem: "tab_group", veri: { ids: [6, 7], title: "Araştırma" } });
assert.deepEqual(grouped, { group: 77, title: "Araştırma", tabs: 2 });
assert.deepEqual(state.grouped, [[6, 7]]);

// --- Yeni pencere yalnız http(s) adres açar ---------------------------------------------------------
await assert.rejects(execute({ islem: "window_new", veri: { url: "javascript:alert(1)" } }), /http\(s\)/);
await assert.rejects(execute({ islem: "window_new", veri: { url: "file:///etc/hosts" } }), /http\(s\)/);

console.log("chrome-core ✓");
