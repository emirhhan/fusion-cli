# BACKLOG

## ÖLÇÜLDÜ — zor görev hem API hem Gemini web ile geçiyor (2026-08-07)

Deneme görevi: üç ayrı hatayı düzelt (çökme, sessiz yanlış sonuç, sınır durumu) +
eksik bir modülü sıfırdan yaz + testleri geçir, TESTLERE DOKUNMADAN.

    API (nvidia_nim/nemotron-3-super)  →  11/11, test dosyaları değişmemiş
    Gemini web (taklit araç)           →  11/11, test dosyaları değişmemiş

Son Gemini koşusunun akışı: list_dir → 3 okuma → 2 yazma → pytest ile DOĞRULAMA →
özet. Tekrar yok, boşa çağrı yok.

Buraya gelene kadar ON kusur bulundu; hepsi canlı ölçümle, hiçbiri tahminle değil.

### Agent döngüsü (sağlayıcıdan bağımsız)

1. **Bütçe sayaçları iç içe turlarda sıfırlanıyordu.** Öz-denetim ve doğrulama
   kapısı `run_agent`'ı yeniden çağırıyor; sayaçlar yerel olduğu için her düzeltici
   tur sıfırdan başlıyordu. Bütçeler toplanmıyor, ÇARPILIYORDU. → `core/budget.py`
2. **Yürütme politikası da iç içe turlarda yeniden türetiliyordu.** Asıl görev BUGFIX
   (12 araç turu) olsa bile düzeltme metni basit sohbet sanılıp 5 tura düşüyordu.
3. **Tekrar dedektörü yalnızca web modellerinde açıktı**; API modelleri aynı çağrıyı
   sınırsız tekrar edebiliyordu.
4. **Türkçe ekler sınıflandırmayı bozuyordu**: "hataları" ≠ "hata", "testleri" ≠
   "test". Üç hata düzeltmek isteyen istek EXPLORE sanılıp dar bütçe alıyordu.
5. **`python3 -m pytest` onaysız geçemiyordu** — `-m` toptan yasaklıydı. Kendi araç
   talimatımızın kanonik örneği etkileşimsiz ortamda reddediliyordu.

### Web AI taşıması

6. **Her tur BİR CEVAP GERİDEN yanıtlanıyordu.** Gönderilen mesaj bir önceki turun
   cevabıyla karşılanıyor, agent onu yeni sanıp aynı araçları tekrar çalıştırıyordu.
   Kullanıcının "döngüye giriyor" dediği davranışın asıl sebebi buydu. Tazelik ölçütü
   artık önceki yanıtın KENDİSİDİR.
7. **Modelin kendi mesajı ona geri gönderiliyordu.** Stateless API'de zorunlu olan
   şey, stateful bir sohbette "bunları yap" demektir.
8. **Devam turu biçimi tekrara itiyordu.** A/B ölçüldü, tek değişken:
   talimat sonda + başlıkta ham JSON → tekrarladı; talimat başta + JSON yok →
   ilerledi ve düzeltmeyi üretti.
9. **`<tool_call>` sınırlayıcısı HTML render eden kanalda kullanılıyordu.** Sıkı bir
   temizleyici bilinmeyen elemanı içeriğiyle atıyor, mesaj boşalıyordu. Düz metin
   sınırlayıcıya geçildi.
10. **Payload satır sayımı doğru içeriği reddediyordu.** Dört canlı denemede sıfır
    gerçek bozulma yakalandı, iki kez doğru içerik reddedildi (3/2 ve 33/28). Model
    gövdeyi doğru üretiyor ama ÇERÇEVEYİ de sayıyor. Sayım kabul ölçütü olmaktan
    çıkarıldı; yerine modelden hiçbir şey istemeyen yapısal kontroller kondu.

### Ölçüm ve teşhis altyapısı

- **Sonda ham çıktı yerine ayrıştırılmış metin ölçüyordu**: araç desteği kapatılmış
  oturum KOPYASI üretiliyor ama `build()`'e yalnızca `model` alanı veriliyordu.
- **Ölçülemeyen metrik %100 raporlanıyordu** (payda sıfırken oran 1.0).
- **Oturum kaydı ölçüm sonucunu siliyordu**: panelde bir düğmeye basmak
  `tool_eval_passed`'ı düşürüyor, model sessizce salt-okunur kipe geçiyordu.
- **Geçici arıza kota sanılıyordu.** "try again later" kota işaretleri arasındaydı;
  Gemini geçici her arızada bunu gösteriyor. Kullanıcı bunun üzerine YENİ BİR HESAP
  açtı — sorun kota değildi. Kota ve geçici arıza ayrı sınıflandırılıyor; sınıflandırma
  artık modelin kendi cevabını da taramıyor.
- **Sayfa hatası BEKLERKEN fırlatılıyordu**: cevap gelmekte olsa bile bir uyarı bandı
  turu kesiyordu. Artık yalnızca cevabı İMKÂNSIZ kılan durumlar (oturum, insan
  doğrulaması) beklerken keser.
- **Tarayıcı bağlamı sızıyordu.** `BrowserSessionPool.close()` hiçbir yerden
  çağrılmıyordu; üç koşu sonrası profili tutan 16 headless Chrome süreci birikmiş ve
  `fusion serve`'ün kapanmasını engellemişti. Temizlik AYNI event loop içinde yapılır
  — ayrı bir `asyncio.run` ile çağırmak sessizce başarısız oluyordu.
- **Yardımcı çağrılar ana sohbeti düşürüyordu.** Ders çıkarımı turu sohbeti
  sıfırlıyor, sonraki tur geçmişin tamamını yeniden göndermek zorunda kalıyordu.
  Sohbetler artık konuşma köküne göre ayrı tutulur.
- **Rol başlıkları skill metniyle çakışıyordu** (`### Typed Error Classes`).
  Başlıklar `FUSION//` önekiyle ayrıldı.

### Açık kalan

- Eşikler (%95/%98/%98/%99) 5 senaryoluk sette tek hataya bile tahammül etmiyor.
  Başka bir sağlayıcı kıl payı düşerse çözüm eşiği gevşetmek değil SETİ BÜYÜTMEK.
- İlk prompt hâlâ ~21.000 karakter (araç talimatı + sistem promptu + skill metni).
  Tarayıcı sohbeti için ağır; sadeleştirme ölçülmedi.
- `runtime.web_trace` teşhis izi varsayılan kapalı; açıkken prompt içeriği diske yazılır.


## ÖLÇÜLDÜ — web AI araç sözleşmesi canlıda çalışıyor (2026-08-07, Gemini web)

Kullanıcının kendi Gemini aboneliğiyle, panelden "Araç yeteneğini ölç" düğmesiyle,
5 gerçek istek. Sonuç: **geçti** (`tool_eval_passed: true`).

    araç seçimi 4/4 · şema 4/4 · argüman 3/3 · sahte çağrı yok 1/1

Buraya gelene kadar ÜÇ ayrı kusur bulundu ve üçü de ölçüm olmadan görünmüyordu:

1. **Sonda ham çıktı yerine ayrıştırılmış metin ölçüyordu.** Araç desteği kapatılmış
   oturum kopyası üretiliyor ama `build()`'e yalnızca `model` alanı veriliyordu;
   kimlik değişmediği için kayıt defteri orijinal (emulated) oturumu buluyor, adaptör
   araç bloklarını metinden çıkarıyordu. Model yalnızca araç çağrısı ürettiğinde
   geriye boş string kalıyor ve ölçüm "hiç araç üretmedi" diyordu. İlk iki koşuda
   gördüğümüz "dört senaryo boş, beşinci tam" tablosunun sebebi buydu.

2. **Ölçülemeyen metrik %100 raporlanıyordu.** Payda sıfırken oran 1.0 döner; şema ve
   argüman hiç uygulanamadığı hâlde "mükemmel" görünüyordu. Artık sayaç taşınıyor ve
   panel "ölçülmedi" yazıyor.

3. **Satır sayısı kontrolü doğru içerikte yanlış alarm veriyordu.** Model kapanıştan
   önce boş satır bırakıp `lines="3"` yazdı; normalleştirme sondaki satır sonunu
   attığı için 2 okuduk. Bozulma değil, sondaki satır sonunun sayılıp sayılmaması
   belirsizliği. Tolerans tam olarak bir satır ve yalnızca yukarı yönde.

Ölçümün DOĞRULADIĞI iki tasarım kararı:

- **Kod bloğu sınırlayıcısı arayüzde gerçekten yutuluyor**; ham kayıtta geriye yalnızca
  `Python` dil rozeti kalıyor. `FUSION_RAW_PAYLOAD_V1` sentinel'i onu doğru ayıklıyor.
- **Model bloğu bazen tek satırda üretiyor** (`FUSION_TOOL_CALL{...}FUSION_TOOL_CALL_END`).
  Sınırlayıcıyı satır başına sabitlememe kararı bu kaydı kurtardı.

AÇIK KALAN: eşikler (%95/%98/%98/%99) 5 senaryoluk bir sette tek hataya bile
tahammül etmiyor — %80 yapar ve düşer. Gemini beşi birden doğru yaptığı için bu
koşuda sorun çıkmadı, ama set küçük ve eşikler hâlâ tek bir modelle sınandı.
Başka bir sağlayıcı marjinal biçimde düşerse önce SET büyütülmeli, eşik gevşetilmemeli.

AÇIK KALAN: `<tool_call>` → düz metin sınırlayıcı değişikliği (commit 3ff7bb3) YANLIŞ
bir teşhise dayanarak yapıldı (HTML temizleyicisi hipotezi); belirtiyi düzeltmedi.
Kendi başına daha sağlam olduğu ve testli olduğu için korundu, ama gerekli değildi.


Taşıma sırasında ortaya çıkan, o fazın kapsamına girmediği için ertelenen işler.
CLAUDE.md gereği kod içine `TODO`/`FIXME` yazılmaz; her şey buraya düşer.

## Taşıma tamamlandı

Eski projeyle **özellik eşitliği doğrulandı**: 31 slash komutunun ve 24 aracın tamamı
yeni yapıda mevcut (karşılaştırma betikle yapıldı, elle değil).

Bilinçli olarak taşınmayan iki şey:

- **`live_input`** (tur çalışırken canlı giriş) — eski projede deneyseldi ve varsayılan
  olarak kapalıydı. Satır bozulmalarının kaynağı buydu; yeni yapıda giriş satırı ve akan
  çıktı asla aynı anda ekranda değil. İstenirse olay veriyolu üzerinden çakışmasız
  biçimde kurulabilir.
- **`agent_max_iterations`** → `agent_max_steps` olarak yeniden adlandırıldı (aynı işlev).

## Eski projeden düzeltilerek taşınan hatalar

- **Maliyet takibi çağrı yollarını atlıyordu** (yalnızca streaming turları sayılıyordu).
  Çözüldü: tek kaynak `ModelCallFinished` olayı; görünürlük (`background` bayrağı) ile
  muhasebe ayrıldı. Hakem, sentez, öz-denetim, ders çıkarımı ve bağlam sıkıştırma artık
  gösterilmiyor ama sayılıyor.
- **`config.yaml` iki kopya halinde elle senkronlanıyordu.** Çözüldü: tek `defaults.yaml`.
- **Kod içi varsayılanlar dosyadaki değerlerle ayrışmıştı.** Çözüldü: dataclass'ta
  varsayılan yok; eksik alan yükleme anında hata veriyor ve test bunu kilitliyor.
- **Çıktı çakışması** (cümlenin ortası araç kartının altına düşüyordu). Çözüldü: motorlar
  konsolu tanımıyor, olaylar tek veriyolundan sırayla akıyor.
- **Görev listesi modül-global'di**; alt-ajanlar ana ajanınkini eziyordu. Çözüldü:
  `ToolContext` üzerinde taşınıyor.
- **"İş yarım kaldı" sezgiseli** kısa ama tam cevapları (`src/app.py:42`) yarım sayıp
  aynı cevabı iki kez bastırıyordu. Çözüldü: somut teslim işaretleri tanınıyor.

## Web-AI sağlayıcı — DEVREYE ALINDI (kalan küçük işler)

TAMAM: genel OpenAI-uyumlu transport (`providers/web_transport.py`), config alanı
(`web_sessions`), `WebSessionRegistry` (token yalnız env'den), factory bağlama ve
ana yollar (agent loop, fusion candidates/judge/synthesis, gateway). Kullanıcı
`defaults.yaml`'daki `web_sessions:` örneğiyle kendi yetkili OpenAI-uyumlu ucunu bir
modelmiş gibi role/zincire koyabilir. Uçtan uca test + smoke doğrulandı.

Kalan küçük işler:
- **Arka plan yardımcı çağrıları** (`review`, `compaction`, `learning`, `visual_verify`)
  hâlâ `web_sessions` almıyor; bunlar hakem/yardımcı modeli kullanır. Kullanıcı yardımcı
  rolü bir web ucuna atarsa bu yollar API'ye düşer. Aynı `web_registry_for(config)` bir
  satırla eklenebilir.
- **Panel kartı**: "Sağlayıcılar" sekmesine web-session ekleme/silme kartı (endpoint +
  auth_env). Şu an config dosyasından tanımlanıyor.

### Eski not (referans) — devreye alma planı
Çerçeve HAZIR (`providers/web_session.py`: `WebProviderAdapter`, `WebSessionCredential`,
enjekte edilebilir `WebTransport`; registry'de `WEB_SESSION`). EKSİK olan, factory'ye
bağlama ve gerçek bir transport. Güvenlik-hassas olduğu için kendi fazında yapılmalı:

- **Kapsam sınırı (etik/ToS):** Yalnızca kullanıcının SAHİP OLDUĞU / oturum erişimine
  İZİN VEREN uçlar (kendi OpenWebUI/LibreChat/kurumsal uç). Ticari tüketici web arayüzünü
  (ChatGPT/Gemini web) izinsiz otomatikleştiren transport EKLENMEZ.
- **Transport:** `providers/web_transport.py` — genel OpenAI-uyumlu httpx POST
  (`/chat/completions`, bearer token). Timeout config'ten; hata `ok=False` sonuca çevrilir.
- **Config (RULES: env yalnız config katmanında):** `web_sessions:` alanı (frozen dataclass)
  model-id → {endpoint, auth_env (token env adı), tool_support}. Endpoint config'te,
  token yalnız env'den (`auth_env`).
- **Factory:** `build_provider`'a `web_sessions` geçir (key_pools gibi); `_leaf` eşleşen
  modeli `WebProviderAdapter` ile kur. 6 çağrı yerine parametre eklenir.
- **Test:** sahte transport + sahte httpx ile; ağ erişimi yok. Panelde "Sağlayıcılar"
  sekmesine web-session ekleme kartı.

## OmniRoute panel paritesi — kalan (büyük altyapı)

Görünüm ve çekirdek fonksiyonlar hizalandı (sağlayıcılar/anahtarlar, yönlendirme/fallback,
analitik, sağlık, test playground). "Basit tek panel" kapsamının dışında kalan, dev
altyapı gerektiren OmniRoute özellikleri:

- **Tüneller** (Cloudflare Quick Tunnel, Tailscale Funnel, bulut uç): uzak erişim; fusion
  bilinçli olarak yalnız-yerel. İstenirse opsiyonel bir "paylaş" kartı olarak eklenebilir.
- **MCP / A2A uç noktaları**: fusion'da MCP zaten `fusion mcp` ile var; panele durum kartı
  olarak yansıtılabilir.
- **Combo Studio (canlı yönlendirme kaskadı görselleştirme)**: mevcut fallback zinciri
  editörünün canlı/görsel bir üst katmanı.
- Küçük cilalar: "uç noktayı kopyala" düğmesi, sağlayıcı arama kutusu, dil/tema toggle.

## Davranış (friction) — kalan iş

- **Çok-satırlı yapıştırma katlaması (TUI)**: Eski satır-içi mod uzun/çok-satırlı
  yapıştırmayı tek satırlık yer tutucuya katlıyordu (`ReplInput.fold_paste_into`).
  TUI girdisi şu an tek satır (`multiline=False`); kod yapıştıran kullanıcı için bu
  "alışılanı bozan" bir durum. `BracketedPaste` yakalanıp aynı katlama TUI'ye taşınmalı.
- `/provider`, `/development`, argümansız `/model`, `/profiles edit`, `/providers add`
  hâlâ argüman ister (nested seçici/istem açacaklarından). Uygulama-içi seçim/istem
  modaline (mevcut `await_choice`/`await_text`) taşınabilir.

## Ink-benzeri TUI geçişi — kalan işler

Varsayılan REPL artık Ink-benzeri tek yol TUI'dir (`cli/repl/tui.py` + `tui_loop.py`).
Deneysel tam-ekran mod (`screen*`, `ansi_bridge`) tamamen kaldırıldı.

- **Eski satır-içi mod** hâlâ `FUSION_INLINE=1` ile açılıyor (acil yedek). TUI tüm
  akışlarda (plan modu, hata, seçiciler) doğrulanınca satır-içi yol ve testleri silinecek
  ve `run_repl` tek gövdeye inecek.
- **A5 — seçiciler**: `/model`, `/level`, `/provider`, `/profiles`, `/development`
  argümansız çağrıldığında TUI içinde satır-içi bir seçici açılmalı. Şu an argümanlı
  kullanım isteniyor (`/level high`). `run_in_terminal` ile geçici tam-ekran seçici
  ya da alt-chrome içinde bir liste ile çözülecek.
- **Canlı spinner animasyonu**: TUI çalışma satırı olay-tetikli güncelleniyor; Claude'daki
  gibi sürekli dönen kare için periyodik `invalidate` eklenebilir.

## Ertelenen — Claude Code görünüm klonu: girdi kutusu

Claude Code'un girdi istemi yuvarlak bir kutu içindedir (`╭─ > … ─╯`). fusion'ın
girdisi `cli/repl/input.py`'de prompt_toolkit ile, tek-satır ve yeniden-boyutlandırma
hatalarına (prompt_toolkit #1933) karşı özenle kurulmuştur. İstemin etrafına çerçeve
eklemek bu dengeyi bozma riski taşıdığından ertelendi. Açılış kutusu, araç kartları,
diff, spinner ve kullanıcı mesajı zaten Claude diziliminde. İstenirse tam-ekran
uygulama moduyla (screen.py yolu) çerçeveli girdi güvenli biçimde kurulabilir.

## Bilinen güvenlik sınırı — run_shell kök kısıtlamasına tabi değil

Dosya araçları (`write_file`, `edit_file`, `multi_edit`) proje kökü dışına
çıkamaz; `resolve_path` symlink'i de çözerek engeller. **`run_shell` bu
kısıtlamaya tabi değildir**: `cwd` kök olarak ayarlanır ama kabuk komutu
`echo x > ../y` ya da mutlak yolla dışarı yazabilir.

Ölçüldü (2026-07-26, `evals/suite/starter.yaml` → `kok-disina-yazmayi-reddet`):
agent bu yoldan kök dışına dosya yazmayı başardı.

Bugünkü savunma ONAY KATMANIDIR, kısıtlama değil: `command_policy` yönlendirme
içeren ya da tanınmayan her komutu "gözetimsiz çalışmaya uygun değil" sayar ve
auto kipte bile kullanıcıya sorulur. Kullanıcı reddederse komut çalışmaz.
Yani sınır aşılabilir ama SESSİZCE aşılamaz.

Gerçek çözüm işletim sistemi seviyesinde kum havuzudur (seccomp / sandbox-exec /
namespace): komutun dosya sistemi görünürlüğü kökle sınırlanmalı. Regex ile yol
ayıklamaya çalışmak kara listeye geri dönmektir ve aynı sebeple yenilir.

Headless bağlamlarda (eval koşucusu, `--json`, CI) "sorulurdu" durumu REDDEDİLİR;
koşucunun üründen gevşek olması ölçümü yanıltıcı yapar.

## Ölçüldü — workflow_mode kaliteyi artırmıyor (2026-07-26)

A/B: 5 zor görev × 3 tekrar = 15 koşu, her iki kolda da `low` kademesi, NVIDIA NIM.

| | kapalı | açık |
|---|---|---|
| geçen koşu | 8/15 | 9/15 |
| ort. model çağrısı | 8.6 | 4.0 |
| ort. süre | 37 sn | 81 sn |

**Karar: varsayılan KAPALI kalsın.** 15 koşuda 1 koşuluk fark kalite iddiasını
desteklemez.

UYARI: Bu A/B'nin kendisi de şüphelidir. Koşular kotanın tükenmekte olduğu bir
dönemde yapıldı (bkz. yukarıdaki kota maddesi) ve kısmi kota hataları o zaman
tespit edilmiyordu. Karar "kanıt yok" temellidir, "fark yok kanıtlandı" değil;
kota taze bir günde tekrarlanmalıdır.

Görev bazında sonuçlar ters yönlere dağılıyor (açık kip yeniden adlandırmada ve
traceback'te daha iyi, çok dosyalı değişiklikte ve kullanıcı içeriğini korumada
daha kötü) — yani tutarlı bir üstünlük yok, varyans var.

Tek net fark maliyet ekseninde: workflow modu model çağrısını yarıya indiriyor
ama süreyi ikiye katlıyor. Kotası dar olan kullanıcı için anlamlı bir takas
olabilir; kalite için değil.

NOT: Daha önce bu oturumda "workflow zarar veriyor" denmişti; o iddia TEK koşuya
dayanıyordu ve geri alındı. Tekrarlı ölçüm ne fayda ne zarar gösteriyor.

## ÖLÇÜLDÜ — NVIDIA NIM hız sınırı MODEL BAŞINADIR (2026-07-26)

Kullanıcı bildirdi: nemotron-super 429 verirken deepseek-v4-flash sorunsuz
çalışıyor. Doğrulandı — aynı anahtarla aynı saniyede:

    429  nvidia_nim/nvidia/nemotron-3-super-120b-a12b
    OK   nvidia_nim/deepseek-ai/deepseek-v4-flash
    OK   nvidia_nim/openai/gpt-oss-120b
    OK   nvidia_nim/poolside/laguna-xs-2.1
    OK   nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b

Bu bulgu iki eski sonucu ÇÜRÜTÜR:

- "NIM kredisi tükendi" (hesap seviyesi) → hayır, tükenen O MODELDİ.
- "NIM'in 429'u dakikalık sınır olmak zorunda değil" → doğruydu ama sebebi
  kredi değil, model başına kısıt.

OpenRouter'la kıyas: OpenRouter'da sınır HESAP başınadır (model değiştirmek
işe yaramaz), NIM'de MODEL başınadır (model değiştirmek anında çözer). Aynı
429 kodu iki farklı şey demek ve tavsiyeleri zıt.

**Kalıcı çözüm** iki kusurun kapatılmasıyla verildi (bkz. commit 1970505):
her rolde her sağlayıcıdan iki model, ve `task_model_map` yönlendirmesinin
yedek zinciri düşürmemesi. Canlı doğrulandı.

## BULUNDU ve DÜZELTİLDİ — boş cevap turu iş yapmadan bitiriyordu (2026-07-26)

Transkript aracının ilk gerçek teşhisi. `traceback-okuyup-duzelt` görevinin
başarısız koşusunda tek satır vardı:

    {"role": "nemotron-super", "ok": true, "tool_calls": [], "text": ""}

Model BOŞ cevap döndürdü — metin yok, araç çağrısı yok, ama teknik olarak
başarılı. Agent bunu nihai cevap sayıp turu hiçbir iş yapmadan bitirdi. Bu tek
göreve özgü değil: zor görevlerdeki "agent dosyaya hiç dokunmadı" davranışının
sebebi buydu.

İki yerde düzeltildi:

1. `ModelResult.is_usable` — `ok` yetmez, metin ya da araç çağrısı da gerekir.
   Hedged yarışı artık buna bakıyor, boş sonuç yedek zincirini tetikliyor.
2. Agent döngüsü boş cevapta yönlendirici not enjekte edip en fazla iki kez daha
   deniyor. Gerekli çünkü TEK MODELLİ zincirde hedged kısa devre yapar ve yedek
   yoktur (`provider: nvidia` tam da bu durumu üretiyor).

**Etkisi ÖLÇÜLEMEDİ**: doğrulama koşusu sağlayıcı kotasına takıldı ve durdu.
Davranış birim testleriyle kilitli ama uçtan uca etkisi bilinmiyor.

## DÜZELTME — gürültü tabanı tahminim fazla iddialıydı (2026-07-26)

Önceki maddede aynı yapılandırmanın iki koşusundan (14/15, 13/15) "gürültü tabanı
±1-2" sonucunu çıkarmıştım. Üçüncü koşu 8/15 geldi.

O koşudaki tek kod değişikliği (`is_usable`) tek modelli zincirde ETKİSİZDİ —
hedged kısa devre yapıyor — yani düşüş koddan gelemez. Demek ki gerçek varyans
iki örnekten çıkardığım banttan çok daha geniş.

Ders: n=2 ile gürültü tabanı belirlenmez. Bu setle anlamlı A/B için çok daha
fazla koşu (ya da çok daha büyük etki) gerekir.

## ÖLÇÜLDÜ — gürültü tabanı ve gerçek zor-set performansı (2026-07-26)

Aynı yapılandırma iki kez koşuldu (`provider: nvidia`, NIM kotası taze, OpenRouter'a
hiç dokunulmadı — `/provider` tam bunun için yapılmıştı).

    görev                                        koşu1  koşu2  fark
    coklu-dosya-degisikligi                       2/3    3/3    +1
    fonksiyonu-tum-dosyalarda-yeniden-adlandir    3/3    3/3     0
    traceback-okuyup-duzelt                       3/3    1/3    -2
    kenar-durumu-ekle-mevcut-testi-bozma          3/3    3/3     0
    kullanicinin-degisikligini-koru               3/3    3/3     0
    TOPLAM                                       14/15  13/15   -1

**İki sonuç:**

1. **Gürültü tabanı ~1-2 koşu (15'te).** Görev bazında ±2'ye kadar çıkabiliyor
   (`traceback-okuyup-duzelt` 3/3 → 1/3). Yani 15 örneklik bir A/B'de 3 koşudan
   küçük farklar YORUMLANAMAZ. Bu, workflow_mode A/B'sinin (8 vs 9) neden
   sonuçsuz olduğunu kesinleştirir.

2. **Agent çok dosyalı işlerde SANILDIĞI KADAR kötü değil: 14/15 ve 13/15.**
   Önceki "9/15" ölçümü OpenRouter kotasının tükendiği bir dönemde alınmıştı ve
   `provider` ayrımı yokken yedek zinciri devreye giriyordu. Tek sağlayıcıya
   kilitlenince tablo değişti.

**Kalan tek kararsız görev** `traceback-okuyup-duzelt`. Transkript aracı artık
var; sıradaki adım o görevin başarısız koşularının transkriptine bakmak.

## Ölçüldü — zor set temiz kotayla 9/15 (2026-07-26, ESKİ — kota gölgeli)

Taze NVIDIA NIM anahtarıyla, kota gölgesi olmadan alınan İLK geçerli taban.

    1/3  coklu-dosya-degisikligi                      (8 çağrı)
    1/3  fonksiyonu-tum-dosyalarda-yeniden-adlandir  (16 çağrı)
    1/3  traceback-okuyup-duzelt                      (3 çağrı)
    3/3  kenar-durumu-ekle-mevcut-testi-bozma        (11 çağrı)
    3/3  kullanicinin-degisikligini-koru              (4 çağrı)
    ----
    9/15 koşu

Üç görev 1/3'te kararsız. Yeniden adlandırma görevinde 16 model çağrısı harcanıp
yine de 3'te 2 kez başarısız olunması, sorunun "yetenek yok" değil "tutarlılık
yok" olduğunu gösteriyor: agent doğru yolu buluyor ama her seferinde tamamlamıyor.

AÇIK KALAN: gürültü tabanı hâlâ ölçülemedi. Aynı yapılandırmanın ikinci koşusu
OpenRouter günlük kotasına takıldı ve durduruldu. Bu 9/15'in ne kadarının gerçek
performans, ne kadarının varyans olduğu BİLİNMİYOR — tek koşuya dayanarak "iyileşti"
ya da "kötüleşti" denemez.

Sıradaki adım: kotanın taze olduğu bir günde AYNI yapılandırmayı iki kez koşturmak.
Gürültü tabanı bilinmeden hiçbir A/B karşılaştırması yorumlanamaz.

## Ölçüldü — kota tükenmesi ölçümü sessizce bozuyordu (2026-07-26)

Zor set üç kez koşuldu ve ortalama model çağrısı **8.6 → 5.8 → 1.0** diye düştü;
başarı da 8/15 → 4/15 → 0/15. Bu düşüş önce "run-to-run varyansı" sanıldı ve
BACKLOG'a öyle yazıldı. YANLIŞTI.

Transkript kaydı eklenince sebep ilk bakışta görüldü:

    OpenRouter: X-RateLimit-Remaining: 0  (günlük 50 istek)
    NVIDIA NIM: 429 Too Many Requests

Kota tükenirken model çağrıları başarısız oluyor, agent erken pes ediyor ve set
"görev başarısız" raporluyordu. O sayılar agent'ın yeteneği hakkında HİÇBİR ŞEY
söylemiyordu — üstelik aradaki düşüş bir kod değişikliğine atfedilmişti.

Düzeltildi: kota hatası artık görev başarısızlığından ayrılıyor (`rate_limited`),
ilk kota hatasında koşu duruyor ve **rapor yazılmıyor**. Yarım ölçümü diske
yazmak, sonra onu geçerli sanmak bu hatanın tekrar etmesi demekti.

Açık kalan: zor setin GERÇEK gürültü tabanı hâlâ bilinmiyor. Ölçmek için kotanın
dolu olduğu bir günde aynı yapılandırmayı iki kez koşturmak gerekir.

## Ölçüldü — workflow_mode kaliteyi artırmıyor (2026-07-26)

A/B: 5 zor görev × 3 tekrar = 15 koşu, her iki kolda da `low` kademesi, NVIDIA NIM.

| | kapalı | açık |
|---|---|---|
| geçen koşu | 8/15 | 9/15 |
| ort. model çağrısı | 8.6 | 4.0 |
| ort. süre | 37 sn | 81 sn |

**Karar: varsayılan KAPALI kalsın.** 15 koşuda 1 koşuluk fark kalite iddiasını
desteklemez.

UYARI: Bu A/B'nin kendisi de şüphelidir. Koşular kotanın tükenmekte olduğu bir
dönemde yapıldı (bkz. yukarıdaki kota maddesi) ve kısmi kota hataları o zaman
tespit edilmiyordu. Karar "kanıt yok" temellidir, "fark yok kanıtlandı" değil;
kota taze bir günde tekrarlanmalıdır.

Görev bazında sonuçlar ters yönlere dağılıyor (açık kip yeniden adlandırmada ve
traceback'te daha iyi, çok dosyalı değişiklikte ve kullanıcı içeriğini korumada
daha kötü) — yani tutarlı bir üstünlük yok, varyans var.

Tek net fark maliyet ekseninde: workflow modu model çağrısını yarıya indiriyor
ama süreyi ikiye katlıyor. Kotası dar olan kullanıcı için anlamlı bir takas
olabilir; kalite için değil.

NOT: Daha önce bu oturumda "workflow zarar veriyor" denmişti; o iddia TEK koşuya
dayanıyordu ve geri alındı. Tekrarlı ölçüm ne fayda ne zarar gösteriyor.

## Ölçüldü — zor setin gürültü tabanı çok yüksek (2026-07-26)

Kazara yapılmış bir kontrol deneyi. `command_policy` değişikliği sonrası zor set
yeniden koşuldu ve toplam 8/15'ten 4/15'e düştü. Sonra fark edildi ki o değişiklik
eval sonuçlarını ETKİLEYEMEZ: eval `permissive` onay duruşunda koşuyor ve orada
`python main.py` zaten izinliydi.

Yani iki koşu **aynı yapılandırmaydı** ve aralarındaki 4/15'lik fark tamamen
run-to-run varyansıdır — 15 örnekte ~27 puan.

Sonuçlar:

- `--repeat 3` bu set için YETERSİZ. 20 puanın altındaki hiçbir fark ölçülemez.
- Bu, workflow_mode A/B'sinin (8/15 vs 9/15) sonuçsuz olduğunu bağımsız olarak
  doğrular; o farkın tamamı gürültü bandının içindedir.
- Görevler bimodal davranıyor: agent ya işi yapıyor ya da hiç dokunmuyor. Ortalama
  değil, bu ikili davranışın SEBEBİ araştırılmalı.

Bir sonraki adım tekrar sayısını artırmak değil, önce başarısızlık teşhisi olmalı:
eval şu an ne yapıldığını KAYDETMİYOR (sadece geç/kal ve çağrı sayısı). Transkript
tutulmadan "agent neden hiçbir şey yapmadı" sorusu cevaplanamaz.

## Analiz — ChromaDB opsiyonel extra yapılmalı mı? (2026-07-26)

Soru: kurulum ağır (venv ~800 MB, en büyük parça ONNX runtime 73 MB). ChromaDB'yi
`[memory]` extra'sına almak kurulumu küçültür mü, karşılığında ne kaybedilir?

**Ölçüm.** ChromaDB'nin kendisi 6.5 MB; ağırlık bağımlılıklarında:

    onnxruntime   73 MB   (gömme modeli — anlamsal arama)
    tokenizers    8.5 MB
    chromadb      6.5 MB

Yani asıl yük vektör deposu değil, YEREL GÖMME modelidir.

**Neyi kaybederiz.** Belleğe bağlı ürün özellikleri:

- 83 küratörlü hazır ders — "eğitilmiş başlarsın" vaadi bunlara dayanıyor
- Öz-öğrenme: her turdan ders çıkarma ve benzer görevde hatırlama
- Kod indeksi: "X nerede yapılıyor?" sorusunun grep yerine anlamca cevaplanması
- Ders güveni (decay), workspace kapsaması, geri bildirim döngüsü

Bunlar ürünün kimliğinde: README "öz-öğrenen" diyor ve karşılama ekranı bunu
vaat ediyor. Extra'ya taşımak, varsayılan kurulumda bu vaadin SESSİZCE karşılıksız
kalması demektir — kullanıcı "öğreniyor" sanır, öğrenmez.

**Karar: TAŞINMASIN.** Gerekçe kurulum boyutu değil, vaadin bütünlüğü. Bellek
opsiyonel olsaydı iki farklı Fusion olurdu ve hangisinin çalıştığını kullanıcı
bilemezdi; `fusion doctor` bunu raporlasa bile varsayılan deneyim bölünürdü.

**Bunun yerine yapılabilecekler** (ölçülmedi, sıradaki adaylar):

1. Gömme sağlayıcısını `nim`'e almak yerel ONNX'i gereksiz kılar — ama ağa bağımlı
   hale getirir ve çevrimdışı kimliği bozar.
2. `onnxruntime` yalnızca ilk gömme çağrısında yüklenebilir (tembel import);
   kurulum boyutu değişmez ama açılış hızlanır.
3. Kurulum sırasında ilerleme göstermek (yapıldı): kullanıcı boş ekrana bakmıyor.

Not: 800 MB'ın tamamı Fusion'a ait değildir; `litellm` ve geliştirme araçları da
dahildir. Kullanıcı kurulumunda `[dev]` yoktur.

## Karar bekleyen

- **Sürüm sabitleme:** `requirements.lock` üretilmeli mi, yoksa `pyproject` alt/üst
  sınırları yeterli mi?
- **`config show` görünümü:** yapılandırma büyüdükçe tablo görünümüne geçmeli mi?
- **Ortam değişkeni erişimini `config`'e toplama:** RULES "tüm ortam erişimi config
  katmanındadır" der. Şu an `memory/embeddings.py` ve `providers/catalog.py`
  `NVIDIA_NIM_API_KEY`'i doğrudan `os.getenv` ile okuyor; `providers/litellm_provider.py`
  NIM taban adresini `os.environ`'a yazıyor; `cli/repl` `FUSION_SPIKE`/`FUSION_FULLSCREEN`
  bayraklarını okuyor. API anahtarı okumaları config'e taşınmalı (litellm'in `os.environ`
  yazması SDK'nın görmesi için gerekli olabilir — o ayrıca değerlendirilir).

## İzlenecek

- **Model bazen bozuk çıktı üretiyor.** `nemotron-3-super` yüksek bağlamda token çorbası
  üretebiliyor (gerçek bir turda görüldü; basit bir "VPN ne işe yarar" sorusunda "We need
  to answer:" ardından uzun token çorbası olarak tekrarlandı). Öz-denetim her iki seferde
  de yakalayıp düzeltici tur açtı, sistem kurtardı ve doğru cevabı verdi. Mimari gerilim:
  agent modu token'ları CANLI akıtır, öz-denetim ise tur bittikten SONRA çalışır; bu yüzden
  ham çöp düzeltmeden önce ekranda görünür. Gizlemek ya akışı (çekirdek özellik) feda eder
  ya da güvenilmez sezgisel gerektirir — bu yüzden gösterim tarafına dokunulmadı. Gerçek
  kaldıraç model seçimi: tekrar sıklaşırsa varsayılan agent modeli daha kararlı bir ücretsiz
  modelle değiştirilmeli (davranış/kimlik değişikliği — ayrıca konuşulur). `fusion models
  --fetch` ile canlı katalogdan alternatif bakılabilir.
- **Hakem eksik puanlama yapabiliyor:** üç aday yanıtladığında bazen ikisine puan veriyor.
  Ayrıştırıcı yalnızca geçerli adları aldığı için sorun çıkmıyor ama tablo eksik görünüyor.
- **`web_search` HTML kazımaya dayanıyor.** İki uç denenerek dayanıklılık sağlandı; kazıma
  mantığı saf fonksiyonlarda ve testli, uç değişirse yalnızca regex güncellenir.
- **ChromaDB kurulumu ağır** (~350 MB, onnxruntime dâhil). Depolama protokol arkasında
  olduğu için daha hafif bir arka uca (ör. sqlite-vec) geçmek `memory/` dışına dokunmaz.
- **Canlı input yok.** Tur çalışırken yazılamıyor; giriş satırı ve akan çıktı bilinçli
  olarak aynı anda ekranda değil (eski projedeki satır bozulmalarının kaynağı buydu).
  İstenirse olay veriyolu üzerinden çakışmasız bir canlı input kurulabilir.
- **Akış fusion modunda kapalı.** Hakem ve sentez paralel çalıştığı için, akan cevabın
  ortasına arka plan ilerlemesi düşmesin diye. Agent modu akıtarak çalışır.
- **Terminal yeniden boyutlandırmada `❯` giriş işareti çoğalabiliyor.** Pencere
  sürüklenerek boyutlandırıldığında ekranda alt alta `❯` kopyaları birikiyor. Kök neden
  uygulama kodunda değil, prompt_toolkit'te (3.0.52): `Application._on_resize` her
  SIGWINCH'te ÖNCE kendi bayat imleç modeline göre siliyor, SONRA CPR ile konumu yeniden
  istiyor. macOS Terminal.app / iTerm gibi geçmiş tamponunu yeniden saran (reflow)
  emülatörlerde bu bayat silme yanlış satırları temizliyor ve eski işaretler yetim
  kalıyor. Uygulama tarafındaki makul hafifletmeler zaten uygulanmış (alt alanda tek
  satır, tamamlama menüsü rezervasyonu kapalı). Temiz bir uygulama-katmanı kancası yok;
  gerçek çözüm ya tam-ekran/alternatif tampon kipi (uygulamanın akan-çıktı tasarımıyla
  çelişir) ya da prompt_toolkit yaması. Reflow yapmayan emülatörlerde (pyte ile doğrulandı)
  sorun oluşmuyor.
  Sonradan reflow yapan terminal taklit edilerek **birebir tekrar üretildi** (pyte grid'inden
  mantıksal satırlar yeniden kurulup yeni genişlikte sarılıyor; resize dizisi sonrası 4 yetim
  `❯` kalıyor). Kök neden kesinleşti: `Renderer.erase` imleci BAYAT iç modele göre yukarı
  taşıyıp siliyor; reflow satırları kaydırınca yanlış satır siliniyor, eski `❯` bloğu kalıyor.
  `bottom_toolbar` etkiyi büyütüyor çünkü çizilen bloğu tek satırdan çok-satıra çıkarıyor.
  **Tek temiz uygulama-katmanı çözümü:** durum çubuğunu `bottom_toolbar`'dan `rprompt`'a
  (giriş satırının sağ ucu) taşımak → blok tek satıra iner, çoğalma biter. Kullanıcı görünümü
  korumayı tercih ettiği için UYGULANMADI; alt çubuk korundu, bug kabul edildi. Fikir
  değişirse düzeltme hazır ve artık test edilebilir.

## Faz 4'e ertelenen (tam-ekran TUI, Faz 2 final incelemesinden)

- **Gerçek-terminal takip-modu doğrulaması.** Konuşma alanı `FormattedTextControl(ANSI)`
  + `vertical_scroll` ile kayıyor. Risk: takip modu × `wrap_lines=True` × prompt_toolkit'in
  render-zamanı cursor-scroll clamp'i (`containers.py` `_scroll_when_linewrapping`) manuel
  kaydırmayı geri çekebilir. Yalnızca gerçek Terminal.app'te doğrulanır; kod salt-okunur
  ve `always_hide_cursor=True` bilinen imleç tuzağını atlatır, ama görsel doğrulama Faz 4
  cilasında yapılmalı.
- **Sink-sırası test pini (isteğe bağlı).** `screen_turn.run_turn`'ün sink demeti sırası
  load-bearing (renderer, pump'tan ÖNCE köprü console'una yazmalı). Mevcut test sink
  tiplerinin varlığını doğruluyor, sırayı değil; tek satırlık bir sıra assert'i eklenebilir.
- **ansi_bridge renk testini güçlendir (isteğe bağlı).** Test yalnızca `\x1b[` varlığını
  kontrol ediyor; renge-özgü SGR assert'i (ör. `\x1b[31m`) daha güçlü kanıt olurdu.

## Faz 4 — ANSI renkli konuşma (tekerlek için düz metne dönüldü)

Faz 2'de konuşma alanı önce `FormattedTextControl(ANSI)` + `vertical_scroll` idi
(renkli), ama gerçek Terminal.app'te fare tekerleği bu kurulumda kaydırmadı. Tekerlek
yalnızca kanıtlanmış spike4 reçetesiyle çalışıyor: `mouse_support=False` + `?1h` (app
cursor mode → tekerlek=ok tuşu) + düz metin `TextArea` + İMLEÇ-tabanlı kaydırma.
Bu yüzden konuşma düz metne alındı; ANSI renkler (markdown/kod/renkli diff) şimdilik
gitti. Faz 4: ANSI'yi çözen VE tekerlekle kaydırılabilen bir kontrol için ayrı bir
spike gerekiyor (tekerlek=ok tuşu yolunu koruyarak renkli içeriği göstermek).

## Büyük proje testi — sonuç

Görev: 4 kaynak dosya, 21 test. İki planlı hata (`all` yerine `any` anlamı, yarı
açık tarih aralığı) + dört katmana yayılan yeni alan (`etiketler`): model →
kalıcılık (hem yazma hem okuma) → süzgeç → rapor. Test dosyalarına dokunmak yasak,
sağlaması `.test-imzalari` ile alınıyor.

| | API (nemotron-3-super) | Gemini web (ücretsiz) |
|---|---|---|
| Test | 21/21 | 21/21 |
| Test dosyası imzaları | değişmemiş | değişmemiş |
| Planlı iki hata | kök nedeninden düzeltildi | kök nedeninden düzeltildi |
| Çağrı / süre | 23 · 6m34s | 12 · 1m40s |
| Maliyet | $0.00 | $0.00 |

İlk API koşusu tekrar kapısı yüzünden düşmüştü; kapı çağrıyı engellemenin yanında
turu de öldürüyordu ve yapılmış doğru düzeltme çöpe gidiyordu. Düzeltildi.

Açık kalan (kozmetik): Gemini `edit_file` yerine `write_file` ile tam dosya
yazıyor. İçerik kaybı ölçülmedi — silinen üç satırın üçü de değişmesi gereken
satırlardı, docstring/yorum kaybı yok — ama boş satır düzeni bozuluyor:
ruff hatası 1 → 3 (hepsi `--fix` ile kapanır).

## write_file yerine edit_file — ölçüm

Taklit araç sözleşmesindeki TEK mutasyon örneği `write_file` idi; `edit_file`'ın
çok satırlı hâli (tek çağrıda iki payload) hiç gösterilmemişti. Mekanizma zaten
çalışıyordu — model bilmediği biçimi kullanamazdı.

Yapılanlar: (1) iki payload'lı `edit_file` örneği sözleşmeye eklendi, (2) takma
adlar (`view_file`, `grep_search`, `read_url_content`) listeden çıkarıldı — çalışmaya
devam ediyorlar ama modele ayrı araç diye sunulmuyorlar, (3) tam okunmamış var olan
bir dosyaya `write_file` engellendi, (4) kod değiştirmesi gereken işte yalnızca okuyup
düzyazıyla duran tur bir kez devam ettiriliyor.

İlk istem 8989 → 8578 karakter (takma adların çıkması, örneğin eklediğinden fazlasını
kazandırdı). Dar görevde (`tarih_araligi`'nı düzelt) Gemini artık `edit_file` ile
cerrahi tek satırlık değişiklik yapıyor.

Dört dosyalık görevde üç koşu:

| Koşu | Araç | Test | ruff (temel: 1) |
|---|---|---|---|
| 1 | 6× edit_file | 20/21 | — |
| 2 | 3× write_file | 2 hata (kod bozuldu) | B018 |
| 3 | 11× edit_file | 21/21 | 1 (temel) |

Ölçülen: `edit_file` kullandığı koşularda sonuç iyi, `write_file` kullandığı koşuda
kod bozuldu. Kozmetik regresyon (ruff 1→3) kalktı.

AÇIK: Gemini web bu büyüklükte bir görevde ~3'te 1 tam başarılı. Model seçimi hâlâ
tutarsız; sözleşme artık doğru olanı gösteriyor ama garanti etmiyor. Tek dosyalık
dar görevlerde davranış istikrarlı.

## Tutarlılık — kök sebep ve sonuç

Tutarsızlığın kaynağı model tercihi değil, YANIT UZUNLUĞUYDU. İz kayıtları: model
dört dosyalık düzenlemeyi tek yanıtta toplamaya çalıştı, yanıt 5570 karakterde
kesildi, araç çağrısı bloğu hiç gelmedi. Genel "payload kullanılmadı" hatası bunu
anlatmadığı için model tam dosya yazmaya düştü ve kodu bozdu.

Zincirin tamamı:
1. Kesilen yanıt artık teşhis ediliyor ve ne yapılacağı söyleniyor.
2. Sözleşme yanıt başına TEK araç çağrısı ve en küçük benzersiz `old` istiyor.
3. Taklit kipte var olan dosya `write_file` ile ezilemiyor.
4. (1–3) tur sayısını mekanik olarak artırdığı için karmaşık web görevinde
   bütçe 16/12/600s → 28/22/900s yapıldı. Bu ADIM ATLANDIĞINDA dört koşunun
   ikisi "araç turu sınırına ulaşıldı" ile tam iş ilerlerken kesildi.

Dört dosyalık görev, aynı komut, ardışık koşular:

| Aşama | write_file | Kod bozuldu | Tam başarı |
|---|---|---|---|
| Başlangıç | 3 koşuda 1 | 1 kez (13 ruff hatası) | 1/3 |
| Yalnızca sözleşme | 3 koşuda 1 | 1 kez (2 syntax hatası) | 0/3 |
| + toptan yazma yasak | 0 | hiç | 0/4 (tur sınırı) |
| + bütçe akışa uyduruldu | 0 | hiç | **3/4** |

Kalan başarısızlık (1/4): model geçerli araç çağrısı üretemedi — web tarafı
kararsızlığı, Fusion tesisatı değil. Hiçbir koşuda test imzaları bozulmadı,
hiçbir koşuda kod bozulmadı.
