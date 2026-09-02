# Entegre Görsel, Kalite ve Masaüstü Yayın Kapısı Planı

> **REQUIRED SUB-SKILL:** `production-audit`, `e2e-testing`, `superpowers:requesting-code-review`, `superpowers:verification-before-completion` ve son aşamada `superpowers:finishing-a-development-branch` kullan.

**Goal:** Yenilenen Fusion uygulamasını kullanıcı onaylı görseller, tam test kanıtı ve macOS Apple Silicon/Intel + Windows indirilebilir paketleriyle yayınlanabilir hâle getirmek.

**Architecture:** Bu plan önceki dört planın entegrasyon kapısıdır; yeni ürün davranışı eklemez. Tek commit SHA tüm platform paketlerinin kaynağı olur. Apple Developer hesabı olmadığı için macOS paketleri imzasız/noterlenmemiş olarak açıkça etiketlenir. Talk saydamlığı `macOSPrivateApi` gerektirdiğinden desteklenen macOS kanalı doğrudan indirilen DMG'dir; Mac App Store dağıtımı bilinçli olarak desteklenmez. App Store hedefi eklenirse önce özel API bağımlılığı kaldırılarak Talk penceresi yeniden tasarlanır.

**Tech Stack:** Vitest, Playwright, pytest, cargo, GitHub Actions, Tauri bundler, PyInstaller runtime.

**Spec:** `docs/superpowers/specs/2026-08-30-uygulama-gorsel-yenileme-ve-mcp-dogrulama-design.md`

**Global Constraints:** Kullanıcının untracked dosyaları commit'e alınmaz. `.env`, token, kişisel yol ve sohbet içeriği screenshot/log/release metadata'sına girmez. Tüm görsel değişiklikler kullanıcıya screenshot olarak gösterilir.

## Task 1: Mevcut alpha.8 taban düzeltmelerini koru ve commit et

**Files:**
- `CHANGELOG.md`
- `README.md`
- `app/src-tauri/tauri.conf.json`
- `app/src/screens/Conversation.perf.test.tsx`
- `desktop_build/runtime/build_runtime.py`
- `src/fusion_cli/__init__.py`
- `tests/test_runtime_bundle.py`

1. Diff'i yalnız sürüm, CP1252-safe `Archive:` çıktısı ve 2500 ms performans eşiği değişiklikleri içeriyor mu kontrol et.
2. `pytest -q tests/test_runtime_bundle.py`, ilgili React perf testi ve `npm run build` çalıştır.
3. `:memory:.ses` ve kök `index.html` staged olmadığını `git status --short` ile doğrula.
4. Commit: `fix(release): alpha.8 masaüstü paket kapılarını sağlamlaştır`.

## Task 2: Altı dilimlik görsel kabul

**Files:**
- `app/e2e/*.visual.ts`
- `app/e2e/*.visual.ts-snapshots/*`

1. Dilimleri sırayla üret: sohbet/composer; sol panel/profil; sağ panel/terminal; önizleme; MCP; Talk normal+mini.
2. Her dilimde screenshot'ı kullanıcıya göster ve yazılı onay gelmeden bir sonraki görsel dilime geçme.
3. Onaylanan görselleri kalıcı snapshot yap; `cd app && npm run test:visual` sonucunun sıfır farkla geçmesini sağla.
4. Commit: `test(app): onaylı masaüstü görsel sözleşmelerini kilitle`.

## Task 3: Tam yerel kalite kapısı

**Files:** Test sonuçları dışında kaynak değişikliği beklenmez.

1. React/Rust: `cd app && npm run check` — beklenen 0 başarısız Vitest, başarılı TypeScript build, fmt, clippy ve cargo test.
2. Görsel: `cd app && npm run test:visual` — beklenen 0 diff.
3. Python: `.venv/bin/python -m pytest -q` — beklenen tüm testler başarılı.
4. Deadlock tekrarları: kritik session/agent testlerini `pytest-repeat` ile 100+ kez çalıştır — beklenen 0 kilitlenme.
5. macOS runtime: `cd app && npm run runtime:build && npm run runtime:smoke` — beklenen gömülü Fusion sürümü alpha.8 ve başarılı smoke.
6. Gerçek MCP smoke: güvenli test sunucusunda initialize + tools/list + tek salt-okunur tool çağrısı — beklenen UI'da `bagli` ve doğru araç sayısı.
7. Gerçek Talk smoke: izin, partial/final, TTS sırasında mikrofon kesme ve otomatik devam — beklenen aynı sohbette tek mesaj.
8. Hata olursa yalnız ilgili planın TDD döngüsüne dön; kapıyı gevşetme.

## Task 4: Bağımsız kod incelemesi ve güvenlik denetimi

**Files:** İnceleme bulgularının gerektirdiği dosyalar.

1. Bağımsız review agent'ına diff, tasarım spec'i ve test kanıtlarını ver. Özellikle process yaşam döngüsü, MCP redaksiyonu, path sınırları ve voice feedback yarışlarını incelet.
2. Kritik/önemli bulguları testle yeniden üret ve düzelt; kozmetik bulguları raporda başlık olarak tut.
3. `fusion serve` için mevcut Origin/CSRF koruma testlerini ve config eşzamanlı yazma testlerini çalıştır; regresyon varsa yayın yapma.
4. Düzeltmelerden sonra Task 3 kapısını baştan çalıştır.

## Task 5: Üç platform paketleme ve sürüm

**Files:**
- Modify if needed: `.github/workflows/desktop.yml`
- Modify if needed: `CHANGELOG.md`

1. Temiz working tree ve tek commit SHA doğrula; kullanıcı dosyalarını hariç tut.
2. `v0.3.0-alpha.8` etiketi yalnız tüm yerel kapılar geçince oluştur ve gönder.
3. GitHub Actions'ta Apple Silicon macOS, Intel macOS ve Windows işlerini tamamlanana kadar izle.
4. Her artifact için arşiv açma, executable/bundle varlığı, runtime smoke ve Talk helper varlığı doğrulamasını çalıştır.
5. Release notunda macOS paketlerinin Apple Developer hesabı olmadığı için imzasız/noterlenmemiş olduğunu ve ilk açılış adımını açıkça yaz.
6. Kullanıcıya üç indirilebilir artifact bağlantısı, SHA-256 değerleri, doğrulanan test sayıları ve bilinen önemsiz noktaları ver.

## Task 6: Son kabul

1. Son macOS paketini yerel olarak aç; ana sohbet, proje açma, ek sürükleme, `/` menüsü, terminal, preview, MCP ve Talk normal/mini için kısa uçtan uca smoke yap.
2. Son sürümden ana pencere, sağ panel ve Talk normal/mini ekran görüntülerini kullanıcıya göster.
3. Kullanıcı son görsel kabulü verdikten sonra çalışmayı tamamlandı say; aksi halde ilgili görsel planına geri dön.
