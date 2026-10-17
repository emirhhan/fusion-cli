// Gerçek mobil sayfada bekleyen ve başarısız eşleştirme istekleri.
import { chromium } from '../app/node_modules/playwright/index.mjs';
import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
const root = process.argv[2];
const browser = await chromium.launch({headless:true});
try {
 const page = await browser.newPage({viewport:{width:390,height:844},isMobile:true});
 await page.route('http://localhost:9876/**', async route => {
  const path = new URL(route.request().url()).pathname;
  if(path.startsWith('/v1/')) return route.fulfill({json:{accountLogin:false}});
  const name=path==='/'?'index.html':path.slice(1);
  const contentType=name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':'text/html';
  await route.fulfill({body:await readFile(`${root}/${name}`),contentType});
 });
 await page.goto('http://localhost:9876/');
 await page.locator('#eslestir').waitFor({state:'visible'});
 await page.locator('#kod').fill('ABCDEFGH');
 let release;
 await page.route('**/v1/pair/submit',async route=>{await new Promise(r=>release=r);await route.abort();});
 await page.locator('#eslestirDugme').click();
 await page.waitForTimeout(100);
 assert.match(await page.locator('#durum').innerText(),/gönderiliyor/i,'İstek beklerken anında geri bildirim verilmeli');
 assert.equal(await page.locator('#eslestirDugme').isDisabled(),true,'Çift gönderim engellenmeli');
 release();
 await page.waitForTimeout(200);
 assert.match(await page.locator('#durum').innerText(),/ulaşılamıyor/i,'Ağ hatası gösterilmeli');
 assert.equal(await page.locator('#eslestirDugme').isEnabled(),true,'Hata sonrası yeniden denenebilmeli');
 await page.route('**/v1/pair/submit',route=>route.fulfill({json:{message:'Kod geçersiz veya süresi doldu.'},status:400}));
 await page.locator('#eslestirDugme').click();
 await page.waitForTimeout(100);
 assert.match(await page.locator('#durum').innerText(),/Kod geçersiz/);
 await page.route('**/v1/pair/submit',route=>route.fulfill({json:{state:'onay_bekliyor'}}));
 await page.route('**/v1/pair/claim',route=>route.fulfill({status:400,json:{message:'Kod geçersiz veya süresi doldu.'}}));
 await page.locator('#eslestirDugme').click();
 await page.waitForTimeout(100);
 assert.match(await page.locator('#durum').innerText(),/bu cihazı onayla/);
 assert.equal(await page.locator('#eslestirDugme').isDisabled(),true);
 await page.waitForTimeout(2100);
 assert.equal(await page.locator('#eslestirDugme').isEnabled(),true);
 await page.addInitScript(() => {
  const original = window.setTimeout;
  window.setTimeout = (fn, ms, ...args) => original(fn, ms === 20000 ? 50 : ms, ...args);
 });
 await page.reload();
 await page.locator('#eslestir').waitFor({state:'visible'});
 await page.locator('#kod').fill('ABCDEFGH');
 // Yanıt vermeyen ağ isteği, üretimdeki zaman aşımını tetikler.
 await page.route('**/v1/pair/submit',() => {});
 await page.locator('#eslestirDugme').click();
 await page.waitForTimeout(100);
 assert.match(await page.locator('#durum').innerText(),/ulaşılamıyor/);
 assert.equal(await page.locator('#eslestirDugme').isEnabled(),true);
 console.log('Mobil eşleştirme: bekleme, ağ hatası, yeniden deneme, masaüstü onayı, geçersiz kod ve zaman aşımı doğrulandı.');
} finally {await browser.close();}
