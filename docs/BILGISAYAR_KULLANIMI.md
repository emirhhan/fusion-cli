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
- **Her zaman reddet** — uygulama `desktop.denied_apps`'e eklenir.

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
| Sistem Ayarları, Finder | tam kontrol | Uyarılı; Sistem Ayarları'nda her eylem ayrıca sorulur |
| Diğer her şey | tam kontrol | |

Kademeler: **yalnız bak** = ekran görüntüsü ve öne getirme; **tıkla** = tıklama, hover,
kaydırma; **tam kontrol** = ayrıca yazma, tuş/kısayol, sürükleme. Sıra: ret listesi →
Fusion → `desktop.app_levels` → kategori → `desktop.control_level` tavanı. Engelli uygulama ya
da yetmeyen kademe her kipte (İzinleri atla dahil) sorulmadan kapanır ve modele önerilen yol
söylenir. Hedef okunamazsa (Erişilebilirlik izni yok) çağrı eski temkinli yolla, her seferinde
sorulur.
