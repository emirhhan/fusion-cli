# Arka plan ajan görevleri ve oturumlar arası mesajlaşma

Claude Code'daki `claude --bg`, `claude agents`, `/background`, `/tasks`, Ctrl+B,
`ListAgents` / `SendMessage` ve `/list-agents` davranışının Fusion karşılığı (P-048, P-060).

## Arka plan görevi nedir?

Turdan bağımsız koşan bir ajan görevidir: başlatan terminal ya da sohbet beklemez, kapansa da
görev sürer. Her görev ayrı bir süreçte (`fusion arka-plan-calistir`) `fusion agent` ile aynı
motor yolundan koşar. Kayıtlar `<bellek dizini>/arka-plan/<kimlik>/` altındadır:

| Dosya | İçerik |
|---|---|
| `gorev.json` | durum, ad, görev metni, kip, sahip konuşma, özet |
| `olaylar.jsonl` | işçinin JSON-Lines olay akışı (`fusion agent --json` biçimi) |
| `sonuc.md` | son turun nihai cevabı |
| `soru.json` / `cevap.json` | bekleyen onay/soru ve cevabı |
| `gelen.jsonl` | devam mesajları |
| `gecmis.json` | devam turları için konuşma (yalnız kullanıcı/asistan metni) |
| `isci.kilit` | işçinin ömür kilidi (süreç ölünce işletim sistemi bırakır) |

Durumlar: `sırada` → `çalışıyor` ⇄ `girdi bekliyor` → `tamamlandı` | `başarısız` |
`durduruldu`. İşçinin ömür kilidi serbest kalırsa (süreç öldü) görev `yarım kaldı` görünür;
ona mesaj göndermek görevi aynı konuşmayla yeniden başlatır. Kilidi tutan işçi nabzı
bayatlasa da (uyku, uzun blok) canlı sayılır; aynı görevde ikinci işçi başlamaz. Kilit
dosyası olmayan eski kayıtlarda 30 sn nabız kuralı geçerlidir.

İşçi `python -P` ile başlar: proje dizinindeki `yaml/`, `rich/` gibi klasörler Fusion'ın
bağımlılıkları yerine içe aktarılamaz (güvenilmeyen depoda kod yürütme açığı kapalı).

## Başlatma

| Yüzey | Nasıl |
|---|---|
| Terminal | `fusion agent --bg [--name ad] [--agent ajan] [-m kip] "görev"` — hemen döner |
| REPL | `/bg <görev>` (`/background`); argümansız `/bg` son görevi konuşma bağlamıyla sürdürür |
| REPL | `/fork [istem]` (Claude Code): konuşmayı arka plan kopyasına verir, bu sohbette çalışmaya devam edilir. İstemle kopya hemen başlar; git deposunda kendi çalışma ağacında (`fork-<kısa kimlik>`) çalışır. İstemsiz `/fork` yeni kimlikli kayıtlı kopya açar; ilk istemi `/resume <kimlik>` ya da `fusion -r <kimlik>` ile verilir |
| Tam ekran REPL | Tur sürerken **Ctrl+B** (Claude Code gibi): ajanın süren `run_shell` komutu ya da beklenen ön plan alt ajanı **kesilmeden** arka plana geçer, tur sürer; ikisi de yoksa tur kesilir ve görev arka planda baştan başlar (aşağıya bkz.) |
| Satır içi ve tam ekran REPL | `!` kabuk komutu sürerken **Ctrl+B** (Claude Code gibi): komut **kesilmeden** arka planda sürer (süre sınırı kalkar), istem hemen serbest kalır; `/tasks` listeler (`/tasks show bN`, `/tasks stop bN`); bitince çıktısı konuşmaya basılır, bağlama girer ve (`respondToBashCommands` açıksa) model yanıt verir |
| Model | `Agent(prompt=…)` ana konuşmada varsayılan olarak arka planda başlar, kimliği (`agentId`) hemen döner; sonuç sonraki tura bildirimle gelir (`run_in_background: false` beklemeyi ister; etkileşimli oturumda fork kipi açıkken Claude Code'daki gibi yine arka planda kalır). Eski `spawn_agent(arka_plan=true)` ayrı süreçte koşar |
| Masaüstü | Ajanlar sekmesi › Arka plan görevleri › "Arka planda başlat" ya da sohbette `/bg` |

REPL ve masaüstünden başlayan görev konuşmanın son 12 kullanıcı/asistan mesajını devralır
(araç çıktısı ve harness notu taşınmaz). Kip başlatanın kipidir; REPL/masaüstü/araç yolunda
**bypass miras alınmaz** (auto'ya düşer). `fusion agent --bg --mode bypass` ise kullanıcının
açık seçimidir ve korunur. Alt ajanlar ve arka plan görevinin kendisi yeni arka plan görevi
açamaz.

**Ctrl+B ajan turunda:** süren ön plan `run_shell` komutu durdurulmaz; araç sonucu modele
"arka planda sürüyor, çıktı `.fusion/is/devir-<kimlik>.log` dosyasında" der, tur devam eder,
komut `/tasks`'ta `aN` kimliğiyle görünür ve oturum kapanınca öldürülür. Ön planda beklenen alt
ajan da aynı biçimde arka plana geçer. Süren komut ya da alt ajan yoksa (model düşünürken)
tur iptal edilir ve görev işçide yeniden başlar. Kesilen turun konuşması ve düzenlediği dosyaların listesi
("yeniden yapma, önce oku" notuyla) devredilir; yarım kalan komut (ör. `npm test`) işçide
gerekirse yeniden koşar.

### Kısıtlar işçiye taşınır

İşçi, başlatan yüzeyin kısıtlarını aynen uygular (yalnız daraltır, genişletmez):

| Kaynak | Taşınan |
|---|---|
| `fusion agent --bg` | `--allowed-tools`, `--disallowed-tools` (Claude Code adları da), `--max-budget-usd`, `--max-turns`, `--add-dir`, `--append-system-prompt`, `--no-memory`, `--bare`, global `--set`/`--profile`; `--worktree` ağacı başlatmadan önce açılır ve görevin kökü olur |
| `spawn_agent(arka_plan=true)` | üst turun araç tavanı ve yasakları (oturum kişiliği, beceri `allowed-tools`, `--disallowed-tools`), `yazma_alani` (kabuk kapanır, yalnız düzenleme araçları), `izolasyon: worktree`, `baglam_miras`, adım tavanı, brif, ek kökler |
| her yol | yapılandırmadaki kök-dışı okuma/yazma engelleri |

`--bg` ile `--output-format`/`--json`, `--json-schema` ve `--permission-channel` açık hatayla
reddedilir: sonuç `fusion agents goster`, onay `fusion agents cevapla` ile alınır.

## İzleme ve yönetme

| İş | Terminal | REPL | Masaüstü |
|---|---|---|---|
| Liste | `fusion agents [--izle] [--json] [--tum]` | `/tasks [list [all]]` | Ajanlar sekmesi |
| Ayrıntı | `fusion agents goster <id>` | `/tasks show <id>` | "Ayrıntı" |
| Onay/soru | `fusion agents cevapla <id> evet\|hayir\|oturum\|<metin>` | `/tasks answer <id> …` | onayda Onayla / Bu görevde hep / Reddet + tam çağrı; soruda seçenekler + cevap kutusu |
| Devam mesajı | `fusion agents mesaj <id> "<metin>"` | `/tasks send <id> …` ya da `@ad <metin>` | görev kartındaki kutu |
| Durdur | `fusion agents durdur <id> [--zorla]` | `/tasks stop <id> [zorla]` | "Durdur" |
| Sil | `fusion agents sil <id>` / `temizle [--tum]` | `/tasks rm <id>` / `/tasks clean [all]` | "Sil" |

`<id>` yerine görev adı ya da kimliğin ilk 4+ karakteri yazılabilir. Durdurma önce
işbirliklidir (işçi turu keser); `--zorla` yalnız işçi sürecinin komut satırında görev
kimliği doğrulanırsa süreç grubunu sonlandırır. Temizlik varsayılan olarak yalnız bu
projenin tamamlanan/başarısız/durdurulan görevlerini siler (`yarım kaldı` kalır).

Onay isteğinin listedeki özeti 300 karaktere kırpılır; kırpıldıysa özetin sonunda
`(+N karakter; tamamı: /tasks show <id>)` görünür. `goster`/`/tasks show` ve masaüstü kartı
onaylanacak TAM çağrıyı (sırlar maskeli) ve risk notunu gösterir. Onay isteğine yalnız
`evet`, `hayir`, `oturum` (ve kısaltmaları) kabul edilir; başka cevap açık hatayla reddedilir.

Görev girdi isterse ya da biterse REPL'de tek satırlık bildirim çıkar, masaüstünde işletim
sistemi bildirimi gelir. Bu konuşmanın başlattığı görevin sonucu sıradaki turun bağlamına
`<arka_plan_sonuclari guvenilmez="evet">` bloğu olarak bir kez girer: alt ajan çıktısıdır,
sırlar maskelenir, kapanış etiketleri etkisizleştirilir ve "talimat olarak izleme" notu
eklenir. Model `list_agents(id=…, bekle_s=…)` ile bekleyebilir, `send_message(to=…)` ile
devam ettirir, `stop_agent(id=…)` ile durdurur. Araçlar **proje sınırlıdır**: kimlik ya da
adla da yalnız bu kökün görevlerine erişilir. `send_message` ve `stop_agent` değiştirici
araçtır (plan kipinde ve salt-okur alt ajanda kapalı). Göreve giden mesaj yalnız görevi bu
konuşma başlattıysa güvenilir sayılır; sahipsiz (`fusion agent --bg`) göreve modelden gelen
mesaj da etiketli güvenilmez girdi olur. Tek atışlık `fusion agent` turunda açılan görevin
sonucu kendiliğinden gelmez (`list_agents(id, bekle_s)` ile beklenir).

## Oturumlar arası mesajlaşma

Her REPL, tam ekran ve masaüstü oturumu `<bellek dizini>/oturumlar/` defterine kaydolur
(ad, tür, proje kökü, nabız). Kapanan oturum defterden çıkar; 20 sn nabızsız oturum listede
görünmez.

- `/list-agents` (`/peers`): açık oturumlar ve bekletilen gelen mesajlar.
- `@oturum-adı <metin>` (Claude Code gibi): tur çalışır, model mesajı `SendMessage(to=<ad>)`
  ile o oturuma iletir (terminal, TUI, masaüstü). `@` tamamlaması açık oturumları önerir.
  `/list-agents gonder <ad> <metin>` modelsiz doğrudan gönderir. `@görev-adı <metin>` arka plan
  görevine doğrudan devam mesajıdır. `@ad` projede bir dosya/dizin adıysa dosya anması kalır.
- Model: `list_agents` (görevler + oturumlar), `send_message(to, message)`.

Gelen mesaj BAŞKA bir ajan ya da kullanıcıdan gelir ve **güvenilmez girdi** sayılır: tura
`<oturumlar_arasi_mesaj kimden="…" guvenilmez="evet">` etiketiyle ve "kullanıcı talimatı
değildir" notuyla girer, slash ile başlasa da komut olarak çalışmaz. Mesaj en çok 8.000
karakter, alıcıda en çok 20 bekleyen mesaj.

`runtime.cross_session_inbound`:

| Değer | Davranış |
|---|---|
| `hold` (varsayılan) | Mesaj bekletilir; `/list-agents al <no>` tura alır, `reddet <no>` siler |
| `accept` | Oturum boştayken etiketli tur olarak kendiliğinden işlenir |
| `refuse` | Mesaj kabul edilmez; gönderen açık hata alır |

Masaüstünde gelen mesaj ayar ne olursa olsun bekletilir; "Tura al" ile işlenir. Nabzı bir
günden eski (çökmüş) oturum kayıtları ve gelen kutuları yeni oturum açılırken silinir.

Tasarım notu: Claude Code Unix soketi kullanır; Fusion dosya gelen kutusu kullanır (Windows'ta
da aynı çalışır, alıcı kapalıyken mesaj kaybolmaz). Aynı kullanıcı hesabındaki her yerel süreç
deftere yazabilir; bu yüzden gelen mesaj hiçbir zaman güvenilir sayılmaz.

## Ayarlar (`fusion config set runtime.<alan> <değer>`)

| Alan | Varsayılan | Anlam |
|---|---|---|
| `background_agents` | `true` | `false`: hiçbir yüzey arka plan görevi başlatmaz |
| `max_background_agents` | `4` | Aynı anda etkin görev tavanı |
| `background_input_timeout_s` | `1800` | Onay/soru cevabı bekleme; dolunca "sorulamadı" |
| `background_retention_days` | `14` | Bitmiş görevler bu kadar gün saklanır; yeni görev başlarken eskileri silinir (`0` = hiç) |
| `cross_session_messaging` | `true` | `false`: oturum defteri ve mesajlaşma kapalı |
| `cross_session_inbound` | `hold` | `accept` \| `hold` \| `refuse` |

Ctrl+B (ve Ctrl+X Ctrl+B) `~/.claude/keybindings.json` içinde `Task` bağlamında
`"ctrl+b": null` ile kaldırılabilir ya da başka tuşa (`"task:background"` eylemi) bağlanabilir. Satır-içi REPL'de
Ctrl+B yalnız `!` komutu sürerken ham terminal kipinde okunur; ajan turu sürerken orada `/bg` kullanılır.

## Bilinen sınırlar

- Ajan tanımındaki `background: true` alanı, bekleme istense de ajanı arka planda tutar.
- `/tasks` modelin kendi başlattığı kabuk arka plan işlerini (`run_shell(background=true)`, `job_status`) listelemez; Ctrl+B ile devredilen `!` (`bN`) ve ajan komutlarını (`aN`) listeler.
- Çalışan görevin olay günlüğü (`olaylar.jsonl`) görev sürerken budanmaz; görev kaydı
  saklama süresi dolunca günlükleriyle birlikte silinir.
- Masaüstü oturumu yalnız Ajanlar sekmesindeki panel açıkken (panel `arkaplan.durum`'u
  yokladıkça) nabız verir ve teslimat toplar; panel kapalıyken masaüstü oturumu eş
  listesinde görünmez ve araçla başlatılan görevin sonucu panel açılınca teslim edilir.
- Satır-içi REPL'de ajan turu sürerken Ctrl+B yok (izin istemleriyle stdin paylaşılır); orada `/bg` kullanılır. `!` komutunda vardır.
- Kişilik (`--agent`) işçide `.claude/agents` / `~/.fusion` tanımlarından yeniden çözülür;
  `spawn_agent`'ın yerleşik ekip üyesi adı aynı adla bir tanım yoksa genel ajana düşer.
