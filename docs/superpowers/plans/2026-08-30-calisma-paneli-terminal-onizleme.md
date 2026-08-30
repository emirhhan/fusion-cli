# Çalışma Paneli, Terminal ve Önizleme Uygulama Planı

> **REQUIRED SUB-SKILL:** `superpowers:test-driven-development`, `react-patterns`, `make-interfaces-feel-better` ve tamamlamadan önce `superpowers:verification-before-completion` kullan.

**Goal:** Sağ paneli ChatGPT/Codex benzeri gerçek bir çalışma alanına dönüştürmek; çoklu terminal, dosya önizleme ve yerel web önizlemesini aynı görev bağlamında kullanılabilir yapmak.

**Architecture:** `Inspector` sekme kabuğu olarak kalır. Terminal sekmesi süreç listesini sekme modeline yansıtır, yeni bir terminal motoru yaratmaz. Önizleme yalnız mevcut yerel URL/dosya API'lerini kullanır. Panel genişliği ve seçili sekme yerel UI tercihi olarak saklanır.

**Tech Stack:** React 19, TypeScript, CSS, Vitest, Playwright, mevcut Fusion appserver process/file/browser yolları.

**Spec:** `docs/superpowers/specs/2026-08-30-uygulama-gorsel-yenileme-ve-mcp-dogrulama-design.md`

**Global Constraints:** Terminal çıktısı ve dosya önizlemesi görev kökünün dışına çıkamaz. Komut çalıştırma onay politikası çekirdekte kalır. Sağ panelde sahte tarayıcı güvenliği veya sahte bağlantı durumu gösterilmez.

## Task 1: Yeniden boyutlanabilir Inspector kabuğu

**Files:**
- Modify: `app/src/screens/Inspector.tsx`
- Modify: `app/src/screens/Inspector.css`
- Modify: `app/src/App.tsx`
- Test: `app/src/screens/Inspector.test.tsx`

1. Seçili sekme, daraltma ve genişlik sınırı testlerini yaz. `Inspector` için `width`, `onWidthChange`, `collapsed`, `onCollapsedChange` sözleşmesini kullan.
2. `cd app && npm test -- Inspector.test.tsx` ile kırmızı testi doğrula.
3. 320–720 px sınırlarında klavye ile de ayarlanabilen ayırıcı ekle; seçili sekme ve genişliği `localStorage` altında `fusion.inspector.layout.v1` anahtarında sakla.
4. Mobil/dar ana pencerede paneli içerik üstüne bindiren geçici drawer yap; masaüstünde sohbet sütununu sıkıştıran dock davranışını koru.
5. Test ve build çalıştır; commit: `feat(app): çalışma paneli kabuğunu yenile`.

## Task 2: Çoklu terminal sekmeleri

**Files:**
- Create: `app/src/processes/TerminalTabs.tsx`
- Create: `app/src/processes/TerminalTabs.test.tsx`
- Modify: `app/src/processes/TerminalPanel.tsx`
- Modify: `app/src/processes/processes.css`
- Modify: `app/src/processes/useProcesses.ts`

1. `TerminalTabs` testlerinde süreç açma, aktif sekme seçme, çalışan süreci durdurma, bitmiş sekmeyi kapatma ve output auto-scroll davranışını yaz.
2. Kırmızı test: `cd app && npm test -- TerminalTabs.test.tsx`.
3. `ProjectProcess.surec_id` değerini sekme kimliği olarak kullan; seçili olmayan süreçlerin çıktısını kaybetme. “+” düğmesi komut composer'ını açsın, kullanıcı komutu onaylayınca mevcut `start()` çağrılsın.
4. Terminal toolbar'a süreç durumu, cwd, temizle/kopyala ve kapat kontrolleri ekle. ANSI kaçışlarını metin olarak sızdırmadan güvenli biçimde çiz.
5. Testleri çalıştır; commit: `feat(app): çoklu terminal sekmelerini ekle`.

## Task 3: Tarayıcı ve dosya önizleme deneyimi

**Files:**
- Modify: `app/src/workspace/PreviewPanel.tsx`
- Modify: `app/src/workspace/PreviewPanel.css`
- Test: `app/src/workspace/PreviewPanel.test.tsx`
- Modify: `app/src/workspace/FileExplorer.tsx`

1. Testlerde geri/ileri/yenile, URL girişi, localhost dışı URL reddi, dosya seçimi, metin/resim önizlemesi ve desteklenmeyen tür durumu oluştur.
2. Kırmızı test: `cd app && npm test -- PreviewPanel.test.tsx`.
3. Önizleme toolbar'ını sekme başlığı, adres, geri/ileri, yenile, harici aç ve viewport seçenekleriyle oluştur. Geçmiş yığınını yalnız UI durumunda tut.
4. Dosya ve web önizlemelerini ayrı alt modlar yap; dosya seçiminde `FileExplorer` ile aynı proje-kökü kısıtını kullan.
5. iframe yüklenemezse boş beyaz alan yerine açıklama ve “harici aç” eylemi göster.
6. Test/build; commit: `feat(app): yerel web ve dosya önizlemesini tamamla`.

## Task 4: Görsel onay

**Files:**
- Modify: `app/e2e/workspace.visual.ts`
- Candidate snapshots: `app/e2e/workspace.visual.ts-snapshots/*`

1. 1440×900 sahnede iki terminal sekmesi, çalışan süreç ve web önizlemesi; 1100×760 sahnede daraltılmış panel durumlarını üret.
2. Aday ekran görüntülerini kullanıcıya göster. Sekme yoğunluğu, terminal okunabilirliği, toolbar ve resize davranışı ayrı ayrı onaylanır.
3. Onaydan sonra snapshot'ları kalıcılaştır, `npm run test:visual` çalıştır ve commit et: `test(app): çalışma paneli görsel sözleşmelerini ekle`.
