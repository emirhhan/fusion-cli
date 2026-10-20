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

- **Sohbetler:** diskteki sohbetler (`sohbet.listele`) + telefondan açılanlar tek listede; proje süzgeci
  (Tümü / Projesiz / proje adı), `+` ile yeni sohbet, satıra dokununca geçmiş açılır (`chats.history`).
  Sohbet içinde proje ve model seçilir. Görev çalışırken sohbet listesi/geçmişi açılamaz (tek oturum
  kilidi): telefon son listeyi korur ve "bitince yüklenecek" der.
- **Mesaj:** yanıt akar (`delta` olayları ~4/sn'de birleştirilir), "Durdur" görevi iptal eder, `/görsel …`
  çekirdekte çalışır ve üretilen görsel sohbette görünür (`media.get`: yalnız izinli köklerdeki görsel
  dosyalar, ≤4 MB, anahtar/kimlik dizinleri hariç). Dosya/görsel eki (`uploads.put`): telefonda 1280 px
  JPEG'e küçültülür, ≤700 KB, Fusion'ın kendi yükleme dizinine yazılır, ajan yolu `ekler` ile alır.
  Ses: tarayıcının SpeechRecognition'ı (tr-TR); ses tarayıcı hizmetine gider, Fusion'dan geçmez.
- **Projeler:** `projects.*` + `chats.assign`; masaüstü kaydı (`fusion.projects.v1`, WebView deposunda)
  açıkken `uzak.projeler_esitle` ile çekirdeğe eşitlenir. Telefon klasör SEÇEMEZ; klasörlü projeler yalnız
  masaüstünden gelir. Telefondan açılan proje klasörsüzdür (varsayılan kökte çalışır).
- **Görevler:** çalışan/biten listesi, "Durdur" (iptal). **Zamanlananlar** listelenir, duraklatılır/sürdürülür;
  "Şimdi çalıştır" görev metnini bu oturumda yeni sohbet olarak başlatır (masaüstü uygulaması kapalıyken de).
  **Kits** yalnız `remote_allowed` olan kitler için listelenir.
- **Yetki:** hiçbir kapsam genişletilmedi. Okuma: `project.read`; yazan çağrılar (proje/ek/model/zamanlama/
  görev): `agent.run`; durdurma: `agent.cancel`; ekran: `desktop.observe`. Riskli işlemler yine masaüstü onayı ister.
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
etkin cihazları verir. Masaüstü tarafı yazıldı: `app/src/remote/ScreenWatchWindow.tsx` etkin oturum varken sağ altta küçük,
kapatılabilir pencere açar (cihaz adı, "Kes", "Kapat"; kare ~1 sn'de bir). Yoklama yalnız Ayarlar → Uzaktan
Erişim bir kez açılıp dinleme başlamışsa çalışır (`fusion.remote.inuse`); kurulmamış kullanıcıda `uzak.*`
çağrılmaz. Uygulama derlenmedi; bileşen testleri (vitest) ve tsc temiz.

## Eşleşmenin kalıcılığı ve hesapla giriş
- **"PWA açılıp sıfırlanıyor" nedeni:** PWA aynı anda birkaç imzalı istek atıyordu; sunucu monoton sıra
  numarası istediği için ters sırada ulaşan istek `sira_eski` ile 401 alıyor, istemci her 401'i "iptal"
  sayıp cihaz anahtarını SİLİYOR ve sayfayı yeniliyordu; üstüne bu hatalar kilit sayacına yazılıp
  15 dk kilit (429) açabiliyordu. Düzeltme: istekler istemcide tek tek (sırayla) gider; 401 yanıtı
  `reason` taşır; yalnız `cihaz_iptal`de eşleşme silinir, `sira_eski`/`nonce_tekrar` bir kez yeniden
  denenir, imza/saat hataları banner'da kalır; imza geçerliyken gelen sıra/saat/nonce hataları kilit
  sayacına yazılmaz. 20 sn zaman aşımı kuyruğu tıkamaz. `navigator.storage.persist()` istenir.
- **Hesapla giriş:** `/v1/auth/login` (kimlik + parola → Fusion hesap deposu, scrypt) yalnız TLS ya da
  güvenilir özel tünel seçiliyken açılır (`/v1/auth/options` PWA'ya söyler). Hız sınırı hem istemci hem
  kimlik başına: 5 hata → 15 dk kilit; doğru parola da kilitteyken reddedilir. Cihaz YALNIZ varsayılan
  kapsamlarla (proje okuma, ajan çalıştırma, iptal) kaydolur; ekran/masaüstü/yazma yetkileri masaüstünde
  ayrıca verilir. Parola loglanmaz/saklanmaz. Kod ile eşleştirme aynen durur.
- **Doğrulanamayanlar:** iOS Safari sekmesi ile ana ekran uygulaması AYRI depo kullanır; eşleştirme
  hangisinde yapıldıysa orada kalır (başka yerde yeniden giriş gerekir). iOS'un depoyu temizlemesi
  (7 gün kullanılmayan site verisi) gerçek cihazda sınanmadı.

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
