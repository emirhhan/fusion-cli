# Fusion macOS Dersler ve Yayın Kapısı Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** G aşamasının kalan parçası olan etkileşimli dersleri uygulamaya bağlamak ve H yayın kalite kapısını kapatarak DMG'yi arkadaşlara dağıtılabilir hâle getirmek.

**Architecture:** Ders tanımları Python tarafında veri olarak durur ve masaüstü protokolünden okunur; React yalnız gösterir ve ilerlemeyi güvenli metadata olarak saklar. Dersler ayrı bir doküman okuyucusu DEĞİLDİR: her adım kullanıcının gerçek çalışma alanında küçük ve geri alınabilir bir görevle ilerler, kaldığı yeri hatırlar. Yayın kapısı yeni özellik yazmaz; yalnız kanıt toplar, bulgu çıkarsa düzeltir ve paketi yeniden üretir.

**Tech Stack:** Python 3.11+, pytest, React 19, TypeScript, Vitest, Tauri 2, Playwright.

**Spec:** `docs/superpowers/specs/2026-08-29-tam-macos-uygulamasi-design.md` §12, §13, aşama G ve H

## Global Constraints

- Ders içeriği kullanıcıya görünen metindir: Türkçe yazılır, tanımlayıcılar İngilizce kalır.
- Ders adımı kullanıcının dosyalarını onaysız değiştirmez; mevcut onay ve geri alma sözleşmesi değişmez.
- Ders ilerlemesi yalnız güvenli metadata olarak saklanır (ders kimliği, adım, tamamlanma); mesaj, dosya içeriği, PID ve hassas değer saklanmaz.
- Kullanıcıya ait `:memory:.ses` ve `index.html` dosyalarına dokunulmaz.
- Her davranış önce başarısız testle sabitlenir; her görev sonunda dar kapı, sonra `make app-check` çalışır.
- Yayın kapısında ölçüm uydurulmaz: her sayı gerçekten çalıştırılmış komuttan alınır.

---

### Task 1: Ders kataloğu ve ilerleme protokolü

**Files:**
- Create: `src/fusion_cli/appserver/lessons.py`
- Modify: `src/fusion_cli/appserver/session.py`
- Create: `tests/test_appserver_lessons.py`

**Interfaces:**
- Produces: `ders.listele` → tasarımdaki sekiz dersin kimlik/başlık/özet/adım sayısı.
- Produces: `ders.getir` → tek dersin adımları; her adım `baslik`, `aciklama`, `eylem` alanlarını taşır.
- `eylem` yalnız uygulamanın zaten sunduğu bir yüzeyi işaret eder (composer'a metin koymak, bir sekmeyi açmak); kendi başına dosya yazmaz veya komut çalıştırmaz.

- [x] Sekiz dersin listelendiğini, bilinmeyen ders kimliğinin çökmeden hata döndürdüğünü ve hiçbir adımın yürütülebilir komut taşımadığını kırmızı testle sabitle.
- [x] Uygula, yeşile getir, `pytest` + Ruff + mypy kapısını çalıştır ve commit et.

### Task 2: Dersler ekranı ve ilerleme kalıcılığı

**Files:**
- Create: `app/src/lessons/Lessons.tsx`
- Create: `app/src/lessons/Lessons.css`
- Create: `app/src/lessons/Lessons.test.tsx`
- Modify: `app/src/App.tsx`
- Modify: `app/src/screens/Sidebar.tsx`

**Interfaces:**
- Sol navigasyondaki "Dersler" gerçek ekrana bağlanır; şu an hiçbir yere gitmiyor.
- Ders adımı "Bunu dene" ile composer'a hazır görev metnini koyar; kullanıcı göndermeden hiçbir şey çalışmaz.

- [x] Ekranın dersleri listelediğini, adım ilerlettiğini, kaldığı yeri hatırladığını ve kayıtta hassas veri bulunmadığını kırmızı testle sabitle.
- [x] Uygula, yeşile getir, `npx vitest run` + `npm run build` çalıştır ve commit et.

### Task 3: Ders görselleri ve erişilebilirlik denetimi

**Files:**
- Modify: `app/e2e/preview.tsx`
- Modify: `app/e2e/product-surfaces.visual.ts`

- [x] Açık/koyu tema, 920 px dar görünüm ve ilerlemiş ders durumu için görsel senaryolar ekle.
- [x] Üretilen PNG'leri gözle incele; hizalama/taşma/kontrast kusuru görürsen toleransı yükseltmeden CSS'i düzelt.
- [ ] Klavye ile dersler arasında dolaşımı ve odak görünürlüğünü doğrula.
- [x] `make app-visual` çalıştır ve commit et.

### Task 4: Güvenlik denetimi ve açık bulguların kapatılması

**Files:**
- Modify: `src/fusion_cli/gateway/app.py`
- Modify: `tests/test_gateway.py`

- [x] `_foreign_host` içindeki `Host: local` kaçışını kapat: sentetik test adı üretim yolunda kabul edilmesin, testler kendi yerel adıyla çalışsın. Önce bu davranışı kırmızı testle sabitle.
- [ ] `npm audit` ve Python bağımlılık yüzeyini gözden geçir; bulguları raporla.
- [x] Kök kapısını çalıştır ve commit et.

### Task 5: Yayın kalite kapısı ve dağıtım paketi

**Files:**
- Create: `docs/superpowers/reports/2026-08-29-macos-dersler-ve-yayin-sonuc.md`
- Modify: `docs/kurulum.md` (varsa; yoksa mevcut son kullanıcı belgesi)

- [x] Tam zinciri çalıştır: `make check && make app-check && make app-visual && make app-package`.
- [x] Büyük konuşma performansını ölç (çok mesajlı oturumda arayüzün yanıt verdiğini kanıtla).
- [ ] Çevrimdışı açılışı doğrula (ağ yokken uygulama açılmalı ve sebebi açıkça söylemeli).
- [ ] Bozuk çalışma zamanını onarma ve geri alma senaryosunu paketli uygulamada tekrar çalıştır.
- [ ] Temiz HOME'da paketli uygulamayı aç, bir ders adımını uçtan uca dene.
- [x] Masaüstündeki paylaşılabilir DMG kopyasını tazele; SHA-256 ve boyutu rapora yaz.
- [x] Intel paketi bu makinede üretilemiyorsa bunu raporda AÇIKÇA yaz; sessizce atlanmış gibi bırakma.
- [x] Sonuç raporunu yaz ve commit et.

## Phase G/H Exit Criteria

- [x] Sol navigasyondaki sekiz satırın hiçbiri ölü bağlantı değil.
- [x] Dersler gerçek çalışma alanında ilerler ve kaldığı yeri hatırlar.
- [x] Ders kaydında mesaj, dosya içeriği veya hassas değer bulunmaz.
- [x] Gateway'de test kolaylığından doğan üretim kaçışı kalmaz.
- [x] Python, React, Rust, görsel ve paketli kapılar temizdir.
- [x] Masaüstünde güncel, imzasız, Apple Silicon DMG'si ve dürüst kurulum yönergesi vardır.
