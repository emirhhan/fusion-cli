# Fusion macOS Beceriler, Ajanlar ve MCP — E Aşaması Ara Sonuç

## Teslim edilenler

- Claude, Codex, Hermes, proje ve Fusion kaynakları tek native katalogda birleşir.
- Aynı adlı kopyalar tek satırda `[claude] [codex]` gibi çoklu kaynak etiketi taşır.
- Skill/ajan metni yalnız keşfedilmiş kayıt üzerinden, 12.000 karakter tavanıyla okunur; kullanıcı yolu kabul edilmez.
- İzin kapsamı sade Türkçeyle görünür. Kaynak metin okumak komut veya ağ iznini kendiliğinden vermez.
- Oturumda kapatılan skill/ajan gerçek agent registry'sinden çıkar; MCP kapatma kalıcı config'i değiştirmeden o oturumun bağlantı listesini filtreler.
- Açıkça seçilen skill veya ajan yalnız sonraki tur için, 6.000 karakter tavanıyla sisteme eklenir ve sonra temizlenir.
- Otomatik skill eşleşmesi yapılandırılmış `CapabilityActivated` olayıyla konuşma akışında görünür.
- Native katalogda arama, kaynak filtresi, detay, izin etiketleri, oturum anahtarı ve sonraki turda kullan eylemi vardır.

## Doğrulama

- İlgili Python kümeleri: 141 test geçti.
- Ruff ve mypy: temiz.
- React tam küme: 29 dosya / 116 test geçti.
- TypeScript üretim derlemesi: geçti.
- Katalog görselleri: açık, koyu ve 920 px senaryolarında 3/3 geçti.

Paketli runtime doğrulaması H aşamasındaki son DMG üretiminde yeniden çalıştırılacaktır; bu nedenle E planındaki son paket kutusu o kapıya kadar açık bırakılmıştır.
