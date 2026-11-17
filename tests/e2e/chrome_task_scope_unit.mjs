// Real extension executor, with only browser/transport boundaries faked.
import assert from 'node:assert/strict';
import {execute} from '../../chrome-extension/core.js';

let permissions = 0, updates = 0;
let store = {fusionTab:{id:99,origin:'https://foreign.test'}};
const tabs = new Map([
  [7,{id:7,url:'https://example.com/',status:'complete',windowId:1}],
  [99,{id:99,url:'https://foreign.test/',status:'complete',windowId:1}],
]);
globalThis.chrome = {
  storage:{session:{get:async key=>({[key]:store[key]}),set:async data=>Object.assign(store,data),remove:async key=>{delete store[key];}}},
  permissions:{contains:async()=>{permissions++;return true;}}, // existing global permission
  tabs:{get:async id=>({...tabs.get(id)}),query:async()=>[...tabs.values()],
    update:async(id,data)=>{updates++;Object.assign(tabs.get(id),data);return tabs.get(id);},
    onUpdated:{addListener(){},removeListener(){}},
  },
};
const scope={tabId:7,origin:'https://example.com',version:1};
const command=(islem,veri={})=>({id:'owned',islem,veri,taskScope:scope});
await assert.rejects(execute(command('navigate',{tabId:7,url:'https://www.magnific.com/'})),
  error=>error.code==='task_scope');
assert.equal(permissions,0,'foreign task request must stop before site consent lookup/prompt');
assert.equal(updates,0,'globally granted origin still cannot expand task authority');

await execute(command('navigate',{url:'https://example.com/again'}));
assert.equal(tabs.get(7).url,'https://example.com/again','accepted target survives selected-tab switch');
assert.equal(tabs.get(99).url,'https://foreign.test/');
const listed=await execute(command('tabs'));
assert.deepEqual(listed.tabs.map(tab=>tab.id),[7],'restricted task cannot read unrelated tabs');

tabs.get(7).pendingUrl='https://foreign.test/redirect';
const permissionCount=permissions;
await assert.rejects(execute(command('snapshot')),error=>error.code==='task_scope');
assert.equal(permissions,permissionCount,'changed target is rejected before permission');
delete tabs.get(7).pendingUrl;
tabs.get(7).url='https://foreign.test/redirect';
await assert.rejects(execute(command('snapshot')),error=>error.code==='task_scope');
tabs.get(7).url='https://example.com/';
await assert.rejects(execute(command('navigate',{tabId:99,url:'https://example.com/'})),error=>error.code==='task_scope');
await assert.rejects(execute(command('history',{dir:'back'})),error=>error.code==='task_scope');
await assert.rejects(execute(command('click',{ref:'e1'})),error=>error.code==='task_scope');
// A tab can change while permissions.contains / a consent card is awaiting.
chrome.permissions.contains=async()=>{tabs.get(7).pendingUrl='https://foreign.test/';return true;};
const beforeRace=updates;
await assert.rejects(execute(command('navigate',{url:'https://example.com/reload'})),error=>error.code==='task_scope');
assert.equal(updates,beforeRace);
delete tabs.get(7).pendingUrl;
chrome.permissions.contains=async()=>true;
// Even a navigation between tabs.get and actual script dispatch cannot leak page text.
chrome.scripting={executeScript:async({func,args})=>{
  globalThis.location={origin:'https://foreign.test'};
  return [{result:func(...args)}];
}};
await assert.rejects(execute(command('snapshot')), /başlangıçtaki sitesi değişti/);
delete globalThis.location;
// Unrestricted/manual work retains normal globally granted navigation.
await execute({id:'manual',islem:'navigate',veri:{tabId:99,url:'https://another.test/'}});
assert.equal(tabs.get(99).url,'https://another.test/');

// Missing-monitor fallback must not install a script after the checked document changes.
let monitorTab={id:7,url:'https://example.com/',status:'complete',windowId:1};
let monitorInstalls=0, moveAfterRead=true;
globalThis.chrome={
  storage:{local:{get:async()=>({})},session:{get:async()=>({fusionTab:{id:7,origin:'https://example.com'}})}},
  permissions:{contains:async()=>true}, // foreign site is already globally granted
  tabs:{get:async()=>({...monitorTab})},
  scripting:{executeScript:async spec=>{
    if(spec.files){monitorInstalls++;return [];}
    globalThis.location={origin:new URL(monitorTab.url).origin};
    const result=spec.func(...spec.args);
    if(moveAfterRead) monitorTab.url='https://foreign.test/';
    return [{result}];
  }},
};
delete globalThis.__fusionMonitor;
const absent=await execute(command('console'));
assert.equal(monitorInstalls,0,'pregranted foreign page cannot receive fallback monitor injection');
assert.equal(absent.present,false);
assert.match(absent.ipucu,/kurulmadı/,'missing monitor is reported honestly');
monitorTab.url='https://example.com/';moveAfterRead=false;
const sameOriginAbsent=await execute(command('console'));
assert.equal(sameOriginAbsent.present,false);
assert.equal(monitorInstalls,0,'restricted missing-monitor reads never start an unbound file injection');
globalThis.__fusionMonitor={console:[],network:[],pending:0};
assert.equal((await execute(command('console'))).present,true,'existing same-origin monitoring remains readable');
delete globalThis.__fusionMonitor;
const unrestricted=await execute({id:'manual-monitor',islem:'console',veri:{}});
assert.equal(monitorInstalls,1,'unrestricted same-origin fallback still installs the monitor');
assert.match(unrestricted.ipucu,/şimdi başladı/);
delete globalThis.location;
console.log('chrome-task-scope ✓');
