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
