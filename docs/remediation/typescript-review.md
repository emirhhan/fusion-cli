# TypeScript / JavaScript bağımsız incelemesi

Kapsam: baseline `2b2c8fe4` üzerine `/tmp/fusion-typescript-review.diff`, A01–A07 tarayıcı/izin protokolü ve C03 teslim kartı. Yerel inceleme; PR/CI merge readiness bilgisi yok ve doğrulanmadı. React özel incelemesi ayrıca `react-review.md` içinde.

## Kontroller

- `PATH=/opt/homebrew/opt/node@22/bin:$PATH node_modules/.bin/tsc --noEmit -p tsconfig.json` (app): exit 0.
- `PATH=/opt/homebrew/opt/node@22/bin:$PATH npm run lint:hooks` (app canonical ESLint): exit 0.
- Var olan test paketleri tekrar çalıştırılmadı; iki küçük ağsız gerçek denetleyici/modül repro kullanıldı. Chrome/HTTP dış sınırları fakedir; gerçek hesap/izin/ağ/model/kurulum işlemi yok.

## Bulgular

### TS01 — P1: navigate fallback komutun izin sahipliğini düşürüyor

`chrome-extension/core.js:1549`: `checkedTab(permissionContext)` hata verince `execute({...command,islem:"tab_open"})` ikinci options parametresini taşımıyor. İlk navigate sırasında seçili sekme yoksa bu olağan yoldur. `onPermissionProgress` kaybolduğu için beş dakikalık insan beklemesi backend komut canlılığını ölçmüyor. Backend komut timeout/cancel sonrasında gelen host grant eski komutu açabilir. Üstelik catch, PermissionWaitError cancelled/denied/timeout sonuçlarını da fallback'e çevirebilir.

Gerçek `execute` ile ağsız repro: storage'da seçili sekme yok, tabs.query boş, ilk permissions.contains false; kart storage'a yazılınca grant true; verilmiş `onPermissionProgress` callback aktif:false döndürecekti. Sonuç: `opened=1`, `progressCalls=0`, başarılı opened sonucu. Beklenen: sahipli progress kontrolü çalışmalı ve artık etkin olmayan komut yan etki yapmamalı. Düzeltme: options taşınmalı; fallback yalnız gerçek bağsız/kapanmış sekme durumunda olmalı; terminal permission hataları aynen yayılmalı.

### TS02 — P2: pending snapshot tarayıcı seçim kartını aynı event batch'inde siliyor

`chrome-extension/panel.js` listen akışında `sorular.at(-1) ?? null` reconcile'ı, `applyItem(tarayici_sec)` ile eklenmiş BROWSER_CHOICE'ı hemen siliyor. `chrome_bridge._publish_now` yalnız `soru` kaydını `_questions` snapshot'ına ekliyor; request_switch tarafından yayılan tarayici_sec için `sorular=[]` kalıyor.

Gerçek `listen` VM repro: seq0, tek `{seq:1,tur:"tarayici_sec"}` olayı ve `sorular:[]` yanıtı sonrasında `thread.soru=null`. Beklenen: switch_browser kartı görünür ve yeni panelde geri kazanılır; seçim veya wait timeout sonrası kapanır. Pending switch de sahipli snapshot/lifecycle kapsamına alınmalı veya reconcile bu ayrı prompt'u doğru şekilde korumalı.

## İlk karar

- Kabul: **BLOCK** (TS01 ve TS02 açık).
- TypeScript / JavaScript kalite: **BLOCK** (yan etki güvenliği ve async durum kaybı).
- A06 son delta: request hata nesnesindeki connectionState sınıflandırmasının guard/reportError tarafından korunması kod üzerinden incelendi; bağımsız izin/task hata metni başarılı reconnect ile silinmiyor.
- C03 deliveryEvidence additive warnings kontrolü ve artifact başlık yolu incelendi; ek bulgu yok. Yeni alanlar eski kayıtlarla uyumlu, bozuk warning array fail-closed dönüyor.

Düzeltme sonrası yalnız TS01–TS02 scoped yeniden inceleme bekliyor.


## Scoped yeniden inceleme — TS01 / TS02

İncelenen son üretim kaynakları: `core.js` TabBindingError ve recursive options yolu, `panel.js` kimlikli seçim kartı, `chrome_bridge.py` request_switch/_select/snapshot kapanışı, `chrome_devices.py` wait_switch cleanup. Mevcut rapor `permission-ux-report.md` ve kalıcı `permission-targeted-tests.log` / `permission-app-tests.log` test kanıtları esas alındı; kapsam başka maddelere genişletilmedi.

- **TS01 kapalı.** navigate fallback artık yalnız `TabBindingError` için açılıyor. Terminal PermissionWaitError cancelled/denied/timeout sonuçları fallback'e dönüşmüyor. Recursive `execute` çağrısında `onPermissionProgress` korunuyor; aynı command.id yeni izin beklemesine taşınıyor. Gerçek core regresyonu `chrome_permission_navigation_unit.mjs` iki ayrı yolu ölçüyor: bağsız başlangıçta callback düşmesi ve checkedTab içinde iptalin fallback'e dönmesi. Her ikisinde artık rejected/cancelled, `opened=0`, progress çağrısı mevcut. Worker ilk kırmızıyı `Missing expected rejection`, son scoped toplamı 119 passed / 10.04s ve app 32 passed olarak kaydetti.
- **TS02 kapalı.** tarayıcı seçimi benzersiz soru kimliği ve `veri.tarayici_sec` ile pending snapshot'a dahil. Panel event ve status snapshot'ından aynı kimlikli kartı okuyabiliyor; cevap `/select` isteğine soru_id ekliyor. Sunucu stale soru_id'yi seçimden önce reddediyor. request_switch finally seçim/timeout/cancel sonuçlarının tümünde soru_kapandi yayıyor; owned wait future temizleniyor. Yeni Python regresyonu üç terminal sonucu ve stale seçimin hedefi değiştirmemesini; gerçek panel VM regresyonu event+snapshot ile yeni panel recover yolunu ölçüyor.
- permissionWait.js Tauri kaynak haritalarına eklendiği kontrol edildi; paket içerik test kanıtı worker raporunda ilk kırmızı sonrası iki yeşil olarak kayıtlı. Bu dosya eklenmesi normal eklenti reload/paketleme gerektirir; burada kurulum yapılmadı.

### Son scoped karar

- Kabul: **APPROVE**.
- TypeScript / JavaScript kalite: **APPROVE**.
- TS01–TS02 kapsamında kalan P1/P2 yok.
- Gerçek Chrome/account/OS izin kabulü veya canlı model kalitesi bu incelemeyle ölçülmüş sayılmaz. PR/CI merge readiness bu yerel incelemede mevcut değildi.
