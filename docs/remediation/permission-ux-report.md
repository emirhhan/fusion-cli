# A04–A07 izin deneyimi ve A02/A07 review düzeltmeleri

Durum: uygulama ve hedefli doğrulamalar tamam; bağımsız final code/TypeScript incelemesi controller tarafından yürütülüyor. Commit yapılmadı. Gerçek Chrome hesabı, Chrome/OS izinleri, kurulu uygulama ve main değiştirilmedi; sentetik Chrome/HTTP sınırları kullanıldı.

## Madde bazında sonuç

| Madde | Doğrulanan kök neden | Uygulama | Durum / kabul sınırı |
|---|---|---|---|
| A04 | Chrome belleği yalnız oturumluk, built-in Browser kalıcı; benzer Always allow etiketleri ve panelde kaybolan açıklama kapsamı belirsizleştiriyor. | Etiketler açık eylem/oturum/kalıcı Türkçe kapsamıyla değişti. TUI ve CLI built-in kalıcılığı doğru gösteriyor. Panel onay seçenekleri aciklama alanını koruyor. Motor Chrome oturum + built-in kalıcı izinleri listelenip aynı yerden ayrı geri alınıyor. | Ağsız kabul geçti. Gerçek restart/platform UI kabulü yapılmadı. Chrome izni kalıcı hale getirilmedi; kapsamı açıklaştırıldı. |
| A05 | FIXED_ORIGINS geniş host grantlerini gizliyor; renderer all_urls'ı URL diye açamıyor; motor izinleri ayrı yüzeyde kalıyor. | Yalnız zorunlu localhost köprüsü listeden ayrılıyor. Tüm siteler/HTTP/HTTPS wildcardları görünür ve geri alınabilir. /settings izinler/izin_sil dar API'si Chrome oturum ve built-in kalıcı izinlerini kapsamıyla listeler, yalnız seçili izni geri alır. | Sentetik DOM ve AppSession kabulü geçti. Gerçek kullanıcı grantleri değiştirilmedi. |
| A06 | Storage bağlantı rozeti ve bağımsız hata alanı çelişiyor; successful events eski hatayı temizlemiyor. Eylem guardı da bağlantı hatasını task hatası diye yeniden etiketleyebiliyor. | Rozet, bağlantı hatası ve son kontrol saati gerçek taşıma sonucuna bağlandı. 401/403 eşleştirme gerektirir; ağ kopuşu offline olur; başarılı reconnect yalnız bağlantı hatasını temizler. Bağımsız onay retleri korunur. Guard connectionState bilgisini korur. | Gerçek panel denetleyicisi VM testleri geçti; canlı Chrome restart koşusu yapılmadı. |
| A07 | 25sn insan kartı beklemesi 30sn taşıma sınırına sıkıştırılmış; süre sonu açık ret gibi dönüyor ve kartın terminal sahibi yok. | İnsan bekleme ayrı command lease ile taşınır: aynı commandId/deviceId/waitId, 5dk insan üst sınırı, 5sn heartbeat ve progress için 4sn taşıma sınırı. Normal komut ağ sınırı 30sn kaldı. Kimlikli ayrı storage kartları açık denied/timeout/cancelled/disconnected sonuçlarını ayırır; eski yanıt/cleanup başka kartı silemez. Son izin verilmiş olsa dahi permission_done tekrar sunucu sahipliğini onaylamadan komut devam etmez. | 35sn sentetik gecikmiş izin aynı komutu sürdürdü; ret/timeout/iptal/bağlantı kaybı ayrı; iptal edilmiş komut geç grant ile sekme açmadı. Gerçek Chrome throttling/insan gecikmesi/platform kabulü yapılmadı. |

## Bağımsız incelemede giderilen ek kabul kusurları

- TS P1: `navigate → tab_open` recursive execute progress callbackini kaybediyor ve `checkedTab` izin iptalini fallback'e çeviriyordu. Gerçek core regresyonunda önce `Missing expected rejection`, sonra iki senaryo yeşil: callback taşınıyor, fallback yalnız `TabBindingError` (gerçek bağlanmamış/kapanmış sekme) için açılıyor; cancelled/denied/timeout propagate ediyor. İptal sırasında `opened=0` ölçülüyor.
- TS P2 / A02: `tarayici_sec` olayı pending snapshot'a girmediği için events içindeki boş `sorular` kartı siliyordu. Switch artık benzersiz id/veri ile snapshot'ta; aynı id select/timeout/cancel terminallerinde kapanıyor. `/select` stale soru_id'yi gerçek hedefi değiştirmeden reddediyor. `BrowserDevices.wait_switch` sahibi Future'ı finally temizliyor. Üç backend terminal senaryosu önce 3 failed, sonra 3 passed; Node gerçek listen yeni panel recovery ve event/snapshot uzlaşmasını doğruluyor.

## Red/green kanıtları

- `tests/test_remediation_permission_settings.py`: ilk koşu `KeyError: izinler`; helper + dar endpoint entegrasyonu sonrası yeşil.
- `tests/e2e/chrome_permission_view_unit.mjs`: all_urls renderer ilk koşu `TypeError: Invalid URL`; geniş izin etiketi/kaldırma ve onay açıklaması düzeltmesi sonrası yeşil.
- `tests/test_chrome_site_izni.py -k explain_session`: Chrome etiketi oturum kapsamını taşımadığı için kırmızı; açık etiket ve TUI/CLI scope düzeltmesinden sonra yeşil.
- `tests/test_remediation_permission_wait.py`: ilk üç yeni senaryo `_progress` eksikliğiyle kırmızı; yeni lease/progress sonrası yeşil. Ek geç progress, heartbeat kaybı ve gerçek localhost HTTP progress/result device sahipliği senaryoları yeşil.
- `tests/e2e/chrome_permission_wait_unit.mjs`: yeni bekleme protokolü öncesinde modül yok; sonrasında 35sn izin, ret, timeout, geç ret, iptal edilmiş komuta geç grant ve iki kart cleanup sahipliği yeşil.
- `tests/e2e/chrome_permission_transport_unit.mjs`: gerçek core/background/offscreen modüllerini çalıştırır; yalnız Chrome API/HTTP dış sınırı fake. Başarılı izin gerçek seçili sekmeyi değiştirir; iptal edilmiş komutta izin sonradan verilse de seçili sekme değişmez.
- `tests/e2e/chrome_panel_connection_unit.mjs`: önce offline rozeti güncellenmediği için kırmızı; sonraki guard repro'da `Failed to fetch` kaldığı için yeniden kırmızı; iki kök yol düzeldikten sonra yeşil. Bağımsız task hatasının korunması da ölçülüyor.
- App ilk tam koşusunda 5 ExtensionPanel testi kırmızıydı: eski tek-key izin fixtureları ve timeout=ret beklentileri yeni protokole taşındı. Gerçek pairing iyileşme bug'ı ayrıca giderildi. Son 32 test temiz. Bir ara test teardown'undan sonra devam eden remove callbackinin unhandled rejection'ı görüldü; fixture gerçek getAll/remove durumunu taşıyıp UI son durumunu bekleyecek biçimde düzeltildi, son koşuda yok.

## Son tam hedefli komutlar

Python/Node (119 passed, 10.04s):

```sh
PYTHONPATH="$PWD/src" PATH="/opt/homebrew/opt/node@22/bin:$PATH" /Users/motogate/Desktop/all/01-Projeler/fusion-cli/.venv/bin/python -m pytest -o addopts='' -q tests/test_remediation_permission_js.py tests/test_remediation_permission_settings.py tests/test_remediation_permission_wait.py tests/test_remediation_switch_snapshot.py tests/test_chrome_site_izni.py tests/test_chrome_bridge.py tests/test_chrome_coklu_tarayici.py tests/test_chrome_ayarlari.py tests/test_chrome_core_js.py tests/test_chrome_eklenti_dayaniklilik.py tests/test_remediation_browser_ownership.py tests/test_prompter.py tests/test_chrome_cli.py
```

App (32 passed, unhandled error yok), `app/` içinde:

```sh
PATH="/opt/homebrew/opt/node@22/bin:$PATH" ./node_modules/.bin/vitest run --environment jsdom src/chrome/ExtensionPanel.test.ts
```

Scoped Ruff check/format temiz; `git diff --check` temiz. Mypy:

```sh
PYTHONPATH="$PWD/src" MYPYPATH="$PWD/src" /Users/motogate/Desktop/all/01-Projeler/fusion-cli/.venv/bin/python -m mypy --follow-imports=silent src/fusion_cli/appserver/site_permissions.py src/fusion_cli/appserver/chrome_command_lease.py src/fusion_cli/appserver/chrome_bridge.py src/fusion_cli/appserver/chrome_devices.py src/fusion_cli/appserver/session.py src/fusion_cli/ui/chrome_site_labels.py src/fusion_cli/ui/chrome_messages.py src/fusion_cli/cli/prompter.py
```

Sonuç: `Success: no issues found in 8 source files`.

Kalıcı loglar: `permission-targeted-tests.log`, `permission-app-tests.log`. Final make check/full app/bağımsız review controller sorumluluğunda; yapılmış sayılmadı.

## Dosya ve kurulum notu

Yeni üretim modülleri: `chrome-extension/permissionWait.js`, `src/fusion_cli/appserver/chrome_command_lease.py`, `src/fusion_cli/appserver/site_permissions.py`. Mevcut core/background/offscreen/panel/view, chrome bridge/devices/session, UI scope metinleri ve CLI prompter entegre edildi. Controller'ın A01–A03 değişiklikleri korundu; A02 switch lifecycle review düzeltmesi bunlara eklendi.

Yeni importlar ve background protokolü için eklentinin yeniden yüklenmesi ve aynı protokolde backend gerekir. Manifest version bump/kurulum/paketleme controller-parent kararında; burada bunlar yapılmadı. Gerçek hesap/OS izinleri veya kullanıcı grantleri değişmedi. Kontrollü canlı karşılaştırma ve gerçek platform kabulü açık kaldı.
