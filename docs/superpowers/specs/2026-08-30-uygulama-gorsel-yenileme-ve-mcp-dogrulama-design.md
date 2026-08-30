# Fusion Uygulama Görsel Yenilemesi ve MCP Doğrulaması

**Tarih:** 30 Ağustos 2026

**Durum:** Kullanıcı incelemesi

**Kapsam:** Sohbet, sol kenar çubuğu, sağ çalışma paneli, Fusion karakteri,
yerel profil ve MCP bağlantı sağlığı

## 1. Amaç

Fusion'ın mevcut Tauri, React ve Python mimarisini koruyup masaüstü deneyimini
profesyonel bir agent çalışma alanına dönüştüreceğiz. Uygulama, verilen ChatGPT
UI Kit'in sakin sohbet dilini ve güncel Codex uygulamasının dosya, terminal ve
önizleme düzenini Fusion'ın işlevleriyle birleştirecek.

Bu çalışma yalnız görünümü değiştirmeyecek. MCP satırları gerçek bağlantıyı
kanıtlayacak; terminal ve önizleme panelleri günlük kullanıma uygun olacak;
bağlantılar yerel profil yüzeyinden yönetilecek.

## 2. Başarı ölçütleri

- Sohbet merkezinde ve ses modunda son onaylanan beyaz, siyah ve sinyal yeşili
  Fusion karakteri görünür. Karakterin kulakları, gölgesi ve hareket alanı hiçbir
  pencere boyutunda kırpılmaz.
- Kullanıcı mesajı sağda açık gri balon, Fusion yanıtı balonsuz metin akışı olur.
- Sağ panel dosya, değişiklik, terminal, süreç, test, önizleme ve bağlam
  yüzeylerini ortak bir çalışma alanında sunar.
- Terminal birden fazla oturumu sekmelerle yönetir; çıktı panelin kalan
  yüksekliğini kullanır.
- Yerel web önizlemesi adres, geri, ileri, yenile, harici açma ve ekran boyutu
  kontrolleri taşır. Dosya önizlemesi aynı panel kabuğunu kullanır.
- Sol kenar çubuğu açık ve koyu temada sakin, katmanlı ve hafif yarı saydam
  görünür. Geçmiş varsayılan açık kalır ve daraltılabilir.
- Profil satırı yerel kullanıcı adını, bağlı sağlayıcı sayısını ve bağlantı
  yönetimini açar. Fusion bulut hesabı varmış gibi davranmaz.
- MCP bağlantısı ancak gerçek protokol el sıkışması ve `tools/list` başarılıysa
  **Bağlı** görünür. Arayüz araç sayısını, son kontrol zamanını ve sade hata
  mesajını gösterir.
- Her görsel dilim geniş, dar ve ilgiliyse koyu tema ekran görüntüsüyle kullanıcı
  incelemesine sunulur.
- Üç platform kurucusu ancak işlevsel, görsel ve paketleme kapıları geçtikten
  sonra yayımlanır.

## 3. Tasarım yönü

### 3.1 Amaç ve kullanıcı

Ana kullanıcı kodlama bilmeden proje üreten gençtir. İlk bakışta sohbet ve yeni
görev anlaşılır olmalıdır. Dosya, terminal, test ve MCP ayrıntıları aynı ekranda
bulunmalı, fakat ana konuşmayı boğmamalıdır.

### 3.2 Ton

Arayüz sakin, teknik ve rafine olacaktır. Glossy görünüm yalnız sol panelin
katmanını ve Fusion karakterinin ışığını güçlendirecek. Renkli gradyanlar,
iç içe kartlar, büyük tanıtım başlıkları ve dekoratif parlamalar kullanılmayacak.

### 3.3 Hatırlanabilir ayrıntı

Fusion karakterinin sinyal yeşili yüzü uygulamanın canlı durum göstergesidir.
Karakter; bekleme, çalışma, konuşma, başarı ve onay durumlarında ifade değiştirir.
Yeşil renk büyük yüzeyleri boyamaz; karakterde, küçük durum noktalarında ve
ses dalgasında kalır.

## 4. Görsel kaynaklar ve karakter sistemi

Son kullanıcı referansı
`/Users/motogate/Downloads/fusiontalkingtype.png` içindeki parlak beyaz gövdeli,
siyah ekran yüzlü ve yeşil ışıklı robottur. Depodaki eski 168 × 168
`Fusion_Pixel_Expressions_Clean_v2` kareleri ana sohbet karakteri olmaktan
çıkarılacaktır.

Referanstan aşağıdaki şeffaf, yüksek çözünürlüklü varlıklar hazırlanacaktır:

- `idle`: nötr dikey gözler;
- `thinking`: odaklı/eğik gözler;
- `talking-a` ve `talking-b`: doğal konuşma döngüsü;
- `happy`: kavisli mutlu gözler;
- `approval`: dikkatli ifade;
- `blink`: kısa göz kırpma.

Her kare aynı tuval, optik merkez ve gölge tabanını kullanır. Tuval, gövdenin
iki yanında en az yüzde 12 saydam güvenlik boşluğu bırakır. React bileşeni
`object-fit: contain` kullanır; sabit kırpma maskesi veya taşan negatif kenar
boşluğu kullanmaz. Küçük görünümlerde ayrı kırpılmış dosya yerine aynı kaynak
ölçeklenir.

## 5. Ana kabuk ve duyarlı düzen

Geniş masaüstü düzeni üç sütundur:

| Bölge | Varsayılan ölçü | Davranış |
|---|---:|---|
| Sol kenar çubuğu | 280 px | 72 px ikon şeridine daralır |
| Sohbet | kalan alan | içerik sütunu en fazla 820 px |
| Sağ çalışma paneli | 420 px | 320–680 px arasında yeniden boyutlanır |

1200 piksel altında sol panel ikon şeridine iner. 1024 piksel altında sağ panel
ana alanın üstüne açılır. Sağ panelin son genişliği ve açık sekmesi yerel görünüm
tercihi olarak saklanır. Sohbet içeriği panel açılırken genişlik sıçraması yapmaz;
en fazla genişlik ve yatay boşluk yumuşak geçişle değişir.

## 6. Sohbet ve görev akışı

### 6.1 Mesajlar

- Kullanıcı mesajı sağa yaslanır; `#F5F5F5` yüzey, 18 px köşe ve içerik kadar
  genişlik kullanır.
- Fusion yanıtı balonsuzdur. Paragraflar, listeler, kod ve alıntılar 760–820 px
  okuma sütununda akar.
- Kopyala, yeniden dene ve geri bildirim eylemleri mesajın altında, düşük
  kontrastlı ikonlarla görünür.
- Araç çağrıları sohbet balonuna dönüşmez. Plan, okunan dosya, komut, değişiklik
  ve test kanıtları tek satırlık açılır çalışma bloklarıdır.
- Başarılı bloklar kısa özetle kapanır. Hata ve kullanıcı onayı açık kalır.

### 6.2 Boş durum

Boş konuşmada yüksek çözünürlüklü `idle` karakteri, kısa başlık ve üç gerçek
başlangıç önerisi bulunur. Karakter mevcut `FusionAvatar` durumunu izler.
Çalışma başladığında `thinking`, yanıt okunurken `talking`, görev tamamlanınca
`happy` görünür.

### 6.3 Girdi alanı

Composer ChatGPT referansındaki iki katmanlı düzene yaklaşır:

- üst satırda büyüyen metin alanı;
- alt solda ataç, komutlar ve bağlam;
- alt ortada kip, izin ve model;
- alt sağda mikrofon ile gönder/durdur düğmesi.

`/` için ayrı, açıklamasız metin düğmesi gösterilmez. Kullanıcı `/` yazınca
komut ve kurulu MCP önerileri açılır. Ataç, sürükle-bırak ve görsel küçük
önizlemeleri aynı ek bileşeninde birleşir. `Shift+Tab` izin kipini değiştirmeye
devam eder.

## 7. Sağ çalışma paneli

### 7.1 Panel kabuğu

Panelin üst çubuğunda etkin yüzey adı, ilgili proje/oturum ve üç eylem bulunur:
daralt, ayrı alanda büyüt ve kapat. Sekmeler ikonla birlikte kısa metin taşır;
dar genişlikte yalnız ikon ve erişilebilir açıklama kalır.

Sekmeler:

- Dosyalar
- Değişiklikler
- Terminal
- Süreçler
- Testler
- Önizleme
- Bağlam

### 7.2 Terminal

Terminal yüzeyi tek komut formu ve tek siyah kutu olmaktan çıkar:

- üstte terminal oturum sekmeleri ve `+` düğmesi;
- sekmede çalışma dizini, çalışan/bitti durumu ve kapatma eylemi;
- gövdenin tamamında kaydırılabilir monospace çıktı;
- altta odaklı komut satırı;
- komut çalışırken durdur, tamamlanınca yeniden çalıştır ve çıktıyı kopyala;
- hata durumunda çıkış kodu ve son anlamlı satır.

Python süreç yöneticisi oturumların sahibi kalır. React, kabuk veya süreç
mantığını kopyalamaz.

### 7.3 Önizleme

Önizleme iki kaynağı ortak kabukta gösterir:

1. Proje ağacından seçilen görsel, ses, video, PDF, HTML veya metin dosyası.
2. Yalnız `localhost`, `127.0.0.1` veya `::1` üzerindeki geliştirme sunucusu.

Araç çubuğu adres, geri, ileri, yenile, harici aç, masaüstü/tablet/mobil genişlik
ve paneli büyüt eylemlerini taşır. Localhost iframe mevcut güvenli sandbox
sınırlarını korur. Dosya önizlemesi dosya adı, tür, boyut ve proje içi yolu
gösterir.

## 8. Sol kenar çubuğu ve yerel profil

Sol panel `#F9F9FA` tabanı üzerinde ince iç kenar ışığı, düşük opaklıklı yüzey
katmanı ve gerekirse macOS bulanıklığı kullanır. Metin kontrastı ve seçili satır
Figma ölçülerini korur. Glossy etki gezinme öğelerinin okunmasını azaltmaz.

Alt bölüm şu sırayı kullanır:

1. Beceriler ve Ajanlar
2. Dersler
3. Kontrol Paneli
4. Ayarlar
5. Yerel profil satırı

Profil satırı avatar/baş harf, yerel görünen ad ve bağlı bağlantı sayısını
gösterir. Açılan **Hesap ve bağlantılar** yüzeyi şunları birleştirir:

- yerel görünen ad ve avatar;
- API anahtarlı sağlayıcılar;
- ChatGPT, Claude, Gemini ve Copilot web oturumları;
- bağlı MCP sayısı;
- yerel veri ve gizlilik özeti.

Bu sürüm Fusion bulut hesabı, parola, e-posta doğrulama veya uzaktan eşitleme
sunmaz. Gerçek bir kimlik sunucusu kurulmadan “Fusion'a giriş yap” düğmesi
gösterilmez. Sağlayıcı girişleri kendi gerçek akışlarını kullanır.

## 9. MCP bağlantı sağlığı

### 9.1 Durum modeli

Her MCP satırı şu durumlardan birini taşır:

- `yapilandirildi`: config kaydı var, henüz sınanmadı;
- `kontrol_ediliyor`: alt süreç başlatıldı;
- `bagli`: initialize ve `tools/list` başarılı;
- `hata`: süreç, protokol veya zaman aşımı hatası;
- `kapali`: bu oturumda kullanıcı kapattı.

**Bağlı** etiketi yalnız gerçek `McpClient` bağlantısından sonra kullanılır.
Profil klasörü, config satırı veya çalışan PID bağlantı kanıtı sayılmaz.

### 9.2 Protokol

Python uygulama protokolüne iki işlem eklenir:

- `baglanti.dogrula({ ad })`: yapılandırılmış sunucuyu en fazla 10 saniye içinde
  başlatır, MCP initialize yapar, araçları listeler ve bağlantıyı kapatır.
- `baglanti.durum({ ad? })`: bu uygulama oturumundaki son doğrulama sonucunu
  döndürür.

Başarılı yanıt sunucu adı, araç sayısı, araç adlarının sınırlı özeti, protokol
bilgisi ve kontrol zamanını taşır. Hata yanıtı kullanıcıya uygun kısa açıklama,
hata sınıfı ve yeniden deneme imkânı taşır. Ortam değişkenleri, anahtarlar ve
tam süreç ortamı protokol yanıtına veya loga girmez.

Yeni MCP komutu eklenirken uygulama çalıştırılacak komutu açıkça gösterir.
Kullanıcı onayladıktan sonra config atomik yazılır ve ilk doğrulama başlar.
Doğrulama başarısız olsa da kayıt korunur; kullanıcı komutu düzeltebilir veya
kaldırabilir.

### 9.3 Agent kullanımı

Mevcut agent bağlantı yolu korunur. Regresyon testi, doğrulanan MCP aracının
gerçek bir agent turunda araç kataloğuna girdiğini kanıtlar. Ayarlar ekranındaki
yeşil durum ile agent'ın kullandığı sunucu aynı kanonik config kaydından gelir.

## 10. Hata ve boş durumlar

- Karakter varlığı yüklenemezse düzen çökmez; Fusion logosu ve kısa hata metni
  görünür.
- Terminal süreci kapanırsa sekme kaybolmaz; çıkış kodu ve yeniden çalıştır
  eylemi kalır.
- Localhost önizlemesi yanıt vermezse iframe yerine yeniden dene ve süreçlere
  git eylemleri görünür.
- MCP zaman aşımında “Bağlı” durumu korunmaz. Satır “Zaman aşımı” ve “Tekrar
  dene” gösterir.
- Sağ panel içeriği dar genişlikte yatay taşmaz; gerekli alan kendi içinde
  kaydırılır.
- Profil ve bağlantı ekranı ağ yokken yerel tercihleri açmaya devam eder.

## 11. Ekran görüntüsü ve kullanıcı inceleme kapısı

Her görsel dilim şu sırayla ilerler:

1. Bileşen ve davranış testleri geçer.
2. Playwright gerçek yüzeyi 1440 × 960 açık tema, 1024 × 768 dar düzen ve
   gerekli yüzeylerde koyu tema olarak çeker.
3. Ekran görüntüleri kullanıcıya mutlak dosya bağlantılarıyla gönderilir.
4. Kullanıcı düzeltme isterse görsel referans dosyaları güncellenmez.
5. Kullanıcı onayladıktan sonra kalıcı görsel regresyon referansları yenilenir.

Görsel dilimler:

1. karakter ve boş sohbet;
2. konuşma akışı ve composer;
3. sağ panel kabuğu, terminal ve önizleme;
4. glossy sol panel ile profil;
5. MCP bağlantı yönetimi;
6. ses penceresi.

## 12. Doğrulama

### React ve erişilebilirlik

- Mesaj hiyerarşisi, composer, duyarlı panel ve profil etkileşimleri Vitest ile
  sınanır.
- Sekmeler ok tuşları, Home ve End ile çalışır.
- Görünür metin, ikon açıklamaları, odak sırası ve renk kontrastı denetlenir.
- Playwright tüm görsel dilimleri açık, koyu ve dar düzenlerde karşılaştırır.

### Python ve MCP

- MCP doğrulaması gerçek stdio alt süreç sunucusuyla başarı, süreç hatası,
  geçersiz JSON, zaman aşımı ve sıfır araç durumlarında sınanır.
- Agent turunun doğrulanmış MCP aracını gerçekten gördüğü mevcut uçtan uca test
  genişletilir.
- Config eşzamanlı yazım, sır sızdırmama ve oturumluk kapatma testleri korunur.

### Native uygulama

- Paketli macOS uygulamasında dosya seçme, sürükle-bırak, terminal, localhost
  önizleme, panel yeniden boyutlandırma ve ses penceresi elle/otomasyonla
  doğrulanır.
- Windows WebView katmanı Playwright ile; NSIS kurulumu ve native çalışma zamanı
  temiz Windows CI makinesinde sınanır.
- Apple Silicon, Intel macOS ve Windows paketleri mimari ve çalışma zamanı smoke
  testlerini geçer.

## 13. Kapsam dışı

- Fusion'a ait bulut kimlik sunucusu, e-posta/parola üyeliği ve cihazlar arası
  eşitleme;
- dış internet sitelerini sınırsız iframe içinde açma;
- tam IDE kod editörü veya terminal emülatörünü sıfırdan yazma;
- mevcut CLI, `fusion serve` veya Python iş kurallarını React içinde yeniden
  uygulama;
- Apple Developer hesabı ve notarization.

## 14. Yayın kapısı

Yayın için aşağıdakilerin tümü gerekir:

- kullanıcı altı görsel dilimi ekran görüntüsüyle onayladı;
- React, TypeScript, Rust, Python ve görsel regresyon kapıları geçti;
- gerçek MCP doğrulama ve agent kullanım testleri geçti;
- Apple Silicon DMG, Intel DMG ve Windows NSIS kurucusu temiz CI'da üretildi;
- GitHub Release üç kurucuyu anlaşılır adlarla yayımladı;
- imzasız macOS ve Windows ilk açılış yönergeleri sürüm notunda yer aldı.
