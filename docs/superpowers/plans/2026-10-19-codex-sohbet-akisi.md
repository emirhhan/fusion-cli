# Codex referansına göre sohbet akışı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Kullanıcının iki ekran görüntüsündeki açık paragraf + kompakt işlem satırı + sonuç/dosya kartı düzenini Fusion sohbetine uygulamak.

**Architecture:** Modelin iş geçmişi korunur; görünür geçmiş sunumu araç sonuçlarını aynı canlı olay çözücüsüne taşır. Önceki WorkHistory toplaması kaldırılır. Dosya kartı yalnız başarılı araçların gerçek diff kayıtlarından beslenir; mevcut diff açma ve dosya açma eylemleri kullanılır, desteklenmeyen geri alma düğmesi uydurulmaz.

**Tech Stack:** Mevcut React/TypeScript, CSS tema tokenları, Python appserver ve FileTurnJournal; yeni bağımlılık yok.

**Spec:** Kullanıcının 19 Ekim 00:38:49 ve 00:39:01 tarihli Codex ekran görüntüleri ve “görünüm aynı codexte olduğu gibi olsun” talebi.

## Global Constraints

- Açıklamalar kapalı bir genel çalışma listesine dönüştürülmez.
- Araçlar küçük ikonlu, soluk ve ayrıntısı açılabilir satırlardır.
- Ana cevap/hatada mevcut erişilebilir eylemler korunur.
- Dosya adı/satır sayısı gerçek başarılı diff'ten gelir; başarısız işlem değişmiş dosya sayılmaz.
- Koyu/açık ve dar/geniş görünüm, klavye erişimi, taşma kontrol edilir.
- VFS-BOT kaynakları ve devam noktası değiştirilmez; iş başlatılmaz.

## Review Focus

- Araç sonrası ara açıklama ile son cevabın sırası ve ayrımı.
- Tek dosyaya birden fazla düzenleme, iki ayrı kullanıcı turu ve başarısız diff.
- Geçmişte eksik diff/bozuk argüman ile güvenli eski kayıt uyumu.
- Uzun dosya adları, kod blokları, dar pencere ve yeniden açılmış sohbet.
- Kopyala/değerlendir/yeni sohbette devam eylemlerinin orijinal mesajla ilişkisi.

## Uygulama

- [x] Backend: görünür geçmişe redakte edilmiş araç olayları; opsiyonel tool_diff alanının günlükte korunması. Önce regresyonlar.
- [x] UI: açık anlatım ve ikonlu kompakt işlem satırları; gerçek diff dosya özeti ve çalışan görüntüleme eylemi. Önce regresyonlar.
- [x] Geçmiş decoder'ı iki geri yükleme yolunda aynı olay akışını kullanır.
- [x] Görsel karşılaştırma, UI/Python kontrolleri ve bağımsız incelemeler.
- [x] Yeni yerel paket, imza/smoke kontrolü, yedekli kurulum ve çalışma zamanı doğrulaması.
