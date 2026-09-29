# Öğretmen–çırak aşamaları — sonuç raporu (29 Eylül 2026)

Kaynak görev: `FUSION_CODEX_GOREV_PROMPTU.md` (7 aşama). Aşama 1'i Codex bitirdi
(`3dd0ec7`); kalan işler bu oturumda tamamlandı. Çalışma dalı
`fusion-runtime-hardening-20260827-022831`, push yapılmadı.

## Commit'ler

| Aşama | Commit | Konu |
|---|---|---|
| 1 (düzeltme) | `a3b67b0` | Noktalı virgülle ayrılmış çok adımlı görev öğretmen planı alır |
| 2 | `4756391` | Öğretmen planı sonucuyla hafızaya yazılır, benzer görevde tekrar sorulmaz |
| 3 | `ca571c9` | Dış platforma bağlı istekte resmi kaynak işe başlamadan kontrol edilir |
| 5 | `ae02fd5` | Adımlar tek satır ve açılabilir; ara anlatım akışta kalır |
| 4 | `bfa0e15` | API modelleri için kapsamlı çalışma ve konuşma talimatı katmanı |
| 6 | `0459a64` | Yedeği olan model 429'da beklemeden yedeğe bırakır |
| 7 | `e35077b` | Düğümlü görsel iş akışı, uygulama içi galeri, NIM FLUX üretimi |
| 6 (ölçüm) | bu rapor | Canlı uzun görev sayaçları |

Her aşamada ruff, mypy, tam pytest, vitest, build ve `check:ci` temiz geçti.
Değişen eski davranışlar ilgili testlerin açıklamasına gerekçesiyle yazıldı.

## Aşama 2 — Öğretmen hafızası

- Otomatik plan ve denetim cevapları artık anında "başarılı ders" diye yazılmıyor.
  Plan, tur sonunda yalnız başarılı sonuçla `scope="ogretmen-plani"` dersi olarak
  kaydediliyor; kanıt (değişen dosya sayısı, doğrulama kapısı) `trigger` alanında.
- Benzerlik: ilk beş harfe kırpılmış kök kümeleri üzerinde Jaccard, eşik 0,5
  (üç örnekle testte sabitlendi).
- Hafızadaki plan tutmazsa güveni düşüyor. `success_count <= failure_count`
  olduğunda bir sonraki benzer işte öğretmene yeniden soruluyor.

## Aşama 3 — Dış platform kontrolü

Ad listesiyle tespit edilen platform için yalnız resmi geliştirici sitesinde
(`site:`) arama yapılıyor ve sonuç çırağa veriliyor. Kaynağa ulaşılamazsa bu
nota ve cevaba yazılıyor. Öğretmenin bildirdiği kısıt cevapta anılmadıysa tur
sonunda cevaba ekleniyor. Testler gerçek arama motoruna çıkmıyor
(`tests/conftest.py::izole_web_aramasi`).

## Aşama 4 ve 5 — Claude gibi talimat ve görünüm

- `prompts/system_api.md` yalnız API modellerinde çekirdek talimatın ardına
  ekleniyor. İçeriği: giriş paragrafı ya da gerekli soru, adımlar arası kısa
  anlatım, bitiş özeti ve araç, doğrulama, dış platform, kapsam ve güvenlik
  ilkeleri. Web modelleri dar çekirdekle kalıyor.
- Arayüzde her adım tek satır. Tıklayınca diff, komut ve çıktı açılıyor; diff
  akışa ayrı kart olarak düşmüyor. Araçtan önce akan metin ara anlatım olarak
  kalıyor. Öğretmen, hafıza ve resmi kaynak adımları da iz bırakıyor.

## Aşama 6 — Kırılmayan çalışma

- 429'da yalnız ardından yedek gelen halka beklemeden bırakıyor; yedeksiz model
  eski davranışla kısa bekleyip yeniden deniyor.
- Bozuk araç çağrısı onarımı, takılınca öğretmene danışma ve tur içi sıkıştırma
  mevcuttu, korunuyor.

**Canlı uzun görev** (`python -m evals.long_tasks.run fiyat_aktarimi`, kullanıcının
gerçek yapılandırması: çırak NIM nemotron-3-super, öğretmen Gemini web):

| Ölçü | Değer |
|---|---|
| Süre | 1.289,9 sn (21,5 dk) |
| Model çağrısı | 41 |
| Öğretmen çağrısı | 3 (ilk plan, takılma danışması, son denetim) |
| Araç hatası | 2 |
| Yedeğe geçiş | 0 |
| Gizli kabul testleri | **9/9 geçti** |
| Sahte başarı | yok |

Gerçek Gemini öğretmeni işe başlamadan geçerli JSON plan döndürdü. Plan, beş
adım ve beş dosya olarak çırağın görev listesine aktarıldı. Codex'in gerçek
öğretmenle doğrulayamadığı "önce plan" adımı bu koşuda kanıtlandı.

**Açık madde:** Ajan turu `ok=false` bitirdi. Son doğrulama komutunun çıktısında
çıkış kodu öneki yoktu; rapor bunu "çıkış None" ve başarısız doğrulama olarak
gösterdi. Aynı komut tur sonrasında elle koşulunca 13/13 test 1,6 sn'de geçti.
Öneksiz çıktı zaman aşımında ya da engellenen komutta oluşur. Hangisi olduğu
koşu kaydından belirlenemedi (araç çıktısı saklanmıyor).

## Aşama 7 — Flora tarzı görsel üretimi

- "Görsel oluştur" sayfası artık düğümlü bir tuval. Girdi düğümleri (Metin,
  Görsel), işlem düğümleri (Üret, Varyasyon, Büyüt, Düzenle) ve Çıktı düğümü
  bağlanıyor. Akış kaydediliyor, açılıyor ve yeniden çalıştırılıyor.
- Görseller `~/.local/share/fusion-cli/gallery` altında uygulama içi galeride
  kalıyor. Yalnız "İndir" ile, kayıt penceresinde seçilen yere kopyalanıyor.
- Web modelleri gerçek bir büyütme aracı sunmuyor. Büyütme, referans görselin
  yüksek çözünürlükte yeniden üretilmesi olarak isteniyor.

**Ücretsiz görsel modelleri — canlı ölçüm** (bu kurulumun NIM anahtarı):

| Model | Sonuç |
|---|---|
| NIM `black-forest-labs/flux.1-dev` | çalışıyor, 8,1 sn |
| NIM `black-forest-labs/flux.2-klein-4b` | çalışıyor, 40,9 sn |
| Gemini web (referanslı düzenleme) | çalışıyor, 34,1 sn; kırmızı kask aynı kompozisyonda mat siyaha döndü |

Yalnız çalışan modeller listeleniyor. Ölçümde düşenler: `flux.1-schnell` 240 sn
içinde yanıt vermedi. `flux.1-kontext-dev` base64 görsel kabul etmedi (422).
SD3 medium, SDXL, SDXL turbo ve Bria 2.3 bu hesapta 404 döndü. NIM FLUX uçları
referans görsel almıyor; referans gerektiren düğümlerde yalnız Gemini web
seçilebiliyor.

## Yapılmayanlar

- Push ve sürüm yayını yapılmadı; kullanıcı onayı gerekiyor.
- Kurulu uygulama yeniden paketlenmedi. Arayüz değişikliklerinin paketli
  uygulamada görsel doğrulaması bu yüzden yapılmadı; tarayıcı önizlemesi Tauri
  kabuğu olmadan açılmıyor. DOM davranışı vitest ile doğrulandı.
