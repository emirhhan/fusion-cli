# Fusion macOS Oturum ve Geçmiş Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fusion macOS uygulamasına gerçek çoklu oturum yaşam döngüsü, proje-bağlı konuşma listesi ve yalnız kurulu araçlar için sayfalı Claude/Codex/Hermes sürdürme akışı eklemek.

**Architecture:** Python çekirdeği geçmiş keşfi, listeleme, önizleme ve devralma iş kurallarının tek sahibidir. Her etkin konuşma ayrı `fusion app` sürecinde çalışır; Rust `SessionManager` süreç kimliği/olay kanalı/kapanışını yönetir. React tipli bir oturum deposuyla yalnız görünüm ve kullanıcı etkileşimini yönetir. Dış kaynak hiçbir zaman değiştirilmez; Fusion kendi oturumuna deterministik bir künye aktarır.

**Tech Stack:** Python 3.11+, pytest, Tauri/Rust/Tokio, React 19, TypeScript, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-08-29-tam-macos-uygulamasi-design.md` §7, `docs/superpowers/specs/2026-08-29-uygulama-protokolu-design.md`

## Global constraints

- Yalnız `available_sources(home)` içinde bulunan kaynaklar görünür.
- Liste ve önizleme sayfalıdır; başlangıçta tüm arşiv belleğe alınmaz.
- Dış kaynak salt okunurdur. Devralma yalnız `ReplState.pending_digest` kurar.
- Künye bir sonraki tura `extra_system` olarak tam bir kez aktarılır.
- Kaynak/sır uyarısı gösterilir; sır değerleri uygulama günlüklerine kopyalanmaz.
- Bir oturum sürecinin çökmesi diğer oturumları etkilemez.
- Kullanıcıya ait `:memory:.ses` ve `index.html` dosyalarına dokunulmaz.

### Task 1: Geçmiş protokol uçları

**Files:**
- Modify: `src/fusion_cli/appserver/session.py`
- Create: `src/fusion_cli/appserver/history.py`
- Create: `tests/test_appserver_history.py`

- [x] `gecmis.kaynaklar` için yalnız kurulu kaynakları döndüren kırmızı test yaz.
- [x] `gecmis.oturumlar` için kaynak doğrulama, limit/cursor sınırı ve `SessionRef` serileştirme testleri yaz.
- [x] `gecmis.onizle` için sayfalı `Turn` serileştirme, `next_cursor` ve `has_more` testleri yaz.
- [x] `gecmis.surdur` için kaynağın salt okunması, künye/sır sayısı ve `pending_digest` kurulması testlerini yaz.
- [x] Saf `history.py` servis fonksiyonlarını ve `AppSession._dispatch` yönlendirmesini uygula.
- [x] Run: `.venv/bin/pytest tests/test_appserver_history.py tests/test_appserver_session.py -q`
- [x] Commit: `feat(app): geçmiş kaynaklarını masaüstü protokolüne aç`

### Task 2: Devralınan bağlamı gerçek tura taşıma

**Files:**
- Modify: `src/fusion_cli/appserver/session.py`
- Modify: `tests/test_appserver_session.py`
- Modify: `tests/test_appserver_history.py`

- [ ] `pending_digest` değerinin ilk `tur.calistir` çağrısında `extra_system` olarak geçtiğini ve ikinci turda temiz olduğunu gösteren kırmızı test yaz.
- [ ] Başarısız/iptal edilen turda künyenin kaybolmaması gerekip gerekmediğini CLI davranışıyla eşleştir; kabul edilen sözleşmeyi testle sabitle.
- [ ] `_run_turn` çağrısını `take_pending_digest()` ile bağla.
- [ ] Run: `.venv/bin/pytest tests/test_appserver_history.py tests/test_appserver_session.py -q`
- [ ] Commit: `fix(app): devralınan geçmişi sonraki tura aktar`

### Task 3: Rust çoklu oturum süreç yöneticisi

**Files:**
- Create: `app/src-tauri/src/session_manager.rs`
- Modify: `app/src-tauri/src/lib.rs`
- Modify: `app/src-tauri/src/core_process.rs`

- [ ] Süreç kimliği, proje kökü, PID, durum ve kapanış nedenini modelleyen Rust testlerini yaz.
- [ ] `oturum_olustur`, `oturuma_yaz`, `oturum_kapat`, `oturumlari_listele` Tauri komutlarının kırmızı testlerini yaz.
- [ ] Her süreç için ayrı stdout olay adı ve kontrollü stdin sahipliği uygula.
- [ ] Çöküşün yalnız ilgili oturuma olay ürettiğini ve uygulama kapanışında tüm çocukların kapandığını doğrula.
- [ ] Eski tekil `cekirdek_*` komutlarını geçiş uyumluluğu için yöneticinin varsayılan oturumuna delege et.
- [ ] Run: `cd app/src-tauri && cargo fmt --check && cargo clippy --all-targets -- -D warnings && cargo test`
- [ ] Commit: `feat(app): çoklu oturum süreç yöneticisi ekle`

### Task 4: React oturum deposu ve süreç taşıması

**Files:**
- Create: `app/src/sessions/types.ts`
- Create: `app/src/sessions/store.ts`
- Create: `app/src/sessions/store.test.ts`
- Create: `app/src/sessions/useSessions.ts`
- Create: `app/src/sessions/useSessions.test.tsx`
- Modify: `app/src/App.tsx`

- [ ] Oturum oluşturma/seçme/başlık güncelleme/çalışma durumu/çöküş reducer testlerini yaz.
- [ ] Her oturumun kendi `ProtocolClient` örneğini ve mesaj dizisini taşıdığını test et.
- [ ] Tauri çoklu süreç olaylarını `useSessions` içinde bağla; kapanışta dinleyicileri ve istemcileri temizle.
- [ ] Aktif oturum değişiminde sidebar/header/conversation/composer'ın doğru depoyu kullandığını bağla.
- [ ] Run: `cd app && npm test -- src/sessions src/App.test.tsx && npm run build`
- [ ] Commit: `feat(app): çoklu konuşma durumunu arayüze bağla`

### Task 5: Geçmiş kaynak seçici ve konuşma önizlemesi

**Files:**
- Create: `app/src/history/types.ts`
- Create: `app/src/history/useHistory.ts`
- Create: `app/src/history/useHistory.test.tsx`
- Create: `app/src/dialogs/HistoryPicker.tsx`
- Create: `app/src/dialogs/HistoryPicker.css`
- Create: `app/src/dialogs/HistoryPicker.test.tsx`
- Modify: `app/src/screens/Sidebar.tsx`
- Modify: `app/src/App.tsx`

- [ ] Yalnız protokolden dönen kaynakların sidebar'da görünmesini test et.
- [ ] Kaynak seçimi sonrası başlık/tarih/proje/kaynak listesi, arama ve sayfalama testlerini yaz.
- [ ] Oturum seçilmeden devralma yapılmadığını; önizleme turlarının aşamalı yüklendiğini test et.
- [ ] `gecmis.surdur` başarısında yeni `[claude]`/`[codex]`/`[hermes]` etiketli Fusion oturumu oluştur.
- [ ] Sır sayısı varsa teknik jargon kullanmadan tek, sakin uyarı göster.
- [ ] Run: `cd app && npm test -- src/history src/dialogs/HistoryPicker.test.tsx src/App.test.tsx && npm run build`
- [ ] Commit: `feat(app): geçmiş seçme ve sürdürme akışını ekle`

### Task 6: Oturum arama, yakın projeler ve görünüm kalıcılığı

**Files:**
- Modify: `app/src/screens/Sidebar.tsx`
- Modify: `app/src/screens/Sidebar.test.tsx`
- Create: `app/src/sessions/persistence.ts`
- Create: `app/src/sessions/persistence.test.ts`

- [ ] Başlık, proje ve kaynak üzerinden Türkçe-duyarlı arama testlerini yaz.
- [ ] Sabit/yakın proje ve yakın konuşma bölümlerinin sıralama testlerini yaz.
- [ ] Yalnız güvenli oturum metadata'sını atomik/versiyonlu sakla; mesaj ve sır içeriğini localStorage'a yazma.
- [ ] Bozuk/eski görünüm kaydında güvenli geri dönüşü test et.
- [ ] Run: `cd app && npm test -- src/screens/Sidebar.test.tsx src/sessions && npm run build`
- [ ] Commit: `feat(app): oturum navigasyonunu kalıcılaştır`

### Task 7: Phase C sözleşme, görsel ve paketli E2E kapısı

**Files:**
- Modify: `app/e2e/preview.tsx`
- Create: `app/e2e/history-flow.visual.ts`
- Modify: `Makefile`
- Create: `docs/superpowers/reports/2026-08-29-macos-oturum-ve-gecmis-sonuc.md`

- [ ] Anonim Claude/Codex/Hermes fikstürleriyle Python sözleşme testlerini çalıştır.
- [ ] Kaynak seçici, önizleme, sır uyarısı, boş/hata/uzun başlık ve küçük pencere görsellerini ekle.
- [ ] Çoklu oturum oluşturma, geçiş, durdurma, kapanış ve yeniden bağlanma E2E akışını çalıştır.
- [ ] Run: `make check && make app-check && make app-visual`
- [ ] Run: `make app-package`
- [ ] Sonuç raporunu yaz ve commit et: `test(app): oturum ve geçmiş teslimatını doğrula`

## Phase C exit criteria

- [ ] Birden fazla konuşma ayrı süreçlerde çalışır; biri çökünce diğerleri sürer.
- [ ] Yalnız kurulu geçmiş kaynakları görünür.
- [ ] `/resume<kaynak>` masaüstünde kaynak → liste → önizleme → seçim akışıdır.
- [ ] Dış geçmiş değiştirilmez; Fusion devam oturumu kaynak etiketi taşır.
- [ ] Liste/önizleme sayfalı ve uzun arşivlerde başlangıç maliyeti sınırlıdır.
- [ ] Devralınan künye tam bir sonraki tura aktarılır.
- [ ] Oturum navigasyonu arama, proje ve kaynak metadata'sıyla çalışır.
- [ ] Python, React, Rust, görsel ve paketli E2E kapıları temizdir.
