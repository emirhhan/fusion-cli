# Fusion Browser ↔ Claude in Chrome parite matrisi

Karşılaştırma `mcp__claude-in-chrome__*` araç adlarına dayanır (şemalarını tek tek açmadım,
adlardan ve bilinen davranıştan çıkardım). Doğrulama: `cd app && npx playwright test -c
playwright.extension.config.ts` (gerçek Chromium + yüklü eklenti, yerel test sitesi, 9 test).

| Claude in Chrome | Fusion karşılığı | Durum |
|---|---|---|
| `navigate` (url, geri, ileri) | `chrome_navigate`, `chrome_action back/forward/reload` | Var; e2e'de gezinme |
| `read_page` (erişilebilirlik ağacı, ref'ler) | `chrome_page` (etkileşimli öğe listesi + ref + görünür metin) | Kısmi: tam ağaç/filtre/derinlik parametresi yok, düz liste var |
| `find` (doğal dil) | `chrome_page query` (metin/etiket eşleşmesi) | Kısmi: doğal dil değil, metin araması; model sorguyu kendisi seçer |
| `get_page_text` | `chrome_action text` (sayfa sayfa) | Var |
| `form_input` (değer, onay kutusu, seçim) | `chrome_type`, `chrome_action select`, `check` | Var; e2e'de form, seçim, onay kutusu |
| `computer` sol/çift/sağ/üç tık | `chrome_click`, `click_at`, `double_click`, `right_click`, `triple_click` | Var; e2e'de çift/sağ |
| `computer` yaz | `chrome_type` (ref), `chrome_action type_focused` (odaktaki alan) | Var; e2e |
| `computer` tuş | `chrome_action key` (Enter, Esc, Tab, oklar, Home/End/PageUp/Down, `ctrl+a`, `Shift+Tab`…) | Kısmi: olaylar sayfa içinde üretilir; kopyala/yapıştır gibi gerçek OS kısayolu yok |
| `computer` kaydır (yön, miktar) | `chrome_action scroll` (`down:600`, `left`, `right`, `up`, ref) ve `wheel` | Var |
| `computer` sürükle | `chrome_action drag` (ref→ref ya da x,y) | Var; e2e (HTML5 sürükle-bırak) |
| `computer` ekran görüntüsü | `chrome_action screenshot` | Var; **e2e'de sınanmadı** (Chrome'un "tüm siteler" izni kullanıcı tıklaması ister) |
| `computer` zoom (bölge) | `chrome_action zoom` (x1,y1,x2,y2, 2x kırpma) | Var; Python testi, e2e'de yok |
| `computer` hover / scroll_to | `chrome_action hover`, `scroll` + ref | Var |
| `computer` bekle | `chrome_action wait` (metin görünene kadar) | Var (ağ boşta beklemesi yok) |
| `tabs_context`, `tabs_create`, `tabs_close` | `chrome_action tabs / open / tab / close` | Var; e2e |
| `resize_window` | `chrome_action resize` | Var; e2e |
| `file_upload`, `upload_image` | `chrome_action upload` (proje dosyaları) | Var; e2e (içerik gönderilmez, yalnız alana konur) |
| `javascript_tool` | — | **Bilerek yok:** keyfi sayfa betiği, girişli oturumda veri sızdırma/işlem riski; model aynı işi okuma ve etkileşim araçlarıyla yapar |
| `read_console_messages`, `read_network_requests` | — | **Yok:** `debugger` izni (Chrome'da "tarayıcıyı hata ayıkla" uyarısı) ister; şimdilik eklenmedi, istenirse ayrı iş |
| `shortcuts_list/execute`, `gif_creator` | — | **Bilerek yok:** Claude'a özgü kısayol ve kayıt özellikleri |
| `list/select/switch_browser` | — | **Bilerek yok:** Fusion tek tarayıcıya (kullanıcının Chrome'u) bağlanır |

## Güvenlik ve izin karşılaştırması

- Site izni: ilk girişte panelde kart (tek tık; "tüm siteler" ya da yalnız o site), komut kullanıcıyı bekler.
- Sorulan adımlar: gönder, paylaş, sil, satın al, öde, kayıt ol, hesap oluştur, hesabı bağla, oturumu kapat,
  mesaj kutusunda Enter, `form submit`, sekme kapatma. Parola/OTP/kart alanlarına yazma ve okuma kapalıdır.
- Panel turlarında sunucu tarafı `web_fetch`/`web_search` yoktur (girişli oturumu görmez).

## Doğrulanmayanlar

Gerçek Chrome'da (kullanıcı profili) ve girişli gerçek sitelerde (Meta Ads vb.) denenmedi; ekran görüntüsü,
site izni penceresi ve Erişilebilirlik ile otomatik kurulum otomasyonla sınanamadı. Olaylar sayfa içi betikle
üretildiği için "güvenilmez olay" ayrımı yapan siteler fare/klavye girdisini yok sayabilir.
