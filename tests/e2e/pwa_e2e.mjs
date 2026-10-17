// Gerçek tarayıcıda (Chromium, telefon boyutu) uçtan uca PWA kabul sınaması.
// Kullanım: node pwa_e2e.mjs <taban-adres> <ekran-görüntüsü-dizini>
import { chromium } from "../../app/node_modules/playwright/index.mjs";
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";

const base = process.argv[2];
const shots = process.argv[3];
await mkdir(shots, { recursive: true });
const results = [];
let currentPage = null;
const browser = await chromium.launch({ headless: true });

async function newCode() { return (await (await fetch(`${base}/__code`)).json()).code; }
const text = (page, selector) => page.locator(selector).innerText();
async function overflow(page) { return page.evaluate(() => document.documentElement.scrollWidth - innerWidth); }

async function run(width, height) {
  const tag = `${width}`;
  const context = await browser.newContext({ viewport: { width, height }, isMobile: true, hasTouch: true });
  const page = await context.newPage();
  currentPage = page;
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const step = (name) => results.push(`${tag}px ✓ ${name}`);

  // 1) açılış: hesap girişi görünür, kodla bağlan seçeneği var
  await page.goto(base);
  await page.locator("#hesapGiris").waitFor({ state: "visible" });
  assert.equal(await page.locator("#kodaGec").isVisible(), true);
  await page.screenshot({ path: `${shots}/${tag}-01-giris.png` });
  step("hesap girişi ve 'kodla bağlan' görünür");

  // 2) yanlış kod: açık Türkçe mesaj, düğme yeniden kullanılabilir, mesaj düğmenin ALTINDA
  await page.locator("#kodaGec").click();
  await page.locator("#kod").fill("YANLIS12");
  await page.locator("#eslestirDugme").click();
  await page.waitForFunction(() => /geçersiz|süresi/i.test(document.getElementById("durum").textContent));
  assert.equal(await page.locator("#eslestirDugme").isEnabled(), true);
  const below = await page.evaluate(() => document.getElementById("durum").getBoundingClientRect().top >= document.getElementById("eslestirDugme").getBoundingClientRect().bottom - 1);
  assert.equal(below, true, "durum satırı düğmenin altında olmalı");
  await page.screenshot({ path: `${shots}/${tag}-02-yanlis-kod.png` });
  step("yanlış kod: açık hata, düğme altında durum, yeniden denenebilir");

  // 3) ağ kopması: açık mesaj
  await context.setOffline(true);
  await page.locator("#kod").fill("ABCDEFGH");
  await page.locator("#eslestirDugme").click();
  await page.waitForFunction(() => /ulaşılamıyor/i.test(document.getElementById("durum").textContent));
  assert.equal(await page.locator("#eslestirDugme").isEnabled(), true);
  await context.setOffline(false);
  step("ağ kopması: 'ulaşılamıyor' mesajı, yeniden denenebilir");

  // 4) doğru kod: otomatik onay, bağlanır
  await page.locator("#kod").fill(await newCode());
  await page.locator("#eslestirDugme").click();
  await page.locator("#uygulama").waitFor({ state: "visible", timeout: 15000 });
  await page.screenshot({ path: `${shots}/${tag}-03-baglandi.png` });
  step("doğru kod desktop onayı beklemeden bağlar");

  // 5) yeniden yükle: hâlâ bağlı (eşleştirme ekranına dönmez)
  await page.reload();
  await page.locator("#uygulama").waitFor({ state: "visible", timeout: 15000 });
  assert.equal(await page.locator("#eslestir").isVisible(), false);
  await page.waitForTimeout(6000); // eşzamanlı yoklamalar sonrası da bağlı kalmalı
  assert.equal(await page.locator("#uygulama").isVisible(), true);
  step("yeniden yükleme + 6 sn yoklama sonrası hâlâ bağlı");

  // 6) sohbet listesi, geçmiş, mesaj, akan yanıt
  await page.locator('[data-view="sohbetler"] .row-item', { hasText: "Ürün sayfası" }).click();
  await page.getByText("Fiyatı başlığın altına koy").waitFor();
  await page.screenshot({ path: `${shots}/${tag}-04-sohbet.png` });
  await page.locator("#mesaj").fill("uzun bir iş yap");
  await page.getByRole("button", { name: "Gönder" }).click();
  await page.getByRole("button", { name: "Durdur" }).waitFor({ timeout: 5000 });
  await page.getByText("Merhaba,", { exact: false }).last().waitFor({ timeout: 5000 });
  await page.screenshot({ path: `${shots}/${tag}-05-akan-yanit.png` });
  await page.getByRole("button", { name: "Durdur" }).click();
  await page.getByRole("button", { name: "Gönder" }).waitFor({ timeout: 10000 });
  step("geçmiş açılır, mesaj gider, yanıt akar, Durdur çalışır");

  // 7) onay: yeni görev → sohbet içinde onay kartı → onayla → yanıt
  await page.locator("#mesaj").fill("onay gerektiren iş");
  await page.getByRole("button", { name: "Gönder" }).click();
  const card = page.locator(".approval").first();
  await card.waitFor({ timeout: 8000 });
  await page.screenshot({ path: `${shots}/${tag}-06-onay.png` });
  await card.getByRole("button", { name: /izin ver|onayla/i }).first().click();
  await page.getByRole("button", { name: "Gönder" }).waitFor({ timeout: 10000 });
  step("onay kartı gelir, verilir, görev tamamlanır");

  // 8) sekmeler: görevler (zamanlananlar), onaylar, ekran, ayarlar
  await page.locator(".chat .bar-btn").first().click();
  await page.locator('[data-tab="gorevler"]').click();
  await page.getByText("Sabah stok raporu").waitFor();
  await page.screenshot({ path: `${shots}/${tag}-07-gorevler.png` });
  await page.getByRole("button", { name: "Şimdi çalıştır" }).click();
  await page.getByText("Görev başlatıldı").waitFor({ timeout: 5000 });
  step("Zamanlananlar listelenir ve 'Şimdi çalıştır' görev başlatır");
  await page.locator('[data-tab="onaylar"]').click();
  await page.locator('[data-tab="ayarlar"]').click();
  await page.getByText("Model", { exact: true }).first().waitFor();
  await page.screenshot({ path: `${shots}/${tag}-08-ayarlar.png` });
  step("Onaylar ve Ayarlar sekmeleri açılır");

  // 9) canlı ekran: izin ver, kare, oturum süresi dolunca yeniden bağlanma
  await page.locator('[data-tab="ekran"]').click();
  await page.locator("#ekranIste").click();
  const confirm = page.getByText("Onayla ve izlemeyi başlat");
  if (await confirm.waitFor({ timeout: 4000 }).then(() => true, () => false)) await confirm.click();
  await page.waitForFunction(() => document.getElementById("ekranKare").naturalWidth > 0, null, { timeout: 15000 });
  const ratio = await page.evaluate(() => { const r = document.getElementById("ekranKare").getBoundingClientRect(); return r.width / r.height; });
  assert.ok(Math.abs(ratio - 1.6) < 0.05, `en-boy oranı korunmalı (${ratio})`);
  await page.screenshot({ path: `${shots}/${tag}-09-canli-ekran.png` });
  await context.setOffline(true);
  await page.waitForFunction(() => /koptu|deneniyor/i.test(document.getElementById("ekranDurum").textContent), null, { timeout: 15000 });
  await page.screenshot({ path: `${shots}/${tag}-10-ekran-koptu.png` });
  await context.setOffline(false);
  await page.waitForFunction(() => document.getElementById("ekranDurum").textContent.includes("Canlı"), null, { timeout: 30000 });
  step("canlı ekran: kare gelir, oran korunur, ağ kopunca mesaj, dönünce kendiliğinden sürer");

  // 9b) iki aşamalı dock: uygulamalar → pencereler/sekmeler, arama, tek dokunuşla odak, geri
  await page.locator('[data-tab="ekran"]').click();
  await page.locator(".mini-dock__app").first().waitFor({ timeout: 10000 });
  assert.equal(await page.locator(".mini-dock__row").count(), 0, "1. aşamada satır olmamalı");
  assert.equal(await page.locator(".mini-dock__app").count(), 3);
  await page.screenshot({ path: `${shots}/${tag}-12-dock-uygulamalar.png` });
  await page.locator('[data-app="Finder"]').click(); // tek pencere: doğrudan odak
  await page.waitForTimeout(400);
  assert.equal((await (await fetch(`${base}/__focused`)).json()).id, 20);
  await page.locator('[data-app="Google Chrome"]').click();
  await page.locator(".mini-dock__group").first().waitFor();
  assert.equal(await page.locator(".mini-dock__apps").count(), 0, "2. aşamada uygulama şeridi gizli");
  await page.locator(".mini-dock__search").fill("sayfa 11");
  assert.equal(await page.locator(".mini-dock__row").count(), 1);
  await page.locator(".mini-dock__search").fill("");
  await page.locator(".mini-dock__list").scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${shots}/${tag}-13-dock-chrome.png` });
  await page.getByRole("button", { name: "Sayfa 3 sekmesini öne getir" }).click();
  await page.waitForTimeout(400);
  assert.deepEqual(await (await fetch(`${base}/__focused`)).json(), { kind: "tab", id: 3 });
  await page.getByRole("button", { name: "Uygulamalara dön" }).click();
  assert.equal(await page.locator(".mini-dock__app").count(), 3);
  step("dock: uygulamalar şeridi, tek pencerede doğrudan odak, Chrome sekmeleri gruplu/aramalı, geri");

  assert.equal(await overflow(page), 0, "yatay taşma olmamalı");
  assert.deepEqual(errors, [], `sayfa hataları: ${errors.join("; ")}`);
  await context.close();

  // 10) hesapla giriş (ayrı bağlam): yanlış parola → hata, doğru parola → bağlı, yeniden yüklemede de
  const second = await browser.newContext({ viewport: { width, height }, isMobile: true, hasTouch: true });
  const p2 = await second.newPage();
  await p2.goto(base);
  await p2.locator("#hesapKimlik").fill("emir");
  await p2.locator("#hesapParola").fill("yanlis");
  await p2.locator("#hesapDugme").click();
  await p2.waitForFunction(() => /hatalı/i.test(document.getElementById("durum").textContent));
  await p2.locator("#hesapParola").fill("parola123");
  await p2.locator("#hesapDugme").click();
  await p2.locator("#uygulama").waitFor({ state: "visible", timeout: 15000 });
  await p2.reload();
  await p2.locator("#uygulama").waitFor({ state: "visible", timeout: 15000 });
  await p2.screenshot({ path: `${shots}/${tag}-11-hesapla-giris.png` });
  step("hesapla giriş: yanlış parola hata, doğru parola bağlar, yenilemede kalıcı");
  await second.close();
}

try {
  await run(375, 812);
  await run(430, 932);
  console.log(results.join("\n"));
} catch (error) {
  await currentPage?.screenshot({ path: `${shots}/HATA.png` }).catch(() => {});
  console.log(results.join("\n"));
  throw error;
} finally {
  await browser.close();
}
