// Gerçek Talk bileşenini test verisiyle doğrular; hesap/mikrofon/model erişimi yok.
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { chromium } from 'playwright';
const out=resolve('../.superpowers/sdd/2026-10-12-fusion-profesyonel-uygulama/ui-review-2026-10-15');
await mkdir(out,{recursive:true});
const browser=await chromium.launch();
const page=await browser.newPage({viewport:{width:320,height:360},reducedMotion:'reduce'});
const errors=[];const checks=[];
page.on('pageerror',error=>errors.push(error.message));
try {
 for(const theme of ['light','dark']) {
  await page.setViewportSize({width:320,height:360});
  await page.goto(`http://127.0.0.1:4174/e2e/pet-review.html?theme=${theme}&question=0`);
  await page.evaluate(()=>document.fonts.ready);
  assert.equal(await page.locator('.voice-ask').count(),0);
  const surfaces=await page.evaluate(()=>[document.documentElement,document.body,document.querySelector('.voice-panel')].map(node=>getComputedStyle(node).backgroundColor));
  assert.deepEqual(surfaces,['rgba(0, 0, 0, 0)','rgba(0, 0, 0, 0)','rgba(0, 0, 0, 0)']);
  assert.equal(await page.locator('.voice-panel').evaluate(node=>getComputedStyle(node).boxShadow),'none');
  assert.equal(await page.locator('.voice-wave').count(),0);
  await page.mouse.move(-10,-10);
  await page.screenshot({path:resolve(out,`${theme}-pet-thinking.png`),omitBackground:true});
  await page.goto(`http://127.0.0.1:4174/e2e/pet-review.html?theme=${theme}`);
  await page.evaluate(()=>document.fonts.ready);
  const summary=page.getByRole('button',{name:'Sorunun tamamını oku'});
  assert.equal(await summary.getAttribute('aria-expanded'),'false');
  assert.equal(await page.locator('.voice-ask__details').count(),0);
  assert.equal(await page.locator('.voice-ask__text').textContent(),'İki dosyadaki düzenlemeler uygulansın mı?');
  assert.equal(await page.locator('.voice-ask').evaluate(node=>getComputedStyle(node).backgroundColor),theme==='dark'?'rgb(48, 48, 48)':'rgb(255, 255, 255)');
  await page.mouse.move(-10,-10);
  await page.screenshot({path:resolve(out,`${theme}-pet-question.png`),omitBackground:true});
  await summary.click();
  await page.setViewportSize({width:380,height:460});
  assert.equal(await page.locator('.voice-ask__full').count(),1);
  assert.deepEqual(await page.evaluate(()=>window.petReview.answers),[]);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:resolve(out,`${theme}-pet-expanded.png`),omitBackground:true});
  await page.getByRole('button',{name:'Reddet',exact:true}).click();
  assert.deepEqual(await page.evaluate(()=>window.petReview.answers),['deny']);
  await page.evaluate(()=>window.petReview.newQuestion());
  assert.equal(await page.getByRole('button',{name:'Sorunun tamamını oku'}).getAttribute('aria-expanded'),'false');
  assert.equal(await page.locator('.voice-ask__details').count(),0);
  await page.getByRole('button',{name:'Sorunun tamamını oku'}).click();
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('.voice-ask__details').count(),0);
  assert.equal(await page.evaluate(()=>document.activeElement?.getAttribute('aria-label')),'Sorunun tamamını oku');
  checks.push(`${theme}: alpha/no extra microphone/summary/full question/decision/new question/Escape`);
 }
 await page.goto('http://127.0.0.1:4174/e2e/pet-review.html?pending=1');
 await page.getByRole('button',{name:'Sorunun tamamını oku'}).click();
 assert.equal(await page.getByRole('button',{name:'Bu kez izin ver'}).isDisabled(),true);
 checks.push('pending decision disabled');
 assert.deepEqual(errors,[]);
} finally {
 await browser.close();
 await writeFile(resolve(out,'pet-browser-checks.json'),JSON.stringify({checks,errors,mode:'actual-components-local-fixture'},null,2)+'\n');
}
console.log(JSON.stringify({checks:checks.length,errors}));
