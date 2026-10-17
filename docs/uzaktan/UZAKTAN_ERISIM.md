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
Servis `/` adresinde gerçek bir mobil uygulama düzeni sunar: alt sekme çubuğu (Sohbetler, Görevler,
Onaylar, Ekran, Ayarlar), güvenli alan boşlukları, PNG ana ekran simgesi ve Fusion marka kitinin
renk/yazı dili (Kits'in sistem yazı tipi, 14 px, nötr mürekkep; açık/koyu tema sistemden gelir).
İmza için WebCrypto gerekir: **HTTPS veya localhost** şarttır. Cihaz sırrı IndexedDB'de dışa
aktarılamaz anahtar olarak durur. Push bildirimi bu sürümde **yok**.

- **Sohbetler:** bu telefondan ve masaüstünden açılan görevler sohbet satırı olarak listelenir;
  sohbet balonları görevin olay akışından gelir (araç adımları, yanıt, hata, satır içi onay).
  Uzaktan RPC'de "mevcut sohbete mesaj ekle" yöntemi yoktur: mesaj kutusundan yazılan her metin
  yeni görevdir (ekranda bu da yazar). Masaüstündeki sohbet geçmişi uzaktan listelenmez.
- **Canlı ekran:** JPEG kare akışı (WebRTC değil). Kutu görüntüyü en-boy oranını koruyarak sığdırır;
  dokununca tam ekran olur.

### Canlı ekran: kopma nedeni ve çözüm
Eski davranış: onay 5 dk sonra **kare çekilse de** kapanıyordu ve telefon bunu "paylaşılmıyor"
diye gösterip hiç yeniden bağlanmıyordu; sayfa yenilenince döngü de başlamıyordu; ağ hatasında
yalnız hata yazıp bir sonraki turu bekliyordu, arka plan/uyku ayrımı yoktu.
Şimdi:
- Oturum **boşta kalma süresiyle** ölçülür (`SCREEN_IDLE_TTL_SECONDS` = 10 dk): kare çekildikçe
  uzar; telefon 10 dk hiç kare istemezse kapanır. Mutlak üst sınır `SCREEN_MAX_SESSION_SECONDS` =
  2 sa; sonra masaüstünde yeniden onay gerekir. Masaüstü her an kesebilir (`uzak.ekran_kes`).
- İstek tek tek (üst üste binmeden) gider; ağ hatasında 1 sn → 15 sn üstel bekleme ile süresiz
  yeniden dener; sayfa arka plana geçince durur, öne gelince hemen sürer; `online` olayı da tetikler.
- Sayfa yenilenince etkin oturum varsa **yeni izin istemeden** sürdürür.
- Oturum yine de biterse (üst sınır / masaüstü kesmesi dışında kullanıcı durdurmadıysa) bir kez
  kendiliğinden yeniden izin ister ve "bilgisayarda onayla" der. Kullanıcı "Durdur"a bastıysa istemez.
- Sınanan senaryolar: `tests/test_remote_pwa_screen_stream.py` (Node'da, sahte RPC ile).

### Masaüstünde izleme önizlemesi (tasarım)
Daha önce konuşulan "ekran paylaşılırken masaüstünde ne gösterildiğini görme" isteği için depoda
yazılı bir plan bulunamadı. Tasarım: masaüstü ek ekran yakalaması YAPMAZ; telefona en son verilen
kareyi gösterir ("telefonun gördüğü bu"). Çekirdek tarafı hazırdır: `uzak.ekran_onizleme`
`{cihazId}` → `{ok, seq, at, jpegBase64}` (etkin oturum yoksa `ok: false`); `uzak.ekran_bekleyen`
etkin cihazları verir. Kalan iş masaüstü arayüzüdür (Ayarlar → Uzaktan Erişim ekranı henüz yok):
etkin oturum varken küçük yüzen bir pencere `uzak.ekran_onizleme`yi ~1 sn'de bir çağırır, cihaz
adı + "Kes" düğmesi gösterir. Uygulama derlenmediği için bu fazda yazılmadı.

## Yönetim istekleri (masaüstü ↔ çekirdek)
`uzak.durum`, `uzak.eslestir_baslat|onayla|reddet`, `uzak.cihazlar`, `uzak.cihaz_iptal`,
`uzak.baslat|durdur`, `uzak.ekran_bekleyen|onayla|kes|onizleme`, `uzak.telegram_baglan|kes`, `uzak.gorevler`, `uzak.onay_cevapla`.
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
