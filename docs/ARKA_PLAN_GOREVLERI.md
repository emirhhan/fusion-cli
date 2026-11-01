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
| Tam ekran REPL | Tur sürerken **Ctrl+B**: süren kabuk komutu ya da ön plan alt ajanı kesilmeden arka plana geçer, tur sürer (aşağıya bkz.) |
| Model | `Agent(prompt=…)` ana konuşmada varsayılan olarak arka planda başlar, kimliği (`agentId`) hemen döner; sonuç sonraki tura bildirimle gelir (`run_in_background: false` beklemeyi ister; etkileşimli oturumda fork kipi açıkken Claude Code'daki gibi yine arka planda kalır). Eski `spawn_agent(arka_plan=true)` ayrı süreçte koşar |
| Masaüstü | Ajanlar sekmesi › Arka plan görevleri › "Arka planda başlat" ya da sohbette `/bg` |

REPL ve masaüstünden başlayan görev konuşmanın son 12 kullanıcı/asistan mesajını devralır
(araç çıktısı ve harness notu taşınmaz). Kip başlatanın kipidir; REPL/masaüstü/araç yolunda
**bypass miras alınmaz** (auto'ya düşer). `fusion agent --bg --mode bypass` ise kullanıcının
açık seçimidir ve korunur. Alt ajanlar ve arka plan görevinin kendisi yeni arka plan görevi
açamaz.

**Ctrl+B:** süren `run_shell` komutu (Claude Code Bash gibi) durdurulmadan `.fusion/is`
iş kaydına devredilir; model iş kimliğini ve çıktı dosyasını alır, tur sürer. Beklenen ön
plan alt ajanı da aynı şekilde arka plana geçer. O anda devredilecek komut ya da alt ajan
yoksa (model yanıt yazıyorsa) tur kesilir ve görev işçide konuşma bağlamı ve düzenlenen
dosyaların listesiyle ("yeniden yapma, önce oku" notuyla) sürer.

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
- `@oturum-adı <metin>` ya da `/list-agents gonder <ad> <metin>`: mesaj gönder. `@ad`
  projede bir dosya/dizin adıysa dosya anması olarak kalır.
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

Ctrl+B `~/.fusion/keybindings.json` içinde `"tui": {"c-b": null}` ile kaldırılabilir ya da
başka tuşa (`"arka_plana_al"` eylemi) bağlanabilir. Satır-içi REPL'de tur sürerken tuş
okunmadığı için orada `/bg` kullanılır.

## Kabuk komutu ayarları (Claude Code Bash ile aynı)

- `run_shell(timeout=<ms>)`: çağrı başına zaman aşımı. Varsayılan `BASH_DEFAULT_TIMEOUT_MS`
  (120000), tavan `BASH_MAX_TIMEOUT_MS` (600000).
- Zaman aşımına uğrayan ön plan komutu durdurulmaz, **arka plana taşınır**: sonuç iş
  kimliğini ve `.fusion/is/<kimlik>.log` çıktı dosyasını verir. `sleep` ile başlayan komutlar ve `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`
  iken komut eskisi gibi durdurulur.
- `run_shell(run_in_background=true)`: komut arka plan işi olur (eski ad `background` de okunur).
  `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` iken arka plan isteği yok sayılır, komut ön planda çalışır.
- Claude Code gibi arka plan işi bitince (ya da durdurulunca) yoklama gerekmez: bildirim
  ("Arka plan işi <kimlik> bitti (çıkış kodu N) … Çıktı dosyası: …") sıradaki model isteğine
  girer; oturum boştaysa (terminal, TUI, masaüstü) yeni bir tur başlar. Çıktı `read_file` ile
  okunur, iş `task_stop(task_id)` ile durdurulur (Claude TaskStop; eski `shell_id` ve
  `job_status(id, stop=true)` kullanımdan kalkan takma ad, `job_status` şemada sunulmaz).
- `monitor(command, description, timeout_ms?)` (Claude Monitor): komutu arka planda çalıştırır,
  her stdout satırı bildirim olarak gelir; süre varsayılan 5 dk, en çok 1 sa kabul edilir, etkin
  tavan 30 dk; süre dolunca iş durdurulur ve bir kez haber verilir. Komut Bash izin kurallarından
  ve sandbox'tan geçer; `task_stop` ile erken biter. `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`
  iken çalışmaz. Claude'dan fark (henüz): WebSocket kaynağı (`ws`) yok.
- `/tasks` (`/bashes`) kabuk arka plan işlerini de listeler (`kabuk <kimlik> · sürüyor · komut`);
  `/tasks stop <kimlik>` işi durdurur (süreç başlangıç kimliği doğrulanır).
- Arka plan işinin ömrü: Fusion kapanırken o oturumun başlattığı işler durdurulur; çıktısı
  5 GB'ı geçen iş durdurulur ve nedeni günlüğe yazılır. Yalnız gözetimsiz koşuda
  (`fusion agent`) süre sınırı vardır: 10 dk (metin istem) ya da `timeout` (en çok 2 sa);
  `BASH_DEFAULT_TIMEOUT_MS` / `BASH_MAX_TIMEOUT_MS` sınırı yükseltir, kısaltmaz. Terminal ve
  masaüstü oturumunda süre sınırı yoktur.
- Çıktı (Claude Code Bash ile aynı): geçerli sonuç ~30.000 karaktere kadar satır içi; aşınca
  oturumun çıktı dizinindeki dosyanın yolu ve ilk 2.000 karakter. Hatalı sonuç ~10.000
  karaktere kadar; aşınca baş+son kesit (dosya yolu yok). Çıkış kodu 1 yalnız `grep`, `rg`,
  `egrep`, `fgrep`, `find`, `diff`, `test`, `[`, `git diff`, `git grep` için geçerli sayılır.
  `BASH_MAX_OUTPUT_LENGTH` geri okuma penceresi (tavan 150.000); Claude `settings.json`'daki
  `bashOutputMaxChars` (≤128.000) satır içi sınırı ve pencereyi birlikte ayarlar.

## Bilinen sınırlar

- Ajan tanımındaki `background: true` alanı, bekleme istense de ajanı arka planda tutar.
- Çalışan görevin olay günlüğü (`olaylar.jsonl`) görev sürerken budanmaz; görev kaydı
  saklama süresi dolunca günlükleriyle birlikte silinir.
- Masaüstü oturumu yalnız Ajanlar sekmesindeki panel açıkken (panel `arkaplan.durum`'u
  yokladıkça) nabız verir ve teslimat toplar; panel kapalıyken masaüstü oturumu eş
  listesinde görünmez ve araçla başlatılan görevin sonucu panel açılınca teslim edilir.
- Satır-içi REPL'de Ctrl+B yok (tur sürerken tuş okunmaz); orada `/bg` kullanılır.
- Kişilik (`--agent`) işçide `.claude/agents` / `~/.fusion` tanımlarından yeniden çözülür;
  `spawn_agent`'ın yerleşik ekip üyesi adı aynı adla bir tanım yoksa genel ajana düşer.
