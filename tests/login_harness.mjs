// Hesap girişinin varsayılan olması ve kodla girişe geçiş.
import { webkit } from '../app/node_modules/playwright/index.mjs';
import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
const root=process.argv[2];
const browser=await webkit.launch();
try {
 const page=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
 let enabled=true;
 await page.route('http://localhost:9876/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path==='/v1/auth/options')return route.fulfill({json:{accountLogin:enabled}});
  const name=path==='/'?'index.html':path.slice(1);
  const contentType=name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':name.endsWith('.svg')?'image/svg+xml':'text/html';
  await route.fulfill({body:await readFile(`${root}/${name}`),contentType});
 });
 await page.goto('http://localhost:9876/');
 await page.locator('#hesapGiris').waitFor({state:'visible'});
 assert.equal(await page.locator('#kod').isVisible(),false,'İlk açılış hesapla giriş olmalı');
 await page.getByRole('button',{name:'Şifremi unuttum',exact:true}).tap();
 assert.equal(await page.locator('#kod').isVisible(),true);
 assert.equal(await page.locator('#hesapKimlik').isVisible(),false);
 await page.getByRole('button',{name:'Hesapla girişe dön',exact:true}).tap();
 assert.equal(await page.locator('#hesapKimlik').isVisible(),true);
 assert.equal(await page.locator('#kod').isVisible(),false);
 await page.route('**/v1/auth/options',async route=>{
  await new Promise(resolve=>setTimeout(resolve,500));
  await route.fulfill({json:{accountLogin:true}});
 });
 await page.reload();
 await page.locator('#hesapParola').fill('test-only');
 await page.waitForTimeout(600);
 assert.equal(await page.locator('#hesapParola').inputValue(),'test-only','Geç seçenek yanıtı yazılan parolayı silmemeli');
 await page.reload();
 await page.getByRole('button',{name:'Şifremi unuttum',exact:true}).tap();
 await page.waitForTimeout(600);
 assert.equal(await page.locator('#kod').isVisible(),true,'Geç seçenek yanıtı seçilen formu değiştirmemeli');
 await page.unroute('**/v1/auth/options');
 enabled=false;await page.reload();
 await page.locator('#kod').waitFor({state:'visible'});
 assert.equal(await page.locator('#hesapGiris').isVisible(),false,'Hesap girişi kapalıysa kod kullanılmalı');
 console.log('WebKit: varsayılan hesap, şifremi unuttum, geri dönüş ve kod fallback doğrulandı.');
}finally{await browser.close()}
