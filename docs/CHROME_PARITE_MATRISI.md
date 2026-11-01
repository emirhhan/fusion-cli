# Fusion Browser ↔ Claude in Chrome parite matrisi

## Araç adları (#431)

Model Claude in Chrome'un araçlarını Claude'un adı ve argüman şemasıyla görür:
`claude-in-chrome__navigate`, `read_page`, `find`, `form_input`, `computer`, `get_page_text`,
`tabs_context_mcp` her istekte; `tabs_create_mcp`, `tabs_close_mcp`, `read_console_messages`,
`read_network_requests`, `gif_creator`, `shortcuts_list`, `shortcuts_execute`, `javascript_tool`,
`file_upload`, `upload_image`, `resize_window`, `browser_batch`, `list_connected_browsers`,
`select_browser`, `switch_browser` yalnız Chrome/tarayıcı/masaüstü işinde (istem bütçesi).
Fusion MCP araçlarını `sunucu__araç` biçiminde adlandırdığı için izin kuralı ve kanca
eşleştiricisi Claude'daki `mcp__claude-in-chrome__computer` adını aynen tanır
(`--disallowedTools`, `permissions.deny`, PreToolUse `matcher`).

Ajan döngüsü çağrıyı onaydan önce iç `chrome_*` çağrısına çevirir (`tools/claude_chrome_translate.py`,
`engines/agent/claude_chrome_call.py`); yasak eylemler (#422), yükleme kuralları (#437), plan kipi
(#450) ve panel akışı aynı kalır. Claude adına yazılmış izin kuralı o çağrı için iç ada da
uygulanır (toplu çağrıda yalnız deny/ask). `tabId` verilirse işlemden önce o sekme bağlanır;
`navigate` boş sekmede de (`tabs_create_mcp`) adrese gider. Eski `chrome_page`, `chrome_action`,
`chrome_click`, `chrome_type`, `chrome_navigate`, `chrome_javascript`, `chrome_batch` adları modele
sunulmaz, çağrılırsa çalışır.

`computer` `modifiers` (`cmd+shift`, `ctrl`, `alt`, `win`) tıklama olayına geçer; `hover`
koordinatla da çalışır; `left_click_drag` `start_coordinate` → `coordinate` noktadan noktaya
sürükler. `read_page` `max_chars` çıktıyı keser, `tabs_context_mcp` `createIfEmpty` sekme yoksa
gruba boş sekme açar. `gif_creator` Claude gibi üç adımdır: `stop_recording` kare almayı durdurur
(kareler tutulur), `export` GIF'i `.fusion/kayitlar/` altına yazar (`filename` verilebilir),
`clear` kareleri atar. Her ekran görüntüsü bir `imageId` (`ss_N`, köprü başına son 10 görüntü,
yalnız bellekte) taşır; `upload_image` onu dosya alanına (`ref`) ya da sürükle-bırak hedefine
(`coordinate`) koyar.

Kalan farklar: `list_connected_browsers` tek yerel köprüyü (`fusion-local`) gösterir,
`switch_browser` çoklu tarayıcı bağlantısı olmadığı için hata verir; `gif_creator` `download`
yok sayılır (GIF her zaman proje içine yazılır). Değiştirici tuşlar sayfa içi olay bayraklarıdır,
gerçek tuş basımı değildir.
Aşağıdaki tablo iç adlarla eşlemeyi gösterir.

Karşılaştırma `mcp__claude-in-chrome__*` araç adlarına dayanır (şemalarını tek tek açmadım,
adlardan ve bilinen davranıştan çıkardım). Doğrulama: `cd app && npx playwright test -c
playwright.extension.config.ts` (gerçek Chromium + yüklü eklenti, yerel test sitesi, 9 test).

| Claude in Chrome | Fusion karşılığı | Durum |
|---|---|---|
| `navigate` (url, geri, ileri) | `chrome_navigate`, `chrome_action back/forward/reload` | Var; e2e'de gezinme |
| `read_page` (erişilebilirlik ağacı, ref'ler) | `chrome_page` (düz liste) ve `chrome_page tree=all|interactive` (girintili rol/ad/durum ağacı; `depth`, `ref` alt ağaç) | Var (P-043); Playwright testi `test_chrome_page_action.py::test_agac_*` |
| `find` (doğal dil) | `chrome_page query` ("kaydet düğmesi", "e-posta alanı": rol sözcüğü + sözcük eşleşmesi + Türkçe ek atma; tek rol sözcüğünde ("Menü") o adı taşıyan öğe önde; tutmazsa alt dize) | Var (P-043, modelsiz sezgisel); küçük modelle anlamsal seçim yok (ücretli çağrı kararı bekliyor) |
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
| `computer` bekle | `chrome_action wait` (metin görünene kadar ya da `network_idle`: bekleyen istek yok + belge yüklü + DOM 600 ms sabit) | Var (P-043) |
| `tabs_context`, `tabs_create`, `tabs_close` | `chrome_action tabs / open / tab / close` | Var; e2e |
| `resize_window` | `chrome_action resize` | Var; e2e |
| `file_upload`, `upload_image` | `chrome_action upload` (proje dosyaları) | Var; e2e (içerik gönderilmez, yalnız alana konur) |
| `javascript_tool` | `chrome_javascript` (`text`) | Var (#432): bağlı sekmenin ana dünyasında çalışır, son ifadenin değeri (söz verilmişse beklenerek) JSON metni olarak döner; sayfa CSP'si `unsafe-eval`e izin vermiyorsa tarayıcı reddeder. Betik satın alma yasağını aşabileceği için İzinleri atla dahil her seferinde sorulur. Yalnız Chrome/tarayıcı işinde sunulur. Claude adına geçiş #431 |
| `read_console_messages`, `read_network_requests` | `chrome_action console` (`errors`, `errors:desen`, desen) ve `network` (url deseni, `id:N` ile gövde) — `pageMonitor.js` izinli sitelere kayıtlı içerik betiği (ANA dünya, `document_start`), `console.*`/hata/`fetch`/XHR sarmalar | Var (P-042) **`debugger` izni olmadan**; başlıklar kaydedilmez, çıktı sır maskesinden geçer; panelden kapatılabilir |
| `shortcuts_list/execute` | `chrome_action shortcuts` / `shortcut=ad`; panelde Bağlantı ayarları → Kısayollar, yazarken `/ad`; Chrome `commands`: Ctrl/⌘+Shift+F panel, Ctrl/⌘+Shift+. durdur | Var (P-073) |
| `gif_creator` | `chrome_action record start|halt|stop|clear` → `.fusion/kayitlar/chrome-<zaman>.gif` (ardışık `captureVisibleTab`, en çok 120 kare / 60 sn, Pillow ile GIF) | Var (P-044); `tabCapture` izni yok; Kit bilgisayarı canlı akışı ayrı iş |
| `tabs_create` pencere, sekme grubu | `chrome_action window=URL`, `group=id,id:başlık` (`tabGroups` izni) | Var (P-073) |
| Kit'ten (Kits) tarayıcıya erişim | `fusion_browser` (Kit aracı) → `chrome.kit_komut` RPC; okuma bir kez, etkileşim her seferinde onaylı; yalnız metin | Var (P-063); bkz. `docs/KITS_KOPRUSU.md` |
| `browser_batch` | `chrome_batch` (`actions=[{name, input}]`) | Var (#432): en çok 20 Chrome eylemi sırayla, ilk hatada durur; her öğenin izin denetimi (deny/ask kuralı, yasak eylem, yükleme `Read(...)` kuralı) ayrı uygulanır, en sıkı öğe sorulur; yalnız okuyan öğelerden oluşan toplu çağrı okuma sayılır |
| `list/select/switch_browser` | `list_connected_browsers` tek yerel köprüyü gösterir, `select_browser fusion-local` | Kısmi (#431/#432): aynı anda tek tarayıcı; `switch_browser` hata verir; yerel mesajlaşma kaydı artık Chrome, Chromium, Edge, Brave, Arc, Vivaldi, Opera ve Linux dizinlerine yazılır (#433) |

## Konsol, ağ, ağaç, kayıt ve kısayollar (31 Ekim, parite turu)

- **Konsol/ağ** (`P-042`): `chrome_action console value=errors` yalnız hataları, `errors:TypeError` desenli hataları,
  `Uncaught` serbest deseni getirir; `network value=/api/` url deseni, `id:17` tek isteğin gövdesini (metin/JSON,
  ≤16 KB) verir. İzleyici sayfaya izin verilmeden önce yüklendiyse ilk okuma onu şimdi ekler ve "izleme şimdi
  başladı" ipucu döner. Panel → Bağlantı ayarları → "Konsol ve ağ isteklerini izle" kapatılabilir (`chrome.storage.local`
  `fusionMonitor`). Köprüde `COMMAND_TIMEOUT` içinde okuma: zaman aşımı "SONUÇ BİLİNMİYOR" üretmez (salt okuma).
- **Ağaç** (`P-043`): `chrome_page tree=interactive depth=6` ya da `tree=all ref=e12`. Satır biçimi:
  `  button "Kaydet" [e3] disabled`, `heading "Başlık" level=1`, `text "..."`. 600 satırda kırpılır ve not düşer.
- **Ağ boşta** (`P-043`): `chrome_action wait value=network_idle` (yalnız bu anahtar; `network`/`ağ` gibi sözcükler sayfa metni olarak beklenir); en çok 20 sn.
- **GIF** (`P-044`): `record start` → işlemler → `record stop`; kareler eklentinin uzun yaşayan belgesinde (offscreen
  ya da elle bağlantıda panel) toplanır, köprüye ≤2,5 MB parçalarla gelir, GIF `.fusion/kayitlar/` altına yazılır.
  Ekran görüntüsüyle aynı "tüm siteler" izni gerekir.
- **Kısayollar** (`P-073`): panelde ad + görev kaydedilir; composer'da `/ozet kalan metin` kayıtlı görevi gönderir;
  ajan `chrome_action shortcuts` ile listeler, `shortcut=ozet` ile görev metnini alır. Klavye kısayolları
  `chrome://extensions/shortcuts` sayfasından değiştirilir.
- **Masaüstü Ayarlar → Tarayıcı** (31 Ekim, inceleme sonrası): eklenti bağlıyken "Eklenti ayarları" bölümü paneldeki
  iki ayarı masaüstünden yönetir: "Konsol ve ağ isteklerini izle" anahtarı ve kısayol listesi (kaydet/kaldır). RPC'ler:
  `chrome.izleme` (`{acik?: bool}` → `{acik}`), `chrome.kisayollar`, `chrome.kisayol_kaydet` (`{ad, metin}`),
  `chrome.kisayol_sil` (`{ad}`) → `{kisayollar}`; eklenti tarafında `monitor_get/set`, `shortcut_set/delete`
  (`appserver/chrome_settings.py`, `core.js`). Depo eklentinin `storage.local`'ı: panel ve masaüstü aynı listeyi görür.
  CLI'de bu iki ayar eklentinin panelinden yönetilir.
- **Onay sınıfı**: `record start|stop` REMOTE_INTERACT'tır (Manuel kipte sorulur, otomatik kipte sorulmaz);
  `window`, `open` okuma kalır. Plan kipinde `record`, `open`, `window` ve `shortcut` izin sorar, onaylanırsa
  çalışır (Claude: "Browser tools in plan mode", #450). Kayıt sırasında etkin sekme
  değişirse kare alınmaz (`record_check`), atlanan kare sayısı çıktıya düşer; kareler GIF yazılınca `release` ile bırakılır.
- **Windows/Linux**: Fusion Chrome kapalıyken `chrome_launch_command` ile açar (`start chrome`, PATH'teki
  `google-chrome`/`chromium`). Kılavuzlu kurulum hâlâ macOS/Windows.

## Panel izin modları (#434)

Yan paneldeki seçici Claude in Chrome'un üç modudur: **Manuel onay** (Manually approve; okuma dışındaki her
işlem sorulur), **Otomatik onay** (Automatically approve; varsayılan, her eylem güvenlik için denetlenir,
yalnız riskli işlem sorulur) ve **Tüm onayları atla** (Skip all approvals; açılırken onay ister; satın alma her
kipte yasak). Seçim sonraki panel oturumlarında hatırlanır; eski kayıtlı `edits`/`plan` Manuel onay olarak
gösterilir. Terminal ve masaüstü sohbetinden gelen Chrome eylemleri o oturumun kendi izin kipini kullanır.

## Oturum sekme grubu (#436)

Fusion'ın açtığı sekmeler (`tab_open`, yeni pencere) pencere başına tek bir **Fusion** sekme grubunda
toplanır; kullanıcının gruba sürüklediği http(s) sekmeleri `tabs` listesinde görünür ve seçilebilir.
Kapanış Claude in Chrome kuralıyla: terminalde ve masaüstü sohbetinde `/clear` grubu açık
sayfalarıyla kapatır (masaüstünde tur sürüyorsa yalnız boş grup kapanır, süren işin sekmesi
alınmaz); `/resume` ya da masaüstünde başka sohbete geçince, çıkışta ve masaüstü oturumu kapanınca
grup yalnız boş yeni sekmelerden oluşuyorsa kapanır. Kapanış Chrome'u açmaz ve en çok 3 sn bekler.
Gerçek Chrome'da elle denenmedi (sahte köprüyle sınandı).

## Terminalde Chrome (`--chrome`, `/chrome`; #421)

Claude Code ile aynı akış (code.claude.com/docs/en/chrome):

- `fusion --chrome` oturumu masaüstüyle aynı yerel köprüye (`ChromeBridge`, 127.0.0.1 + rastgele anahtar,
  yerel mesajlaşma ile eşleşme) bağlar; `--no-chrome` kapatır. Köprü açıkken `chrome_*` araçları modele sunulur,
  kapalıyken hiç sunulmaz. Chrome açık değilse oturum normal başlar; ilk tarayıcı eyleminde Chrome açılır.
- İlk `--chrome` açılışında bir kerelik tanıtım (Enter ile devam).
- `/chrome`: `Status: Enabled | Not connected | Disabled`, `Extension: Installed | Not detected`, bağlı tarayıcı ve
  **Enabled by default**. Seçenekler alt komuttur: `/chrome reconnect` (Reconnect extension), `/chrome select`
  (Select browser…), `/chrome default on|off`, `/chrome install`, `/chrome permissions`.
- **Enabled by default** kullanıcının yapılandırma dizinindeki `chrome-cli.json`'dadır ve sonraki oturumlara uygulanır.
  Bayraksız açılışta eklenti bulunur ve tercih yoksa "eklenti bulundu" sorusu: Evet ayarı açar ve oturumu bağlar;
  Hayır/Esc ayarı kapatır ve kurulum önerisini durdurur.
- Eklenti kurulu değilken tarayıcı gerekince oturumda en çok bir kez "Fusion tarayıcını kullanmak istiyor":
  Install extension (kılavuzlu kurulum, bağlanınca görev sürer) / Not now / Don't ask again.
- `CLAUDE_CODE_ENABLE_CFC=1` kullanıcının kabuğunda ya da `~/.claude/settings.json` `env` bloğunda Chrome'u açar;
  projenin `.claude/settings(.local).json`'ındaki aynı değer yok sayılır ve uyarılır (bir depo tarayıcıyı bağlatamaz).
- **Henüz yok**: birden çok bağlı tarayıcı arasında seçim (#432; köprü en son eşleşen tarayıcıyı kullanır),
  `-p` yolunda `--chrome`, masaüstü ile terminal aynı anda açıkken iki köprü (en son açılan eşleşir).

## Güvenlik ve izin karşılaştırması

- Site izni: ilk girişte panelde kart (tek tık; "tüm siteler" ya da yalnız o site), komut kullanıcıyı bekler.
- **Her kipte yasak** (#422; Claude in Chrome: "prohibited ... regardless of permissions"): satın alma ve finansal
  işlem, hesap oluşturma, bot doğrulaması (CAPTCHA). Tıklama, koordinat tıklaması ve form Enter'ı öğe adına bakılarak
  çalıştırılmaz; model kullanıcıya bu adımı kendisinin yapmasını söyler (`tools/chrome_guard.py`).
- **Her kipte sorulan** (İzinleri atla dahil): izin/yetki verme düğmeleri ("Authorize", "İzin ver", "Hesabı bağla")
  ve hassas alana yazma (parola, kart, CVV, IBAN, kimlik numarası).
- Sorulan adımlar (kipe göre): gönder, paylaş, sil, oturumu kapat, mesaj kutusunda Enter, `form submit`, sekme kapatma.
- Dosya yükleme (#437): toplam 10 MB; sabit bağlantılı (hard link) dosya, kimlik bilgisi adı taşıyan dosya
  (`.env`, `.pem`, `.key`, `.ssh/…`, `.aws/…`) ve `sandbox.deny_read` altındaki dosya reddedilir; `Read(...)` izin
  kuralları yüklemeye de uygulanır (`deny` reddeder, `ask` sorar; `allow` yüklemeyi genişletmez).
- Yerel adresler (#438): projenin çalışan önizleme/dev sunucularının kökenleri onaysız açılır; diğer yerel portlar,
  özel ağ ve metadata ucu kapalıdır.
- Panel turlarında sunucu tarafı `web_fetch`/`web_search` yoktur (girişli oturumu görmez).
- Konsol/ağ izleyicisi istek ve yanıt BAŞLIKLARINI (çerez, Authorization) hiç kaydetmez; gövde yalnız metin/JSON
  türünde, akış okuyucuyla 16 KB'ta kesilip iptal edilir (`truncated: true`), `text/event-stream` hiç okunmaz;
  bekleyen istek sayısı başlıkta düşer. Fusion çıktıyı `redact` ile maskeler. İzleyici yalnız kullanıcının TEK TEK izin verdiği
  sitelere kayıtlıdır (ekran görüntüsü/kayıt için verilen `<all_urls>` izni izleyiciyi kurmaz; o sitelerde ilk
  okuma izleyiciyi şimdi ekler ve ipucu döner) ve manifestte `debugger`/`webRequest` izni yoktur.

## Doğrulanmayanlar

Gerçek Chrome'da (kullanıcı profili) ve girişli gerçek sitelerde (Meta Ads vb.) denenmedi; ekran görüntüsü,
site izni penceresi ve Erişilebilirlik ile otomatik kurulum otomasyonla sınanamadı. Olaylar sayfa içi betikle
üretildiği için "güvenilmez olay" ayrımı yapan siteler fare/klavye girdisini yok sayabilir.
