# Web giriş ve arayüz doğrulaması — 10 Eylül 2026

## Gözlenen hatalar

- Kurulu a9 ikilisi, panelin ürettiği `web-login gemini_web main` komutuna
  `unexpected extra argument (main)` ve çıkış kodu 2 döndürdü. Hesap CLI'da
  `--account` seçeneği; kaynak Python modülünde ise konumsal argümandır.
- Gerçek CLI ayrıştırıcısı üzerinden main/work hesaplarını sınayan test önce
  aynı hatayla başarısız oldu; komut düzeltildikten sonra geçti.
- Doğru komut Chrome'u açtı; eski Fusion Gemini profilinde Google CookieMismatch
  ekranı görüldü. Yalnız bu izole profil silinmeden yedeklendi. Temiz profilde
  normal Google e-posta giriş formu görüntülendi. Hesap girişi kullanıcıya bırakıldı.
- Yeni profil Chrome ilk kurulum ekranına takılabiliyordu; normal giriş
  başlatıcısına no-first-run/no-default-browser-check eklendi.

## Gerçek uygulamada kontrol edilenler

- Kurulu a9 güncelleme paneli a10'u buldu, indirdi ve uygulama yeniden başladı.
  Applications içindeki Info.plist a10 sürümünü doğruladı; DMG kurulumu kullanılmadı.
- Paketli a10 panelinde Oturum aç düğmesi doğru --account argümanıyla Chrome
  sürecini başlattı. Fusion normal çıkışında o test Chrome süreci de kapandı.
- MCP kataloğunda Ekle ortalanmış pencere açtı; Escape pencereyi kapattı.
- Yerel a11 ekranında kontrol panelinin çalışma alanına yayıldığı doğrulandı.
- Kategori değişiminde ProviderList'in yaşamaya devam etmesi, Chrome kapanınca
  kayıt ve doğrulama işlemlerinin sürmesi otomatik regresyon testiyle sınandı.

## Tasarım referansı ve sınırlar

Kullanıcının güncel referansı:
https://www.figma.com/design/xM1HCxdgHNN8i8jlpqwxva/ChatGPT-UI-Kit--AI-Chat--Community-?node-id=665-2049

Dosya tarayıcıda açıldı; sohbet/giriş ekranları yakınlaştırılarak görüldü.
Bileşen seçme ve ölçü inceleme Figma girişi istedi. Bu çalışma kontrol paneli,
kenar çubuğu yoğunluğu ve iki MCP formunun iyileştirilmesidir; bütün kitin
piksel eşleşmeli uygulaması değildir. Gerçek Google girişi tamamlanmadan
Gemini ile uçtan uca mesaj alışverişi doğrulanmış sayılmaz.
