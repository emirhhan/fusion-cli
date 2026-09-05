# Genel agent güvenilirliği

Kullanıcı 5 Eylül 2026 tarihinde analizdeki bütün geliştirme ve teslim fazlarını onayladı. Hedef genel amaçlı Fusion'dır; Godot yalnız kabul alanlarından biridir. Başlangıç HEAD: `8882baa`.

## Ortak sözleşme

Mevcut agent, provider, MCP, plan ve checkpoint altyapısı genişletilir. İkinci agent motoru kurulmaz. Web/API modelleri aynı araç sonuçlarını tüketir; desteklemedikleri içerik sessizce kaybolmaz. Metin, görsel, yapılandırılmış sonuç ve kaynak bağlantısı çekirdek tiplerle taşınır. Sağlayıcı sınırında uygun biçime dönüştürülür. Web görsel desteği için mevcut yapılandırılmış vision yolu kullanılabilir; yoksa açık yetenek eksikliği bildirilir, görsel görülmüş gibi davranılmaz.

## Kanıt

Araç çağrısı görev başarısı değildir. Başarı koşulları tipli kontrollerle bağlanır: dosya içeriği/yapısı, gerçek komut sonucu, yapılandırılmış araç sonucu ve gözlem. Tanımlı test çalıştırılmış test sayılmaz. Eksik kontrol doğrulanamadı sonucudur; açıkça bozuk koşul başarısızdır. Öznel kalite model değerlendirmesiyle desteklenebilir ama mekanik kanıt olarak sunulmaz. Adım sırasında henüz kurulmamış projenin final koşulları bütün ilerlemeyi kilitlemez.

## Kurtarma ve devam

Final hatası ilişkili adımları yeniden açan sınırlı onarıma gider. Yan etkileri tekrar güvenliğiyle koru; OBSERVE_FIRST ayrı salt okunur gözlem olmalıdır. Checkpoint plan, ölçüm kanıtları, artifact/sürüm ve bütçe durumunu saklar. Eski çalışma alanı durumuna ait kanıt körlemesine kullanılmaz. Araç ailesi sınırı gerçek çağrı yolunda uygulanır; ortak onay politikaları korunur.

## Bilgi erişimi

Skill seçimi, kısa özet ve talep üzerine tam içerik aynı registry üzerinden yürür. Modelin gerekli aracı bulabilmesi ve kullanılan bilgiye dair gözlem üretmesi sınanır. Büyük skill ithalatı bu çalışmanın ön koşulu değildir. Zorunlu ölçülebilir koşullar yalnız prompt metnine bırakılmaz.

## Ölçüm ve teslim

Önce bilinen hataları ağsız gerçek bileşen testleriyle tekrar üret. Her davranış RED/GREEN ile düzeltilir. Çok dosyalı kod, tarayıcı, yapılandırılmış veri MCP'si ve görsel uygulama alanında kabul ölçümleri yapılır. Canlı koşularda seçilen gerçek sağlayıcı, kod revizyonu, başarı/başarısızlık, süre, araç sayısı ve insan düzeltmesi kaydedilir. İnsan tarafından tamamlanan çıktı otonom başarı değildir.

Her faz ruff format/check, mypy, pytest ve mevcut deadlock kapısını geçip ayrı commit alır. Ardından masaüstü kapıları, runtime arşivi, uygulama/DMG ve kurulu paket hash eşleşmesi doğrulanır. Model eşitliği veya tüm görevlerde kusursuzluk iddiası yapılmaz; ölçülmüş sonuç teslim edilir.

## Yetki ve çalışma sınırı

Onay mevcut depoda geliştirme, yerel testler, gerekli model denemeleri ve yerel paket/kurulumu kapsar. Kullanıcı dosyalarını veya önceki oyunları silme; temiz denemeler geçici/ayrı alanlarda yapılır. Depo `.env` içeriği okunmaz/yazdırılmaz; normal config yükleyicisi sırları kendi içinde kullanabilir. Reklam, ödeme, mesaj gönderme gibi gerçek dış etkiler kabul deneyi değildir. Mevcut dal korunur; paylaşılan remote'a push bu teslimin gereği değildir.
