# Task 4 Raporu — Uygulama kapanışında speech ve TTS temizliği

## Uygulama

- `AppSession.close()` kapanış sırası çalışan turu iptal et → `voice_stop()` → yönetilen süreçleri kapat → bekleyen soruları iptal et olarak merkezileştirildi.
- Tauri kapanışı `Talk` ve `Application` kapsamlarına ayrıldı. Talk yalnız speech yardımcısını; Application speech, session ve terminalleri bu sırayla temizliyor.
- Onaylanmış ana pencere kapanışı, `RunEvent::ExitRequested`, final `RunEvent::Exit`, Talk kırmızı düğmesi ve beklenmeyen Talk `Destroyed` olayı ilgili ortak temizleme yoluna bağlandı.
- `SpeechManager::stop()` mevcut tek-sahipli, `take()` tabanlı idempotent davranışını koruyor.

## RED kanıtı

- `.venv/bin/pytest -q tests/test_appserver_session.py::test_kapanis_tts_childini_diger_surecleri_beklemeden_durdurur`
  - FAIL: gerçek TTS helper PID `56894`, yönetilen süreç kapanışı bloklanırken iki saniye içinde kapanmadı.
- Brief'teki `cargo test speech shutdown -- --nocapture`
  - Cargo tek filtre kabul ettiği için `unexpected argument 'shutdown'` ile komut-seviyesi hata verdi.
- Eşdeğer filtreler ayrı çalıştırıldı:
  - `cargo test speech -- --nocapture`
  - `cargo test shutdown -- --nocapture`
  - RED: eksik `SpeechCleanupScope`, `cleanup_for_scope`, `ShutdownScope` ve `shutdown_plan` sözleşmeleri nedeniyle derleme başarısız oldu.

## GREEN ve kalite kanıtı

- Focused gerçek-PID TTS testi: PASS.
- `tests/test_appserver_session.py`: 27 passed.
- `tests/test_appserver_session.py tests/test_voice.py`: 59 passed.
- `cargo test speech -- --nocapture`: 11 passed, 1 ignored.
- `cargo test shutdown -- --nocapture`: 3 passed.
- `cargo fmt --check`: PASS.
- `cargo clippy --all-targets -- -D warnings`: PASS.
- `cargo test`: 69 passed, 2 ignored; doc tests PASS.
- Ruff, değişen Python dosyaları: PASS.
- `git diff --check`: PASS.

## Dosyalar

- `app/src-tauri/src/speech.rs`
- `app/src-tauri/src/lib.rs`
- `src/fusion_cli/appserver/session.py`
- `tests/test_appserver_session.py`
- `.superpowers/sdd/2026-08-31-chatgpt-benzeri-talk/task-4-report.md`

## Öz-inceleme

- Talk-only plan session ve terminalleri kapatmıyor; Application plan tüm sahipli kaynakları kapsıyor.
- Tam kapanış sırası speech → sessions → terminals; Python TTS kapanışı başka managed process bekleyişinin önünde.
- Stop yolları birden çok kez çağrılmaya uygun: Talk `CloseRequested` ardından `Destroyed`, ayrıca `ExitRequested` ardından `Exit` güvenli.
- Testler kaynak metni değil gerçek child PID bitişini ve kullanıcıya görünür kapsam sözleşmesini doğruluyor.
- İlgisiz untracked dosyalara dokunulmadı.

## Endişeler

- Brief'teki birleşik Cargo filtre komutu Cargo CLI tarafından desteklenmiyor; iki ayrı komutla aynı kapsam doğrulandı.
- Paketli uygulamanın GUI kabul testi bu görevde otomatikleştirilmedi; Rust event yolları birim/lifecycle testleri ve tam crate testleriyle doğrulandı.

## Fix round 1 — davranışsal lifecycle kapsamı

### Uygulama

- Plan boolean testlerinin yerine production tarafından kullanılan tek `cleanup_route → cleanup_scope` coordinator zinciri eklendi.
- Coordinator `CleanupOwners` arayüzü üzerinden speech, session/appserver ve terminal sahiplerini gerekli sırada temizliyor. Production adaptörü gerçek `SpeechManager`, `SessionManager` ve `TerminalManager` durumlarını kullanıyor.
- Onaylanmış ana kapanış, `ExitRequested` ve `Exit` tam uygulama kapsamına; Talk kırmızı kapanışı ve beklenmeyen `Destroyed` Talk kapsamına eşlenip aynı coordinator girişine bağlandı.
- Talk ve tam uygulama cleanup’ı iki kez çağrılarak idempotence gerçek child sahipleriyle doğrulandı.
- Cleanup süresi worker/channel üzerinden `recv_timeout(2s)` ile ölçülüyor. Timeout dalı bütün child sahiplerini temizliyor ve worker’ı join etmeden testi bırakmıyor.

### RED kanıtı

- `cargo test shutdown -- --nocapture`
  - RED: `CleanupOwners`, `cleanup_scope`, `ShutdownRoute` ve `shutdown_scope_for_route` production sözleşmeleri yoktu; test derlemesi beklenen sembol eksikleriyle başarısız oldu.

### GREEN kanıtı

- `cargo test cleanup -- --nocapture`: 4 passed.
- `cargo test shutdown -- --nocapture`: 2 passed.
- Gerçek TTS PID focused Python testi: 1 passed.
- `tests/test_appserver_session.py tests/test_voice.py`: 59 passed.
- Ruff: PASS.
- `cargo fmt --check`: PASS.
- `cargo clippy --all-targets -- -D warnings`: PASS.
- `cargo test`: 69 passed, 2 ignored; doc tests PASS.

### Davranış kanıtı ve öz-inceleme

- Talk coordinator çağrısı gerçek speech child’ını bitirirken gerçek session ve terminal child’larını çalışır bırakıyor; test sonunda kalan child’lar açıkça temizleniyor.
- Application coordinator çağrısı gerçek speech, session ve terminal child’larını `speech → session → terminal` sırasında bitiriyor.
- Rust `SessionManager::stop()` önce appserver stdin sahipliğini bırakıyor; Python server `finally` bloğu kanonik `AppSession.close()` yolunu çalıştırıyor. Ayrı gerçek-PID Python testi bu yolun managed-process bekleyişinden önce TTS’yi bitirdiğini doğruluyor.
- Yanlış route, eksik owner çağrısı, yanlış sıra, Talk kapsamının session/terminali kapatması ve tekrar çağrıda blok/panic mutasyonlarının her biri yeni testlerden en az birini düşürüyor.

### Endişeler

- Tauri event nesneleri birim testte doğrudan kurulmadığı için event davranışı production'ın kullandığı route-to-scope saf fonksiyonu üzerinden doğrulandı.
- Paketli GUI kabul testi hâlâ bu otomatik fix-round kapsamının dışında.

## Fix round 2 — gerçek manager sahipliği ve bounded harness

### Uygulama

- Lifecycle testleri artık `cleanup_scope` ve ayrı route mapping testleri kullanmıyor; doğrudan production `cleanup_route` girişini çağırıyor.
- `AppCleanupOwners`, Tauri handle yerine concrete `SpeechManager`, `SessionManager` ve `TerminalManager` referanslarını tutuyor. `cleanup_route_from_app` yalnız Tauri state çözümleyen ince production adaptörü olarak kaldı.
- Speech test factory’si gerçek `SpeechManager::start` sahipliğini ve deterministic helper child’ı kullanıyor; helper pipe’ları drain edilerek child’ın test harness çıktısında erken kapanması önlendi.
- Session test factory’si gerçek `ManagedSession` kaydına stdin bekleyen deterministic child yerleştiriyor; kapanış normal `SessionManager::stop_all` → stdin bırakma → bounded `stop_child` yolunu çalıştırıyor.
- Terminal testi gerçek `TerminalManager::open` ile gerçek PTY shell child açıyor ve normal `close_all` sahiplik yolunu çalıştırıyor.
- Test fixture Drop’u speech/session/terminal manager’larını her sonuçta temizliyor.
- Production route cleanup çağrıları testte worker/channel üzerinden iki saniye deadline ile gözleniyor. Timeout harness’ı timeout’ta worker’a join yapmadan dönüyor.

### RED kanıtı

- İlk `cargo test cleanup -- --nocapture`:
  - RED derleme: concrete manager test factory’leri, `AppCleanupOwners::from_managers`, `CleanupStep` ve manager yaşam sorguları henüz yoktu.
- Factory’ler eklendikten sonraki focused koşu:
  - RED davranış: gerçek SpeechManager helper pipe’ı erken kapandığı için cleanup öncesi `speech.is_running()` false oldu. Test gevşetilmedi; helper stdout/stderr güvenli drain edilerek gerçek child yaşamı düzeltildi.

### GREEN ve kalite kanıtı

- `cargo test cleanup -- --nocapture`: 3 passed.
- `cargo test shutdown -- --nocapture`: 3 passed.
- `tests/test_appserver_session.py tests/test_voice.py`: 59 passed.
- Ruff: PASS.
- `cargo fmt --check`: PASS.
- `cargo clippy --all-targets -- -D warnings`: PASS.
- `cargo test`: 68 passed, 3 ignored; doc tests PASS.

### Davranış kanıtı ve öz-inceleme

- `TalkClose` ve `TalkDestroyed`, production `cleanup_route` üzerinden gerçek SpeechManager child’ını bitiriyor; gerçek SessionManager ve TerminalManager child’ları çalışmaya devam ediyor.
- `ConfirmedMainClose`, `ExitRequested` ve `Exit`, aynı production girişinden speech → session → terminal sırasında bütün gerçek manager child’larını bitiriyor.
- Her route aynı fixture’da iki kez çağrılıyor; tekrar çağrılar gerçek manager stop/close kodunda idempotent kalıyor.
- `shutdown_scope_for_route` çağrısı bypass edilirse route testleri yanlış gerçek child yaşam durumunda başarısız oluyor; mapping ve davranış artık ayrı testler değil.
- Deterministic blocking cleanup testi 50 ms timeout’tan bir saniyeden kısa sürede dönüyor, join yapmıyor; kontrollü release sonrası detached worker’ın bir saniye içinde çıktığını ayrıca doğruluyor.

### Endişeler

- Tauri event değerleri framework tarafından doğrudan construct edilemediği için event callback’in seçtiği enum route production kodunda, route’un gerçek kaynak etkisi ise concrete manager lifecycle testinde doğrulanıyor.
- Paketli GUI kabul testi bu fix round’da çalıştırılmadı.
