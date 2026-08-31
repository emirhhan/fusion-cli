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
