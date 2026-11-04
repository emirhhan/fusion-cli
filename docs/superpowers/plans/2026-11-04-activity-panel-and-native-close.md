# İşlem paneli ve yerel kapatma uygulama planı

> **For agentic workers:** Use superpowers:subagent-driven-development with the already authorized delegated workflow.

**Goal:** Kullanıcının istediği iki satırlık açılır işlem görünümü, kendi içinde kayan ayrıntı paneli ve anında yerel kapatma davranışı.
**Architecture:** Conversation turu seviyesinde etkinlik projeksiyonu; mevcut ToolTrail/StepDetail ayrıntıları. Tauri ana pencere CloseRequested olayı mevcut sınırlı temizlik yolunu doğrudan başlatır.
**Tech Stack:** React, TypeScript, CSS, Playwright, Vitest, Rust, Tauri.
**Spec:** docs/superpowers/specs/2026-11-04-activity-panel-and-native-close-design.md

## Global Constraints
Inter 16px/24px korunur. Araç izinleri ve asıl yürütme değişmez. Aktif onay/soru kartları panelde gizlenmez. Diğer çalışanların düzenlemeleri geri alınmaz.

## Review Focus
Yeni mesaj/akış mevcut açılmış ayrıntıyı kaybetmemeli. Ayrı sohbetlerde eş indeksler durum sızdırmamalı. Panel açmak ana sohbeti otomatik alta çekmemeli. Panel sınırında tekerlek sohbeti kaydırmamalı. Yerel kapatma donmuş UI veya yinelenen olayda takılmamalı.

### 1. İşlem paneli
- [ ] Conversation, ActivityLine/ToolTrail ve useStickToBottom arayüzlerini izleyerek panel birimini ayır.
- [ ] Bir/iki/çok adım, üçüncü adımın akışta gelişi, seçilen kod/çıktı, sohbet değişimi ve onay kartları için davranış testini önce başarısız gör.
- [ ] Kullanıcı turu seviyesinde en fazla iki görünür işlem; çok işlemde seçilen dahil tüm satırları iç kaydırılan panele taşı. Mevcut ayrıntı çizimini tekrar kullan.
- [ ] Panel etkileşiminde otomatik ana sohbet kaydırmasını durdur; normal yeni mesaj gönderme davranışını koru.
- [ ] Gerçek tarayıcıda iç tekerlek/sınır kaydırmasını doğrula; dar ve açık/koyu görünümü kontrol et.
- [ ] Odaklı testler, tsc, hooks lint; izole commit ve React/TypeScript/genel inceleme.

### 2. Kırmızı düğme
- [ ] lib.rs/kapanis.rs mevcut onay ve temizleme zincirinde ana pencere kırmızı düğme rotasını yeniden üret.
- [ ] Yerel kapanışın UI onayı beklememesi ve yinelenen olayda tek temizlik için başarısız test yaz.
- [ ] Yerel pencereyi hemen gizleyip sınırlı ve idempotent tam uygulama temizliğini başlat; diğer pencere kapsamlarını koru.
- [ ] Rust test/check/clippy ve bağımsız Rust/genel inceleme.

### 3. Paket ve gerçek kullanım
- [ ] İncelenmiş backend düzeltmelerini runtime paketine al; protokol/bütünlük doğrula.
- [ ] İncelenmiş UI/Rust kaynaklarını asıl depoya uygula; uygulamayı derle ve kararlı imzayı doğrula.
- [ ] Eski uygulamayı yedekleyerek kur. İşlem paneli, font, kırmızı düğme ve yeniden açılma kabulünü yap.
- [ ] Son rapor, kaynak yaması ve güncel ZIP bütünlük kaydını yenile.
