# Bağımsız genel code/spec incelemesi — ilk pass

Kök: izole worktree; temel `2b2c8fe4`. Immutable ilk paket
`/tmp/fusion-code-review-first.diff`. RULES.md, A01–D04 spec kabul ölçütleri,
plan ve B/D/Python/React raporları okundu. İlk pass kapsamı B01–B07,
C01–C06 ve screenshot yönlendirmesi, D01–D04. A04–A07 henüz worker tarafından
sabitlenmediği için bu ilk karara dahil değildir. Snapshot sonrasındaki
`output_contract.py` ayrımı ve boş sohbet için `evidence_payload=None`
projeksiyonu mevcut kaynaktan ayrıca okundu.

**İlk kabul verdict: BLOCK — D01 ve C06 için aşağıdaki iki P2 düzeltmesi bekliyor.**
**İlk kod kalitesi verdict: WARNING — iki doğrulanmış davranış kusuru.**

## CR01 — P2: MCP kabul bayraklarını adayın kendisi yazabiliyor

Dosya: `evals/fixtures/production_acceptance.py:22`–23 ve `:63`.
`_MeasuredClient.listed/called` aday `smoke(client)` fonksiyonuna verilen nesne
üzerinde doğrudan yazılabilir. Kabul yalnız bu iki bool'a bakıyor. Bu nedenle
`client.listed=True; client.called=True` yapan aday, `list_tools` veya
`call_tool` çağırmadan geçiyor. Harness'in kendi initialize çağrısı, adayın
istenen listele/çağır davranışını kanıtlamaz.

Çalıştırılmış sentetik kanıt: geçici `smoke_test.py` yalnız bu iki bayrağı
True yapıyor. Gerçek sırsız yerel stdio fixture ile `check_mcp` normal dönüyor:
`accepted_without_candidate_list_or_call=True`. Harici ağ/model veya hesap
kullanılmadı. Bu repro bir bütün test paketi tekrarı değildir.

Düzeltme: kabul ölçümünü adayın değiştirebildiği client alanlarından ayır.
Adaya verilmeyen sahipli gözlem kaydı veya bağımsız sunucu tarafı listele/çağır
kaydı kullan. İki bool'u yazan sahte adayın reddedildiğini ve gerçek
listele/çağır adayının geçtiğini test et. Amaç kötü niyetli Python için genel
sandbox icat etmek değil, sıradan aday çıktısının ölçüt sonucunu doğrudan
atamasını önlemek.

## CR02 — P2: İkinci önizleme çağrısı henüz hazır olmayan URL'yi teslim ediyor

Dosya: `src/fusion_cli/tools/preview_server.py:194` ve `:174`–176.
Süreç sahipliği için `_RUNNING` readiness öncesinde dolduruldu. Fakat
`running(root)` yalnız alive sürece bakıyor. İlk `start` readiness'i
beklerken aynı kökten ikinci `start` doğrudan pending preview döndürüyor;
böylece `start`ın "yanıt verene kadar bekle" sözleşmesi bozuluyor.

Çalıştırılmış sentetik kanıt: subprocess sınırı yalnız `returncode=None`
taşıyan fake ile değiştirildi; readiness bir asyncio.Event üzerinde bekledi.
İlk çağrı beklerken ikinci start normal döndü:
`second_start_returned_before_ready=True`. Hiç gerçek süreç başlatılmadı.
Repro teardown'unda `/var`–`/private/var` resolve farkı yüzünden fake kayıt
atexit'e kaldı ve fake'de pid bulunmadığına dair AttributeError çıktı; bu
teardown uyarısı bulgunun kanıtı değildir. İşletim sistemi sürecine dokunulmadı.

Düzeltme: erken sahiplik kaydını koruyup pending/ready ayrımı ekle; eşzamanlı
çağrılar aynı başlatmanın sonucunu beklesin. Başlatma failure/cancel sonucu da
bekleyen çağrılara doğru yansısın; ikinci çağrı sahte ready dönmesin veya
sahipsiz ikinci süreç açmasın.

## Ek blocker bulunmayan alanlar

- B model metadata çözümü doğru kimliğe ait kayıtları kullanıyor; bilinmeyen
  yedeğe birincilin doğrulanmış yeteneği kopyalanmıyor.
- B araştırma projeksiyonu URL/çağrı metadata'sını ortak bütçeye katıyor;
  kaynak kimlikleri sığmadığında özgün geçmişi koruyan açık fail-closed yol var.
  Canlı sentez doğruluğu ve canlı tarih filtresi kabulünün açık bırakılması doğru.
- B03 kullanıcı ara düzeltmeleri özetin doğruluğuna emanet edilmiyor.
- C01 toparlanan aynı komutun başarısı engelleyici kararda da aynı şekilde
  kullanılıyor. C02 ek izlenen dosya sürümleri fingerprint'in dist/build/.fusion
  körlüğünü gideriyor; son review mutasyonu yeniden ölçülüyor.
- C03 ölçülmeyen browser kriteri ve uyarı payload/kart boyunca korunuyor.
- C04 quoted boşluklu adlar, kök içi absolute adlar ve dış kök reddi mevcut
  dosya sözleşmesi içinde ele alınıyor.
- C05 biçim okuyucuları bütçeli; yeni output baseline ve sıfır mutasyon teslim
  kapısı wiring'i mevcut. Artifact görevlerinde bütün composite'ı atlayan
  önceki Python PR01 düzeltmesi artık uygulanmış; yalnız kod komutu ayrılıyor.
- D görev isimleri gerçek yerel ölçüm kapsamını anlatıyor; büyük fixture
  gerçekten büyük ve bütün baytların korunmasına bağlı. Setup üretimi tek
  executor'a bounded metin sağlıyor.
- D02 yok raporu ölçülmedi olarak taşıyor; geç raporu/paket özeti/görev seti ve
  tekrar model kimliğini kontrol ediyor. `claimsReady=false` ve gerçek canlı
  CI kapısının açık olması korunuyor. Bu bir imzalı güvenilir rapor üretim
  zinciri veya gerçek canlı kabul yapılmış iddiası değildir.
- D03 headless politika sayacı insan onayı diye sunulmuyor; ölçülmeyen insan
  alanları null. D04 gerçek platform kabulleri açık ve dağıtım kapsamı sınırlı.
- Boş soru-cevap raporunda kart üretilmemesi mevcut kanıtı saklamıyor:
  gate/criteria/command/job/tamper/blocking/warning varsa payload korunuyor.

## Doğrulama sınırı

B/D/Python/React raporlarındaki testler tekrar çalıştırılmadı. İnceleme gerçek
kaynak/çağrı yolları, immutable diff ve yukarıdaki iki küçük sentetik repro'ya
dayanır. Gerçek model/harici ağ/kullanıcı sırları/hesaplar/kurulum/OS izinleri
kullanılmadı. Üretim kodu değiştirilmedi; yalnız bu rapor yazıldı.

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 2 | fix required for acceptance |
| LOW | 0 | pass |

Verdict: WARNING — CR01/CR02 düzeltilip scoped yeniden inceleme bekleniyor.
A04–A07 için son snapshot ayrıca incelenecek.

# Scoped yeniden inceleme ve A backend son pass

İkinci paket `/tmp/fusion-code-review-final.diff` ve mevcut kaynak okundu.
Bu pass CR01/CR02 düzeltmeleri ile önceki snapshot dışında kalan A backend
kodunu kapsar. Son switch delta'sı worker tarafından hazır bildirildikten sonra
`request_switch`, `_select`, `_publish_now` ve `BrowserDevices.wait_switch`
mevcut kaynakta tekrar okundu. JavaScript TS01/TS02 kapanışı ayrı TypeScript
inceleyicisine aittir; bu rapor o ayrı async/DOM incelemesinin yerine geçmez.

## CR01 kapandı

`production_acceptance.py::_measured_client` adayın görebildiği nesneden ayrı
`listed/called` closure durumuna sahip. Adaya verilen yerel client `__slots__=()`
kullanıyor; kabul bayrakları nesne alanlarından okunmuyor. Kabul callback'i
harness'te kalıyor. İlk rapordaki doğrudan bool atama yolu artık kabulü
üretemiyor. Mevcut spoof regresyonu ve gerçek list/ping kabulü bu eski kusuru
ayrı ayrı hedefliyor. Controller'ın bildirdiği iki scoped test başarısı
uygulamayla tutarlı; reviewer testleri yeniden çalıştırmadı. Bu tasarım keyfi
kötücül Python için genel bir sandbox iddiası taşımıyor; rapor böyle bir iddia
vermiyor.

## CR02 kapandı

`preview_server.start` artık spawn await'inden önce sahipli bir placeholder ve
`starting` future'ını kaydediyor. Aynı kökün eşzamanlı çağrısı kendi ikinci
başlatmasını açmak veya hazır olmayan URL'yi döndürmek yerine aynı future'a
`shield` altında katılıyor. Readiness geçince ortak sonuç veriliyor;
failure/cancel'de cleanup beklenip ortak future aynı terminal sonuçla kapanıyor.
`_failure_message` artık cleanup bitmeden kaydı düşüren `stop` çağrısını yapmıyor.
Controller'ın ready/failure/cancel üç red→green ve geniş 111 preview testi
kanıtı mevcut akışla tutarlı; paket burada tekrar koşturulmadı.

## A backend kabul ve kalite

Yeni açık P1/P2 bulunmadı:

- A01 açık seçilmiş kopuk cihazda başka tarayıcıya fallback'i kesiyor. Bağlı
  tek cihazın seçim olmadan kullanılabilmesi ayrı korunuyor; `describe` yanlış
  hesabı in-use göstermiyor.
- A02/A03 pending onaylar bounded event feed'den ayrı tutuluyor; status/events
  snapshot'ı kimliğiyle taşıyor. Kapanış ve kabul/ret kimliğe bağlı. Sunucu
  reddini HTTP taşıma başarısından ayıran `ok:false+hata` mevcut.
- Switch sorusu artık unique kimlik ve `veri.tarayici_sec` ile aynı pending
  snapshot'a giriyor. `_switch_lock` eşzamanlı soruları sıralıyor. Select,
  timeout ve cancel terminallerinde finally aynı soru kimliğini kapatıyor.
  `_select` stale `soru_id` için gerçek seçimi değiştirmeden ret dönüyor;
  `wait_switch` sahipli future'ını finally iptal edip temizliyor. Elle açık
  browser seçimi için kimliksiz mevcut API yolu korunuyor.
- A04/A05 Chrome motor oturum scope'u ve built-in kalıcı liste ayrı adlarla
  gösteriliyor. Revoke yalnız istenen scope'u bellekte unutturuyor; built-in
  kalıcı kayıt ilgili yapılandırma adapter'ında kaldırılıyor. Yazma başarısızlığı
  açık ret döndürüyor. Listeleme ve kaldırma mevcut session belleğinin üzerinden;
  yeni ikinci bir izin deposu eklenmiyor. CLI/TUI label ve hint kalıcılığı
  oturumluk diye göstermiyor.
- A07 command lease cihaz/komut kimliğine, insan beklemesi ayrı wait-id'ye bağlı.
  Yanlış cihaz, yanlış bekleme, kapanmış/cancel edilmiş future ve dolmuş ağ/insan
  süresi progress tarafından reddediliyor. İnsan süresinin ayrı 5 dakika,
  bağlantı heartbeat'inin 5 saniye sınırı var; taşıma zaman aşımı bütün komutlar
  için büyütülmemiş. `_await_command` terminalinde pending/lease kaydı temizleniyor.
  `/result` da aynı cihaz sahipliğini kontrol ediyor. Bu backend, geç izinle eski
  komutun yeniden canlandırılmasına onay vermiyor; gerçek eylem öncesindeki
  extension callback wiring'inin doğruluğu ayrı TS review kapsamındadır.

## Güncel karar

**Final genel code/spec kabul verdict: APPROVE — incelenen yerel kod sözleşmeleri
ve CR01/CR02 kapalı; bu kapsamlarda kalan P1/P2 yok.**

**Final genel kod kalitesi verdict: APPROVE.** İlk pass'teki BLOCK/WARNING geçmiş
kanıtıdır; güncel karar bu bölümdedir. A extension JavaScript/TypeScript async
sahipliği için ayrı reviewer'ın nihai kararı ayrıca gereklidir.

Bu onay bütün repo testlerinin, kurulu paketin veya gerçek canlı model/platform
kabulünün yerine geçmez. B01 canlı sentez/B06 sağlayıcı filtre doğruluğu,
D02 güvenilir canlı yayın kapısı, D03 gerçek insan metrikleri ve D04 platform
kabulleri raporlarda açık kaldığı için yapılmış sayılmadı. Masaüstü pencere odağı,
Hesap Makinesi temiz başlangıç ve Playwright kurulum tekrarları bu düzeltmelerle
otomatik kapalı sayılmıyor.

## Final Review Summary

| Severity | Open count | Status |
|----------|------------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | pass — CR01/CR02 closed |
| LOW | 0 | pass |

Verdict: APPROVE — tanımlı genel code/spec kapsamı; ayrı TS ve son bütünleşik
çalıştırma kanıtı ayrıca takip edilir.

# Son scoped B07 / kabul referansı entegrasyon delta incelemesi

Paket: `/tmp/fusion-web-delta-review.diff`; aday `283cc3bd` üzerine yalnız
`tools/web.py`, `tests/test_web_provenance_remediation.py` ve
`tests/test_eval_criteria_sound.py`. Önceki genel onaydan sonraki bu üç dosya
ayrıca incelendi; başka kapsama yayılınmadı.

**Scoped kabul verdict: APPROVE.**
**Scoped kod kalitesi verdict: APPROVE — yeni açık P1/P2 yok.**

- `web_fetch` erişim duvarı bulunduğunda `CAPABILITY_WALL_PREFIX` taşıyan banner'ı
  çıktı başına koyuyor. `loop.py` içindeki `startswith` protokolü böylece tekrar
  erişilemedi kararına ulaşabiliyor; provenance erişim duvarını başarı metninin
  içine gömmüyor. Duvar yokken normal provenance+gövde çıktısı korunuyor.
  Structured kaynak alanları aynı kalıyor; URL/final URL/erişim zamanı ve tarih
  beyanı kaybolmuyor. Yeni regresyon hem gerçek protokol önekini hem structured
  final URL ve fetched_at alanlarını kontrol ediyor.
- `_check_file_reference` artık ham `python` dizgesi değiştirme yerine gerçek
  executor'ın da kullandığı `plan_acceptance` komut planını çalıştırıyor.
  `assert acceptance.command is not None` belirsiz başlatıcıyı sessizce raw shell'e
  düşürmüyor. Aynı `_verification_env` scratch cwd'de repo `evals` paketini ve
  çalışan yorumlayıcıyı bulma, `PYTHONOPTIMIZE=0` ve güvenli Python başlangıcı
  semantiğini koruyor. Referans çözümün beklenen exit-code assertion'ı kaldırılmadı
  veya gevşetilmedi. Bu küçük helper değişikliği kriterleri atlamıyor.
- `/tmp/fusion-web-delta-tests.log` inceleme sırasında okundu:
  **82 passed in 16.99s**. Reviewer testleri tekrar çalıştırmadı. Bu kayıt yalnız
  bu delta'nın scoped kanıtıdır; aday `283cc3bd` üzerinde başlamış dört shard'ın
  son değişmiş kaynak ağacının tamamını ölçtüğü şeklinde bir iddia verilmedi.

Bu scoped delta önceki genel code/spec APPROVE kararını korur. Son web/deadlock
koşuları ve bütünleşik kaynak-sürüm kaydı controller tarafından ayrıca tutulur.

# Son scoped test fixture / metin uyumu incelemesi

Paket: `/tmp/fusion-fixture-review.diff`; yalnız iki test satırı, üretim kodu
farkı yok. Testlerin çevresindeki gerçek dosya üretimi ve negatif kontroller
okundu.

**Scoped kabul verdict: APPROVE.**
**Scoped kod kalitesi verdict: APPROVE — anlamsal test zayıflatması yok.**

- `test_tamper_check.py` yalnız `SAYILMAZ` büyük harf biçimine bağlı kontrolü
  `"sayılmaz" in metin.casefold()` yapıyor. Aynı testte temiz raporun doğrulanmış,
  şüpheli raporun doğrulanmamış olması, açık `ŞÜPHELİ TEST DEĞİŞİKLİĞİ` uyarısı
  ve `✓ Doğrulandı` yokluğu aynen korunuyor. Davranış sözleşmesi daralmıyor;
  yalnız aynı Türkçe anlamın harf biçimi bağımlılığı kaldırılıyor.
- `test_creative_verification_contract.py::_baglam`, fixture'ın hemen önce
  tmp dizininde gerçekten ürettiği/yazdığı `out/video.mp4` yolunu touched
  kümesine ekliyor. Bu fixture gerçek üretimin sahipliğini doğru ifade ediyor;
  format, çözünürlük, süre, kesilmiş video ve video olmayan dosya negatif
  kontrolleri atlanmıyor. Tüm dosyaları genel olarak sahipli sayan bir bypass
  veya üretim freshness kuralı gevşetmesi eklenmiyor.

Controller'ın bu iki satır sonrası **82 passed in 44.44s** ve temiz Ruff kanıtı
uygulamayla tutarlı; reviewer testleri yeniden koşturmadı. Ayrı Rich/COLUMNS
ortam bulgusu bu iki dosyalık delta kapsamında değiştirilmedi veya bu onayla
ürün düzeltmesi sayılmadı. Önceki genel code/spec APPROVE kararı korunur.

# Son scoped test sözleşmesi / ağsız fixture bütçesi incelemesi

Paket: `/tmp/fusion-final-test-policy-review.diff`; yalnız beş test dosyası.
Üretim kaynakları bu deltada değişmiyor. Yeni fixture'ın kullanıldığı iki testin
çevresindeki gerçek politika/SSRF/Chrome batch denetimleri, manual compact
fikstürü ve emulation prompt bütçe testleri okundu.

**Scoped kabul verdict: APPROVE.**
**Scoped kod kalitesi verdict: APPROVE — anlamsal test zayıflatması yok.**

- Manual compact artık ara kullanıcı mesajının kaybolmasını beklemiyor.
  Kök mesajlar ve özet/odak kontrolleri korunuyor; `harness_note` summary olduğu
  ve kalan gerçek `Message("user", "testleri ekle")` mesajının birebir taşındığı
  açıkça ölçülüyor. Bu değişiklik B03'ün yeni güvenlik/koruma sözleşmesini test
  ediyor; yalnız mesaj sayısı beklentisini gevşeten bir yeşile boyama değil.
- `public_example_dns` autouse değildir ve yalnız iki ilgili testte isteniyor.
  Harici DNS sınırı sentetik literal genel IPv4 ile karşılanıyor; beklenmeyen
  host assertion ile düşüyor. Politika kapısı veya `is_public_ip` denetimi
  mocklanmıyor. Managed dış gezinme reddi, Chrome batch sırasında parola alanını
  yeniden görme ve gerçek `type` eyleminin çalışmaması assertion'ları aynı.
  Bu testlerin amacı canlı DNS doğruluğu değil ilgili politika/batch kararı;
  yeni fixture onları ağ kararsızlığından ayırıyor.
- Full emulation test tavanı `14600`→`14704` bilinçli özellik maliyeti kararı
  olarak belgelenmiş. Controller'ın bağımsız baseline/yeni ölçümü
  `14578`→`14682`, yeni üç tarih filtresi şemasının +104 karakter maliyetiyle
  örtüşüyor; aynı 22 karakter pay korunuyor. Kompakt tavan 10000 değişmiyor.
  Gerçek production renderer, property description'ları atma, tüm araçların
  görünürlüğü ve payload/araç sözleşmesi assertion'ları korunuyor. Bu küçük ve
  açıklanmış şema bütçesi artışı sessiz sınırsız bound gevşetmesi değil.

İnceleme sırasında `/tmp/fusion-final-fixture-regressions.log` okundu:
**113 passed in 38.44s**. Reviewer testleri tekrar koşturmadı. Adayın eski dört
shard'ındaki baseline ortam/metadata başarısızlıkları burada ürün düzeltmesi veya
son üretim kaynağının tümünde tam yeşil sonuç sayılmıyor; controller bunları ayrı
kanıt kaydında tutuyor. Önceki genel code/spec APPROVE kararı korunur.
