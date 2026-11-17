// İnsan bekleme süresi, ret, iptal ve geç yanıt gerçek izin akışında ayrılır.
import assert from 'node:assert/strict';
import {ensurePermission, answerPermission, PERMISSION_KEY, setPermissionWait} from '../../chrome-extension/permissionWait.js';
let store = {}, granted = false, now = 0;
globalThis.chrome = {
  permissions:{contains:async()=>granted},
  storage:{session:{get:async(key)=>key===null?{...store}:({[key]:store[key]}), set:async(items)=>Object.assign(store,items), remove:async(key)=>{delete store[key];}}},
};
const pending = () => Object.entries(store).find(([key])=>key.startsWith(`${PERMISSION_KEY}:`))?.[1];
const timing = (step) => ({now:()=>now,sleep:async(ms)=>{now+=ms;await step?.();}});
const reset = () => {store={};granted=false;now=0;setPermissionWait(300000);};
reset();
await ensurePermission('https://work.test','İzin gerekli',{},timing(()=>{if(now>=35000)granted=true;}));
assert.equal(now>=35000,true,'25sn sonra da verilen izin aynı bekleyen komutu sürdürebilir');
assert.equal(pending(),undefined);

reset();
await assert.rejects(ensurePermission('https://work.test','İzin gerekli',{},timing(async()=>{
  await answerPermission(pending().id,'denied',now);
})),(error)=>error.code==='permission_denied');
assert.equal(pending(),undefined);

reset();setPermissionWait(500);
await assert.rejects(ensurePermission('https://work.test','İzin gerekli',{},timing()),(error)=>error.code==='permission_timeout');
assert.equal(pending(),undefined);
assert.equal(await answerPermission('expired','granted',now),false);

reset();let active=true;
await assert.rejects(ensurePermission('https://work.test','İzin gerekli',{
  commandId:'old-command',onProgress:async()=>({ok:active,aktif:active}),
},timing(()=>{active=false;granted=true;})),(error)=>error.code==='permission_cancelled');
assert.equal(pending(),undefined,'iptal edilen komut izin sonradan gelse de sürmez');

reset();let currentId;
const waiting=ensurePermission('https://work.test','İzin gerekli',{},timing(async()=>{
  currentId=pending().id;
  assert.equal(await answerPermission('another-question','denied',now),false);
  assert.equal(pending().id,currentId);
  await answerPermission(currentId,'denied',now);
}));
await assert.rejects(waiting,(error)=>error.code==='permission_denied');
console.log('chrome-permission-wait ✓');

// İki ayrı komutun kartı aynı Chrome deposunda yaşarken eski cleanup yenisini silemez.
reset();
let ready;
const bothSleeping=new Promise((resolve)=>{ready=resolve;});
const sleepers=[];
const clock=(at)=>({now:()=>at,sleep:()=>new Promise((resolve)=>{sleepers.push(resolve);if(sleepers.length===2)ready();})});
const first=ensurePermission('https://one.test','İzin',{},clock(1000));
const second=ensurePermission('https://two.test','İzin',{},clock(2000));
const rejectedFirst=assert.rejects(first,(error)=>error.code==='permission_denied');
const rejectedSecond=assert.rejects(second,(error)=>error.code==='permission_denied');
await bothSleeping;
const cards=Object.values(store);
const firstCard=cards.find((card)=>card.origin==='https://one.test');
const secondCard=cards.find((card)=>card.origin==='https://two.test');
assert.equal(cards.length,2);
await answerPermission(firstCard.id,'denied',2000);
sleepers[0]();
await rejectedFirst;
assert.equal(Object.values(store)[0].id,secondCard.id);
await answerPermission(secondCard.id,'denied',2000);
sleepers[1]();
await rejectedSecond;
assert.deepEqual(store,{});
