import { expect, it } from 'vitest';
import { historyMessages } from './history';
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
