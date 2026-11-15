import {describe,expect,it} from 'vitest';
import {olayEkle} from './olayAkisi';
import type {Mesaj} from '../screens/Conversation';
const identity={session_id:'session',turn_id:'turn:1',attempt_id:'turn:1'};
const start=(call_id:string,path='a.html',extra={})=>({olay:'ToolStarted',name:'start_preview',args:{path},metin:`Önizleme ${path}`,call_id,...identity,...extra});
const finish=(call_id:string,path='a.html',extra={})=>({olay:'ToolExecuted',name:'start_preview',args:{path},outcome:'ok',output:`Tamam ${path}`,call_id,...identity,...extra});
const steps=(messages:Mesaj[])=>messages.flatMap(message=>message.adimlar??[]);

describe('tool call identity pairing',()=>{
 it('completes one preview step across its PreviewReady card',()=>{
  let m=olayEkle([{rol:'kullanici',metin:'Rapor'}],start('preview'));
  m=olayEkle(m,{olay:'PreviewReady',url:'http://127.0.0.1:8770/a.html'});
  m=olayEkle(m,finish('preview'));m=olayEkle(m,{olay:'TurnAnswered'});
  expect(steps(m)).toHaveLength(1);expect(steps(m)[0]).toMatchObject({basladi:false,durum:'ok',cikti:'Tamam a.html'});
  expect(m.filter(x=>x.rol==='onizleme')).toHaveLength(1);
 });
 it('pairs concurrent same-named calls in reverse completion order across narration',()=>{
  let m=olayEkle([],start('first','a.html'));m=olayEkle(m,start('second','b.html'));
  m=olayEkle(m,{olay:'NarrationPublished',text:'Önizlemeler'});
  m=olayEkle(m,finish('second','b.html',{outcome:'failed',output:'İkinci hata'}));m=olayEkle(m,finish('first','a.html'));
  expect(steps(m)).toHaveLength(2);
  expect(steps(m)[0]).toMatchObject({metin:'Önizleme a.html',cikti:'Tamam a.html',durum:'ok',basladi:false});
  expect(steps(m)[1]).toMatchObject({metin:'Önizleme b.html',cikti:'İkinci hata',durum:'failed',basladi:false});
 });
 it.each(['session_id','turn_id','attempt_id'])('does not merge a mismatched %s',field=>{
  let m=olayEkle([],start('same'));m=olayEkle(m,finish('same','a.html',{[field]:'foreign'}));
  expect(steps(m)).toHaveLength(2);expect(steps(m)[0].basladi).toBe(true);
 });
 it('does not merge different call IDs by adjacent name',()=>{
  let m=olayEkle([],start('first'));m=olayEkle(m,finish('foreign'));
  expect(steps(m)).toHaveLength(2);expect(steps(m)[0].basladi).toBe(true);
 });
 it('does not cross a user turn boundary',()=>{
  let m=olayEkle([],start('same'));m=[...m,{rol:'kullanici',metin:'Yeni tur'}];m=olayEkle(m,finish('same'));
  expect(steps(m)).toHaveLength(2);expect(steps(m)[0].basladi).toBe(true);
 });
 it('keeps legacy adjacent name pairing',()=>{
  let m=olayEkle([],{olay:'ToolStarted',name:'read_file',args:{path:'a'},metin:'a okunuyor'});
  m=olayEkle(m,{olay:'ToolExecuted',name:'read_file',args:{path:'a'},outcome:'ok',output:'A'});
  expect(steps(m)).toHaveLength(1);expect(steps(m)[0]).toMatchObject({basladi:false,durum:'ok'});
 });
 it('deduplicates the same owned terminal event after another card',()=>{
  const event=finish('preview','a.html',{event_id:'turn:1:2'});
  let m=olayEkle([],event);
  m=olayEkle(m,{olay:'PreviewReady',url:'http://127.0.0.1:8770/a.html'});
  m=olayEkle(m,event);
  expect(steps(m)).toHaveLength(1);
 });
 it('does not deduplicate another call using the same event id',()=>{
  let m=olayEkle([],finish('first','a.html',{event_id:'collision'}));
  m=olayEkle(m,finish('second','b.html',{event_id:'collision'}));
  expect(steps(m)).toHaveLength(2);
 });
});
