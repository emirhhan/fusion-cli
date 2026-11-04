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

// HTTP and event completion can arrive in either order; old events cannot revive a turn.
context.setGlow = async () => {};
run('thread={mesajlar:[{rol:"asistan",turnId:"panel:1",durum:"calisiyor"}],seq:1,soru:null}; inflight=true;');
await run('applyItem({tur:"bitti",turnId:"panel:1",ok:true,metin:"done"}).then(next=>{thread=next;})');
assert.equal(run('running()'), false, 'terminal event settles even while HTTP is pending');
await run('applyItem({tur:"basladi",turnId:"panel:1"}).then(next=>{thread=next;})');
assert.equal(run('running()'), false, 'delayed started event cannot resurrect completed owner');
run('thread={mesajlar:[{rol:"asistan",turnId:"panel:2",durum:"calisiyor"}],seq:2,soru:null};');
await run('applyItem({tur:"bitti",turnId:"panel:1",ok:true}).then(next=>{thread=next;})');
assert.equal(run('running()'), true, 'old completion cannot settle a newer owner');
run('request=async(path,data)=>{globalThis.cancelBody=data;return {ok:false,metin:"wrong owner"};};');
await assert.rejects(run('cancel()'), /wrong owner/);
assert.equal(run('cancelBody.turnId'), 'panel:2');
assert.equal(run('running()'), true, 'rejected stop does not claim cancellation');

// Finish over HTTP, then drain queued started+finished events: exactly one final row.
context.crypto = {randomUUID: () => 'http:1'};
context.expandShortcut = async (value) => value;
context.autoGrow = () => {};
run('thread={mesajlar:[],seq:0,soru:null}; request=async()=>({ok:false,turnId:"http:1",metin:"busy"});');
await run('sendPrompt("request")');
assert.equal(run('running()'), false, 'busy HTTP rejection leaves the composer idle');
run('thread={mesajlar:[],seq:0,soru:null}; request=async()=>({ok:true,turnId:"http:1",metin:"done"});');
await run('sendPrompt("request")');
await run('applyItem({tur:"basladi",turnId:"http:1"}).then(next=>{thread=next;})');
await run('applyItem({tur:"bitti",turnId:"http:1",ok:true,metin:"done"}).then(next=>{thread=next;})');
assert.equal(run('running()'), false);
assert.equal(run('thread.mesajlar.length'), 2, 'event replay cannot append a phantom assistant');

// Accepted cancellation survives terminal delivery and HTTP completion in either order.
for (const eventFirst of [true, false]) {
  let finishTurn;
  context.crypto = {randomUUID: () => `cancel:${eventFirst}`};
  context.cancelTransport = (path) => path === '/cancel'
    ? Promise.resolve({ok: true})
    : new Promise((resolve) => { finishTurn = resolve; });
  run('thread={mesajlar:[],seq:0,soru:null};request=cancelTransport;');
  const pendingTurn = run('sendPrompt("cancel request")');
  while (!finishTurn) await new Promise((resolve) => setTimeout(resolve, 0));
  await run('cancel()');
  assert.equal(run('thread.mesajlar.at(-1).durum'), 'iptal', 'accepted cancel marks its owner');
  const terminal = `applyItem({tur:"bitti",turnId:"cancel:${eventFirst}",ok:false,metin:"stopped"}).then(next=>{thread=next;})`;
  if (eventFirst) await run(terminal);
  finishTurn({ok: false, metin: 'stopped'});
  await pendingTurn;
  if (!eventFirst) await run(terminal);
  await run(terminal);
  assert.equal(run('thread.mesajlar.at(-1).durum'), 'iptal', `cancellation survives ${eventFirst ? 'event then HTTP' : 'HTTP then event'} and terminal replay`);
  assert.equal(run('thread.mesajlar.at(-1).metin'), 'stopped');
  assert.equal(run('running()'), false);
  assert.equal(run('thread.mesajlar.length'), 2);
}

// The terminal event can also beat the cancel HTTP response itself.
for (const terminalState of ['hata', 'bitti', 'foreign']) {
  let finishCancel, finishLateTurn;
  context.crypto = {randomUUID: () => 'cancel:late'};
  context.delayedCancel = (path) => path === '/cancel'
    ? new Promise((resolve) => { finishCancel = resolve; })
    : new Promise((resolve) => { finishLateTurn = resolve; });
  run('thread={mesajlar:[],seq:0,soru:null};request=delayedCancel;');
  const lateTurn = run('sendPrompt("late cancellation")');
  while (!finishLateTurn) await new Promise((resolve) => setTimeout(resolve, 0));
  const pendingCancel = run('cancel()');
  while (!finishCancel) await new Promise((resolve) => setTimeout(resolve, 0));
  await run(`applyItem({tur:"bitti",turnId:"cancel:late",ok:${terminalState === 'bitti'},metin:"terminal text"}).then(next=>{thread=next;})`);
  if (terminalState === 'foreign') run('thread={...thread,mesajlar:[...thread.mesajlar,{rol:"asistan",turnId:"newer",durum:"calisiyor"}]};');
  finishCancel({ok: true});
  await pendingCancel;
  finishLateTurn({ok: terminalState === 'bitti', metin: 'terminal text'});
  await lateTurn;
  if (terminalState === 'hata') {
    assert.equal(run('thread.mesajlar.at(-1).durum'), 'iptal', 'accepted cancel reconciles after unsuccessful terminal');
    await run('applyItem({tur:"bitti",turnId:"cancel:late",ok:false,metin:"terminal text"}).then(next=>{thread=next;})');
    assert.equal(run('thread.mesajlar.at(-1).durum'), 'iptal', 'terminal replay preserves late accepted cancel');
    assert.equal(run('thread.mesajlar.at(-1).metin'), 'terminal text');
  } else {
    assert.equal(run('thread.mesajlar.at(-1).durum'), terminalState === 'bitti' ? 'bitti' : 'calisiyor', 'accepted stop cannot change successful completion or foreign owner');
  }
}
