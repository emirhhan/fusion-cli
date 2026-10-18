# Fusion proje, görünüm ve yerel model düzenlemesi

## Kullanıcının istediği sonuç

- Ad ve klasör seçilerek oluşturulan proje hemen o klasörde açılır. Projenin yanındaki + aynı proje içinde yeni ve boş bir sohbet açar.
- Home ve diğer yerel ekranların font, boyut, zemin ve sidebar renkleri Kits ile aynı olur. Sidebar'ın mevcut işlevleri korunur; eşdeğer öğeler Kits'teki üst/alt konumlarına getirilir.
- En soldaki bölüm şeridi gönderilen Codex görüntüsü gibi dar ve yalnız ikonlardan oluşur. Etiketler fareyle üzerine gelince veya klavye odağında görünür. Kullanıcının ek düzeltmesi: hesap menüsü bu ince şeridin en altında olacak, sohbet listesinin altında olmayacak.
- Seslendirme emojileri okumaz. Sohbetin görünen metni korunur.
- Kits'in gezinmedeki kaynak/lisans tanıtım alanı kaldırılır.
- Bazı sohbet tablolarının hatalı görünümü araştırılır ve örnekle doğrulanarak giderilir.
- Huihui-Qwen3.5-9B-abliterated yerel olarak Fusion'da kullanılabilir hale getirilir.

## Doğrulanan mevcut durum

`SessionApplication.tsx` içindeki `onProjectCreate` yalnız proje kaydını oluşturuyor; sohbet oluşturma veya etkin klasörü değiştirme yapmıyor. Kullanıcının Desktop'ta kalma bildirimi bu yolla açıklanıyor.

Proje satırının + düğmesi `project-id:` veya `project:` hedefine gidiyor. İlk yol kayıtlı klasörde sohbet oluşturmayı zaten deniyor. Bunun hata nedeni henüz doğrulanmadı; hatayı genel mesajla gizleyen catch yerine kullanıcıya anlamlı ayrıntı gösterilmeli ve gerçek klasör/süreç hatası yeniden üretilmeli. Kök neden kanıtlanmadan düzeldi denmeyecek.

`voice_text.prepare_speech` Markdown ve sayıları hazırlıyor fakat emoji temizlemiyor. Hem `speak` hem `prepare_voice` bu ortak yolu kullanıyor.

`MainRail` 76 px genişliğinde ve görünür metin etiketleri taşıyor. Mevcut tema renklerinden bağımsız koyu renkler kullanıyor.

Home token dosyasındaki son kural sistem fontuna geçiyor; Kits'in son etkin stili Inter kullanıyor. Kits stil sırası `style.css`, `kits.css`, `kits-dark.generated.css`, `fusion-brand.generated.css`; eşleştirme ilk dosyadaki değerlerden değil, hesaplanmış stillerden yapılmalı.

Tablolar GFM lexer ile çiziliyor. CSS tüm tabloları en az 700 px genişletiyor ve ilk sütunu satır kırmadan gösteriyor. Bu bir dar ekran adayıdır; kullanıcının asıl bozuk tablosu henüz verilmedi. HTML hücrelerindeki satır sonları ve akış sırasında tamamlanmamış Markdown da ayrı doğrulanacak.

Mac arm64 ve 16 GiB belleğe sahip. Ollama kurulu bulunmadı. Model kartı doğrudan `huihui_ai/qwen3.5-abliterated:9b` Ollama etiketini yayımlıyor. Fusion sağlayıcı kaydında `ollama` ve `ollama_chat` zaten var; gerçek bağlantı henüz denenmedi.

Kurulu Fusion.app'in Kits paketi, mevcut kaynakla aynı değil: kurulu pakette `Kaynak ve lisans` bağlantısı CopilotKit/OpenDots'a gidiyor; güncel kaynakta aynı yerde `Fusion kaynakları` var. Kullanıcının gördüğü alan böylece tespit edildi. Çözüm yalnız kaynak düzenlemesiyle bırakılmayacak; güncel Kits çıktısının yeni Fusion paketine girdiği doğrulanacak.

Yayıncının Ollama model sayfası 9b etiketini Q4_K_M ve 6.6 GB olarak listeliyor (2026-10-18 kontrolü). Bu indirme boyutudur, toplam çalışma belleği değildir.

## Uygulama kararları

### Proje ve sohbet

Kayıt oluşturma ile ilk sohbet açma tek kullanıcı akışı olacak. Klasör seçilmişse ilk sohbet bu klasörde oluşturulacak, proje kimliğine atanacak ve Home sohbet ekranı açılacak. Klasörsüz projeler mevcut Desktop davranışını koruyabilir; ekranda bunun çalışma klasörü olduğu açık olmalı. Klasör açılması başarısızsa mevcut sohbet korunacak ve yeni sohbet başka klasörde sessizce açılmayacak. Oluşturulan proje kaydı hatadan sonra tekrar denenebilir kalacak; kullanıcı aynı adla ikinci kayıt oluşturmaya zorlanmayacak.

Proje + akışı yeni bir sohbet kimliği üretecek, kayıtlı kökü kullanacak ve projeye atayacak. Geçersiz/silinmiş klasör veya çekirdek başlatma hatası görünür olacak. Başarılı akışta Desktop yerine gerçek klasör ve kullanıcı proje adı gösterilecek.

### Görünüm

Tasarım tercihi: bölüm şeridi 52 px, düğmeleri 40 px olacak; tüm ekranlarda aynı genişlik kullanılacak. Etiketler ikon altında yer tutmayacak. Düğmeler erişilebilir adlarını koruyacak; tooltip hem hover hem focus ile açılacak ve ekran kenarında kırpılmayacak. macOS pencere kontrolleriyle çakışma görsel testte kontrol edilecek.

Kits'in etkin açık/koyu tema stilleri ölçülüp Home'un ortak tokenlarına uygulanacak; font Inter olacak. Sidebar içindeki işlev listesi korunacak. Marka/yeni sohbet üstte, proje/geçmiş kaydırılabilir ortada, hesap/ayar alt işlevleri altta kalacak; Kits'teki eşdeğer konumlar esas alınacak. Başlık ve eylem satırları gereksiz boşluğu azaltacak. Mobil ve dar pencere davranışları korunacak.

Kits gezinmesindeki `Fusion kaynakları` bağlantısı kaldırılacak. Çalışan pakette görünen lisans tanıtımının kaynak bileşeni bulunup aynı alandan kaldırılacak. Depodaki LICENSE ve font atıf dosyaları, araştırma cevaplarının kaynakları ve belge kaynak düzenleme kipi bu UI isteğinin kapsamı değil.

### Ses ve tablolar

Emoji temizliği ortak Python konuşma hazırlama katmanına uygulanacak. Birleşik aile/meslek, ten rengi, bayrak, variation selector ve keycap dizileri test edilecek. Normal rakamlar, Türkçe harfler, matematik işaretleri ve noktalama bozulmayacak. Yalnız emojiden oluşan metin senteze gönderilmeyecek.

Tablolarda küçük tablolar gereksiz genişlemeyecek, geniş tablolar yalnız kendi kutusunda kayacak, uzun hücre içeriği okunabilir kırılacak. Güvenli hücre satır sonları gerekiyorsa yalnız açıkça tanınan `br` biçimleri React elemanına dönüştürülecek; genel HTML çalıştırılmayacak. Kullanıcı örneği gelmeden tüm tablo sorunları çözülmüş sayılmayacak.

### Yerel model

Ollama yerelde yalnız loopback üzerinden kullanılacak. İlk seçenek yayıncının `huihui_ai/qwen3.5-abliterated:9b` etiketi. Bellek ve bağlam tüketimi gerçek çalıştırmayla ölçülecek; önceden hız veya kalite garantisi verilmeyecek. Model indirme boyutu önceden kontrol edilecek. Kullanıcıya mevcut sağlayıcılarının yanında yerel model seçimi sunulacak; varsayılanları kendiliğinden değiştirmek gerekmiyor.

Doğrulama sırası: yerel sunucu/model listesi, Türkçe yanıt, akış, iptal, dosya okuma ve kontrollü araç çağrısı. Sohbet çalışması araç kullanımı çalışıyor anlamına gelmez. Desteklenmeyen yetenekler doğru bildirilecek. Ayarlar uygulama yeniden açılınca kalıcı olmalı.

## Kabul ve teslim

Proje oluşturma ve + için davranış testleri; emoji temizliği için Python testleri; ikon şeridi erişilebilirlik testleri; tema için açık/koyu geniş/dar ekran görsel kontrolü; tablo için uzun hücre, dar ekran, satır sonu ve güvenilmeyen HTML örnekleri çalıştırılacak. İlgili uygulama testleri ve üretim derlemesi çalıştırılıp başarısızlıklar açıkça raporlanacak. Mevcut başkalarına ait değişiklikler korunacak.

Kaynak kod değişmesi ile kurulu Fusion.app'in değişmesi ayrı aşamalardır. Paketleme gerekiyorsa mevcut imzalama/dağıtım yordamı izlenecek; çalışmakta olan uygulama kullanıcı çalışması kaybedilerek kapatılmayacak. Son raporda neyin kaynakta, neyin kurulu uygulamada doğrulandığı belirtilecek.
