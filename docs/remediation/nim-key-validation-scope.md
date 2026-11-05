# NIM katalog sınamasının kapsamı

## Tasarım ve uygulama planı

NIM'in herkese açık `/v1/models` yanıtı API anahtarının kabul edildiğini veya belirli bir modelin çıkarım yapabildiğini kanıtlamaz. Bu nedenle yalnız NIM'in başarılı katalog sınaması mesajı, erişim sonucunu ve doğrulanmayan yetkileri açıkça belirtir. `ValidationResult(ok, message)` biçimi ve mevcut hata dalları korunur. Yeni ağ isteği, çıkarım sınaması, kimlik bilgisi veya model tercihi değişikliği eklenmez.

1. RPC ve arayüz tüketicilerinin mesajı yeniden doğrulanmış anahtar iddiasına dönüştürmediğini kontrol et.
2. NIM başarı metnini ve fonksiyon kapsamı belgesini düzelt; diğer sağlayıcılara ve hata yanıtlarına dokunma.
3. Mevcut API, kontrol paneli ve sağlayıcı kayıt testlerini; Ruff ve dar mypy kontrolünü çalıştır.
4. Değişikliği bağımsız incelemeye sun; canlı çıkarım yetkisi doğrulanmış gibi raporlama.

## Tüketici ve sınırlar

`AppSession` RPC sonucu `ok` ve `metin` olarak aynen döndürür. `ProviderList` bu metni gösterir; normal yanıtta kendi başarı cümlesini üretmez. API kartının “anahtar kayıtlı” durumu ve model seçicinin doğrulanmamış sağlık durumu değişmez. `ok=True`, NIM için beklenen katalog yanıtının alındığını ifade eder.

401/403 erişim reddi, 429 kullanım sınırı, diğer HTTP hataları, bozuk yanıt ve yönlendirme davranışları değişmez. Bu düzeltme gözlenen 120B çıkarım isteğinin 404 nedenini belirlemez ve hiçbir modelin genel olarak kullanılamaz olduğu sonucunu çıkarmaz.

Mevcut NIM testinin yanıltıcı adı ve açıklaması düzeltilmiştir; yalnız metni tekrar eden yeni bir test eklenmemiştir. Canlı ağ, model veya native uygulama çalıştırılmamıştır.

## Doğrulama

`PYTHONPATH=src` ve mevcut Python ortamıyla API doğrulama, appserver kontrol ve sağlayıcı kayıt modüllerindeki 37 test çalıştırıldı: 36 başarılı, bir bağımsız eski istem metni beklentisi başarısız. `test_sohbet_kipi_proje_taramasini_zorunlu_kilmaz`, artık bulunmayan “çalışma dizininde gerçek iş yaparsın” ifadesini bekliyordu. Onaylanan `f9b6489f` istemiyle mevcut istemin baytları aynıdır; söz konusu ifade başlangıç sürümünde de yoktur. İlk NIM düzeltmesi o isteme veya teste dokunmadı. İlk başarısız koşunun XML'i saklanmıştır.

Yalnız bu bilinen test dışlanarak ilgili 36 test tekrar başarılı çalıştı; bir test dışlandı. Ruff kontrolü ve biçim denetimi iki dosyada, mypy değiştirilmiş kaynak dosyada başarılıdır. `git diff --check` temizdir. Tüm test süreçleri terminaldir; başarısız test gizlenerek tam paket başarılı iddiası yapılmaz.

Ana ajanın açık kapsam genişletmesiyle bu eski testin iki metin beklentisi, çalışma ve sohbet kimliklerinin ayrı olması sözleşmesine dönüştürüldü. Sohbetin kendiliğinden proje taramaması ve aynı onay sözleşmesine tabi olması kontrolleri aynen korundu; ürün istemi değiştirilmedi. Tarihsel test açıklaması güncellendi. Son üç modül koşusu **37 başarılı, sıfır başarısız/hata/atlanan** olarak tamamlandı; Ruff ve biçim kontrolü üç dosyada temizdir. Önceki başarısızlık ve dışlanmış koşu kayıtları korunmuştur.
