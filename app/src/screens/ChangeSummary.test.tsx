import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { Conversation, type Mesaj } from "./Conversation";
afterEach(cleanup);
const diff = '--- a/src/main.py\n+++ b/src/main.py\n@@ -1 +1,2 @@\n-old\n+new\n+more\n';
const edit: Mesaj = { id:'edit',rol:'olay',metin:'düzenlendi',adimlar:[{metin:'düzenlendi',arac:'edit_file',yol:'src/main.py',durum:'ok',diff}] };
const final: Mesaj={id:'final',rol:'asistan',metin:'Düzeltildi ve test edildi.'};
it('sonucun altında gerçek dosyalar ve diff satır sayılarıyla tek kart gösterir',()=>{
 const {container}=render(<Conversation running={false} mesajlar={[{id:'u',rol:'kullanici',metin:'Düzelt'},edit,final]} />);
 const card=screen.getByRole('region',{name:'Dosya değişiklikleri'});
 expect(card.textContent).toContain('1 dosya düzenlendi');
 expect(card.querySelector('.change-summary__added')?.textContent).toBe('+2');
 expect(card.querySelector('.change-summary__removed')?.textContent).toBe('−1');
 expect(card.textContent).toContain('src/main.py');
 const article=container.querySelector('.conversation__message--assistant')!;
 expect(article.textContent).toContain('Düzeltildi ve test edildi.');
 expect(article.querySelector('.change-summary')).toBeTruthy();
});
it('görüntüleme düğmesi gerçek diffi açar, dosya adı gerçek açma eylemine bağlıdır',()=>{
 const open=vi.fn();render(<Conversation running={false} onOpenFile={open} mesajlar={[edit,final]} />);
 const card=screen.getByRole('region',{name:'Dosya değişiklikleri'});
 fireEvent.click(within(card).getByRole('button',{name:'src/main.py dosyasını aç'}));
 expect(open).toHaveBeenCalledWith('src/main.py');
 const button=within(card).getByRole('button',{name:'Değişiklikleri görüntüle'});
 fireEvent.click(button);expect(button.getAttribute('aria-expanded')).toBe('true');
 expect(card.querySelector('.diff-card')?.textContent).toContain('+more');
});
it('aynı dosyayı bir kez listeler ve başarısız düzenlemeyi saymaz',()=>{
 render(<Conversation running={false} mesajlar={[edit,{...edit,id:'again'}, {...edit,id:'failed',adimlar:[{...edit.adimlar![0],yol:'other.py',durum:'failed'}]},final]} />);
 const card=screen.getByRole('region',{name:'Dosya değişiklikleri'});
 expect(card.textContent).toContain('1 dosya düzenlendi');
 expect(card.textContent).not.toContain('other.py');
 expect(card.querySelector('.change-summary__added')?.textContent).toBe('+4');
});
it('kullanıcı turlarının dosya özetleri karışmaz ve çalışan turun kartı erken çizilmez',()=>{
 const {rerender}=render(<Conversation running mesajlar={[{id:'u',rol:'kullanici',metin:'İlk'},edit,final,{id:'u2',rol:'kullanici',metin:'İkinci'},{...edit,id:'e2',adimlar:[{...edit.adimlar![0],yol:'b.py'}]}]} />);
 expect(screen.getAllByRole('region',{name:'Dosya değişiklikleri'})).toHaveLength(1);
 expect(screen.getByRole('region',{name:'Dosya değişiklikleri'}).textContent).not.toContain('b.py');
 rerender(<Conversation running={false} mesajlar={[{id:'u',rol:'kullanici',metin:'İlk'},edit,final,{id:'u2',rol:'kullanici',metin:'İkinci'},{...edit,id:'e2',adimlar:[{...edit.adimlar![0],yol:'b.py'}]}]} />);
 expect(screen.getAllByRole('region',{name:'Dosya değişiklikleri'})).toHaveLength(2);
});

it('eski biçimde diff ile biten durdurulmuş turda özet görünür',()=>{
 render(<Conversation running={false} mesajlar={[{id:'legacy',rol:'degisiklik',metin:'src/main.py',diff}]} />);
 expect(screen.getByRole('region',{name:'Dosya değişiklikleri'}).textContent).toContain('1 dosya düzenlendi');
});
