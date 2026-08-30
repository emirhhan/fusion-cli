# Fusion Karakteri, Sohbet ve Composer Uygulama Planı

> **REQUIRED SUB-SKILL:** `superpowers:test-driven-development` ile görev görev ilerle; görsel varlık üretiminde `imagegen`, React değişikliklerinde `react-patterns`, son kontrolde `superpowers:verification-before-completion` kullan.

**Goal:** Ana sohbeti verilen ChatGPT UI referansının yoğunluk ve kullanım kalitesine ulaştırmak; eski/kırpılan piksel karakteri yeni Fusion marka karakteriyle değiştirmek ve dosya/komut girişini güvenilir hâle getirmek.

**Architecture:** Mevcut `App → Shell → Conversation → Composer` veri akışı korunur. Marka görselleri tek bir `FusionAvatar` bileşeninden, yüzey ölçüleri ortak CSS değişkenlerinden gelir. İşlevsel davranış görsel bileşenlere gömülmez; mevcut sohbet ve ek yönetimi hook'ları kullanılmaya devam eder.

**Tech Stack:** React 19, TypeScript, CSS, Vitest/Testing Library, Playwright, Tauri 2.

**Spec:** `docs/superpowers/specs/2026-08-30-uygulama-gorsel-yenileme-ve-mcp-dogrulama-design.md`

**Global Constraints:** `.env` ve kimlik bilgileri arayüzde düz metin olarak gösterilebilir ancak log/snapshot'a yazılmaz. `:memory:.ses` ve kökteki `index.html` kullanıcı dosyalarıdır; dokunulmaz. Kalıcı Playwright snapshot'ı yalnız kullanıcı ekran görüntüsünü onayladıktan sonra güncellenir.

## Task 1: Yeni Fusion karakter varlık seti

**Files:**
- Create: `app/src/brand/character/idle.png`
- Create: `app/src/brand/character/listening.png`
- Create: `app/src/brand/character/thinking.png`
- Create: `app/src/brand/character/talking-a.png`
- Create: `app/src/brand/character/talking-b.png`
- Create: `app/src/brand/character/happy.png`
- Create: `app/src/brand/character/approval.png`
- Modify: `app/src/voice/FusionAvatar.tsx`
- Modify: `app/src/voice/FusionAvatar.css`
- Test: `app/src/voice/FusionAvatar.test.tsx`

1. Önce `FusionAvatar.test.tsx` içinde her durumun doğru erişilebilir etiketi ve doğru `data-state` değeri verdiğini; `talking` durumunun iki kare arasında geçtiğini yaz ve kırmızı testi çalıştır: `cd app && npm test -- FusionAvatar.test.tsx`.
2. `imagegen` ile `/Users/motogate/Downloads/fusiontalkingtype.png` referans alınarak şeffaf arka planlı, aynı açı/ışık/gövde oranına sahip yedi ifade üret. Kulakların ve neon halesinin hiçbir karede kırpılmadığını 1:1 önizlemede kontrol et.
3. Görselleri yalnız yukarıdaki hedef adlara yerleştir; eski `app/src/brand/pixel/*.png` dosyalarını henüz silme.
4. `FusionAvatar` eşlemesini yeni varlıklara geçir; `talking-a/b` animasyonunu `prefers-reduced-motion` altında sabit kareye düşür.
5. Testi yeniden çalıştır; beklenen sonuç tüm `FusionAvatar` testlerinin geçmesidir.
6. Commit: `git add app/src/brand/character app/src/voice/FusionAvatar.* app/src/voice/FusionAvatar.test.tsx && git commit -m "feat(app): Fusion karakter setini yenile"`.

## Task 2: Sohbet boş durumu ve mesaj ritmi

**Files:**
- Modify: `app/src/screens/EmptyState.tsx`
- Modify: `app/src/screens/EmptyState.css`
- Modify: `app/src/screens/Conversation.tsx`
- Modify: `app/src/screens/Conversation.css`
- Modify: `app/src/screens/Shell.css`
- Test: `app/src/screens/Conversation.test.tsx`
- Test: `app/src/screens/Conversation.perf.test.tsx`

1. Testlere boş durumda karakterin kırpılmadığını belirleyen kapsayıcı sınıfı, mesajlarda rol etiketi ve işlem durumunun ayrı canlı bölge olmasını ekle.
2. Kırmızı testi çalıştır: `cd app && npm test -- Conversation.test.tsx Conversation.perf.test.tsx`.
3. Sohbet sütununu masaüstünde `min(760px, calc(100% - 48px))`, dar pencerede `calc(100% - 28px)` yap; metin satır boyunu okunabilir tut, gereksiz kart çerçevelerini kaldır.
4. Boş durumda yeni karakteri büyük ama taşmadan göster; selamlama, örnek görevler ve aktif proje bilgisini aynı görsel hiyerarşiye yerleştir.
5. Kullanıcı mesajı, Fusion cevabı, araç çağrısı, hata ve çalışan durumlarını yalnız renk değil ikon/metin ile ayırt et.
6. Testleri ve `npm run build` komutunu çalıştır; beklenen sonuç sıfır hata ve performans testinin 2500 ms eşiğini aşmamasıdır.
7. Commit: `git add app/src/screens && git commit -m "feat(app): sohbet yüzeyini profesyonel ritme taşı"`.

## Task 3: Composer, ekler ve eğik çizgi önerileri

**Files:**
- Modify: `app/src/screens/Composer.tsx`
- Modify: `app/src/screens/Composer.css`
- Modify: `app/src/screens/Composer.test.tsx`
- Modify: `app/src/App.tsx`

1. Testlerde ataç tıklaması, dosya seçimi, sürükle-bırak resim/dosya, `/m` ile MCP önerisi, tıklayınca yalnız input'a yazılması ve Enter ile çalışması senaryolarını oluştur.
2. Kırmızı test: `cd app && npm test -- src/screens/Composer.test.tsx`.
3. Sol taraftaki bağımsız `/` düğmesini kaldır; menüyü yazılan `/` önekine bağla. Kurulu olmayan sağlayıcılara ait `/resume…` komutlarını listeden filtrele.
4. Ataç düğmesini dosya diyaloguna, drop zone'u mevcut ek veri akışına bağla; desteklenmeyen veya çok büyük dosyada kullanıcıya görünür hata ver.
5. `Shift+Tab` ile mod geçişini focus textarea içindeyken de çalıştır; IME composition sırasında kısayolu devre dışı bırak.
6. Testler, `npm run build` ve ilgili Rust komut testlerini çalıştır.
7. Commit: `git add app/src/screens/Composer.tsx app/src/screens/Composer.css app/src/screens/Composer.test.tsx app/src/App.tsx && git commit -m "feat(app): composer ve komut önerilerini tamamla"`.

## Task 4: Görsel inceleme kapısı

**Files:**
- Modify: `app/e2e/visual-shell.visual.ts`
- Modify: `app/e2e/product-surfaces.visual.ts`
- Candidate snapshots: `app/e2e/*.visual.ts-snapshots/*`

1. Playwright sahnesine boş sohbet, dolu sohbet, açık komut menüsü ve ek önizlemesi durumlarını ekle.
2. `cd app && npm run test:visual -- --update-snapshots` ile aday görseller üret.
3. Aday PNG'leri kullanıcıya gerçek ekran görüntüsü olarak göster; karakter kırpılması, metin ritmi, composer ve sol panel için onay al.
4. Kullanıcı onaylamadan snapshot commit etme. İstenen düzeltmeleri aynı dilimde yapıp yeniden ekran görüntüsü üret.
5. Onaydan sonra `npm run test:visual` çalıştır ve commit et: `git commit -m "test(app): sohbet görsel sözleşmelerini yenile"`.
