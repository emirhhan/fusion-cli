# Bilgisayar kullanımı (computer use)

Fusion macOS'ta ekranı görebilir (`desktop_screenshot`), fareyi ve klavyeyi kullanabilir
(`desktop_mouse`, `desktop_click`, `desktop_scroll`, `desktop_type`, `desktop_key`) ve arka
plandaki pencerelerle işaretçiyi almadan çalışabilir (`desktop_background_*`). İki macOS izni
gerekir: **Erişilebilirlik** (tıklama/yazma) ve **Ekran Kaydı** (ekranı görme); durumları
Ayarlar › Bu bilgisayar kartında görünür.

## Ayarlar › Bu bilgisayar

Masaüstünde Ayarlar › **Bu bilgisayar**; terminalde `fusion config set desktop.<alan> <değer>`
ya da sohbette `/config desktop.<alan>=<değer>`. Hepsi `config.yaml` içindeki `desktop:`
bölümüne yazar; değişiklik bir sonraki turda geçerlidir.

| Ayar | Varsayılan | Anlamı |
|---|---|---|
| `desktop.enabled` | `true` | `false`: `desktop_*` araçları modele hiç sunulmaz |
| `desktop.control_level` | `full` | Tavan: `observe` (yalnız bak) · `click` (tıkla) · `full` (tam kontrol) |
| `desktop.category_defaults` | `true` | Kategori tablosu (aşağıda); `false`: her uygulama tavanı alır |
| `desktop.denied_apps` | `[]` | Hiç dokunulmayan uygulamalar (ad ya da paket kimliği) |
| `desktop.app_levels` | `[]` | Uygulama başına kademe: `Terminal=full`, `com.apple.Safari=click` |
| `desktop.app_consent` | `true` | Uygulama oturumda ilk kez kullanılırken sor |
| `desktop.background` | `true` | `false`: ilk ekran eyleminde diğer uygulamalar gizlenir |
| `desktop.unhide_on_finish` | `true` | Tur bitince gizlenen uygulamaları geri göster |
| `desktop.escape_stops` | `true` | Fusion fareyi/klavyeyi kullanırken fiziksel Esc turu durdurur |

Örnekler:

```bash
fusion config set desktop.enabled false            # computer use'u kapat
fusion config set desktop.denied_apps "Mail, Notes"
fusion config set desktop.app_levels "Terminal=full"
fusion config get desktop.control_level
```

Masaüstü RPC'leri: `bilgisayar.ayarlar`, `bilgisayar.ayar_yaz {anahtar, deger}`,
`bilgisayar.uygulamalar`, `bilgisayar.uygulama_reddet {uygulama}`.

## Uygulama başına onay ve kademe tablosu

Her masaüstü eyleminden önce Fusion hedef uygulamayı çözer: tıklamada noktadaki pencerenin
sahibi, klavyede öndeki uygulama, arka plan araçlarında `pid`, `desktop_open`'da verilen ad.
Uygulama oturumda ilk kez kullanılacaksa kart sorar:

- **Bu oturumda <Uygulama> için izin ver** — o uygulamadaki sıradan tıklama, kaydırma ve
  yazma bu oturumda bir daha sorulmaz (izin uygulamaya bağlıdır, araca değil).
- **Evet** — yalnız bu çağrı.
- **Hayır** — çağrı yapılmaz, tur durur.
- **Her zaman reddet** — uygulama `desktop.denied_apps`'e eklenir (yalnız masaüstü
  uygulamasının kartında); aynı turdaki sonraki çağrılar da kart açılmadan reddedilir.

Terminalde `o` (oturum), `e` (yalnız bu kez), `h` (hayır) yazılır. Kip tablosu: Otomatik,
Düzenlemeleri kabul et ve Manuel kipte ilk kullanım sorulur; Plan kipinde masaüstü eylemi
yapılmaz; İzinleri atla kipinde oturum onayı sorulmaz (riskli eylem yine sorulur).
`desktop.app_consent: false` ilk kullanım sorusunu kapatır.

| Kategori | Kademe | Not |
|---|---|---|
| Tarayıcılar (Safari, Chrome, Firefox, Edge, Arc…) | yalnız bak | Web işi için `chrome_*` / `browser_*` |
| Terminaller (Terminal, iTerm2, Warp…) ve IDE'ler (VS Code, Cursor, Xcode, JetBrains…) | tıkla | Kabuk erişimine eşdeğer; komut için `run_shell` |
| Yatırım / kripto (Binance, MetaTrader, TradingView, Ledger Live, Midas…) | engelli | |
| Parola yöneticileri (Anahtar Zinciri Erişimi, Parolalar, 1Password, Bitwarden…) | engelli | |
| Fusion'ın kendisi | engelli | Ayarla da açılmaz: ajan kendi onay kartını onaylayamaz |
| Sohbet (Slack, Mesajlar, WhatsApp, Telegram, Discord, Teams…) | tam kontrol | Enter ile gönderme her seferinde sorulur |
| Sistem Ayarları, Finder | tam kontrol | Uyarılı; Sistem Ayarları'nda her eylem ayrıca sorulur |
| Diğer her şey | tam kontrol | |

Kademeler: **yalnız bak** = ekran görüntüsü ve öne getirme; **tıkla** = tıklama, hover,
kaydırma; **tam kontrol** = ayrıca yazma, tuş/kısayol, sürükleme. Sıra: ret listesi →
Fusion → `desktop.app_levels` → kategori → `desktop.control_level` tavanı. Engelli uygulama ya
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

- **Tek oturum kilidi**: aynı anda yalnız bir Fusion turu fareyi/klavyeyi kullanır; ikinci
  oturum "Başka bir Fusion oturumu bilgisayarı kullanıyor" hatası alır.
- **Esc ile durdur** (`desktop.escape_stops`): ilk fare/klavye eyleminde küresel bir Esc
  dinleyicisi kurulur (Erişilebilirlik izni). Fiziksel Esc turu durdurur (Ctrl+C / Durdur ile
  aynı) ve tuş uygulamaya **gitmez**; Fusion'ın kendi gönderdiği `desktop_key key=esc`
  durdurmaz. Masaüstünde sohbetin üstünde "Fusion bilgisayarı kullanıyor · durdurmak için Esc"
  şeridi ve **Durdur** düğmesi görünür (`BilgisayarKullaniliyor` olayı).
- **Arka planda çalış** (`desktop.background`, varsayılan açık): diğer uygulamalar gizlenmez.
  Kapatılırsa ilk ekran eyleminde öndeki uygulama, eylemin hedef uygulaması ve Fusion (Fusion.app ya da Fusion'ı çalıştıran
  terminal) dışındaki uygulamalar gizlenir; `desktop.unhide_on_finish` açıksa tur bitince
  (iptal dahil) geri gösterilir.
- **Ekran görüntüsünden dışlananlar**: Fusion'ın kendi penceresi (ve CLI'de terminal;
  `runtime.desktop_exclude_fusion_window`), reddedilen uygulamalar ve engelli kategoriler
  (yatırım/kripto, parola yöneticileri). Bölge yakalama (`region=`) da ScreenCaptureKit ile
  dışlamalı yapılır; Fusion dışlamasını kapatmak ret listesi dışlamasını kapatmaz.
  ScreenCaptureKit yoksa (macOS < 14, yardımcı derlenemedi) `screencapture`'a düşülür; o yol
  dışlama yapamadığı için ekranda engelli bir uygulamanın penceresi görünüyorsa (ya da pencereler
  okunamıyorsa) görüntü **alınmaz** ve model kullanıcıdan uygulamayı gizlemesini ister.
- **Listeler ve erişilebilirlik ağacı**: `desktop_windows` ve `desktop_background_windows`
  reddedilen/engelli uygulamaların pencerelerini listelemez; öndeki uygulama engelliyse
  `desktop_accessibility` ağacı vermez. Ad eşleşmesi pencere sahibinin adıyla yapılır; ret
  listesine paket kimliği yazıldıysa (`com.…`) listelerde ad da eklenmeli.

## `fusion mcp` sunucusunda

`fusion mcp` (Fusion'ın araçlarını başka MCP istemcilerine açan sunucu) aynı `desktop:` ayarını
okur: `desktop.enabled: false` ise `desktop_*` araçları sunulmaz (yapılandırma okunamazsa da
kapalı sayılır). Açıkken her masaüstü çağrısı politikadan geçer: reddedilen/engelli uygulama
ve yetmeyen kademe kapanır; MCP'de Fusion kullanıcıya soramadığı için hedefi okunamayan
eylem ve riskli eylem (gönder/sil, Terminal'de Enter, Sistem Ayarları) de çalıştırılmaz.
İlk kullanım onayı dış istemcinin kendi araç onayına bırakılır.
