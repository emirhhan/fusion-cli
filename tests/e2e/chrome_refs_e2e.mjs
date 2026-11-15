// Gerçek Chromium'da eklentinin sayfa çekirdeği: eski sayfanın ref'i yeni sayfada tıklamaz.
// pageAction, eklentinin chrome.scripting.executeScript({func}) ile yaptığı gibi
// serileştirilip sayfaya enjekte edilir.
import { chromium } from "../../app/node_modules/playwright/index.mjs";
import assert from "node:assert/strict";
import { pageAction } from "../../chrome-extension/core.js";

const source = pageAction.toString();
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
const run = (operation, args = {}) => page.evaluate(([src, op, a]) => {
  try { return { ok: true, value: (0, eval)(`(${src})`)(op, a) }; }
  catch (error) { return { ok: false, error: String(error.message || error) }; }
}, [source, operation, args]);
const html = (body) => `data:text/html;charset=utf-8,${encodeURIComponent(`<!doctype html><body>${body}</body>`)}`;

await page.goto(html(`<button onclick="document.title='A-sil'">Hesabı sil</button><button>Kaydet</button>`));
const a = await run("snapshot");
assert.ok(a.ok, a.error);
assert.equal(typeof a.value.doc, "string");
const silRef = a.value.elements.find((el) => el.name === "Hesabı sil").ref;

await page.goto(html(`<button onclick="document.title='B-tiklandi'">Bülten aboneliği</button><button>İptal</button>`));
const b = await run("snapshot");
assert.ok(b.ok, b.error);
assert.notEqual(b.value.doc, a.value.doc, "her belge kendi kimliğini taşımalı");

// Eski sayfanın ref'i (aynı "e0" adı yeni sayfada başka düğmeye denk gelir) belgesiyle gönderilir.
const stale = await run("click", { ref: silRef, doc: a.value.doc });
assert.equal(stale.ok, false);
assert.match(stale.error, /önceki sayfa/i);
assert.equal(await page.title(), "", "eski ref yeni sayfada hiçbir şeye tıklamamalı");

// Eklentinin gerçek çağrısı `__hataDondur` ile yapılır: hata veri olarak döner (injectionOutcome).
const viaExtension = await run("click", { ref: silRef, doc: a.value.doc, __hataDondur: true });
assert.ok(viaExtension.ok);
assert.match(String(viaExtension.value?.__hata), /önceki sayfa/i);
assert.equal(await page.title(), "", "eklenti yolu da eski ref ile tıklamamalı");

const fresh = await run("click", { ref: b.value.elements[0].ref, doc: b.value.doc });
assert.ok(fresh.ok, fresh.error);

const legacy = await run("find", { query: "iptal" });
assert.ok(legacy.ok && legacy.value.doc === b.value.doc);

await browser.close();
console.log("chrome-refs ✓");
