// Gerçek panel taşıması: rozet, hata ve kontrol saati aynı bağlantı sonucunu kullanır.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../../chrome-extension/panel.js',import.meta.url),'utf8')
 .replace(/^import .*;$/gm,'').split('$("composer").addEventListener')[0];
const elements=new Map();
const context=vm.createContext({
 document:{getElementById:(id)=>{if(!elements.has(id))elements.set(id,{textContent:'',dataset:{},lastChild:{},replaceChildren(){}});return elements.get(id);}},
 chrome:{storage:{session:{get:async()=>({fusionAuto:{bagli:true}})}}},
 setTimeout,AbortSignal,console,
});
vm.runInContext(source+'\nmanual={port:1234,token:"test"}; listen=async()=>{};loadSettings=async()=>{};',context);
const run=(text)=>vm.runInContext(text,context);
context.fetch=async()=>{throw new Error('Failed to fetch');};
await assert.rejects(run('request("/events")'));
assert.equal(elements.get('status')?.dataset.state,'offline','transport hatasında eski online rozeti kalmaz');
context.fetch=async()=>({ok:false,status:401,json:async()=>({hata:'Eşleştirme anahtarı geçersiz'})});
await assert.rejects(run('request("/status")'));
assert.match(elements.get('status').lastChild.textContent,/Eşleştirme/);
context.fetch=async()=>({ok:true,status:200,json:async()=>({ok:true})});
await run('request("/events")');
assert.equal(elements.get('status').dataset.state,'online');
assert.equal(elements.get('error').textContent,'');
assert.match(elements.get('connection-checked').textContent,/Son kontrol/);
run('error("İzin cevabı kabul edilmedi")');
await run('request("/events")');
assert.equal(elements.get('error').textContent,'İzin cevabı kabul edilmedi','bağlantı başarısı bağımsız kullanıcı hatasını silmez');
console.log('chrome-panel-connection ✓');

context.fetch=async()=>{throw new Error('Failed to fetch');};
run('guard(()=>request("/settings"))()');
await new Promise((resolve)=>setTimeout(resolve,0));
context.fetch=async()=>({ok:true,status:200,json:async()=>({ok:true})});
await run('request("/events")');
assert.equal(elements.get('error').textContent,'','eylem guardı üzerinden gelen ağ hatası da reconnect sonrasında silinir');
