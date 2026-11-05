import { expect, it } from 'vitest';
import { historyMessages } from './history';
import backendFixtures from '../protocol/__fixtures__/document-delivery-v6.json';

it.each(backendFixtures)('backend teslim kaydı yeniden açıldığında aynı kanıtı taşır: $name', fixture=>{
 const [message]=historyMessages([{rol:'asistan',metin:fixture.text,kanit:fixture.kanit,id:'persisted'}]);
 expect(message.id).toBe('persisted');
 expect(message.metin).toBe(fixture.text);
 expect(message.delivery?.presentation).toBe(fixture.compact?'document':undefined);
 expect(message.delivery?.changeSummary).toEqual(fixture.kanit.degisiklik_ozeti);
});
it('geri yüklemede açıklama ile araç sonucunu aynı sırada çözer',()=>{
 const result=historyMessages([
  {rol:'kullanici',metin:'Düzelt',id:'u'},
  {rol:'asistan',metin:'Dosyayı düzenliyorum',ara:true,id:'n'},
  {rol:'olay',id:'c',olay:{olay:'ToolExecuted',name:'edit_file',args:{path:'a.py'},outcome:'ok',output:'Düzenlendi',diff:'--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old\n+new'}},
  {rol:'asistan',metin:'Düzeltildi',id:'final'},
 ]);
 expect(result.map(m=>m.rol)).toEqual(['kullanici','asistan','olay','asistan']);
 expect(result[1].ara).toBe(true);
 expect(result[2].adimlar?.[0]).toMatchObject({arac:'edit_file',yol:'a.py',durum:'ok'});
 expect(result[2].adimlar?.[0].diff).toContain('+new');
 expect(result[3].id).toBe('final');
});
it('bozuk veya bilinmeyen geçmiş olayını kod gibi çalıştırmaz',()=>{
 expect(historyMessages([null,5,{}, {rol:'olay',olay:'metin'}, {rol:'olay',olay:{olay:'arbitrary',name:'write_file'}}])).toEqual([]);
});

it('zamanı bilinmeyen eski araç için açılış zamanından sahte süre üretmez',()=>{
 const result=historyMessages([{rol:'olay',olay:{olay:'ToolExecuted',name:'run_shell',outcome:'ok',output:'ok'}}]);
 expect(result[0].baslangicZamani).toBeUndefined();
});

it('yeniden yüklenen /code-review cevabındaki bulguları kart olarak çözer (#214)',()=>{
 const result=historyMessages([
  {rol:'asistan',metin:'İki bulgu.',id:'r',bulgular:[{file:'a.py',line:3,summary:'s',failure_scenario:'f',verdict:'CONFIRMED'},{file:''}]},
  {rol:'asistan',metin:'Düz cevap',id:'d'},
 ]);
 expect(result[0].findings).toEqual([{file:'a.py',line:3,summary:'s',failureScenario:'f',verdict:'CONFIRMED'}]);
 expect(result[1].findings).toBeUndefined();
});

it('alan kısaltma ve hassas içerik bayraklarını tek araç olmayan bildirimde sunar', () => {
 const rows = [{rol:'olay',olay:{olay:'ToolExecuted',name:'read_file',args:{path:'.env'},outcome:'ok',output:'gizlendi',history_truncated:['output'],history_redacted:['output']}}];
 const messages=historyMessages(rows);
 expect(messages[0].rol).toBe('bildirim');
 expect(messages[0].metin).toContain('kısaltıldı');
 expect(messages[0].metin).toContain('hassas');
 expect(messages.filter(message=>message.rol==='olay')).toHaveLength(1);
 expect(messages[0].adimlar).toBeUndefined();
});

it('yeniden açılan belge cevabı temiz metin ve kanıt ayrıntılarını birlikte korur', () => {
 const [message] = historyMessages([{rol:'asistan', id:'receipt-answer', metin:'Rapor hazır.', kanit:{
  schema_version:1,dogrulandi:true,engelliyor:false,yanlis_iddia:false,degisen:['rapor.html'],degisen_sayisi:1,
  sorunlar:[],sunum:'document',kontroller:['Tarayıcıda açıldı'],oneriler:['Main önerisi'],degisiklik_ozeti:['67 satır'],
 }}]);
 expect(message).toMatchObject({id:'receipt-answer',metin:'Rapor hazır.',delivery:{presentation:'document',
  checks:['Tarayıcıda açıldı'],advisories:['Main önerisi'],changeSummary:['67 satır']}});
 expect(message.metin).not.toContain('67 satır');
});

it('metni boş kanıt kartını ve bozuk kanıtın görünür hata durumunu korur', () => {
 const result=historyMessages([{rol:'asistan',metin:'',kanit:{schema_version:1}}, {rol:'asistan',metin:''}]);
 expect(result).toHaveLength(1);
 expect(result[0].delivery).toMatchObject({kind:'invalid',blocking:true});
});
