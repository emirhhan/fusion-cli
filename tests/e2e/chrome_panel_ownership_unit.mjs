// Gerçek panel denetleyicisi: DOM çizimi ve dış taşıma sınırları sahte tutulur.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../../chrome-extension/panel.js', import.meta.url), 'utf8')
  .replace(/^import .*;$/gm, '').split('$("composer").addEventListener')[0];
const elements = new Map();
const context = vm.createContext({
  chrome: { storage: { session: { set: async () => {} } } },
  document: { getElementById: (id) => {
    if (!elements.has(id)) elements.set(id, {textContent:'', dataset:{}, lastChild:{}, replaceChildren(){}, querySelectorAll:()=>[]});
    return elements.get(id);
  } },
  setTimeout, console,
});
vm.runInContext(source + '\nconst originalRenderThread = renderThread; renderThread = () => {};', context);
const run = (code) => vm.runInContext(code, context);
run('thread = { mesajlar: [], seq: null, soru: null }; request = async () => ({ son: 12, sorular: [{id: "pending", veri: {tur:"onay"}}] }); connection = async () => null;');
await run('listen()');
assert.equal(run('thread.soru?.id'), 'pending', 'yeni panel bekleyen onayı snapshot üzerinden geri alır');
run('request = async () => ({ok: false, hata: "Soru kapandı"});');
await assert.rejects(run('answer({secim:"evet"})'), /Soru kapandı/);
assert.equal(run('thread.soru?.id'), 'pending', 'ret kartı sessizce silmez');
let finish;
context.transport = () => new Promise((resolve) => { finish = resolve; });
run('request = transport;');
const waiting = run('answer({secim:"evet"})');
await Promise.resolve();
assert.equal(run('thread.soru?.id'), 'pending', 'kabul gelene kadar kart görünür');
run('thread = {...thread, soru: {id:"newer", veri:{tur:"onay"}}};');
finish({ok: true});
await waiting;
assert.equal(run('thread.soru?.id'), 'newer', 'gecikmiş yanıt yeni kartı silmez');
console.log('chrome-panel-ownership ✓');

run('thread = {mesajlar:[], seq:1, soru:{id:"pending",veri:{tur:"onay"}}}; renderMessage = ()=>null; controlSummary = ()=>({used:false, counts:{},last:""}); renderAsk = (_node,_question,onAnswer)=>{globalThis.cardAnswer=onAnswer;}; request=async()=>({ok:false,hata:"Eski soru reddedildi"}); originalRenderThread();');
run('cardAnswer({secim:"evet"})');
await new Promise((resolve)=>setTimeout(resolve,0));
assert.equal(elements.get('error').textContent, 'Eski soru reddedildi', 'sunucu ret nedeni kullanıcıya görünür');

run('thread={mesajlar:[],seq:0,soru:null};let switchPolls=0;connection=async()=>switchPolls++===0?{}:null;request=async()=>({ok:true,son:1,sorular:[{tur:"tarayici_sec",id:"switch-owned",veri:{tur:"soru",tarayici_sec:true,soru:"Bu tarayıcı?"}}],olaylar:[{seq:1,tur:"tarayici_sec",id:"switch-owned",veri:{tur:"soru",tarayici_sec:true,soru:"Bu tarayıcı?"}}]});');
await run('listen()');
assert.equal(run('thread.soru?.id'),'switch-owned','switch sorusu canlı olay ve snapshot uzlaşmasında kaybolmaz');
run('thread={mesajlar:[],seq:null,soru:null};connection=async()=>null;request=async()=>({son:1,sorular:[{tur:"tarayici_sec",id:"switch-owned",veri:{tur:"soru",tarayici_sec:true}}]});');
await run('listen()');
assert.equal(run('thread.soru?.id'),'switch-owned','yeni panel switch sorusunu snapshot üzerinden geri alır');
