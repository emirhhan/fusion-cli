# Uzaktan erişim (Faz 11–13)

Uzaktan servis ikinci bir ajan motoru değildir; mevcut `AppSession` oturumunun önüne konan
kimlik, yetki ve olay katmanıdır (`src/fusion_cli/remote/`).

## Güvenlik modeli
- **Varsayılan dinleme `127.0.0.1`.** `0.0.0.0` ve genel IP reddedilir. Yerel ağ için açık izin
  (`yerelAg`) **ve** TLS sertifikası ya da güvenilir özel tünel (`guvenilirTunel`) gerekir.
- **Eşleştirme:** masaüstünde tek kullanımlık 8 karakterlik kod (120 sn) → cihaz kodu girer →
  masaüstü kullanıcısı onaylar → cihaz kimliğini ve sırrını **bir kez** alır. Yüksek yetkili
  kapsamlar (`project.write`, `desktop.control`, `mcp.write.*`, `production.deploy`) açıkça seçilir.
- **İmzalı istek:** her RPC HMAC-SHA256 ile imzalanır (yol, gövde özeti, zaman, nonce, monoton
  sıra). Saat sapması >60 sn, tekrar eden nonce ve eski sıra numarası reddedilir. Beş başarısız
  deneme 15 dakika kilitler. İptal edilen cihaz anında reddedilir.
- **Step-up:** masaüstü kontrolü, MCP yazma, tehlikeli ve sınıflandırılamayan işlemler uzaktan
  **onaylanamaz**, yalnız reddedilebilir; onay masaüstünde verilir. Uzaktan kalıcı ("oturum")
  izin verilemez.
- **Veri:** olaylar ve bildirimler sır kalıplarından arındırılır; Telegram'a kod/diff dökülmez.
- **Uyku/kapalı:** görevler bilgisayarda çalışır; uyku, kilit veya bağlantı kopukluğunda ilerlemez
  (`service.status` bunu `notice` ile bildirir, PWA gösterir).

## Telegram
Her kullanıcı kendi botunu BotFather'dan oluşturur; Fusion `getUpdates` ile dışarı bağlanır, port
açılmaz. Yalnız eşleşmiş kullanıcı kimliği ve yalnız özel sohbet işlenir. **Telegram bot
sohbetleri uçtan uca şifreli (Secret Chat) değildir.** Onay düğmesi yoktur.
Komutlar: `/projects /tasks /status /kits /kit <ad> /pause /resume /cancel /audit /devices`.
`/audit` bu sürümde son görevin olay kaydı özetidir (ayrı bir Project Audit motoru değildir).
`/pause` ve `/resume`, oturum duraklatmayı desteklemediği için dürüstçe "desteklenmiyor" döner.

## Mobil PWA
Servis `/` adresinde PWA'yı sunar (görev, onay, iptal, cihaz kaldırma). İmza için WebCrypto gerekir:
**HTTPS veya localhost** şarttır. Cihaz sırrı IndexedDB'de dışa aktarılamaz anahtar olarak durur.
Canlı ekran (WebRTC) ve push bildirimi bu sürümde **yok**.

## Yönetim istekleri (masaüstü ↔ çekirdek)
`uzak.durum`, `uzak.eslestir_baslat|onayla|reddet`, `uzak.cihazlar`, `uzak.cihaz_iptal`,
`uzak.baslat|durdur`, `uzak.telegram_baglan|kes`, `uzak.gorevler`, `uzak.onay_cevapla`.
Bu isteklerin masaüstü arayüzü (Ayarlar → Uzaktan Erişim ekranı) henüz yapılmadı.

## Sınırlar
Gerçek telefon, gerçek Telegram botu ve LAN TLS ile uçtan uca deneme yapılmadı; testler sahte
Telegram API'si ve ASGI istemcisi kullanır.

## Kurulum adımları

**Telegram:** (1) @BotFather → `/newbot` → belirteci al. (2) Fusion → Ayarlar → Uzaktan Erişim →
belirteci yapıştır → *Bağlan*. (3) *Telegram için kod oluştur* (2 dk). (4) Botuna `/pair KOD` yaz.
(5) Fusion'da *Cihazı onayla*. Sonra düz mesaj görev açar.

**Telefon (PWA):** Erişim türünü seç.
- *Özel tünel (önerilen):* Mac ve telefona Tailscale kur → *Dinlemeyi başlat* → Terminalde
  `tailscale serve --bg --https=443 http://127.0.0.1:8791` → telefonda verilen `https://…ts.net`
  adresini aç → *Ana Ekrana Ekle*.
- *Yerel ağ:* yerel adres + telefonun güvendiği HTTPS sertifikası (ör. mkcert) ve anahtarı gerekir;
  şifresiz yerel ağ dinlemesi reddedilir.
- Sonra *Telefon için eşleştirme kodu oluştur* → telefonda kodu gir → Fusion'da *Cihazı onayla*.

Mac uyurken/kapalıyken görev ilerlemez. Yüksek yetkili işlemler (masaüstü kontrolü, dış servis,
silme) yalnız Fusion'daki *Bekleyen onaylar* bölümünden onaylanır.
