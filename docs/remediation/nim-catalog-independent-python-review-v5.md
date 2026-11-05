# NIM katalog sınaması: bağımsız Python incelemesi

5 Kasım 2026. `f83938ff` ve `df7f93db` için sonuç: **ONAY**, açık bulgu yok.

Ürün değişikliği yalnız NIM'in beklenen başarılı katalog yanıtını nasıl açıkladığını
ve fonksiyonun kapsam belgesini değiştirir. `ok=True` katalog erişimini belirtir;
anahtar kabulü, çıkarım yetkisi, model kullanılabilirliği veya kota kanıtı sayılmaz.
`ValidationResult(ok, message)` biçimi, hata dalları, diğer sağlayıcılar ve tercihler
korunmuştur. RPC metni aynen taşır; mevcut arayüz bu metni gösterir. Yeni çıkarım
isteği veya kalıcı ayar yazımı eklenmemiştir.

Bağımsız doğrulama, mevcut Python ortamı ve `PYTHONPATH=src` ile yapıldı:

- API ve appserver kontrol modüllerinde 17 test başarılı, 2,19 saniye.
- Sağlayıcı kayıt modülünde 20 test başarılı, 1,37 saniye.
- 12 ek çevrimdışı `httpx.MockTransport` kontrolü başarılı, 0,13 saniye. NIM için
  200/401/403/429/500 ve üç bozuk yanıt biçimi; diğer dört sağlayıcı için mevcut
  kimlik başlıkları, resmî hedef, salt GET, URL'de anahtar taşınmaması sınandı.
  NIM durumlarında tek katalog GET'i, değişmeyen sonuç alanları ve anahtarın
  yanıt metnine sızmaması ayrıca doğrulandı. Bu testler metin kopyasına dayanmaz.
- Üç değişen Python dosyası için Ruff ve biçim denetimi temiz; ürün dosyasında
  kapsamlı import izlemeyen mypy başarılı; `git diff --check` temiz.

Kontrol panelindeki eski çalışma kimliği cümlesini bekleyen testin değişikliği,
onaylanan istemle ayrı sohbet kimliği sözleşmesini sınar. Sohbetin kendiliğinden
proje taramaması ve aynı onay sözleşmesine tabi olması kontrolleri korunmuştur.

İncelenen ürün dosyasının SHA-256 değeri:
`64162b7defeec3f3a29155991da0b29c49f48b825018959c474e7fe5e1493953`.

Ek kontroller görev çalışma alanındaki
`work/reliability-v2/nim-catalog-python-review-v5/test_catalog_scope.py` içinde
korunur. Gerçek ağ, model veya native çağrı yapılmadı. Bu inceleme herhangi bir
gerçek anahtarın çıkarım yetkisinin çalıştığını ileri sürmez.
