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
  Geri yazım onaylı alan adlarıyla süzülür: ajanın gezdiği başka sitelerin çerezi profile girmez.
  Çerezlerin yanında `localStorage` (Playwright `origins`) da saklanır; oturumu JWT ile
  localStorage'da tutan siteler de çalışır.
- **Kullanım anı onayı:** ajan bir profili yüklemek üzereyken (`profile` argümanı ya da
  `default_profile`) her kipte onay sorulur — "girişli tarayıcı oturumunu ajana açıyor".
  Plan kipinde profil yüklenmez. Profil etkinken `browser_click` ve `browser_type(submit)`
  uzak yazma sayılır ve otomatik kipte de sorulur; çerezsiz tarayıcıda eski davranış sürer.
- Normal Chrome profilin **kendiliğinden hiç okunmaz**; yalnız sen `import-chrome` dediğinde ve
  macOS Keychain izin diyaloğunda "İzin ver" dediğinde okunur.

## Komutlar

```bash
fusion browser profiles                                   # kayıtlı profiller (ad, alan adı, sayı)
fusion browser import-cookies cookies.txt -p is           # Netscape cookies.txt ya da JSON
fusion browser import-cookies dump.json -p is -d example.com -d shop.example.org --yes
fusion browser chrome-profiles                            # bu bilgisayardaki Chrome profilleri
fusion browser import-chrome -p is --chrome-profile "İş" -d example.com
fusion browser import-chrome -p hepsi --chrome-profile "İş" --all-domains   # bilerek: tüm siteler
fusion browser login is --url https://example.com/login   # görünür pencerede gir, kapatınca kaydet
fusion browser web-sessions                               # web MODEL oturumları (ChatGPT/Claude/…)
fusion browser import-web-session chatgpt -p gpt -d chatgpt.com   # model oturumundan tek yönlü kopya
fusion browser default is                                 # browser_open hep bu profille açılsın
fusion browser default                                    # varsayılanı kaldır
fusion browser set headless off                           # pencere görünür açılsın
fusion browser set profiles_enabled off                   # ajan hiçbir profil yükleyemez
fusion browser delete is --yes
```

İçe aktarma önce alan adı listesini gösterir ve onay ister; betiklerde (TTY yok) `--yes`
zorunludur — silme için de. Chrome'dan aktarırken alan adı seçmek zorunludur (`-d`); bütün
Chrome oturumunu taşımak ancak açık `--all-domains` ile olur.
`login`: pencere kapanınca ya da Chrome'dan çıkılınca (Cmd+Q) son alınan oturum yazılır.
Desteklenen dosyalar: Netscape `cookies.txt` (curl/wget/"Get cookies.txt" eklentisi, `#HttpOnly_`
öneki tanınır) ve JSON (Cookie-Editor/EditThisCookie listesi ya da Playwright `storage_state`).

## Web model oturumundan aktarma

ChatGPT/Claude/Gemini/Copilot web aboneliklerinin oturumları (`web_profiles/<sağlayıcı>/<hesap>/`)
ajanın tarayıcısıyla **kendiliğinden hiç paylaşılmaz**: girişli abonelik çerezi, istem
enjeksiyonlu bir sayfanın o siteye girişli istek yaptırmasına kapı açar. İstersen tek yönlü,
alan adı seçimli bir kopya alırsın:

- CLI: `fusion browser import-web-session <sağlayıcı> --profile <ad> -d <alan> [-d …]
  [--account main] [--yes]`. Sağlayıcı `chatgpt`, `claude`, `gemini`, `copilot` (ya da
  `chatgpt_web` …). `-d` zorunludur; `localhost`, özel IP, `.local`/`.internal` ve tek etiketli
  adlar (`com`, `intranet`) reddedilir. Önce aktarılacak alan adları ve uyarı gösterilir.
- REPL: `/oturum-aktar <sağlayıcı> <profil> <alan>… [--hesap <ad>]` önizler; aynı komut
  `--yes` ile yinelenince kopyalar (`/import-web-session` takma adı da çalışır).
- Masaüstü: Ayarlar › Web oturumları › **Model oturumundan aktar** — oturumu seç, "Alan
  adlarını göster", gerekli siteleri işaretle (hiçbiri hazır seçili gelmez), "İçe aktar".
  RPC'ler: `tarayici.web_oturumlari` (`{saglayici?, hesap?}` → oturumlar + alan adları) ve
  `tarayici.web_oturumu_aktar` (`{saglayici, hesap, ad, alan_adlari}`).

Değerler web oturumunun kendi paylaşılan Chrome'undan (CDP) okunur: oturum açıksa ona
katılınır ve yalnız bu okumanın kirası bırakılır, sohbet sekmeleri kopmaz; kapalıysa görünmez
açılıp okunur ve kapatılır. Alan adı önizlemesi `Cookies` veritabanının kopyasından, şifre
çözmeden yapılır. Kopya `kaynak: web_oturumu` ile normal şifreli profile yazılır; o profili
yükleyen her ajan çağrısı yine "girişli tarayıcı oturumunu ajana açıyor" onayından geçer.
Giriş penceresi açıkken aktarma "tarayıcısına bağlanılamadı" hatası verir; pencereyi kapatıp yinele.

## Kits: Kit tarayıcısına Fusion profili

Kit'in kendi tarayıcısı (fusion-kits, Node/Playwright) şifreli `cookies.enc`'i okuyamaz; anahtar
Kit sürecine açılmaz. Fusion izni açık bir Kit, Kits'teki `fusion_profile` aracıyla
`{profile, domains[], reason?}` ister; akış Chrome köprüsüyle aynı güven modelidir:

1. Kit iframe'i → Fusion hostu (`app/src/kits/kitsProfileHost.ts`; yalnız Kits kökeni ve o iframe).
2. `tarayici.profil_tarif {ad, alanlar}` kapıları uygular, kullanıcıya sormadan reddeder:
   `runtime.disabled_tools` içinde `fusion_profile`, `browser.profiles_enabled: false`, anahtar yok,
   profil yok, en çok 20 alan adı, iç ağ adı, **profilin onay listesi dışındaki alan adı**.
3. Onay penceresi HER istekte Kit adını, profili, istenen ve profilde eşleşen alan adlarını
   gösterir ("Oturumu ver" / "Reddet"); izin hatırlanmaz.
4. `tarayici.profil_disa_aktar {ad, alanlar}` yalnız istenen alan adlarına süzülmüş
   `storage_state`'i döndürür; host onu yalnız o iframe'e postalar (bellek içi). Kits sunucusu
   oturumu kalıcı olmayan bir tarayıcı bağlamına verir (profil klasörüne yazmaz, loglamaz) ve
   tarayıcı kapanınca siler. Kit'in modeli yalnız "profil yüklendi: N çerez, alan adları" görür.

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
"Dosyadan" / "Chrome'dan" içe aktarma (önce alan adlarını gösterir; hiçbiri hazır işaretli
gelmez, işaretlediklerin onaylı listedir), "Giriş penceresi aç" (mevcut profil) ve "Yeni profil
için giriş…" (ad + adres), "Varsayılan yap", "Sil", iki anahtar: profilleri yükleyebilsin
(`profiles_enabled`) ve pencere görünür açılsın (`headless: false`). Giriş penceresi hata ile
kapanırsa sebebi (ör. `playwright install chromium`) hata satırında görünür.
RPC'ler: `tarayici.profiller`, `tarayici.dosya_onizle`, `tarayici.chrome_profilleri`,
`tarayici.ice_aktar`, `tarayici.sil`, `tarayici.giris` / `tarayici.giris_durumu`,
`tarayici.varsayilan`, `tarayici.ayar` (`{anahtar: "headless"|"profiles_enabled", deger: bool}`),
`tarayici.web_oturumlari`, `tarayici.web_oturumu_aktar`, `tarayici.profil_tarif`,
`tarayici.profil_disa_aktar` (Kits; yukarıdaki bölüm).

## Sınırlar

- Windows'ta Chrome çerezleri (DPAPI) çözülmez; Cookie-Editor ile JSON dışa aktarıp
  `import-cookies` kullan. Safari (binarycookies) desteklenmez.
- Linux'ta anahtarlık (gnome-keyring/kwallet) etkinse Chrome çerezleri `v11` ile şifrelidir ve
  çözülmez (yalnız `v10`/"peanuts"); çözülemeyen kayıtlar atlanır ve sayısı günlüğe yazılır,
  hiçbiri çözülemezse açık ipucu verilir. Çözüm yine Cookie-Editor JSON + `import-cookies`.
- Giriş penceresinden gelen profilde onay listesi yoktur ("hepsi"): girdiğin her sitenin çerezi
  saklanır. Daraltmak için `import-cookies -d` ile yeniden aktar.
- Model oturumundan aktarılan kopya kendiliğinden tazelenmez: abonelik oturumu yenilense de
  profil eski çerezle kalır; gerekirse aynı komutla yeniden aktar.
