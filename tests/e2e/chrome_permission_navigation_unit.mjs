// Navigate geri dönüşü komut sahibini korur; iptal/ret yeni sekmeye dönüşemez.
import assert from 'node:assert/strict';
import {execute} from '../../chrome-extension/core.js';
let store={},granted=false,opened=0,progressCalls=0;
const tab={id:7,url:'https://redirect.test',status:'complete',windowId:1};
globalThis.chrome={
 storage:{session:{get:async(key)=>({[key]:store[key]}),set:async(items)=>{Object.assign(store,items);if(Object.keys(items).some((key)=>key.startsWith('fusionPermission:')))granted=true;},remove:async(key)=>{delete store[key];}}},
 permissions:{contains:async()=>granted},
 tabs:{query:async()=>[],get:async()=>tab,create:async()=>{opened++;return tab;},onUpdated:{addListener(){},removeListener(){}}},
};
const options={onPermissionProgress:async()=>{progressCalls++;return{ok:false,aktif:false};}};
await assert.rejects(execute({id:'owned',islem:'navigate',veri:{url:'https://destination.test'}},options),
 (error)=>error.code==='permission_cancelled');
assert.equal(opened,0,'bağlı sekme yok geri dönüşü iptal edilmiş komutla yeni sekme açamaz');
assert.ok(progressCalls>0,'recursive execute komut progress callbackini taşır');

store={fusionTab:{id:7,origin:'https://original.test'}};granted=false;opened=0;progressCalls=0;
await assert.rejects(execute({id:'owned',islem:'navigate',veri:{url:'https://destination.test'}},options),
 (error)=>error.code==='permission_cancelled');
assert.equal(opened,0,'checkedTab izin iptali tab_open geri dönüşüne çevrilemez');
assert.equal(progressCalls,1);
console.log('chrome-permission-navigation ✓');
