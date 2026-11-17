# Hedef istisnaları ve landmark: son bağımsız Python onayı

5 Kasım 2026. İncelenen son ürün sürümü `12069aa1f3e2bcf01214203567902ad253458b17`.
Sonuç: **ONAY**, önceki incelemede bildirilen açık bulgu kalmadı.

Önceki `1a564b2e` ve `72093dbf` inceleme kayıtları tarihsel kanıt olarak korunur.
Görünmeyen/etkisiz landmark bağlamları `54e1661f` ile; eşleşmeyen kapanışlarda
karesel yığın taraması `12069aa1` ile giderilmiştir.

Son sürüm, ilgisiz devam eden değişiklikler karışmasın diye `git archive` ile ayrı
kaynak/test görüntüsünde incelendi. Mevcut Python ortamı ve `PYTHONPATH=src` kullanıldı.

- **171 test başarılı, 14,22 saniye.** Önceki 12 bağımsız landmark/önem derecesi/
  ölçülemeyen durum/geometri kontrolü, beş yeni yığın karmaşıklığı kontrolü ve web,
  browser, hedef istisnaları, önem derecesi, d4 browser ve istek koruması modülleri
  çalıştırıldı.
- Deterministik kontrolde 100, 500 ve 6.000 açık öğe üzerindeki aynı sayıda
  eşleşmeyen kapanış **sıfır ata yığını okuması** yaptı. Eşleşen kapanışlarda her
  açık öğe tam bir kez çıkarıldı. Gizli bağlamın korunması, uyumsuz kapanışla alt
  öğelerin temizlenmesi ve aynı adlı iç içe öğelerin konumları ayrıca doğrulandı.
- Dört değişen Python dosyasında Ruff ve biçim kontrolü, iki ürün dosyasında dar
  mypy başarılıdır. Bu incelemenin bütün süreçleri terminaldir.

Konum dizini yalnız son ekten çıkarılan yığın konumlarını tuttuğundan kalan
ataların konumları geçerli kalır. Açılmamış etiket sözlük sorgusuyla döner;
eşleşen kapanışlarda temizlenen her ata toplam ayrıştırma boyunca bir kez çıkar.

İncelenen SHA-256 değerleri:

- `browser_verify.py`: `2a095d6b39977e6e732aac42bdf82c95a8f705a8465b445e9a8e7a8c2c31e024`
- `web_verify.py`: `106bd43f76cd3aa780cd5d08fa89e591381fda915e20ead1c8772784ee838514`

Browser kaynağı önceki bağımsız JavaScript onayındaki baytlarla aynıdır.
Temas formu/istek korumasındaki önceki 58 başarılı test tarihsel kanıt olarak
korunur; bu son dar değişiklikte istek koruması yeniden çalıştırılmıştır.

Ek kontroller görev alanında `work/reliability-v2/a11y-python-review-v6/` altında
korunur. Ürün dosyası değiştirilmedi; gerçek ağ/model/native çağrı yapılmadı.
Onay dar statik landmark önerisi, önem derecesi ve yığın hesabıyla sınırlıdır;
tam CSS/ARIA erişilebilirlik ağacı veya bütün WCAG uygunluğu iddiası değildir.
