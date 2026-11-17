// Gerçek background→offscreen→progress yolu; yalnız Chrome API ve HTTP dış sınırı sahtedir.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {execute, MONITOR_KEY, registerMonitor} from '../../chrome-extension/core.js';
import {PROGRESS_REQUEST_TIMEOUT_MS} from '../../chrome-extension/permissionWait.js';
import {TASK_SCOPE_VERSION} from '../../chrome-extension/taskScope.js';

let store={},granted=false,acceptCompletion=true;
const listeners=[];
const noop={addListener(){}};
const chrome={
 action:{onClicked:noop},commands:{onCommand:noop},permissions:{onAdded:noop,onRemoved:noop,contains:async()=>granted},
 storage:{onChanged:noop,session:{get:async(key)=>({[key]:store[key]}),set:async(items)=>Object.assign(store,items),remove:async(key)=>{delete store[key];}}},
 tabs:{get:async(id)=>({id,url:'https://work.test',windowId:1})},
 runtime:{onMessage:{addListener:(listener)=>listeners.push(listener)},sendMessage:(message)=>new Promise((resolve,reject)=>{
  let pending=false;
  for(const listener of listeners) pending=listener(message,{},resolve)===true||pending;
  if(!pending) reject(new Error('Yanıt veren yok'));
 })},
};
globalThis.chrome=chrome;
const background=fs.readFileSync(new URL('../../chrome-extension/background.js',import.meta.url),'utf8')
 .replace(/^import .*;$/gm,'').split('chrome.runtime.onStartup.addListener')[0];
vm.runInNewContext(background,{chrome,execute,MONITOR_KEY,registerMonitor,TASK_SCOPE_VERSION,console});
const offscreen=fs.readFileSync(new URL('../../chrome-extension/offscreen.js',import.meta.url),'utf8')
 .replace(/^import .*;$/gm,'').split('setInterval(')[0];
const calls=[];
const surface=vm.createContext({chrome,console,AbortSignal,setTimeout,PROGRESS_REQUEST_TIMEOUT_MS,
 fetch:async(_url,request)=>{
  const progress=JSON.parse(request.body);calls.push(progress);
  assert.equal(progress.cihaz.id,'work');
  if(progress.durum==='permission_wait') granted=true;
  return {ok:true,json:async()=>({ok:progress.durum!=='permission_done'||acceptCompletion,aktif:acceptCompletion})};
 },
});
vm.runInContext(offscreen+'\nconnection={port:1,token:"fake"};device={id:"work",ad:"İş"};activeCommandId="owned";',surface);
const result=await chrome.runtime.sendMessage({type:'fusion.exec',command:{id:'owned',islem:'tab_select',veri:{id:5}}});
assert.equal(result.ok,true);
assert.equal(store.fusionTab.id,5);
assert.equal(calls.at(-1).durum,'permission_done');

store={};granted=false;acceptCompletion=false;
const cancelled=await chrome.runtime.sendMessage({type:'fusion.exec',command:{id:'owned',islem:'tab_select',veri:{id:5}}});
assert.equal(cancelled.ok,false);
assert.equal(cancelled.neden_kodu,'permission_cancelled');
assert.equal(store.fusionTab,undefined,'durmuş komut gerçek seçili sekmeyi değiştiremez');
assert.equal(Object.keys(store).some((key)=>key.startsWith("fusionPermission:")),false);
assert.equal((await chrome.runtime.sendMessage({type:'fusion.taskScopeCapability'})).version,1);
// Offscreen must not strip taskScope when dispatching its special recorder path.
const scopedRecord=await vm.runInContext('run({id:"owned",islem:"record",veri:{op:"start"},taskScope:{version:1,tabId:5,origin:"https://work.test"}})',surface);
assert.equal(scopedRecord.ok,false);
assert.equal(scopedRecord.neden_kodu,'task_scope');
console.log('chrome-permission-transport ✓');
