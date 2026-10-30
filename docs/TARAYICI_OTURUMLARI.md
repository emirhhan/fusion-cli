# Tarayıcı oturumları — ajanın tarayıcısına çerez / oturum aktarma

Fusion'ın kendi tarayıcısı (`browser_open`, `browser_click`, … araçları) normalde **girişsiz**
açılır. Claude in Chrome gibi kullanıcının gerçek profilinde çalışmaz. "Girişli sitede iş yap"
için iki yol var:

1. **Chrome eklentisi** (`chrome_*` araçları) — Fusion senin açık Chrome sekmende çalışır,
   oturumlar zaten oradadır. Bkz. `CHROME_EKLENTISI_KURULUM.md`.
2. **Tarayıcı profili** (bu belge) — oturumunu bir kez Fusion profiline aktarırsın; ajanın
   kendi tarayıcısı o profille açılır. Başsız/arka plan işler ve uzak oturumlar için uygundur.

## Nasıl çalışır

- Profiller `~/.local/share/fusion-cli/browser_profiles/<ad>/` altında durur:
  `profile.json` yalnız alan adı, sayı, kaynak ve zamanları tutar; çerezler `cookies.enc`
  içinde sır deposuyla aynı anahtarla şifrelidir. Anahtar yoksa (`fusion doctor`) profil yazılamaz.
- **Alan adı bazlı onay:** içe aktarırken hangi sitelerin aktarılacağını seçersin; profil yalnız
  o sitelerde (ve alt alan adlarında) çerez taşır. Ajan başka siteye giderse çerezsiz gider.
- Çerez değerleri hiçbir çıktıda görünmez: araç sonucu yalnız `profil: <ad>` satırı ekler;
  `Cookie:`/`Set-Cookie:` başlıkları hata ve transkript metinlerinde maskelenir.
- Tur bitince tarayıcının güncel oturumu profile geri yazılır (yenilenen belirteçler kaybolmaz).
- Normal Chrome profilin **kendiliğinden hiç okunmaz**; yalnız sen `import-chrome` dediğinde ve
  macOS Keychain izin diyaloğunda "İzin ver" dediğinde okunur.

## Komutlar

```bash
fusion browser profiles                                   # kayıtlı profiller (ad, alan adı, sayı)
fusion browser import-cookies cookies.txt -p is           # Netscape cookies.txt ya da JSON
fusion browser import-cookies dump.json -p is -d example.com -d shop.example.org --yes
fusion browser chrome-profiles                            # bu bilgisayardaki Chrome profilleri
fusion browser import-chrome -p is --chrome-profile "İş" -d example.com
fusion browser login is --url https://example.com/login   # görünür pencerede gir, kapatınca kaydet
fusion browser default is                                 # browser_open hep bu profille açılsın
fusion browser default                                    # varsayılanı kaldır
fusion browser delete is --yes
```

İçe aktarma önce alan adı listesini gösterir ve onay ister; betiklerde `--yes` zorunludur.
Desteklenen dosyalar: Netscape `cookies.txt` (curl/wget/"Get cookies.txt" eklentisi, `#HttpOnly_`
öneki tanınır) ve JSON (Cookie-Editor/EditThisCookie listesi ya da Playwright `storage_state`).

## Araç argümanları

`browser_open(url, profile?, headed?)`: `profile` verilen (ya da `browser.default_profile`)
profili yükler; `headed: true` pencereyi görünür açar. Açık bir oturumda başka profil istenirse
araç önce `browser_close` ister — iki profilin çerezleri aynı bağlamda karışmaz.

## Ayarlar (`config.yaml`)

```yaml
browser:
  profiles_enabled: true   # false: ajan hiçbir profil yükleyemez (açık istek bile reddedilir)
  default_profile: ""      # boş = çerezsiz
  headless: true           # false = pencere görünür
```

## Masaüstü

Ayarlar › **Web oturumları**: profil listesi (alan adları, çerez sayısı, kaynak, son kullanım),
"Dosyadan" / "Chrome'dan" içe aktarma (önce alan adlarını gösterir, işaretlediklerin onaylı
listedir), "Giriş penceresi aç", "Varsayılan yap", "Sil". RPC'ler: `tarayici.profiller`,
`tarayici.dosya_onizle`, `tarayici.chrome_profilleri`, `tarayici.ice_aktar`, `tarayici.sil`,
`tarayici.giris` / `tarayici.giris_durumu`, `tarayici.varsayilan`.

## Sınırlar

- Windows'ta Chrome çerezleri (DPAPI) çözülmez; Cookie-Editor ile JSON dışa aktarıp
  `import-cookies` kullan. Safari (binarycookies) desteklenmez.
- Kits tarayıcısı ve web MODEL profilleri (`web_profiles/`, ChatGPT/Claude/Gemini/Copilot)
  bu depoyu henüz kullanmaz.
