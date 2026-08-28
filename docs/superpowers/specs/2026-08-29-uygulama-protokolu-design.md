# Uygulama Protokolü Tasarımı

**Tarih:** 2026-08-29

## Amaç

Fusion çekirdeğini terminal dışından sürülebilir hale getirmek. Masaüstü
uygulaması `fusion app` komutunu alt süreç olarak başlatır ve stdio üzerinden
satır satır JSON konuşur.

Bu belge yalnızca protokolü tanımlar. Uygulamanın kendisi, görsel dili ve
dağıtımı ayrı bir projedir.

## Ölçülen başlangıç durumu

Bu tasarım, "motor terminale bağlı" varsayımıyla başladı; ölçüm bunu çürüttü:

- `engines/` ve `core/` katmanlarında hiçbir Rich veya prompt_toolkit importu yok.
- Etkileşim noktaları zaten soyut: onay için `Prompter`, soru için `UserAsker`
  protokolleri mevcut (`engines/agent/approval.py`, `engines/agent/engine_tools.py`).
- Arayüzün çizdiği her şey `EventBus` üzerinden 31 olay tipi olarak akıyor.
- `cli/session.py::run_agent_task` iki dikişi zaten dışarıdan alıyor: `sinks`
  (olay dinleyicileri) ve `prompter_factory`.
- 31 olay sınıfının 30'u düz JSON'a çevrilebilir alanlardan oluşuyor; yalnız
  `FusionCompleted` zengin bir nesne (`FusionResult`) taşıyor.

Sonuç: bu iş bir refactor değil, mevcut dikişlere takılan bir serileştirme ve
taşıma katmanı. Motor katmanına tek satır dokunulmaz.

## Kapsam dışı

- **Uygulamanın kendisi**, görsel dili, paketleme ve imzalama.
- **CLI'ın protokole taşınması.** Terminal bugünkü doğrudan yolunda kalır; bu
  bilinçli bir karardır ve çalışan hiçbir şeye dokunmama amacını taşır.
- **Config yazma yarışının çözümü.** Aşağıda bilinen risk olarak kaydedildi.
- **Eşzamanlı çoklu oturum.** Bir süreç bir oturum yürütür.
- **Kimlik doğrulama.** stdio'da taraf yoktur: süreci başlatan uygulamadır.

## Taşıma

**stdio, satır sınırlı JSON (JSON Lines), UTF-8.**

Gerekçe: masaüstü uygulaması yerel bir çekirdeği paketliyor. Bu, LSP'nin ve
MCP'nin kullandığı desendir; deponun kendi `fusion mcp` komutu da stdio konuşur.

Alternatifler (WebSocket, yerel HTTP+SSE) reddedildi: ikisi de dinleyen bir soket
gerektirir ve kimlik doğrulama sorununu geri getirir. Bu somut bir risktir,
varsayım değil — `fusion serve` kimlik doğrulamasız yerel bir HTTP sunucusu
olduğu için CSRF açığı doğmuştu (bkz. `6ba410d`). Aynı sınıf açığı ikinci kez
üretmemek için soket açılmıyor.

Çerçeveleme satır sınırlıdır: her mesaj tek satırlık bir JSON nesnesidir ve
gövdesindeki satır sonları JSON kaçışıyla taşınır.

## Yerleşim

Yeni paket `src/fusion_cli/appserver/`, `gateway/` ve `mcp_bridge/` ile aynı
seviyede.

| Dosya | Sorumluluk |
|---|---|
| `serialize.py` | Olay nesnesi → sözlük |
| `protocol.py` | Mesaj şekilleri, kodlama ve çözme |
| `session.py` | Oturum ömrü, tur çalıştırma, iptal |
| `commands.py` | Komut köprüsü ve seçenek sağlama |
| `server.py` | stdio okuma/yazma döngüsü |

Yeni CLI alt komutu: `fusion app`. Adı uygulamayı başlatmaz, uygulamanın
konuşacağı protokolü açar; uygulama bu süreci kendisi doğurur.

## Mesaj tipleri

Dört tip vardır. `id` alanı yalnızca cevap bekleyen mesajlarda bulunur ve
eşleştirme için kullanılır.

**Uygulama → çekirdek**

- `istek` — bir işlem çağırır. `{"tip":"istek","id":…,"ad":…,"veri":{…}}`
- `cevap` — çekirdeğin sorduğu soruyu yanıtlar. `{"tip":"cevap","id":…,"veri":{…}}`

**Çekirdek → uygulama**

- `olay` — istenmeden akan durum bildirimi. Cevap beklemez.
- `sonuc` — bir `istek`in sonucu. İstekle aynı `id`yi taşır.
- `soru` — kullanıcı kararı ister (onay ya da `ask_user`). Uygulama aynı `id`
  ile `cevap` döndürmelidir.

## İstekler

| Ad | Ne yapar |
|---|---|
| `oturum.baslat` | Kök dizin, onay modu, motor ve ev dizinini kurar |
| `oturum.durum` | Etkin model, mod, motor, kök dizin |
| `tur.calistir` | Görevi çalıştırır; olaylar akar, `sonuc` ile biter |
| `tur.kes` | Çalışan turu iptal eder |
| `komut.listele` | Slash komut defterini döker (ad, açıklama, grup, kullanım) |
| `komut.calistir` | Komutu adı ve argümanıyla çalıştırır |
| `komut.secenekler` | Seçici açan komut için seçenek listesini döndürür |

## Olay serileştirme

Tek bir genel dönüştürücü kullanılır: olay sınıfının adı `olay` alanına yazılır,
alanları sözlüğe açılır. Bu, yeni bir olay tipi eklendiğinde ek iş gerektirmez.

`FusionCompleted` istisnadır ve elle yazılmış bir çevirici kullanır; taşıdığı
`FusionResult` düz alanlardan oluşmaz.

Bir değişmez test bunu korur: her olay sınıfı serileştirilebilmelidir. Yeni bir
olay düz olmayan bir alan taşırsa test kırmızıya döner ve çevirici yazılması
gerektiği anlaşılır — sessizce bozuk JSON üretilmez.

## Oturum ömrü

**Bir süreç bir oturum yürütür.** Uygulama ikinci bir sohbet istiyorsa ikinci bir
süreç başlatır.

Gerekçe: eşzamanlı oturumlar paylaşılan durum, kilit ve sahiplik sorunları
doğurur. Ayrı süreçler bunu baştan ortadan kaldırır ve bir oturumun çökmesi
diğerini etkilemez.

Uygulama stdin'i kapatırsa çekirdek düzgün kapanır: çalışan tur iptal edilir,
arka plan işleri beklenir, süreç sıfır koduyla biter.

## Onay ve soru gidiş-dönüşü

Bugün bunlar `await` ile bekleyen çağrılardır (`Prompter.confirm`,
`UserAsker.ask`). Protokolde her biri bir `soru` mesajına ve beklenen bir
`cevap`a dönüşür.

Onay sorusu, mevcut üç seçenekli modelin aynısını taşır: bir kez izin ver,
oturum boyunca izin ver, reddet. Yıkıcı işlemlerde oturum izni seçeneği
gönderilmez — kural motorda zaten uygulanıyor, protokol onu yalnızca taşır.

**Cevapsız kapanış:** uygulama cevap vermeden stdin'i kapatırsa çekirdek soruyu
reddedilmiş sayar ve turu güvenli biçimde bitirir. Süresiz beklemez.

## Komut köprüsü

50 komut tek tek taşınmaz. `komut.listele` mevcut kayıt defterini döker,
`komut.calistir` işleyiciyi çağırır. Komut işleyicileri zaten saf ve senkrondur
(`(state, argüman) -> str`), bu yüzden köprü incedir.

Bu bilinçli olarak tipsizdir: argüman metin olarak geçer. Karşılığında yeni bir
komut eklendiğinde uygulamada kendiliğinden belirir ve iki yüzey ayrışmaz.

**Seçici açan komutlar.** Beş komut terminalde bir seçici açar: `/model`
(argümansız), `/provider`, `/development`, `/profiles edit`, `/providers add`.
Protokolde seçici diye bir şey yoktur; `komut.secenekler` seçenek listesini
döndürür, uygulama kendi arayüzünde gösterir ve seçimi argüman olarak geri
gönderir. Bu desen depoda mevcuttur — TUI kendi modalını aynı biçimde besler
(`tui_loop.py` içindeki uygulama-içi seçim dalı).

## Sırlar

`/provider` ve `/providers add` API anahtarı ister. Anahtar stdio üzerinden
geçer: aynı süreç ağacı, ağ yok, diske yalnız şifreli depoya yazılır.

**Kural:** anahtar değerleri protokol günlüğüne, hata mesajına ya da olay
yüküne asla yazılmaz. Hata ayıklama günlüğü açıkken bile maskelenir.

## Bilinen risk: config yazma yarışı

`config/writer.py` oku-değiştir-yaz örüntüsü kullanır ve kilitleme yoktur. Panel
ile terminal aynı anda yazarsa biri diğerinin değişikliğini sessizce ezer; dosya
bozulmaz çünkü yazım atomiktir, ama bir değişiklik kaybolur.

Uygulama üçüncü bir yazar olarak eklendiğinde bu ihtimal artar. Bu tasarım
sorunu **çözmez** ve kapsamına almaz; ayrı ve dar bir iş olarak ele alınmalıdır.
Burada kaydedilmesinin sebebi, uygulama eklendikten sonra "neden ayarım kayboldu"
sorusunun cevabının bilinmesidir.

## Hata durumları

- Bozuk JSON satırı: satır atlanır, hata olayı yollanır, süreç yaşar.
- Bilinmeyen istek adı: `sonuc` mesajı hata ile döner.
- Tur içinde istisna: `sonuc` `ok:false` ve okunabilir sebeple döner; süreç çökmez.
- Eşleşmeyen `id` taşıyan cevap: yok sayılır ve hata olayı yollanır.
- stdout yazılamıyorsa: süreç sessizce kapanır; yazılamayan bir kanala olay
  biriktirmek bellek sızdırır.

Hiçbir durumda tek bir bozuk mesaj süreci düşürmez.

## Test

Protokol saftır: girdi satırları → çıktı satırları. Gerçek süreç başlatmadan,
sahte sağlayıcıyla uçtan uca sınanabilir.

- Her olay sınıfının serileştirilebildiği (değişmez test).
- Onay gidiş-dönüşünün doğru `id` ile eşleştiği.
- Cevapsız kapanışta turun sızmadığı ve sürecin düzgün kapandığı.
- Bozuk satırın süreci düşürmediği.
- `komut.listele` çıktısının kayıt defteriyle birebir örtüştüğü.
- `komut.secenekler`in seçici açan beş komut için de liste döndürdüğü.
- Sır değerlerinin hiçbir çıktı satırında görünmediği.

## Açık sorular

Yok. Uygulama planına geçilebilir.
