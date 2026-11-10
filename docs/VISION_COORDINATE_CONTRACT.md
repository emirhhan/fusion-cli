# Görsel yardımcı konum sözleşmesi

NVIDIA'nın [GUI-coordinate README](https://github.com/NVIDIA-NeMo/Gym/blob/main/resources_servers/gui_coordinate/README.md)
ve [doğrulayıcı kodu](https://github.com/NVIDIA-NeMo/Gym/blob/main/resources_servers/gui_coordinate/app.py),
tek bir noktanın görüntü genişlik/yüksekliğinin binde biri olarak yorumlandığını
belgeler. Bu belge genel bir NIM yanıt birimi garantisi değildir; çoklu nokta
listesi için de bir sözleşme sağlamaz.

Fusion yalnız `mode=locate` açıkça istendiğinde, tam olarak yapılandırılmış
`nvidia_nim/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` ve aynı kimlikle dönen
yanıt için kendi yüksek öncelikli isteğinde bu tek hedef sözleşmesini açıkça
bildirir. Boyutlar kullanıcı sorusundan alınmaz; gönderilen değişmez görsel
çözülür. Yalnız tam `<point>(x,y)</point>` biçimli tamsayı tek nokta kabul edilir.
Görüntünün dış kenarına düşen sonuç kabul edilmez. Nokta açık `image_pixels`,
görüntü boyutları ve piksel koordinatı olarak sunulur; pikselden ekran noktasına
mevcut çerçeve dönüşümü aynen uygulanır. Başka sağlayıcı/modelin küçük sayıları
bu birime benzetilerek yorumlanmaz.

Gözlenen altı noktalı liste, çoklu/bozuk/negatif/sınır dışı veya tanımsız konum
çıktısı ham koordinatlar eyleme taşınmadan reddedilir. Yeni ekran görüntüsü ve
her `view_image` çağrısında tek bir kontrol istenir. Ek yardımcı çağrı, model
seçimi, yeniden deneme veya yapılandırma değişikliği yapılmaz. Normal OCR ve
görsel açıklaması kaynakla sınırlı kalır; hesap yapılmaz.

İç sonuç tipli `ImageObservation`/`CoordinateStatus` taşır; mevcut
`describe_image_data` çağıranları iki alanlı açıklama/hata sözleşmesini korur.
Reddedilmiş konum yanıtı yalnız aynı sahip/kök/tur altında halen güncel olan
dondurulmuş ön plan yakalamasını geçersiz kılar. Böylece aynı yakalamanın eski
başarılı yardımcı onayı yeniden kullanılamaz. Başka yakalama veya arka plan
yardımcısı ön plan yetkisini değiştiremez. Asenkron sınırlarından sonra sahiplik
yeniden denetlenir.

OCR/açıklama kullanılabilirliği (`usable`) ile koordinat yetkisi (`can_ground`)
ayrıdır. Yalnız doğrulanmış `IMAGE_PIXELS` ve geçerli, sonlu, görüntü içi tipli
nokta yardımcı koordinat kanıtı olabilir. Normal OCR metni sunulmaya devam eder;
fakat önceki başarılı noktanın ardından gelen herhangi bir konum kanıtı olmayan
yardımcı yanıtı aynı güncel ön plan yakalamasının eski yetkisini kaldırır.
Tanımsız bir düzyazı konum biçimi tanıyıcıdan kaçsa bile yetki veremez veya eski
yetkiyi koruyamaz. Metin biçimi tanıma, bu güvenlik sınırının yerine geçmez.

`view_image` niyeti açık `mode` alanıyla ayırır: varsayılan `describe`, metin ve
görsel açıklamasıdır; koordinat boyut çözümlemesi veya konum istemi eklenmez.
`locate`, yalnız tek bir kontrolün konumunu ister. Soru metnindeki kelimelerden
bu seçim tahmin edilmez. `describe` içinde beklenmedik nokta çıktısı reddedilir.
Mevcut iki alanlı açıklama/hata sarmalayıcılarının imzası korunur ve varsayılan
`describe` kullanılır. Geçersiz mod, dosya/sağlayıcı erişimi başlamadan reddedilir.

Geçerli boyutları olan bilinen modelin `locate` sistem isteği yalnız tek nokta
yanıt biçimini ister; `visible_text`/`description`/`uncertainty` alanlarını veya
harfi harfine metin dökümünü aynı yanıtta istemez. Her iki mod aynı görsel kanıt
sınırını korur: soru odak belirtir, kanıt değildir; görünmeyen içerik veya
beklenen sonuç hesaplanmaz ve eylem/görev başarısı ilan edilmez. Varsayılan
`describe` sistem isteğinin baytları ve rakam/işleç koruma yönergeleri aynıdır.
Kesilmiş ilk yanıttan sonraki tek 4096 token kurtarması aynı moda özel sistem
isteğini ve ilk çağrının kalan süresini kullanır; yeni bir süre bütçesi açmaz.
Model veya boyut sözleşmesi bilinmiyorsa önceki muhafazakâr açıklama isteği
korunur ve nokta çıktısı koordinat yetkisi kazanamaz.

Bu düzeltme, üç açıklama alanı ile yalnız nokta isteyen çelişkili üretici
isteğini kaldırır. Ham yanıt kanıtı olmadan gözlenen bütün konum hatalarının
bu çelişkiden kaynaklandığı söylenemez; sahte sağlayıcı testleri gerçek modelin
hedef doğruluğunu ölçmez.

Bu ayrım nokta doğruluğu kanıtı değildir. Korunan beş istekli canlı denemede
iki hedefin ayrılmış bölge kontrollerini kaçırması ve OCR'ın nokta çıktısına
itilmesi başarısızlık olarak kalır. Dönüşüm bu hedef kontrollerine göre
ayarlanmamıştır; hedef konum doğruluğu ayrıca kanıtlanmayı bekler.
