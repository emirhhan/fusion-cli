# Bilgisayar kullanımı (computer use)

Fusion macOS'ta ve Windows'ta (yalnız masaüstü uygulamasında; bkz. [Windows](#windows)) ekranı görebilir (`desktop_screenshot`), fareyi ve klavyeyi kullanabilir
(`desktop_mouse`, `desktop_click`, `desktop_scroll`, `desktop_type`, `desktop_key`) ve arka
plandaki pencerelerle işaretçiyi almadan çalışabilir (`desktop_background_*`). İki macOS izni
gerekir: **Erişilebilirlik** (tıklama/yazma) ve **Ekran Kaydı** (ekranı görme); durumları
Ayarlar › Bu bilgisayar kartında görünür.

## Açma

Computer use Claude Code'daki gibi **varsayılan kapalıdır**.

- Masaüstünde: Ayarlar › **Bu bilgisayar** › "Computer use'u etkinleştir" (`desktop.enabled`).
- CLI/REPL/TUI'de proje başına: `/mcp` listesinde yerleşik `computer-use` satırı görünür;
  `/mcp enable computer-use` o projede açar (`/mcp disable computer-use` kapatır). Kayıt
  kullanıcı dizinindedir (`computer-use-projects.json`); depodaki bir dosya computer use'u açamaz.
- Etkileşimsiz yolda (`fusion -p`, arka plan işi) ve `fusion mcp` sunucusunda `desktop_*`
  araçları hiç sunulmaz (Claude: "requires an interactive session").

## Ayarlar › Bu bilgisayar

| Ayar | Varsayılan | Anlamı |
|---|---|---|
| `desktop.enabled` | `false` | Computer use anahtarı |
| `desktop.denied_apps` | `[]` | Sorulmadan reddedilen uygulamalar (ad ya da paket kimliği); masaüstü Ayarlar'dan yönetilir |
| `desktop.background` | `true` | Yalnız masaüstü uygulamasında: arka planda çalış (diğer uygulamalar gizlenmez) |
| `desktop.unhide_on_finish` | `true` | Yalnız masaüstü uygulamasında: "Unhide apps when Claude finishes" |
| `desktop.escape_stops` | `true` | Fusion fareyi/klavyeyi kullanırken fiziksel Esc turu durdurur |

Kullanımdan kalkan anahtarlar (okunur, **yok sayılır**, bir kez uyarılır): `desktop.control_level`,
`desktop.category_defaults`, `desktop.app_levels` (kademeler sabit), `desktop.app_consent`
(onay her zaman sorulur), `runtime.desktop_screenshot_max_width` ve
`runtime.desktop_exclude_fusion_window` (ekran görüntüsü boyutu sabit, Fusion penceresi ve
CLI'de terminal her zaman dışlanır).

Masaüstü RPC'leri: `bilgisayar.ayarlar`, `bilgisayar.ayar_yaz {anahtar, deger}`,
`bilgisayar.uygulamalar`, `bilgisayar.uygulama_reddet {uygulama}`.

## Uygulama başına onay ve kademe tablosu

Her masaüstü eyleminden önce Fusion hedef uygulamayı çözer: tıklamada noktadaki pencerenin
sahibi, klavyede öndeki uygulama, arka plan araçlarında `pid`, `desktop_open`'da verilen ad.
Uygulama oturumda ilk kez kullanılacaksa **her kipte** (İzinleri atla dahil) iki seçenek sorulur:

- **Bu oturumda <Uygulama> için izin ver** — o uygulamadaki sıradan eylemler oturum boyunca
  bir daha sorulmaz (izin uygulamaya bağlıdır, araca değil).
- **Reddet** — çağrı yapılmaz.

Model işe başlamadan kullanacağı uygulamaları `desktop_request_access` ile **tek istemde**
isteyebilir (Claude: `request_access`). İstem denetlenecek uygulamaları kademeleriyle ve
çalışırken kaç diğer uygulamanın gizleneceğini gösterir; "Bu oturumda Mail, Notes için izin
ver" onaylanan her uygulamayı oturum boyu izinli yapar, ilk tıklamada ayrıca sorulmaz. Ret
listesindeki uygulama ve Fusion karta girmez; hepsi engelliyse istek sorulmadan kapanır.

Terminalde Enter, `e` ya da `o` oturum izni verir, `h` reddeder. Tek çağrılık "Evet" ve
"Her zaman reddet" yoktur; ret listesi Ayarlar'dan yönetilir. Plan kipinde masaüstü eylemi
yapılmaz. Riskli eylemler (gönder/sil/öde düğmesi, sohbette Enter, Sistem Ayarları) her
seferinde ayrıca sorulur.

Kademeler uygulama kategorisine göre **sabittir** ve değiştirilemez:

| Kategori | Kademe | Not |
|---|---|---|
| Tarayıcılar (Safari, Chrome, Firefox, Edge, Arc…) ve yatırım platformları (Binance, MetaTrader, TradingView…) | yalnız bak | Ekran görüntüsünde görülür; web işi için `chrome_*` / `browser_*` |
| Terminaller (Terminal, iTerm2, Warp…) ve IDE'ler (VS Code, Cursor, Xcode, JetBrains…) | tıkla | Kabuk erişimine eşdeğer; komut için `run_shell` |
| Fusion'ın kendisi | engelli | Ajan kendi onay kartını onaylayamaz |
| Sistem Ayarları, Finder | tam kontrol | Uyarılı; Sistem Ayarları'nda her eylem ayrıca sorulur |
| Diğer her şey (parola yöneticileri dahil) | tam kontrol | İstersen ret listesine ekle |

Kademeler: **yalnız bak** = ekran görüntüsü ve öne getirme; **tıkla** = tıklama, hover,
kaydırma; **tam kontrol** = ayrıca yazma, tuş/kısayol, sürükleme. Sıra: ret listesi →
Fusion → sabit kategori tablosu. Engelli uygulama ya
da yetmeyen kademe her kipte (İzinleri atla dahil) sorulmadan kapanır ve modele önerilen yol
söylenir. Hedef okunamazsa (Erişilebilirlik izni yok, yardımcı derlenemedi, noktadaki öğe
okunamadı) ret listesi denetlenemez: tıklama/yazma her kipte (**İzinleri atla dahil**) her
seferinde sorulur ve oturum iznine dönüşmez; arka plan araçları (`desktop_background_*`) ise
sorulmadan kapanır. Arka plan araçlarında `pid` metin (`"1234"`) ya da `1234.0` gelse de araçla
aynı kuralla çözülür.

## Riskli eylemler (her seferinde sorulur)

Oturum izni olsa da, İzinleri atla kipinde bile şu eylemler her çağrıda ayrıca sorulur ve
oturum iznine dönüşmez (kart "Dikkat:" satırında nedeni yazar):

- Tıklanan öğenin adı gönder/sil/öde/yayınla/çıkış türündense ("Gönder", "Sil", "Place order",
  "Move to Trash", "Çöp Sepetini Boşalt"…). Sözcük listesi Chrome ile ortaktır
  (`tools/risk_words.py`); öğe adı Erişilebilirlik ağacından okunur, alan değeri okunmaz.
  Yalnız öğenin adı aranır (rol değil); metin kutusuna tıklamak riskli sayılmaz.
- Arka plan `press` hedefinin adı aynı türdense.
- Basılı tutup bırakma (`desktop_mouse action=down|up`) tıklamayla aynı sayılır.
- Terminal ve IDE'de Enter ya da satır sonu içeren `desktop_type` metni (komut çalıştırır).
- Sohbet uygulamalarında (Slack, Mesajlar, WhatsApp, Telegram, Discord, Teams, Signal,
  Messenger) düz Enter ve satır sonu içeren metin (mesajı gönderir); Shift+Enter sorulmaz.
- Her uygulamada Cmd/Ctrl+Enter (genellikle gönderir) ve Cmd+Delete (siler/çöpe atar);
  odakta riskli bir düğme varken Enter.
- Sistem Ayarları'nda her tıklama ve yazma.

## Tur süresince: tek oturum, Esc ile durdurma, gizle / geri göster

- **Tek oturum kilidi**: ilk computer use eyleminde alınır ve görev bitince değil, **oturum
  çıkınca** bırakılır (CLI'de süreç, masaüstünde sohbetten çıkış). İkinci oturum kilidi tutan
  oturumu adıyla anan bir hata alır; çöken oturumun kilidi süreç ölünce kendiliğinden kalkar.
- **Bildirim**: turdaki ilk ekran eyleminde macOS bildirimi "Fusion bilgisayarını kullanıyor ·
  durdurmak için Esc'e bas", bitince ikinci bildirim çıkar.
- **Esc ile durdur** (`desktop.escape_stops`): ilk fare/klavye eyleminde küresel bir Esc
  dinleyicisi kurulur (Erişilebilirlik izni). Fiziksel Esc turu durdurur (Ctrl+C / Durdur ile
  aynı) ve tuş uygulamaya **gitmez**; Fusion'ın kendi gönderdiği `desktop_key key=esc`
  durdurmaz. Masaüstünde ilk başarılı fare/klavye eyleminden sonra sohbetin üstünde "Fusion
  bilgisayarı kullanıyor · durdurmak için Esc" şeridi ve **Durdur** düğmesi görünür
  (`BilgisayarKullaniliyor` olayı); "· durdurmak için Esc" yalnız dinleyici gerçekten kurulduysa
  yazar (Erişilebilirlik izni yoksa kurulamaz). Esc ile durdurulan turdan sonra "Esc ile
  durduruldu" notu görünür; terminalde aynı cümle basılır.
- **Diğer uygulamaları gizleme**: CLI/REPL/TUI'de her zaman açıktır ve tur sonunda gizlenenler
  her zaman geri gösterilir (Claude: "Auto-unhide: Always on"). Masaüstü uygulamasında
  **Arka planda çalış** (`desktop.background`, varsayılan açık) diğer uygulamaları gizlemez;
  kapatılırsa ilk ekran eyleminde öndeki uygulama, eylemin hedef uygulaması ve Fusion (Fusion.app ya da Fusion'ı çalıştıran
  terminal) dışındaki uygulamalar gizlenir; `desktop.unhide_on_finish` açıksa tur bitince
  (iptal dahil) geri gösterilir.
- **Ekran görüntüsü boyutu**: en-boy oranı korunarak sabit hedefe küçültülür (3456x2234 Retina
  → ~1372x887); ayarı yoktur.
- **Ekran görüntüsünden dışlananlar**: her zaman Fusion'ın kendi penceresi (ve CLI'de terminal)
  ve reddedilen uygulamalar. Bölge yakalama (`region=`) da ScreenCaptureKit ile dışlamalı yapılır.
  ScreenCaptureKit yoksa (macOS < 14, yardımcı derlenemedi) `screencapture`'a düşülür; o yol
  dışlama yapamadığı için ekranda engelli bir uygulamanın penceresi görünüyorsa (ya da pencereler
  okunamıyorsa) görüntü **alınmaz** ve model kullanıcıdan uygulamayı gizlemesini ister.
- **Listeler ve erişilebilirlik ağacı**: `desktop_windows` ve `desktop_background_windows`
  reddedilen uygulamaların pencerelerini listelemez; öndeki uygulama engelliyse
  `desktop_accessibility` ağacı vermez. Ad eşleşmesi pencere sahibinin adıyla yapılır; ret
  listesine paket kimliği yazıldıysa (`com.…`) listelerde ad da eklenmeli.

## Windows

Claude Code'daki gibi computer use Windows'ta **yalnız masaüstü uygulamasında** çalışır; CLI,
REPL ve TUI'de Windows'ta `desktop_*` araçları "yalnız Fusion masaüstü uygulamasında" hatası
verir (Claude: "Computer use in the CLI is not available on Linux or Windows. On Windows, use
Desktop instead."). Windows'ta **izin adımı yoktur**: Ayarlar › Bu bilgisayar anahtarı açılınca
hemen etkindir (Erişilebilirlik/Ekran Kaydı "verilmiş" görünür).

| Parça | Windows'ta |
|---|---|
| Fare, kaydırma, klavye, metin | `SendInput` (mutlak sanal masaüstü koordinatı, Unicode metin); `cmd`/`win` = Windows tuşu, `alt`/`option` = Alt |
| Ekran görüntüsü | GDI yakalama, çoklu ekran (ana ekran 1), fiziksel piksel (DPI farkında), aynı sabit hedef boyut |
| Hedef uygulama | tıklama noktasındaki/öndeki üst düzey pencerenin süreci → exe (`chrome` / `chrome.exe`); UWP uygulamalarında (Ayarlar, Hesap Makinesi, Store) çerçeve süreci ApplicationFrameHost.exe değil barındırılan uygulama (`SystemSettings.exe`) sayılır, çözülemezse hedef çözülmemiştir; öğe adı UI Automation ile (riskli düğme denetimi). UI Automation yanıt vermezse (zaman aşımı, PowerShell engelli) öğe "doğrulanamadı" sayılır ve o tıklama her seferinde sorulur |
| Kademe ve ret listesi | aynı sabit tablo; Windows exe adları eklendi (Chrome/Edge/Firefox = Yalnız bak, Windows Terminal/PowerShell/cmd/VS Code = Tıkla, Dosya Gezgini, Ayarlar/Denetim Masası ayrıca sorulur). Ret listesine exe kökü ya da adı yazılır (`1Password`, `notepad.exe`) |
| Fusion'ın penceresi | Fusion.exe ve çocukları (yan süreç → … → Fusion.exe; zincir Fusion.exe'de biter, explorer.exe ve kabuklar asla Fusion sayılmaz) her zaman engelli (kendi onay kartına tıklayamaz); görüntüde karartılır (macOS'taki gibi arkası gösterilmez; pencere WDA_EXCLUDEFROMCAPTURE taşırsa karartılmaz) |
| Reddedilen uygulamalar | pencereleri görüntüde karartılır; yakalama olmazsa karartmasız geri düşüş yapılmaz |
| Diğer uygulamaları gizle | etkinleştirmeden simge durumuna küçültme; tur sonunda yalnız Fusion'ın küçülttükleri geri açılır |
| Esc ile durdur | alçak düzey klavye kancası; fiziksel Esc uygulamaya gitmez, Fusion'ın gönderdiği Esc turu durdurmaz |
| `desktop_open` | ad Kayıt Defteri App Paths, Başlat menüsü kısayolu ya da PATH'teki mutlak klasörlerden çözülür; yol, URL ve kabuk karakteri kabul edilmez, çalışma klasörü aranmaz |

Windows'ta olmayanlar: `desktop_background_*` (arka plan pencere araçları; hedef doğrulanamadığı
için kapalı kalır), `desktop_accessibility` / `desktop_windows` / `desktop_window_focus`
(AppleScript tabanlı) ve işletim sistemi bildirimi (uygulama içi şerit gösterilir). Karartma
pencere dikdörtgenidir: reddedilen pencerenin önünde başka pencere olsa da o alan gösterilmez.
Windows yolu bu sürümde gerçek bir Windows makinesinde elle denenmedi; davranış sahte Win32
katmanıyla sınandı (`tests/test_desktop_win32.py`, `tests/test_desktop_win32_kimlik.py`).

## `fusion mcp` sunucusunda ve etkileşimsiz kipte

Claude Code'da computer use etkileşimli oturum ister. `fusion mcp` (Fusion'ın araçlarını başka
MCP istemcilerine açan sunucu) `desktop_*` araçlarını `desktop.enabled` ne olursa olsun sunmaz;
`fusion -p`/headless ve arka plan işlerinde de masaüstü ailesi kapalıdır.

Kapalıyken masaüstü işine benzeyen bir istekte model, bunu yapamayacağını söyler ve açmayı
önerir (`/mcp enable computer-use` ya da Ayarlar › Bu bilgisayar). Not sabit sistem istemine
girmez; yalnız o turun isteğine eklenir (`engines/agent/computer_use_hint.py`).

## Claude Code'dan hâlâ farklı (Henüz yok)

- Pano okuma/yazma izni: Claude'un pano araçları olduğu için istemde ek izin satırı var;
  Fusion'da pano aracı yok, istemde ek izin satırı çıkmaz — #426.
