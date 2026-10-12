# Başka hesaba devir — GPT-6.1 Sol low uygulaması

Bu dosya kullanıcı tarafından başka hesaba verilecek uygulama talimatıdır; şu anda dış bir hesaba mesaj gönderilmedi. Model adı kullanıcı tercihidir. Aşağıdaki blok mevcut özellikleri silip yeniden yazmaya veya tüm raporu tek turda uygulamaya yetki vermez.

## Başlangıç mesajı

```text
Fusion projemi profesyonel günlük kullanım için geliştireceğiz. GPT-6.1 Sol low ile çalışıyorum; karmaşık kararlarda tahmin ederek geniş değişiklik yapma, mevcut sözleşme ve küçük görev paketi üzerinden ilerle.

Depolar:
/Users/motogate/Desktop/all/01-Projeler/fusion-cli
/Users/motogate/Desktop/all/01-Projeler/fusion-kits

İlk okumalar:
1. fusion-cli/CLAUDE.md ve RULES.md
2. docs/superpowers/reports/2026-10-12-fusion-profesyonel-arastirma/README.md
3. Aynı klasörde 01–07 ekleri; önce mevcut güçlü taraflar ve kanıt sınırı.
D01–D05 kararları 07-kaynak-ve-karar-defteri.md dosyasında; sözleşme uyuşmazlığında önceliklidir.
4. docs/superpowers/plans/2026-10-12-fusion-profesyonel-uygulama.md

Mevcut branch ve kullanıcı değişikliklerini koru. Yeni branch/push/merge/hard reset yapma. .env, çerez, token veya API anahtarı içeriklerini okuma. git add . kullanma; node_modules ekleme. Ücretsiz LLM kimliğini koru; GPT-6.1 Sol bu uygulayıcı model, Fusion'ın yeni varsayılanı değil.

Önce git status ve revision ile güncel durumu doğrula. Raporun hazırlandığı revision 644a2e44, Kits 1dd007c1; bunların ilerisine geçilmiş olabilir. Başka oturumun işine dokunma. Yeni full pytest veya kabul koşusu başlamadan mevcut ağır koşuların durumunu denetle; full pytest ile evals.kabul paralel çalışmaz.

İlk iş Paket 1. Python tam koşusunda üç test başarısız olmuştu:
tests/test_kabul_html_game.py::test_restart_only_on_game_over_with_state_hook_passes
tests/test_remotion_kit.py::test_runtime_edilmis_onceki_kare_feature_markerini_yeniden_kullanmaz
tests/test_remotion_observe.py::test_renderer_ayri_gruptaki_direncli_chromium_benzeri_cocugu_temizler
Önce tek tek üretip nedenini bul; kanıtsız flaky etiketi veya sadece sleep artırma yok.

App testleri Node22 ile 122 dosya/956 test geçmişti. Global Node26 jsdom localStorage hatası üretiyor. Kits farklı: engines>=24 ve kits scriptleri Node24.21.0. App ve Kits'i tek Node sürümünde zorla çalıştırma. Python repo .venv kullan.

145 maddelik liste fikir ve geliştirme kapsamıdır. Hepsini tek turda uygulama. 16 paket planını sırayla izle; o paketin rapor ID'lerini oku, önce gerçek davranış testiyle açığı doğrula. Zaten mevcut ve doğruysa yeniden yazma; kanıtla kaydet. Yeni tip/imza önerisini mevcut API diye varsayma; mevcut karşılığı varsa genişlet. Yeni event bus/agent loop/model yöneticisi/izin deposu/scheduler oluşturma.

Her paket için: davranış testi fail → küçük uygulama → ilgili test pass → gerekli lint/type/full kalite kapısı → bağımsız review → Türkçe conventional commit. Kalite kapısı kırmızı iken commit yok. Kullanıcıya durum, kalan iş ve somut engel bildir. Gereksiz aşama onayı isteme; bu talimat kapsamındaki geri alınabilir yerel işleri sürdür. Dış yayın, harcama, silme veya izin genişletme ayrı somut kapsam gerektirir.

Onay/soru/idempotency/fallback/draft/checkpoint gibi sözleşmelerde eksik karar varsa küçük repro/contract testiyle açıklaştır. Sessiz geniş varsayım yerine gerçek blocker'ı belirt; bağımsız çalışmaya devam et. Model yetersizliği hissedersen testi/kanıtı ve dar alternatifleri göster; projeyi baştan kurma.

Bitti iddiası sadece test değil gerçek task receipt/artefakt/acceptance ile. Model bitti dedi diye UI completed olmayacak. İstenen ve kullanılan model farklıysa görünür olacak. Kaynakta özellik bulunması runtime'da çalıştığı iddiası değil. Mikrofon, MCP OAuth, görünür giriş penceresi, paket kurulum ve gerçek üretim ayrıca canlı kabul ister.

Başlarken güncel başlangıç durumunu ve Paket 1'de hangi testi ürettiğini bildir; sonra işi yap. Paket sonunda aşağıdaki ilerleme kaydını güncelle. Tüm Fusion hazır veya ChatGPT/Claude paritesi sağlandı iddiasını aynı brief/ölçüm olmadan yapma.
```

## Tek paketlik dar devam mesajı

```text
Fusion raporundaki Paket N'yi uygula. Önce README davranış sözleşmeleri, Paket N, ilgili U/E/K/R maddeleri ve önceki tamamlanan paketlerin interface kaydını oku. Güncel kaynakta bug hâlâ var mı davranış testiyle göster. Bu tur yalnız o bağımsız paketi tamamla; diğer paketleri kodlama. Paket bittiğinde test/kanıt, dosya listesi, review, commit ve açık eksikleri ilerleme tablosuna yaz. Paket büyürse çalışan ve test edilebilir alt teslimlere böl; kapsam sessiz genişlemesin.
```

`N` kullanıcı/ilerleme kaydındaki gerçek paket numarasıyla değiştirilir. Otomatik olarak N+1 tahmin edilmez; son committed gate kaydı kontrol edilir.

## İlerleme tablosu

Bu başlangıç tablosu **uygulanmadı** durumundadır. Rapor hazırlanması geliştirme paketinin tamamlandığı anlamına gelmez.

| Paket | Durum | Commit | Test/kanıt yolu | Sonraki engel |
|---|---|---|---|---|
| 1 Taban/runtime | Başlamadı | — | Önceki üç pytest fail | Teşhis |
| 2 Olay/gönderim | Başlamadı | — | — | 1 |
| 3 Onboarding/async | Başlamadı | — | — | 2 |
| 4 Model/thinking | Başlamadı | — | — | 2/3 |
| 5 Onay/soru | Başlamadı | — | — | 2 |
| 6 MCP | Başlamadı | — | — | 5 |
| 7 Skill/ekip | Başlamadı | — | — | 5/6 |
| 8 Resume/iptal | Başlamadı | — | — | 2/5 |
| 9 Teslim kanıtı | Başlamadı | — | — | 2/8 |
| 10 Görsel işler | Başlamadı | — | — | 4/8/9 |
| 11 Kits dayanıklılığı | Başlamadı | — | — | 2/5/8 |
| 12 Asset/theme bridge | Başlamadı | — | — | 10/11 |
| 13 Ses/browser | Başlamadı | — | — | 5/8/11 |
| 14 Gerçek üretim | Başlamadı | — | — | İlgili P0/P1 |
| 15 İleri/protokol | Başlamadı | — | — | İlgili taban |
| 16 Günlük kullanım kabul | Başlamadı | — | — | Kritik kapılar |

## Paket sonunda yazılacak kayıt

```text
Paket / kapsam ID'leri:
Başlangıç revision ve working tree:
Davranış testi (önce fail):
Root cause:
Değişen dosyalar:
Yeni/güncellenen interface ve migration:
İlgili test sonucu:
Tam kapı / hangi ortam / exit:
Gerçek kabul gerekiyorsa kanıt:
Bağımsız review sonucu:
Commit:
Açık eksik/engeller:
Sonraki güvenli paket:
```

## Düşük reasoning modunda hata önleme

Küçük kapsam güçlü korumadır. Bir task'ın testini yazıp çalıştırmadan dört başka modülü değiştirme. Gerçek failure ile öneriyi ayır. TypeScript typecheck, Python mypy ve geriye uyum fixtures sezgisel API tahminlerini erken yakalar. Arayüz görselini ancak gerçek host receipt'inden besle. Büyük raporu her tur tamamını prompt'a yapıştırma; ana sözleşme+aktif paket+ilgili ID+önceki interface kaydı yeterlidir.

Çözülmemiş belirsizlikler için modelin confidence cümlesi kanıt değildir. Örneğin “MCP connected görünüyor” yerine fixture'da list/call sonucu; “iptal edildi” yerine owned process terminal makbuzu; “resim hazır” yerine açılabilir gerçek dosya. Bir paketi bitirmek için testi skip etme, assertion azaltma, timeout'u gerekçesiz şişirme veya screenshot fark toleransını büyütme.
