# Fusion tamamlama listesi — 25 Eylül 2026

Bu liste kullanıcı isteğinin kabul sözleşmesidir. Bir satırın kaynak kodda bulunması yeterli değildir; paketli uygulamada gerçek etkileşim ve davranış kanıtı gerekir.

| Alan | İş | Kabul kanıtı | Durum |
| --- | --- | --- | --- |
| Referans | Codex geniş/dar pencere; kenar çubuğu, başlık, sohbet, ayarlar, hesap, proje ve panel ekranlarının ölçümü | Aynı çözünürlükte referans ve Fusion görüntüleri, etkileşim notları | Kısmi: kullanıcının ekran kaydı ayarlar, hesap ve sol gezinmeyi gösteriyor; sohbet ve proje etkileşimlerinin tamamı görünmüyor |
| Yerleşim | Simge, düğme, boşluk, tipografi, dar ekran ve panel konumlarını düzelt | Görsel farklar ve çalışan kontroller | Kısmi: proje/sohbet seçenekleri fareyle üzerine gelince açılır |
| Hesap/ayar | Tüm menü hedefleri, kişiselleştirme, hafıza, model, izin ve tema | Paketli uygulamada aç/kaydet/yeniden aç akışları | Kısmi; yinelenen Hesap başlığı kaldırıldı |
| Sohbet | Mesaj, düşünme, durdurma, kod/diff, paylaşma, ekler | Gerçek tur ve erişilebilirlik kontrolü | Açık |
| Bağlam | Seçilen model zincirine göre özetleme bütçesi; gerçek token penceresi bilinmiyorsa belirsizliği göster | Farklı model pencereleri, yedek ve web modeli için davranış testleri | Kısmi; yerel model metadatası ve ortak sıkıştırma eşiği kullanılıyor, gerçek token sayımı yok |
| Projeler | Oluştur/taşı/sil, geçmiş ve veri korunumu | Yeniden başlatma sonrası aynı veri | Açık |
| Masaüstü | Kurulu uygulamaları listele/aç, pencereyi seç, erişilebilirlik ağacını oku, ekran görüntüsü, fare/klavye | İzinli uygulamada uçtan uca görev, reddedilen iznin açık hatası | Kod yok |
| Chrome | Kullanıcının mevcut sekmelerine site izniyle bağlan, yan panel, sekme/düğme/form/ekran/console/network | Kurulu Manifest V3 eklentisi ve paketli Fusion arasında gerçek Chrome oturumu | Kısmi; ayrı Playwright oturumunda sekme desteği var, Chrome eklentisi yok |
| Model/ajan | Canlı model, web modeli, öğretmen, alt ajan, `/btw` | Seçilen modelin gerçek çağrısı ve uzun görev etkisi | Kısmi; önceki uzun görev kabulü başarısız |
| Ses | Mikrofon, dikte, konuşma, kesme, yeniden başlatma | Fiziksel sesli paketli uygulama testi | Açık |
| Güvenilirlik | Olumlu işlev ve olumsuz güvenlik kabulü, bağımsız inceleme | Korunan testler, son düzenleme sonrası test/build | Başarısız |
| Dağıtım | Taze `.app`/DMG, veri koruyan kurulum, eski paket temizliği, GitHub release | Paketli uygulama ve indirilebilir artefakt | Kapalı |

## 25 Eylül uygulama notu

Mevcut Fusion tarayıcısı tur başına tek Playwright sayfası açıyordu. Aynı oturumda sekme listeleme, seçme ve açma eklendi; sayfalar ortak bağlam kullanır. Bu özellik Claude in Chrome eşdeğeri değildir: kullanıcının açık Chrome profilini veya eklenti yan panelini kontrol etmez. Codex'in gerçek uygulamasına UI otomasyon aracı tarafından erişim reddedildiğinden ölçülmemiş piksel değerleri kabul edilmiş tasarım kararı sayılmaz.

## Ekran kaydı gözlemi

Kullanıcının `chatgpt ekran kaydı.mov` dosyası 116 saniyelik bir masaüstü ekran kaydıdır. Kaydın büyük bölümü koyu temada ayarların Genel, Profil, Görünüm, Ses, Kişiselleştirme, Tarayıcı, Bağlantılar ve arşiv bölümlerini gösterir. Sol ayar gezinmesi ve ana içerik sütunu için yerleşim referansı sağlar. Kullanıcı ayrıca proje satırındaki üç noktanın yalnız üzerine gelince belirdiğini açıkça belirtti; Fusion'da bu davranış eklendi. Kayıt dar/geniş sohbet penceresinin bütün durumlarını ve Chrome eklentisiyle gerçek etkileşimi göstermediği için ilgili kabul satırları açık kalır.
