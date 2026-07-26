# BACKLOG

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

## Ölçüldü — zor set temiz kotayla 9/15 (2026-07-26)

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
