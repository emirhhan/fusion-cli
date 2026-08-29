# Fusion macOS Tasarım Sistemi ve Uygulama Kabuğu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fusion'ın Figma referansıyla ölçüsel olarak uyumlu, açık/koyu temalı, erişilebilir ve sonraki ürün ekranlarının tamamını taşıyabilecek profesyonel macOS uygulama kabuğunu üretmek.

**Architecture:** React görünümü semantik tasarım tokenları, küçük erişilebilir arayüz ilkelleri ve üç bölmeli uyarlanabilir bir kabuk etrafında kurulacaktır. Sol navigasyon, konuşma yüzeyi ve sağ denetçi yalnız görünüm/durum yönetir; iş kuralları mevcut `ProtocolClient` ve Python çekirdeğinde kalır. Genişlik, tema ve panel görünürlüğü uygulama düzeyindeki görünüm durumuyla yönetilir; Phase C protokol verileri geldiğinde bileşen sözleşmeleri değiştirilmeden gerçek oturumlara bağlanabilir.

**Tech Stack:** React 19, TypeScript 5.8, CSS custom properties, Vitest, Testing Library, Playwright görsel regresyonu, Tauri 2.

**Spec:** `docs/superpowers/specs/2026-08-29-tam-macos-uygulamasi-design.md`, `docs/superpowers/specs/2026-08-29-uygulama-gorsel-dil.md`

## Global constraints

- Kullanıcıya görünen metinler Türkçedir; kod tanımlayıcıları İngilizcedir.
- Figma'dan ölçülmüş açık tema değerleri korunur: `#FFFFFF`, `#F9F9FA`, `#EFEFF0`, `#F5F5F5`, `#000000`, `#EBEBFA`, `#7C7C7D`, `#E9E9EB`.
- Bileşenlerde ham renk, keyfi gölge veya satır içi stil kullanılmaz.
- 1440px görünümde sol panel 281px'tir. Sağ denetçi varsayılan 320px'tir; ana konuşma alanı kalan alanı kullanır.
- Kullanıcı mesajı sağda balonlu, Fusion mesajı balonsuzdur.
- Tüm ikonlar aynı 1.75px çizgi ailesinden gelir; yalnız ikonlu düğmeler erişilebilir ad taşır.
- Odak halkası görünür, renk dışı durum işaretleri bulunur ve `prefers-reduced-motion` uygulanır.
- Küçük pencerede ana görev yüzeyi kaybolmaz: sol panel ikon şeridine, sağ denetçi örtü paneline dönüşür.
- Her görev kırmızı test → en küçük uygulama → hedefli test → ilgili tam kalite kapısı sırasını izler.
- Kullanıcının izlenmeyen `:memory:.ses` ve `index.html` dosyalarına dokunulmaz.

### Task 1: Semantik tokenlar, global reset ve tema sözleşmesi

**Files:**
- Modify: `app/src/theme/tokens.css`
- Create: `app/src/theme/theme.ts`
- Create: `app/src/theme/theme.test.ts`
- Modify: `app/src/theme/tokens.test.ts`
- Modify: `app/src/main.tsx`
- Replace: `app/src/App.css`

- [x] **Step 1: Tema çözümleme testlerini yaz**

`theme.test.ts`, `system`, `light`, `dark` tercihlerinin gerçek temaya dönüşmesini; geçersiz saklı değerin `system` kabul edilmesini ve tema değişikliğinin `document.documentElement.dataset.theme` alanına uygulanmasını doğrular.

- [x] **Step 2: Testin mevcut durumda başarısız olduğunu doğrula**

Run: `cd app && npm test -- src/theme/theme.test.ts`
Expected: FAIL — `theme.ts` bulunmuyor.

- [x] **Step 3: Semantik tema katmanını uygula**

`tokens.css` içinde renk rolleri (`--surface-canvas`, `--surface-sidebar`, `--text-primary`, `--border-subtle`, durum renkleri), 4px tabanlı boşluk ölçeği, tipografi, yarıçap, katman ve hareket tokenları tanımlanır. Ölçülmüş eski Türkçe değişkenler geçiş süresince alias olarak kalır. `[data-theme="dark"]` ve `@media (prefers-color-scheme: dark)` aynı semantik rolleri koyu palete map eder.

`theme.ts` saf çözümleme fonksiyonları ve `applyTheme()` sağlar. İlk boyama `main.tsx` içinde React renderından önce yapılır; varsayılan `system` olur.

- [x] **Step 4: Vite kalıntılarını kaldır ve global reseti bağla**

`App.css` yalnız uygulama düzeyi yardımcı sınıfları içerir; Vite logo, mavi link, genel input/button gölgeleri ve eski dark media kuralları silinir. `main.tsx`, `tokens.css` ve `App.css` dosyalarını tek kez yükler.

- [x] **Step 5: Hedefli ve tam UI testini çalıştır**

Run: `cd app && npm test -- src/theme/theme.test.ts src/theme/tokens.test.ts && npm run build`
Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add app/src/theme app/src/main.tsx app/src/App.css
git commit -m "feat(ui): semantik tema sistemini kur"
```

### Task 2: Erişilebilir ikon ve kontrol ilkelleri

**Files:**
- Create: `app/src/ui/Icon.tsx`
- Create: `app/src/ui/Icon.test.tsx`
- Create: `app/src/ui/Button.tsx`
- Create: `app/src/ui/Button.test.tsx`
- Create: `app/src/ui/controls.css`

- [x] **Step 1: İkon ve düğme erişilebilirlik testlerini yaz**

Testler dekoratif ikonun erişilebilirlik ağacından gizlendiğini, anlam taşıyan ikonun başlık alabildiğini, yalnız ikonlu düğmenin zorunlu `aria-label` ile erişilebilir olduğunu ve yükleniyor/devre dışı durumlarının metinle taşındığını doğrular.

- [x] **Step 2: Testlerin kırmızı olduğunu gör**

Run: `cd app && npm test -- src/ui/Icon.test.tsx src/ui/Button.test.tsx`
Expected: FAIL — bileşen modülleri yok.

- [x] **Step 3: Tek çizgi ailesini ve düğme varyantlarını uygula**

`Icon` yalnız projede kullanılan küçük SVG path kataloğunu (`new`, `search`, `panel`, `settings`, `lessons`, `skills`, `files`, `changes`, `terminal`, `tests`, `preview`, `send`, `attach`, `chevron`, `sidebar`) içerir. Tüm ikonlar `currentColor`, `fill="none"`, `strokeLinecap="round"` ve 1.75px stroke kullanır.

`Button`; `primary`, `secondary`, `ghost`, `danger` ve `icon` varyantlarını aynı odak/hover/disabled sözleşmesiyle sunar.

- [x] **Step 4: Test ve build doğrulaması**

Run: `cd app && npm test -- src/ui && npm run build`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add app/src/ui
git commit -m "feat(ui): erişilebilir kontrol ilkelleri ekle"
```

### Task 3: Üç bölmeli uyarlanabilir macOS kabuğu

**Files:**
- Replace: `app/src/screens/Shell.tsx`
- Create: `app/src/screens/Shell.css`
- Create: `app/src/screens/Shell.test.tsx`
- Create: `app/src/state/useLayout.ts`
- Create: `app/src/state/useLayout.test.tsx`

- [x] **Step 1: Kabuk ve görünüm durumu testlerini yaz**

Testler 281px sol panel tokenını, `navigation/main/complimentary` semantiğini, sol ve sağ panel aç/kapa eylemlerini, tercihin saklanmasını ve Escape ile küçük ekran örtü panelinin kapanmasını doğrular.

- [x] **Step 2: Kırmızı testi çalıştır**

Run: `cd app && npm test -- src/screens/Shell.test.tsx src/state/useLayout.test.tsx`
Expected: FAIL — yeni sözleşme uygulanmadı.

- [x] **Step 3: Kabuk sözleşmesini uygula**

`Shell` şu slotları alır: `sidebar`, `header`, `content`, `composer`, `inspector`. Geniş görünümde 281px + akışkan ana alan + 320px denetçi; 1024–1199px arasında daraltılmış 68px sol şerit; 1024px altında sağ denetçi modal olmayan örtü panelidir. Panel düğmeleri `aria-expanded`/`aria-controls` taşır.

- [x] **Step 4: Görünüm durumunu kalıcılaştır**

`useLayout` yalnız pencere görünümü tercihlerine sahip olur; Phase C oturum durumu burada tutulmaz. `localStorage` erişimi hata verse bile güvenli varsayılanlarla çalışır.

- [x] **Step 5: Test ve build**

Run: `cd app && npm test -- src/screens/Shell.test.tsx src/state/useLayout.test.tsx && npm run build`
Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add app/src/screens/Shell.tsx app/src/screens/Shell.css app/src/screens/Shell.test.tsx app/src/state
git commit -m "feat(ui): uyarlanabilir üç bölmeli kabuk ekle"
```

### Task 4: Figma uyumlu navigasyon ve uygulama başlığı

**Files:**
- Replace: `app/src/screens/Sidebar.tsx`
- Create: `app/src/screens/Sidebar.css`
- Modify: `app/src/screens/Sidebar.test.tsx`
- Create: `app/src/screens/AppHeader.tsx`
- Create: `app/src/screens/AppHeader.test.tsx`
- Create: `app/src/screens/AppHeader.css`

- [x] **Step 1: Bilgi mimarisi testlerini genişlet**

Testler Yeni görev, arama, sabit/yakın oturumlar, `[fusion]`/`[claude]`/`[codex]`/`[hermes]` kaynak rozetleri, Beceriler ve Ajanlar, Dersler, Kontrol Paneli ve Ayarlar satırlarını; yalnız bulunan kaynakların görünmesini; arama filtresini; dar moddaki erişilebilir adları doğrular.

- [x] **Step 2: Başlık testi yaz**

Başlık; etkin konuşma/proje adını, yerel çalışma durumu metnini ve iki panel düğmesini gösterir. Durum yalnız renkle aktarılmaz.

- [x] **Step 3: Kırmızı testleri çalıştır**

Run: `cd app && npm test -- src/screens/Sidebar.test.tsx src/screens/AppHeader.test.tsx`
Expected: FAIL.

- [x] **Step 4: Navigasyonu ve başlığı uygula**

Satırlar 36px hedef yüksekliği, 8px yarıçap ve açık gri aktif yüzey kullanır. Kaynak bilgisi ikincil metindir, parlak rozet değildir. Satır eylemleri hover/focus-within ile görünür; klavyede kaybolmaz. Arama gerçek filtreleme yapar ama Phase C gelene kadar ağ çağrısı yapmaz.

- [x] **Step 5: Test, build ve commit**

Run: `cd app && npm test -- src/screens/Sidebar.test.tsx src/screens/AppHeader.test.tsx && npm run build`
Expected: PASS.

```bash
git add app/src/screens/Sidebar* app/src/screens/AppHeader*
git commit -m "feat(ui): uygulama navigasyonunu tamamla"
```

### Task 5: Bestelenebilir konuşma, çalışma olayları ve composer

**Files:**
- Replace: `app/src/screens/Conversation.tsx`
- Create: `app/src/screens/Conversation.css`
- Create: `app/src/screens/Conversation.test.tsx`
- Replace: `app/src/screens/EmptyState.tsx`
- Create: `app/src/screens/EmptyState.css`
- Create: `app/src/screens/Composer.tsx`
- Create: `app/src/screens/Composer.css`
- Create: `app/src/screens/Composer.test.tsx`
- Modify: `app/src/protocol/olayMetni.ts`
- Modify: `app/src/protocol/olayMetni.test.ts`

- [ ] **Step 1: Konuşma hiyerarşisi testlerini yaz**

Kullanıcı mesajının balon, asistanın düz makale, olayların açılabilir çalışma satırı olduğunu; kopyalama eylemini; uzun metin taşmasını ve güvenli boş durumu doğrula.

- [ ] **Step 2: Composer davranış testlerini yaz**

Enter gönderir, Shift+Enter yeni satır açar, boş metin gönderilmez, çalışan turda gönder düğmesi durdur eylemine dönüşür, `/` komut tetikleyicisi ve ek düğmesi klavyeyle erişilebilirdir.

- [ ] **Step 3: Kırmızı testleri çalıştır**

Run: `cd app && npm test -- src/screens/Conversation.test.tsx src/screens/Composer.test.tsx`
Expected: FAIL.

- [ ] **Step 4: Figma konuşma yüzeyini uygula**

Konuşma sütunu en fazla 768px; kullanıcı balonu en fazla %82; Fusion mesajı balonsuz ve seçilebilir metindir. Olay özetleri sakin, tek satırlı başlıklar; hata/test kanıtı açık; ham ayrıntı `details/summary` ile açılır. Composer alt yüzeyde sticky konumlanır, metin alanı içeriğe göre kontrollü büyür.

- [ ] **Step 5: Boş durumu ürün girişine dönüştür**

Boş ekran tek büyük slogan yerine kısa başlık, görev girişi ve üç gerçekçi başlangıç önerisi gösterir; öneriler `onSelectPrompt` ile composer'a taşınır.

- [ ] **Step 6: Test, build ve commit**

Run: `cd app && npm test -- src/screens/Conversation.test.tsx src/screens/Composer.test.tsx src/protocol/olayMetni.test.ts && npm run build`
Expected: PASS.

```bash
git add app/src/screens/Conversation* app/src/screens/EmptyState* app/src/screens/Composer* app/src/protocol/olayMetni*
git commit -m "feat(ui): konuşma ve görev girişini yenile"
```

### Task 6: Sağ denetçi ve bağlamsal yüzeyler

**Files:**
- Create: `app/src/screens/Inspector.tsx`
- Create: `app/src/screens/Inspector.css`
- Create: `app/src/screens/Inspector.test.tsx`
- Create: `app/src/ui/StatusRow.tsx`
- Create: `app/src/ui/StatusRow.test.tsx`

- [ ] **Step 1: Denetçi sekme testlerini yaz**

Dosyalar, Değişiklikler, Terminal, Süreçler, Testler, Önizleme ve Bağlam sekmelerinin klavye ile dolaşılabildiğini; `tablist/tab/tabpanel` rollerini; boş/yükleniyor/hata durumlarını doğrula.

- [ ] **Step 2: Kırmızı testi çalıştır**

Run: `cd app && npm test -- src/screens/Inspector.test.tsx src/ui/StatusRow.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Denetçi iskeletini uygula**

Sekmeler yatay taşmada kaydırılır; aktif sekme ince alt çizgi ve metinle belirtilir. İçerik sahte ürün verisi üretmez: protokol bağlanana kadar dürüst boş durum ve ilgili eylem gösterir. `StatusRow`, Kontrol Paneli ve ilerideki ayar ekranlarının yoğun satır temelidir.

- [ ] **Step 4: Test, build ve commit**

Run: `cd app && npm test -- src/screens/Inspector.test.tsx src/ui/StatusRow.test.tsx && npm run build`
Expected: PASS.

```bash
git add app/src/screens/Inspector* app/src/ui/StatusRow*
git commit -m "feat(ui): bağlamsal sağ denetçiyi ekle"
```

### Task 7: Uygulama birleşimi, tema menüsü ve onay yüzeyi

**Files:**
- Modify: `app/src/App.tsx`
- Modify: `app/src/App.test.tsx`
- Modify: `app/src/App.runtime.test.tsx`
- Replace: `app/src/dialogs/Approval.tsx`
- Create: `app/src/dialogs/Approval.css`
- Modify: `app/src/dialogs/Approval.test.tsx`
- Modify: `app/src/screens/RuntimeSetup.css`

- [ ] **Step 1: Birleşim testlerini yaz**

Uygulamanın header/sidebar/conversation/composer/inspector slotlarını bağladığını, panel eylemlerini, tema seçimini, yeni görev temizliğini ve protokol mesaj gönderimini doğrula. Runtime kapısı davranışı değişmemelidir.

- [ ] **Step 2: Onay erişilebilirlik testlerini genişlet**

Odak diyaloğa taşınır, Escape yalnız güvenli reddetme seçeneği varsa reddeder, ilk önerilen eylem görsel ve semantik olarak belirtilir, araç/konum/etki sade Türkçeyle gösterilir.

- [ ] **Step 3: Kırmızı testleri çalıştır**

Run: `cd app && npm test -- src/App.test.tsx src/App.runtime.test.tsx src/dialogs/Approval.test.tsx`
Expected: FAIL.

- [ ] **Step 4: Tüm yüzeyleri bağla**

Satır içi `Composer` ve yükleme/hata stilleri kaldırılır. `Uygulama`, Phase B bileşenlerini gerçek protokol istemcisine bağlar. Tema tercihi başlık menüsünden değişir. RuntimeSetup aynı token, kontrol ve odak sistemini kullanır.

- [ ] **Step 5: Tam uygulama kalite kapısı**

Run: `cd app && npm run check`
Expected: 0 exit, tüm React/TypeScript/Rust kontrolleri temiz.

- [ ] **Step 6: Commit**

```bash
git add app/src
git commit -m "feat(app): profesyonel macOS kabuğunu bağla"
```

### Task 8: Görsel regresyon ve Phase B teslimat kanıtı

**Files:**
- Modify: `app/package.json`
- Modify: `app/package-lock.json`
- Create: `app/playwright.config.ts`
- Create: `app/e2e/visual-shell.spec.ts`
- Create: `app/e2e/fixtures/AppPreview.tsx`
- Create: `app/e2e/visual-shell.spec.ts-snapshots/*`
- Modify: `Makefile`
- Create: `docs/superpowers/reports/2026-08-29-macos-tasarim-sistemi-sonuc.md`

- [ ] **Step 1: Playwright görsel kapısını ekle**

`@playwright/test` yalnız geliştirme bağımlılığıdır. Test fixture'ı gerçek bileşenleri deterministik örnek mesajlar ve olaylarla render eder; ürün kodunda demo veri bulunmaz.

- [ ] **Step 2: Durum matrisini yaz**

En az şu ekran görüntüleri tutulur: 1440px açık boş, 1440px açık konuşma+denetçi, 1440px koyu konuşma, 1100px dar navigasyon, 820px örtü denetçi, onay diyaloğu, klavye odak durumu. Animasyonlar ve zaman bağımlı içerik testte kapatılır.

- [ ] **Step 3: İlk snapshotları üret ve tek tek incele**

Run: `cd app && npx playwright test --update-snapshots`
Expected: snapshotlar oluşur. Her PNG yerel olarak açılıp taşma, hizalama, kontrast ve Figma ölçüleri bakımından gözle incelenir; sorun varsa ürün CSS'i düzeltilir, tolerans yükseltilmez.

- [ ] **Step 4: Regresyon modunda doğrula**

Run: `cd app && npx playwright test`
Expected: PASS, snapshot farkı yok.

- [ ] **Step 5: Proje kalite kapılarını çalıştır**

Run: `make check && make app-check`
Expected: Python, React, TypeScript ve Rust testlerinin tamamı geçer.

- [ ] **Step 6: Paketlenmiş uygulamayı yeniden doğrula**

Run: `make app-package`
Expected: `.app` ve `.dmg` yeniden üretilir; temiz HOME ilk/ikinci açılış smoke testi geçer.

- [ ] **Step 7: Sonuç raporunu yaz ve commit et**

Rapor; test sayılarını, ekran matrisini, ölçülen paketleri, bilinen imzasız dağıtım kısıtını ve Phase C'ye kalan gerçek veri bağlantılarını kaydeder.

```bash
git add app Makefile docs/superpowers/reports/2026-08-29-macos-tasarim-sistemi-sonuc.md
git commit -m "test(ui): macOS görsel kalite kapısını ekle"
```

## Phase B exit criteria

- [ ] Açık ve koyu temada semantik tokenlar kullanılıyor; ham bileşen renkleri ve Vite kalıntıları yok.
- [ ] 1440px'te sol panel 281px, ana alan akışkan, sağ denetçi bağlamsal ve 320px.
- [ ] Orta/küçük pencerelerde ana sohbet kullanılabilir; paneller klavyeyle açılıp kapanıyor.
- [ ] Sidebar, başlık, konuşma, composer, onay ve denetçi tek görsel sistemde.
- [ ] Navigasyon Phase C kaynaklarını kabul edecek tipli sözleşmeye sahip; demo veri ürün koduna gömülü değil.
- [ ] Erişilebilir roller, adlar, focus-visible ve reduced-motion davranışları testli.
- [ ] Görsel durum matrisi snapshot regresyonuyla korunuyor.
- [ ] `make check`, `make app-check` ve `make app-package` temiz.
