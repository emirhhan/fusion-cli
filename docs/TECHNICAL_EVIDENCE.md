# Teknik adlarda gerekli kaynak desteği

Olgusal denetimin `supported` etiketi, tek başına teknik ayrıntıyı doğrulamaz.
Parser, tanınan teknik adların **aynı bulgunun atıf yaptığı sahipli belge
parçalarında** bulunmasını da ister. Hakemin gerekçesi, başka bir atıfsız bölüm,
bütün kaynak havuzu veya okuyucu makbuzundaki URL bu desteğin yerine geçmez.
Eksik ad somut `unsupported` bulgusuna dönüşür; ilgili izinli parçayı okumak veya
desteksiz ayrıntıyı düzeltmek gerekir. Bu, iddianın dünyada yanlış olduğu anlamına
gelmez; gösterilen kanıtın yeterli olmadığı anlamına gelir.

Dar biçim denetimi yalnız tek başına inline Markdown/HTML koduyla yazılmış
snake_case adları, nokta/`::` ile nitelenmiş adları, argümansız çağrıları,
`Warning`/`Error`/`Exception` sonlu türleri ve uzun CLI bayraklarını tanır.
Ek olarak `SyntaxError`, `RuntimeWarning`, `CustomException` gibi büyük harfle
başlayan tam tür adları sıradan görünür düz yazıda da tanınır; kod biçimi gerekli
değildir. Tek başına `Error`, `Warning`, `Exception` sözcükleri tür adı sayılmaz.
Bu ek kural genel API adlarına, sayılara, yüzdelere veya anlamsal ilişkilere genişlemez.
HTML metin dönüşümünden doğan açık noktalama boşlukları kabul edilir.
`SyntaxWarning` ile doğal `syntax warning` eşleştirilebilir; `Warning` hiçbir
zaman `Error` yerine geçmez. İlgisiz veya daha uzun başka bir CLI bayrağı aynı
bayrak sayılmaz. Python'a veya belirli bir ürüne ait beklenen doğru API listesi yoktur.

Tam nitelikli ad veya açık niteliksiz taban adı gerekli ad desteğini sağlayabilir.
Aynı taban adı yalnız başka açık namespace altında geçiyorsa bu eşleşme olmaz.
Aynı atıf metnindeki açık `import paket as ad` bildirimi, tek anlamlıysa
kısaltılmış niteleyiciyi asıl ada bağlayabilir. Çelişen bildirim, başka `as`
bağlamı veya yeniden atama bu ek eşleştirmeyi engeller. Atıfsız kaynak/bulgu
gerekçesinden alias alınmaz ve kapsam/genel sembol çözümü yapılmaz.
Bu kural sembol çözümleyici değildir: namespace ilişkisi, imza, davranış, tarih ve
kaldırılma/deprecation ayrımı yine anlamsal denetim gerektirir. Adın kaynakta
bulunması yalnız gerekli koşuldur; ilişkiyi kanıtlamaz ve mevcut anlamsal hatayı
geçersiz kılmaz. Hakem talimatı bu yüzden bileşik listelerin her üyesini ve olgu
iddiası taşıyan başlıkları ayrı kontrol eder; içindekiler/modül başlığı API düzeyi
bir davranış veya kaldırılma kanıtı değildir.

Tür adı dışındaki sıradan düz yazı/çeviri bu dar ad şartına alınmaz.
Yanlış kesinliği azaltmak için URL, sürüm, tanınan dosya yolları,
çitli veya `<pre>` kod örnekleri, atama/argüman içeren karmaşık kod parçaları ve
açık örnek/yerel değişken bağlamı bu dar ad şartına alınmaz. Dosya teslimi bağlamı
ayrıca yerel adların API sanılmasını önler. Örnek/değişken/teslim bağlamı tanıması
İngilizce ve Türkçe açık işaretlerle sınırlıdır; belirsiz kod, bütün diller veya
bütün API yazımları için eksiksiz sınıflandırma iddiası yoktur. Bu dışlamalar
metnin anlamsal kontrolünü kaldırmaz. Düz yazıda `/` veya `\` içeren boşluksuz
parçalar, noktayla birleşmiş dosya/domain/nitelikli adlar ve mevcut kod aralıkları
içinden ayrıca tür adı çıkarılmaz. Bu tutucu dışlama belirsiz yerel adlardan
iddia türetmez; genel bir dosya veya URL ayrıştırıcısı değildir. Örnek bağlamı
aynı cümledeki açık işaretlerle, teslim bağlamı önce gelen işaretlerle sınırlıdır.
Yalnız saf biçimsel başlıkların `nonfactual`
olması talimatla korunur; parser kendi başına her başlığın anlamını çözmez.

İşaretleme aralıkları ve bağlam sınırları önceden hesaplanır; yinelenen adların
biçim çözümü yalnız çağrı içinde paylaşılır, her kullanımın bağlamı ayrı kalır.
Düz yazı tür taraması tam tanımlayıcıları bir kez ayırıp mevcut tür şekliyle tam
eşleştirir; her büyük harf konumundan açgözlü son-ek araması başlatmaz. Kod
aralıkları tek yönde ilerleyen imleçle atlanır; bağlam için mevcut sınır/işaret
indeksleri paylaşılır. Bu yeni taramanın karakter işi doğrusaldır; aday bağlam
aramaları mevcut ikili aramaları kullanır, kaynak eşleştirme yolu değişmez.
Kapatılmamış etiketlerde sondaki iddia düşmez. Eski düz-yazı ayırmanın iki
kullanımında aynı alternatif önceliğini/tırnak ayrıntılarını koruyan tarama vardır;
eşit uzunluklu maske, hedef ofset/ID/özetlerini korur. Uzun boşluk ve yoğun/birbirinden
farklı adlar için de pahalı tekrarlı son-ek taraması yoktur. Üretilen bulgu gerekçesi
hakemle aynı 600 karakter sınırında, kısa ad önizlemesi ve gerçek atlanan ad sayısıyla
kalır. Önizleme sınırı bulguyu temiz kabul haline getirmez.

Yeni model çağrısı, yeniden deneme, bütçe, sahiplik veya izin yolu yoktur. Var olan
sıkı tam kapsam, kaynak makbuzu, özet, sıra ve ikinci değerlendirme kontrolleri
korunur. Önceki doğrulanmamış metin otomatik birleştirilmez.

Test fikstürleri yalnız atıf yapılan kamuya açık kısa parçaları içerir; atıfsız
metin sentetik boşluk/newline yerleşimiyle değiştirilmiştir. Tam özel tanı
repo dışındadır; fixture dizininde kaynak URL'leri ve PSF lisans atfı bulunur.
Test fikstürleri gerçek kaydedilmiş 66 hedefli yanlış-temiz ikinci hükmün iddia ve
atıf metinlerini, ayrıca önceki gerçek destekli 53 hedefli kalibrasyonu içerir.
Test sahipliği ve özetleri yeniden bağlar. Yanlış-temiz örneğin kaynak gövdesi araç
çıktısından yeniden kurulmuştur; özel orijinal makbuz özetinin aynen yeniden
kurulduğu iddia edilmez. Atıf yapılan metinler tanı kaydıyla birebir kontrol
edilmiştir. Gerçek sağlayıcı çağrısı yapılmadan `SyntaxError` ve uydurulmuş kaldırma
listeleri artık gerekli kanıt kontrolünde reddedilir; eski destekli kalibrasyon
bu dar kontrolde kabul edilir. Bu testler evrensel olgusal doğruluk kanıtı değildir.
