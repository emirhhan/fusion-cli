import { afterEach, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/dom';
import { createChat } from '../../../src/fusion_cli/remote/pwa/chat.js';
let chat;
afterEach(()=>{chat?.close();document.body.replaceChildren();});
it('sohbet açıldıktan sonra bulunan görev onayını sohbet içine getirir', async()=>{
 const rpc=vi.fn(async method=>method==='tasks.events'
  ?{ok:true,data:{state:'waiting_approval',events:[{seq:1,kind:'approval_request',payload:{questionId:'q1',title:'Dosyayı kaydet',options:['once','deny']}}]}}
  :{ok:true,data:{messages:[]}});
 const root=document.createElement('section');document.body.append(root);
 chat=createChat({rpc,root,ctx:{projects:[],tiers:[],tasks:[]},onBack:vi.fn(),onChange:vi.fn(),toast:vi.fn()});
 chat.show({chatId:'c1',title:'Sohbet',isNew:false});
 await Promise.resolve();
 chat.reconcile([{chatId:'c1',runId:'r1',state:'waiting_approval',summary:'Görev'}]);
 await waitFor(()=>expect(screen.getByText('Dosyayı kaydet')).toBeTruthy());
 expect(rpc).toHaveBeenCalledWith('tasks.events',expect.objectContaining({runId:'r1'}));
});

it('eski görevin isteği beklerken yeni görev seçilirse akış yeniden başlar', async()=>{
 let release;
 const rpc=vi.fn(async (method,params)=>{
  if(method!=='tasks.events')return {ok:true,data:{messages:[]}};
  if(params.runId==='r1')return await new Promise(resolve=>{release=resolve;});
  return {ok:true,data:{state:'waiting_approval',events:[{seq:1,kind:'approval_request',payload:{questionId:'q2',title:'Yeni görevin onayı',options:['once','deny']}}]}};
 });
 const root=document.createElement('section');document.body.append(root);
 chat=createChat({rpc,root,ctx:{projects:[],tiers:[],tasks:[]},onBack:vi.fn(),onChange:vi.fn(),toast:vi.fn()});
 chat.show({chatId:'c1',run:{chatId:'c1',runId:'r1',state:'running',summary:'İlk görev'}});
 await waitFor(()=>expect(release).toBeTypeOf('function'));
 chat.reconcile([{chatId:'c1',runId:'r2',state:'waiting_approval'}]);
 release({ok:true,data:{state:'done',events:[]}});
 await waitFor(()=>expect(screen.getByText('Yeni görevin onayı')).toBeTruthy());
});
