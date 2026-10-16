# Gerçek kabul bulgusu — ajan görsel sağlayıcı seçimi

Animasyon koşusunda `generate_image` varsayılan NIM sağlayıcısında iki kez 120 saniye timeout verdi. Bağlı Gemini ve ChatGPT seçimleri `image_choices` içinde bulunuyor, fakat `generate_image_tool` kapanışı yalnız ilk seçilen üreticiyi tutuyor. Ajanın başka bağlı üreticiyi açıkça seçebileceği parametre yok.

## Uygulama sınırı

- Mevcut varsayılan üretici sırası korunur. Otomatik gizli fallback veya hesap/model ayarı yazma yok.
- Tool şemasına yalnız mevcut `image_choices` değerlerinden oluşan isteğe bağlı sağlayıcı seçimi eklenir. Kullanıcı/ajan açık seçim verirse o üreticiye gider; yoksa eski varsayılan.
- Bilinmeyen veya artık bağlı olmayan seçim dış çağrıdan önce anlaşılır hata verir. Sağlayıcı kimliği sır içermez.
- Hata, gerçekten denenen üreticiyi ve varsa alternatif bağlı seçimleri görünür kılar. Timeout aynı işi başarılı veya iptal edilmiş diye göstermez.
- Dosya yazımı, scope, gerçek MIME/boyut, cover/crop ve teslim makbuzu mevcut otoritelerinde kalır.

## Test ve kabul

1. Açık bağlı seçim doğru üreticiye gider, varsayılan davranış korunur, yanlış seçim hiçbir sağlayıcı çağırmaz: RED→GREEN.
2. Varsayılan timeout ve açık alternatif denemesi ayrı sonuçlar olarak saklanır; aynı dosyaya sahip olmayan geç sonuç yazmaz.
3. Unit/type/lint inceleme; mevcut bağlı sağlayıcıyla gerçek generate/edit smoke. Referans ve gerçek dosya açılarak kontrol edilir.
4. Yeni manifest ile aynı üretim kabulü boş kökten tekrarlanır. Sağlayıcı değiştiyse eş koşullar/parite iddiası yapılmaz.

Durum: tasarım hazır. Mevcut HTML oyun baseline koşusu tamamlanana kadar Python kaynakları değiştirilmez.
