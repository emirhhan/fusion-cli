# Arka plan pencere gözleminin görsel modele aktarımı

`desktop_background_screenshot` satır içi PNG'yi korur. Geçerli, en fazla 5 MiB ve
32 milyon piksel PNG için mevcut tur/sahip doğrulanırsa ayrıca
`.fusion/tmp/arka-plan-ekrani.png` yolunu döndürür. Metin modeli bu yolu mevcut
`view_image` aracıyla yapılandırılmış görsel modele sorabilir. Model rolleri değişmez.

Görüntü pencerenin yerel pikselleridir. Fiş PID, pencere kimliği, boyut, kök, tur,
sahip, dosya özeti ve açık hazırlık dosyasının nesil bilgisini taşır. Ön planın
çerçevesi, odağı veya koordinat yetkisi değişmez; `view_image` bu gözlemden hiçbir
zaman ön plan yardımcı onayı üretmez. Gözlem bağımsız doğrulama veya teslim değildir;
kullanıcının görsel istemesi de özel gözlem dosyasını teslim çıktısına dönüştürmez.

Yazma POSIX dizin tanıtıcıları ve `O_NOFOLLOW` kullanır. İlk yayın atomik olarak var
olan dosyayı korur. Sonraki yayında yalnız mevcut kullanıcıya ait 0600 kipli,
geçerli ve sınırlı PNG içinde tek CRC-doğrulanmış `FusionBackgroundCapture` tEXt
alanı (sürüm 1 ve rastgele 128 bit nonce) varsa slot değiştirilebilir. Piksel
verileri yeniden kodlanmaz; işaret toplam 5 MiB bütçesine dahildir. İşaret yalnız
önbellek değiştirme uygunluğudur; aynı kullanıcı tarafından taklit edilebilir ve
hiçbir okuma veya pencere yetkisi vermez. Dosya nesli hazırlık dosyası altında
tekrar denetlenir. Tek sabit 0600 kilit dosyasındaki `FileLease`, işbirliği yapan
Fusion yazarlarını beklemeden ayırır. Nesil denetimi ve değiştirme, aynı kullanıcı
kimliğiyle çalışan kötü niyetli süreçlere karşı atomik karşılaştırma/değiştirme
olarak sunulmaz. Bilinmeyen/işaretsiz mevcut dosya veya desteklenmeyen güvenli dosya erişimi durumunda yol
uydurulmaz, satır içi görsel ve açık uyarı döner. Tek sabit hazırlık dosyası normal
başarı/hata yolunda kaldırılır; süreç çökmesinden kalan hazırlık dosyası üzerine
yazılmaz. İşaretli, geçerli PNG hazırlığı kilit alındıktan sonra temizlenebilir;
eksik veya bilinmeyen hazırlık korunur ve satır içi uyarıya düşülür. Böyle bir
çökme sonrası kısmi dosya yerel onarım gerektirebilir. Ön plan görüntüsü saklama
davranışı değişmez.

Yeni tur, farklı sahip, dosya değişimi veya iptal gözlem okumasını geçersiz kılar.
Görsel modelinden dönüldükten sonra da sahiplik ve dosya tekrar denetlenir. İptal
edilmiş bir çağrı yeni fiş yayımlayamaz; başlamış işletim sistemi çağrısının anında
kesilebildiği iddia edilmez. Yardımcının mevcut yayıncı davranışı değiştirilmemiştir.
