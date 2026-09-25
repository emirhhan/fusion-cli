# Fusion tamamlama listesi — 25 Eylül 2026

Bu liste kullanıcı isteğinin kabul sözleşmesidir. Bir satırın kaynak kodda bulunması yeterli değildir; paketli uygulamada gerçek etkileşim ve davranış kanıtı gerekir.

| Alan | İş | Kabul kanıtı | Durum |
| --- | --- | --- | --- |
| Referans | Codex geniş/dar pencere; kenar çubuğu, başlık, sohbet, ayarlar, hesap, proje ve panel ekranlarının ölçümü | Aynı çözünürlükte referans ve Fusion görüntüleri, etkileşim notları | Kısmi: kullanıcının ekran kaydı ayarlar, hesap ve sol gezinmeyi gösteriyor; sohbet ve proje etkileşimlerinin tamamı görünmüyor |
| Yerleşim | Simge, düğme, boşluk, tipografi, dar ekran ve panel konumlarını düzelt | Görsel farklar ve çalışan kontroller | Kısmi: proje/sohbet seçenekleri fareyle üzerine gelince açılır; ayar gezintisi videodaki koyu renk, ikon ve grup düzenine yaklaştırıldı |
| Hesap/ayar | Tüm menü hedefleri, kişiselleştirme, hafıza, model, izin ve tema | Paketli uygulamada aç/kaydet/yeniden aç akışları | Kısmi; yinelenen Hesap başlığı kaldırıldı, ayarlar video referansındaki tam sayfa düzenine taşındı; tüm video bölümleri işlevsel eşdeğer değil |
| Sohbet | Mesaj, düşünme, durdurma, kod/diff, paylaşma, ekler | Gerçek tur ve erişilebilirlik kontrolü | Açık |
| Bağlam | Seçilen model zincirine göre özetleme bütçesi; gerçek token penceresi bilinmiyorsa belirsizliği göster | Farklı model pencereleri, yedek ve web modeli için davranış testleri | Kısmi; yerel model metadatası, seçili zincire göre özetleme eşiği ve son çağrının ölçülmüş girdi tokenı var; doğrulanmış pencere varsa son çağrı yüzdesi ayrıca gösteriliyor; mevcut geçmişin tam token sayımı yok |
| Projeler | Oluştur/taşı/sil, geçmiş ve veri korunumu | Yeniden başlatma sonrası aynı veri | Açık |
| Masaüstü | Kurulu uygulamaları listele/aç, pencereyi seç, erişilebilirlik ağacını oku, ekran görüntüsü, fare/klavye | İzinli uygulamada uçtan uca görev, reddedilen iznin açık hatası | Kısmi; uygulama, pencere, erişilebilir öğe, görüntü, fare ve klavye araçları kaynakta; paketli canlı kabul yok |
| Chrome | Kullanıcının mevcut sekmelerine site izniyle bağlan, yan panel, sekme/düğme/form/ekran/console/network | Kurulu Manifest V3 eklentisi ve paketli Fusion arasında gerçek Chrome oturumu | Kısmi; Manifest V3 yan panel ve anahtarlı yerel köprü, izinli tek sekmede okuma/tık/yaz/gezin/görüntü kaynakta ve pakette; canlı Chrome kabulü, console/network ve çoklu sekme yönetimi yok |
| Model/ajan | Canlı model, web modeli, öğretmen, alt ajan, `/btw` | Seçilen modelin gerçek çağrısı ve uzun görev etkisi | Kısmi; önceki uzun görev kabulü başarısız |
| Ses | Mikrofon, dikte, konuşma, kesme, yeniden başlatma | Fiziksel sesli paketli uygulama testi | Açık |
| Güvenilirlik | Olumlu işlev ve olumsuz güvenlik kabulü, bağımsız inceleme | Korunan testler, son düzenleme sonrası test/build | Başarısız |
| Dağıtım | Taze `.app`/DMG, veri koruyan kurulum, eski paket temizliği, GitHub release | Paketli uygulama ve indirilebilir artefakt | Kapalı |

## 25 Eylül uygulama notu

Mevcut Fusion tarayıcısı tur başına tek Playwright sayfası açıyordu. Aynı oturumda sekme listeleme, seçme ve açma eklendi; sayfalar ortak bağlam kullanır. Ayrıca kullanıcının mevcut Chrome sekmesine bağlanan eklenti ve yerel köprü yazıldı. Eklenti yüklenip paketli uygulamada gerçek sekme akışı sınanana kadar Claude in Chrome eşdeğeri olarak kabul edilmez. Codex'in gerçek uygulamasına UI otomasyon aracı tarafından erişim reddedildiğinden ölçülmemiş piksel değerleri kabul edilmiş tasarım kararı sayılmaz.

## Ekran kaydı gözlemi

Kullanıcının `chatgpt ekran kaydı.mov` dosyası 116 saniyelik bir masaüstü ekran kaydıdır. Kaydın büyük bölümü koyu temada ayarların Genel, Profil, Görünüm, Ses, Kişiselleştirme, Tarayıcı, Bağlantılar ve arşiv bölümlerini gösterir. Sol ayar gezinmesi ve ana içerik sütunu için yerleşim referansı sağlar. Kullanıcı ayrıca proje satırındaki üç noktanın yalnız üzerine gelince belirdiğini açıkça belirtti; Fusion'da bu davranış eklendi. Kayıt dar/geniş sohbet penceresinin bütün durumlarını ve Chrome eklentisiyle gerçek etkileşimi göstermediği için ilgili kabul satırları açık kalır.
