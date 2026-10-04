# Fusion Kits'in Fusion'a birleştirilmesi — faz planı

Kaynak: `~/Desktop/01-Projeler/fusion-kits` (OpenDots türevi, Node yan süreci + iframe).
Sözleşme: `fusion-kits/handoff/BIRLESTIRME.md`. Kullanıcının tarif ettiği en soldaki ana menü:
Home → Zamanlananlar → Kitaplık → Görsel ve video üretimi → Kits.

## Mevcut durum (koddan doğrulandı)

- Masaüstü kabuğu `app/src/screens/Shell.tsx`; sayfa seçimi `SessionApplication.tsx` içindeki
  `Page` birleşimi. Bugünkü kenar çubuğu (`Sidebar.tsx`) sohbet ve proje listesini taşır.
- "Görsel oluştur" sayfası ve galeri var (`imagecreate/`, `appserver/image_flows.py`).
  "Video oluştur" yer tutucu.
- Zamanlayıcı ve genel dosya kitaplığı Fusion'da YOK.
- Tauri CSP `frame-src http://127.0.0.1:*` zaten izinli.
- Kits yan süreci Node 24 ister; makinede Node 22 var, Kits bugün `npx node@24` ile başlıyor.

## Fazlar

### A — Ana menü rayı
`Shell`e en solda dar bir ray eklenir (beş madde, simge + etiket). Home bugünkü ekranın
tamamıdır, değişmez. "Görsel oluştur" / "Video oluştur" girişleri iç kenar çubuğundan raya
taşınır. `Page` türüne `scheduled`, `library`, `kits` eklenir. Test: ray sırası, etkin madde,
klavye gezinmesi, dar ekran.

### B — Kits gömme ve yan süreç
- Kits kaynağı depoya `kits/` olarak alınır (node_modules, dist, veri, .env hariç).
- Tauri tarafında `kits_process.rs`: boş loopback portu seç, Kits sunucusunu kendi veri
  dizininde başlat (`KITS_HOST_ORIGINS` = uygulamanın origin'i), hazır olana kadar bekle,
  uygulama kapanırken SIGTERM. Komutlar: `kits_baslat`, `kits_durum`.
- `app/src/kits/KitsScreen.tsx`: yükleniyor / hata / hazır durumları; iframe menü geçişinde
  saklanır (sohbet korunur). Adreste token taşınmaz.
- Test: adaptör birim testleri, Rust süreç testi, gerçek uygulamada iframe yüklenmesi.

### C — Kitaplık
Çekirdekte `kitaplik.liste` / `kitaplik.ac`: galeri görselleri + turlarda yazılan/eklenen
dosyalar (tur günlüğünden). Arayüz: tür süzgeci, arama, önizleme, "klasörde göster".

### D — Zamanlananlar
Çekirdekte kalıcı görev deposu + zamanlayıcı (tek seferlik ve yinelenen; uygulama açıkken
çalışır, kaçan iş açılışta bildirilir). Arayüz: liste, oluştur, duraklat, şimdi çalıştır, son
sonuç. Sohbetten "yarın 9'da şunu yap" ile oluşturma aracı.

### E — Kits canlı kabulünün kalanı
Kits sohbetinin Nemotron ile uçtan uca çalışması, Fusion görev aracında insan kararları,
yerel ses işçisinin görüşme ekranına bağlanması. Dış hesap isteyenler (Slack, Docker
bilgisayarları, Windows) ayrı tutulur; ayar yoksa "çalışmadı" diye raporlanır.

### F — Paketleme
Node çalışma zamanı ve Kits `dist`'i uygulama paketine girer; sürüm yükseltme, kurulum,
duman testi.

Her faz sonunda: `ruff check` + `mypy` + `pytest`, `npm run check:ci`, sonra commit.

## Varsayılan kararlar (itiraz gelmezse böyle yapılır)

1. Görsel ve video tek ray maddesi; içeride iki sekme (Görsel hazır, Video "yakında").
2. Kits verisi Fusion verisinden ayrı klasörde durur; ortak dosya deposu Kitaplık fazında bağlanır.
3. Zamanlanan işler yalnız uygulama açıkken çalışır (arka plan servisi kurulmaz).
