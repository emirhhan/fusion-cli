# 2026-09-02 Task 6 sonrası Python suite düzeltme raporu

HEAD başlangıcı: `01fd16c` (`fusion-runtime-hardening-20260827-022831`)

## Önce / sonra

- Önceki Task 6 kabul raporu: **2724 collected / 6 failed**.
- Aynı HEAD'de taze `pytest -q --maxfail=6`: ilk iki workspace testi, observability
  testi ve CrossOver/Mono Windows derleme kapıları kırıldı; devamında host diski
  dolduğu için iki ek CrossOver fixture kurulumu `OSError` verdi.
- Düzeltme sonrası odaklı ilgili suite: **95 test, 91 passed / 4 skipped / 0 failed**.
- Düzeltme sonrası tam suite yeniden başlatıldı ancak host filesystem %100 dolduğu için
  test 7% civarında `No space left on device` ile durdu; bu koşuda yeni tam-suite
  toplamı üretilemedi.

## Sınıflandırma ve düzeltmeler

1. `test_proje_listesi_klasorleri_once_ve_sayfali_dondurur` ve
   `test_degisiklikler_agentin_git_ve_yeni_dosya_degisimlerini_gosterir`: test
   izolasyonu problemi. Ortak autouse fixture, Chroma belleğini workspace kökünün
   altına koyuyordu; bu nedenle `fusion-memory` gerçek proje girdisi ve Git değişikliği
   gibi görünüyordu. `FUSION_MEMORY_DIR` artık her test kökünün kardeşindeki benzersiz
   geçici dizine işaret ediyor. Ürün sözleşmesi gevşetilmedi.
2. `test_ic_ice_dataclass_serilestirilir`: **gerçek ürün regresyonu**. JSONL satırı
   bütünüyle redakte edilirken `prompt_tokens` gibi alan adları sır ataması sanılıp
   siliniyordu. Redaksiyon artık dataclass/list/map içindeki string değerlerde,
   JSON kodlamasından önce uygulanıyor; JSON anahtarları korunuyor.
3. Windows `silence`, `low-confidence`, `too-short` parametreleri: host-only.
   macOS CrossOver/Mono derleyicisi Wine prefix kurulumunda timeout/disk tüketimi
   yaptığı için testler yalnız native Windows + `csc` ile otomatik çalışıyor; CrossOver
   ayrıca `FUSION_RUN_CROSSOVER_TESTS=1` ile açıkça opt-in ve capability check reason
   ile skip ediliyor. Windows adapter sözleşmesi ve fake-compiler testleri çalışmaya
   devam ediyor.
4. `test_idle_kipte_yazi_normal_akar`: üretim regresyonu bulunmadı; tek başına ve
   odaklı suite içinde geçti. Önceki tam koşudaki `prompt_toolkit` select fd hatası
   harness/host baskısı olarak sınıflandırıldı.

## Doğrulama

- İlgili Python suite: **91 passed / 4 skipped**.
- `ruff check src tests evals prompt_opt desktop_build`: **PASS**.
- Değişen dosyalar için Ruff format/check: **PASS**.
- `mypy`: **PASS**, 256 source files.
- `npm run build`: **PASS**; mevcut chunk-size warning sürüyor.
- Tam Ruff format check: mevcut, bu değişiklikle ilgisiz 10 dosyada önceden var olan
  format farkları bildiriliyor.
- DMG/reinstall/rebuild yapılmadı.

Kalan blocker: tam Python suite için host filesystem alanı temizlenmeli; CrossOver
Windows çalışma kapısı ise native Windows veya açıkça opt-in edilmiş sağlıklı bir
CrossOver/Mono ortamı gerektiriyor.

## 2026-09-02 full-suite isolation follow-up

- Before the final isolation fix: **2724 collected / 2722 passed / 0 skipped / 2 failed**.
  The failures were `test_macos_listen_sigterm_runs_cleanup_and_exits_cleanly` and
  `test_idle_kipte_yazi_normal_akar`; both reached `select()` with a descriptor
  above macOS `FD_SETSIZE`.
- Root cause: `memory.store._clients` retained Chroma `PersistentClient` instances;
  `reset_clients()` only cleared the dictionary and never called `Client.close()`.
  `tests/test_memory_store.py` consequently leaked roughly 10 descriptors per test,
  eventually causing the runtime helper and prompt_toolkit failures by collection order.
- Fix: `reset_clients()` now closes every cached client before releasing it, and the
  shared pytest autouse fixture resets/collects the cache after every test.
- Focused post-fix verification: **94 collected / 90 passed / 4 skipped / 0 failed**
  across appserver history, memory-store, runtime-bundle, and TUI tests.
- A post-fix full-suite rerun was intentionally not performed after the requested
  stop; the saved pre-fix telemetry run remains the source for the 2-failure count.
