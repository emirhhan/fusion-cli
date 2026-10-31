// Panelin "/ad" kısayol genişletmesi (shortcuts.js) Node'da. Kullanım: node chrome_shortcuts_unit.mjs
import assert from "node:assert/strict";
import { expandShortcut, findShortcut } from "../../chrome-extension/shortcuts.js";

const list = [{ ad: "ozet", metin: "Bu sayfayı kısaca özetle." }, { ad: "Çevir", metin: "Sayfayı Türkçeye çevir." }];

// Kayıtlı kısayol: ad büyük/küçük harf duyarsız (Türkçe), kalan metin görevin altına eklenir.
assert.deepEqual(expandShortcut("/ozet", list), { prompt: "Bu sayfayı kısaca özetle.", shortcut: "ozet", unknown: null });
assert.deepEqual(expandShortcut("/çevir  yalnız başlıkları", list), {
  prompt: "Sayfayı Türkçeye çevir.\nyalnız başlıkları", shortcut: "Çevir", unknown: null,
});
assert.equal(findShortcut(list, "ÇEVİR")?.ad, "Çevir");
assert.equal(findShortcut(list, "yok"), null);

// Ölçüldü (31 Ekim, bağımsız inceleme): "/" ile başlayan her mesaj kısayol sanılıyor, kısayol
// yoksa hata atılıp mesaj GÖNDERİLMİYORDU. Dosya yolu, "/ metin" ve kısayol adı + ek metin
// olduğu gibi gider.
for (const text of ["/Users/x/proje/app.js dosyasını açıkla", "/etc/hosts", "/ bu sayfayı özetle", "/ozett bu sayfayı özetle", "//yorum"]) {
  assert.deepEqual(expandShortcut(text, list), { prompt: text, shortcut: null, unknown: null }, text);
}
// Yalnız "/ad" yazılmış, kayıtlı kısayol var ama bu ad yok: yazım hatası olabilir, panel sorar.
assert.deepEqual(expandShortcut("/ozett", list), { prompt: "/ozett", shortcut: null, unknown: "ozett" });
// Hiç kısayol yokken "/ad" da olduğu gibi gider (eski davranış).
assert.deepEqual(expandShortcut("/ozet", []), { prompt: "/ozet", shortcut: null, unknown: null });
assert.deepEqual(expandShortcut("merhaba", list), { prompt: "merhaba", shortcut: null, unknown: null });

console.log("chrome-shortcuts ✓");
