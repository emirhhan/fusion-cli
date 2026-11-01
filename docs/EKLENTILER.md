# Eklentiler, pazar yerleri ve içe aktarma

Fusion, Claude Code'un eklenti biçimini (`.claude-plugin/plugin.json`) ve pazar yeri biçimini
(`.claude-plugin/marketplace.json`) doğrudan okur. Bir eklenti beceri, komut, alt ajan, çıktı
stili, kanca ve MCP sunucusunu tek paket olarak getirir. Başka bir ajanın (Claude Code, Codex,
Gemini CLI, Cursor) yapılandırması `/import` ile taşınır.

## Eklenti klasörü

```
benim-eklentim/
  .claude-plugin/plugin.json   {"name": "benim-eklentim", "version": "1.0.0", "description": "…"}
  skills/<ad>/SKILL.md         → /benim-eklentim:<ad>
  commands/<ad>.md             → /benim-eklentim:<ad>
  agents/<ad>.md               → benim-eklentim:<ad> (alt ajan)
  output-styles/<ad>.md        → /output-style benim-eklentim:<ad>
  hooks/hooks.json             kancalar (Fusion dışında komut çalıştırır)
  .mcp.json                    MCP sunucuları (süreç başlatır)
```

- Yol kuralları Claude Code ile aynıdır: her bileşen yolu `./` ile başlar (`skills` ayrıca `.`/`./`
  ile eklenti kökünü alır) ve kök dışına çıkamaz. `commands`, `agents`, `outputStyles` varsayılan
  klasörün **yerine** geçer (klasör varsa "Varsayılan commands/ klasörü yok sayıldı" uyarısı);
  `skills` varsayılana eklenir; `hooks` ve `mcpServers` varsayılan dosyayla birleşir.
- `commands` düz `.md` dosyası, klasör ya da `{ad: {source|content, description, argumentHint}}`
  haritası; `agents` yalnız `.md` dosyaları; `outputStyles` dosya ya da klasör; `hooks`/`mcpServers`
  dosya, satır içi nesne ya da ikisini karıştıran dizi alır. `skills/` ve `skills` anahtarı yoksa
  kökteki `SKILL.md` tek beceri olarak yüklenir. Var olmayan yol "yol bulunamadı" hatasıdır.
- Aynı eklentide aynı adlı MCP sunucusu birden çok kez tanımlanırsa sonraki öncekinin yerine geçer.
- Ad kuralı: boş olmayan, boşluk, `@`, `:`, yol ayırıcı ve denetim karakteri içermeyen ad (büyük
  harf serbest); kebab-case dışı ad ve Anthropic'e benzeyen ad doğrulamada uyarı, `claude-…`,
  `anthropic-…` gibi ayrılmış adlar hatadır. Tanınan alanlar Claude'un `plugin.json` alan tablosudur
  (`displayName`, `defaultEnabled`, `dependencies`, `userConfig`, `lspServers`… uyarı vermez); gerçekten
  bilinmeyen üst düzey alan atılır ve uyarı olur.
- `userConfig` (Claude "User configuration"): seçenekler `type` (string/number/boolean/directory/file),
  `title`, `description`, `required`, `default`, `options`, `multiple`, `sensitive`, `min`/`max` ile
  doğrulanır. Değerler `fusion plugin configure <ad@pazar> --values-stdin [--json]` ile kaydedilir
  (önce hepsi doğrulanır; biri geçersizse hiçbiri yazılmaz, çıkış 1); bayraksız `configure` her seçeneği
  `required|optional · sensitive · set|not set` etiketleriyle, değer basmadan listeler. Hassas olmayanlar
  `<eklentiler>/plugin-configs.json` (`pluginConfigs`), hassaslar yalnız sahibinin okuyabildiği (0600)
  `<eklentiler>/.credentials.json` dosyasına yazılır. `${user_config.KEY}` MCP yapılandırmasında ve
  beceri/ajan içeriğinde çözülür (içerikte hassas değer yer tutucu olur); kanca süreçleri her seçeneği
  `CLAUDE_PLUGIN_OPTION_<KEY>` olarak alır. Henüz yok: etkinleştirmede soru penceresi, `install
  --config`, `channels`, `/config` satırları; hassas değer şifreli depo yerine 0600 dosyadadır.
- Eski Fusion adları bir sürüm boyunca kullanımdan kalkmış takma addır ve uyarı verir:
  `.fusion-plugin/plugin.json` (→ `.claude-plugin/plugin.json`), `output-styles` anahtarı
  (→ `outputStyles`), `${FUSION_PLUGIN_ROOT}` (→ `${CLAUDE_PLUGIN_ROOT}`).
- `${CLAUDE_PLUGIN_ROOT}` eklentinin kurulu klasörüne, `${CLAUDE_PLUGIN_DATA}` güncellemelerde korunan
  kalıcı veri klasörüne (`<veri>/eklentiler/.veri/<id>/`, ilk başvuruda oluşur),
  `${CLAUDE_PROJECT_DIR}` proje köküne çözülür: kanca ve MCP tanımlarında, komut/beceri/ajan
  gövdesinde.
- Bütün adlar eklenti adıyla öneklenir: üçüncü taraf bir eklenti kendi `ozet` becerini gölgeleyemez.
  Eklenti beceri/komutlarında `` !`komut` `` dinamik bağlamı Claude Code'daki gibi çalışır: kullanıcının
  kendi becerisiyle aynı kipte (auto/acceptEdits/bypass) ve aynı riskli komut denetimiyle; diğer
  kiplerde yerinde "komut çalıştırılmadı" notu kalır. Güvenlik notu: önceden hiç çalışmıyordu.
- MCP sunucuları `plugin_<eklenti>_<sunucu>` adıyla, `unreviewed` güvenle eklenir; araç çağrıları
  onay ister, hiçbir ayar dosyasına yazılmaz ve güven kararı kalıcı tutulmaz (`fusion mcp remove`
  yerine eklentiyi kapat). Eklentiyi kapatmak/kaldırmak sunucuyu çalışan oturumdan da çıkarır
  (masaüstünde canlı bağlantı hemen kapanır). Desteklenmeyen alan taşıyan sunucu (`type: sse`, `cwd`,
  Authorization dışı başlık…) uyarıyla atlanır, eklentinin geri kalanı kurulur;
  `Authorization: Bearer ${VAR}` başlığı desteklenir. İki eklentinin sunucu adı çakışırsa ada göre
  ilk eklenti kazanır.
- Kancalar Claude Code'daki gibi çalışır: etkin eklentinin `hooks/hooks.json` ve `plugin.json` `hooks`
  girdileri kanca kümesine `eklenti:<ad>` kaynağıyla katılır; süreçler `CLAUDE_PLUGIN_ROOT`,
  `CLAUDE_PLUGIN_DATA` ve `CLAUDE_PROJECT_DIR` alır. `FUSION_HOOKS=off`, `runtime.hooks_enabled:
  false` ve `disableAllHooks` eklenti kancalarını da kapatır.
- Claude Code'un kendi kurduğu eklentiler (`~/.claude/plugins/installed_plugins.json`) ham beceri kökü
  olarak taranmaz: yalnız kullanıcı kapsamında kurulu ve `~/.claude/settings.json` `enabledPlugins`'te
  kapatılmamış olanların beceri/komut/ajanları `<eklenti>:<ad>` önekiyle yüklenir; eski sürümler
  (`.orphaned_at`) ve pazar klonları yüklenmez. Bunların kanca/MCP bileşenleri Claude Code'un
  oturumunda çalışır, Fusion başlatmaz.

## Pazar bildirimi

`marketplace.json`'da `name`, `owner.name` ve `plugins` zorunludur. Her girdi ayrı doğrulanır; bozuk
girdi atlanır ve uyarı olur, pazarın geri kalanı eklenir; yinelenen eklenti adı hatadır. Pazar adı
harf/rakamla başlar ve harf, rakam, `.`, `_`, `-` içerir; resmî adlar (`claude-plugins-official`…),
taklitleri, `inline`, `skills-dir`, `synced`, `npm`, `github`, `claudeai-…` gibi ayrılmış adlar
reddedilir. Göreli kaynak `./` ile başlar (`.` tek başına pazar köküdür); çıplak ad yalnız
`metadata.pluginRoot` altında ve `/` içermeden geçerlidir. `sha` tam 40 karakter küçük harf commit
olmalıdır. Eklenti kaynağındaki `git` türü kullanımdan kalktı (Claude adı `url`).

## Komutlar

```
fusion plugin install rapor@ekip [--yes] [--scope user|project|local] [--json]  # kayıtlı pazardan
fusion plugin install rapor --marketplace <yol|sahip/repo|https…>  # pazar yoksa önce eklenir
fusion plugin install <kaynak> --dry-run       # yalnız doğrula ve özetle
fusion plugin list [--json] [--available]      # --available: pazarlardaki kurulmamışlar (JSON nesnesi)
fusion plugin details <ad|ad@pazar>            # bileşen envanteri + öngörülen token maliyeti
fusion plugin prune [--dry-run] [-y]           # (autoremove) Fusion bağımlılık kurmaz: "Nothing to prune"
fusion plugin validate <yol|ad> [--strict] [--json]   # plugin.json ya da marketplace.json; çıkış 0/1/2
fusion plugin enable|disable <ad|ad@pazar> [--scope user|project|local]  ·  disable --all
fusion plugin uninstall <ad|ad@pazar> [--keep-data] [--scope user|project|local]  # kopya .orphaned_at ile 14 gün kalır
fusion plugin update <ad|ad@pazar>             # önce pazar yenilenir; sürüm aynıysa değişmez
fusion eklenti kesfet [pazar]                  # kullanımdan kalktı → plugin list --json --available
fusion plugin marketplace add <./klasör|./pazar.json|sahip/repo[#ref|@ref]|https://….git[#ref]|resmi>
fusion eklenti pazar ekle <yol|sahip/repo|https…|resmi>  ·  pazar liste  ·  pazar guncelle [ad]  # ad yoksa hepsi
fusion plugin marketplace remove <ad>          # o pazardan kurulan eklentiler de kaldırılır
```

`fusion --plugin-dir <yol> …` (tekrarlanabilir; ortam değişkeni `CLAUDE_CODE_PLUGIN_DIRS`) eklentiyi
kurmadan yalnız o oturum için `<ad>@inline` olarak yükler; eklenti klasörlerini tutan bir klasör
verilirse her `.claude-plugin/plugin.json` içeren çocuk yüklenir. Aynı adlı kurulu eklenti o oturumda
atlanır. `plugin list` bunları `Session-only plugins (--plugin-dir / --plugin-url):` başlığında,
`--json`'da `scope: "session"` ile gösterir. Güvenlik notu: yolu kullanıcı açıkça verdiği için
Claude Code'daki gibi kanca/MCP ayrıca onay istemez. Manifestte `defaultEnabled: false` ya da bir
ayar dosyasında `"enabledPlugins": {"<ad>@inline": false}` oturumluk eklentiyi kapatır; kapalı
kopya gölgelemez, aynı adlı kurulu eklenti yüklenir.

REPL'de `/reload-plugins [--force]` bekleyen eklenti değişikliklerini oturumu yeniden başlatmadan
uygular ve `Yeniden yüklendi: N eklenti · N beceri · N ajan · N kanca · N eklenti MCP sunucusu · 0
eklenti LSP sunucusu` özetini basar; bir eklenti MCP sunucusu eklenip çıkacaksa (istem önbelleği
bozulur) `--force` ister.

**Kapsamlar (`enabledPlugins`):** Claude Code gibi açık/kapalı bilgisi settings dosyalarındaki
`enabledPlugins` (`{"ad@pazar": true|false}`; pazarsız kurulumda yalnız ad) anahtarında durur,
öncelik local (`.claude/settings.local.json`) > project (`.claude/settings.json`) > user. `--scope`
verilmezse local, project, user sırasıyla eklentiyi anan ilk kapsam kullanılır; ilan edilenden düşük
öncelikli kapsam "… kapsamında kurulu, … değil" hatası verir, yüksek öncelikli kapsama geçersiz
kılma yazılır. Güvenlik: `fusion trust` sonrası değişmiş (güvenilmeyen) proje dosyasındaki `true`
eklenti açmaz; `false` her zaman uygulanır. Fusion'ın yazdığı güvenilir dosya güvenilir kalır.
Kaldırma eklentinin `${CLAUDE_PLUGIN_DATA}` klasörünü siler (`--keep-data` korur).
`install --scope project|local` dosyaları ortak depoya kurar, user kaydını kapalı başlatır ve yalnız
o kapsamın dosyasına `enabledPlugins["ad@pazar"] = true` yazar. `install`, `uninstall`, `enable`,
`disable` `--json` ile son satıra `{"command","outcome":"ok|failed","message",…}` nesnesini basar.
Yerel klasör/https/sahip-repo kaynağından doğrudan kurulum bir sürüm boyunca çalışır ama
kullanımdan kalktı uyarısı verir (Claude `install` yalnız pazardan kurar; `--marketplace` kullan).

**Bildirilen pazarlar (`extraKnownMarketplaces`):** depo `.claude/settings.json` ya da
`.claude/settings.local.json` içinde `{"extraKnownMarketplaces": {"ad": {"source": {...}}}}`
(takma ad `additionalMarketplaces`; ikisi birden varsa asıl anahtar) ile bildirilen ve henüz
bilinmeyen pazar, klasöre güvenildiyse Claude Code gibi kaydedilir: REPL açılışında arka planda,
`plugin install`/`plugin list`/`plugin marketplace list` öncesinde. Güvenilmeyen klasörde girdiler
sessizce yok sayılır; aynı adlı girdide local, project'in girdisini bütünüyle ezer. Kaynak türleri:
`github` (`repo`, isteğe bağlı `ref`), `git` (`url`), `directory`/`file` (`path`, göreli ise depo
köküne göre). `url` ve `settings` türleri Fusion'da yok, uyarıyla atlanır.
Projenin güvenilen `.claude/settings.json`/`.claude/settings.local.json` dosyasında
`enabledPlugins["ad@pazar"] = true` olan ama bu makinede kurulmamış eklenti, pazar girdisi göreli
yollu ise kurulum kaydı yazılmadan pazarın kendisinden yüklenir; dış kaynaklı girdi yüklenmez ve
`Plugin "<ad>" is enabled in project settings but isn't installed here` günlüğe yazılır.

Claude Code'daki gibi: zaten kurulu eklentiyi yeniden kurmak bilgi mesajıyla 0, zaten açık/kapalı
eklentiyi açmak/kapatmak "zaten açık/kapalı" ile 1 döner; `--all` bir adla birlikte kullanılamaz;
`ac --hepsi` (Claude'da `enable --all` yok) yalnız eski genel kapatmayı kaldırır ve kullanımdan
kalktı. Eklenti ajanlarında `permissionMode`, `hooks`, `mcpServers`, `initialPrompt` yok sayılır;
`agents/` alt klasörleri ada katılır (`eklenti:inceleme:guvenlik`). Kurulum boyut sınırı Claude'un
kopyalama sınırıdır: 20.000 dosya / 256 MiB.

Birincil adlar Claude Code'unkilerdir ve yardımda görünür: `fusion plugin install (i) | list | validate |
enable | disable | uninstall (remove, rm) | update`, `fusion plugin marketplace add | list | update |
remove (rm)`; `fusion plugins` da aynı gruptur. Yukarıdaki Türkçe adlar (`eklenti kur`, `pazar ekle`…)
bir sürüm boyunca gizli, kullanımdan kalkmış takma addır; kullanılınca stderr'e Claude adını söyleyen
uyarı basılır. `marketplace add|remove|update --json` aynı sonuç nesnesini (`command`:
`marketplace-add|remove|update`, `marketplace`) basar. Eski `FUSION_PLUGINS=off` ortam değişkeni bir
sürüm boyunca okunur ve süreç başına bir kez uyarır (Claude karşılığı `disable --all`). `details`, `prune` (`autoremove`) var; henüz yok:
`configure`, `init`, `tag`, `eval`, `test`. REPL'de `/plugin` (`/plugins`, `/eklenti`) aynı alt
komutları alır; kanca ya da MCP içeren eklenti önce önizlenir, `--yes` ile kurulur (araya giren
değişiklik varsa kurulmaz). Masaüstünde Beceriler ekranındaki **Eklentiler** düğmesi Kurulu · Keşfet ·
Pazarlar sekmelerini açar; her eklentide Güncelle/Doğrula, değişmiş eklentide "İncele ve yeniden
onayla" (RPC: `eklenti.*`, `eklenti.guncelle|dogrula|pazar_guncelle`).

Yerel klasörden eklenmiş bir pazarın göreli yollu (`./plugins/x`) eklentileri Claude Code gibi
kopyalanmaz, kaynak klasöründen yerinde yüklenir: kaynakta yapılan düzenleme sürüm artırmadan sonraki
oturumda ya da `/reload-plugins`'te geçerli olur, `CLAUDE_PLUGIN_ROOT` kaynak klasörü gösterir,
`plugin list --json` `readFromFolder`/`folderVersion` verir; kaldırma kaynak klasöre dokunmaz.

Pazar kaynağı Claude Code tablosuyla çözülür: `owner/repo`, `owner/repo#ref`/`@ref` (GitHub),
`.git` ile biten ya da `/_git/` içeren https adresi, github.com/gitlab.com adresi, klasör ya da `.json`
dosyası (dosya türü yerinde okunur). Claude'da olup Fusion'da açıkça reddedilenler: SSH
(`user@host:path`), düz `http://`, `.git`'siz başka https adresinin marketplace.json olarak
indirilmesi (url türü) ve `--sparse`; Fusion yalnız genel https adreslerini iç ağa çıkmadan klonlar.

Pazar girdisinin kaynağı göreli yol (`./…`), `github` (`repo`), `url` ve `git-subdir` (`url` tam git
adresi ya da `owner/repo`, `path` depodaki eklenti klasörü; yalnız o klasör kurulur) olabilir; `npm`,
`archive` ve `command` kaynakları henüz yok.

`plugin marketplace update` sonrasında pazarın `renames` haritası uygulanır (zincir en eski addan
izlenir): yeniden adlandırılan kurulum yeni girdi adıyla sürer, project/local `enabledPlugins`
anahtarı yeni ada yazılır ve `Renamed to "<yeni>" in the "<pazar>" marketplace` basılır; `null`
eşlemede anahtar düşer (`Removed from the "<pazar>" marketplace`). `forceRemoveDeletedPlugins: true`
iken girdilerde ve `renames`'te olmayan kurulum kaldırılır. Claude bunu her oturum başında yapar;
Fusion yalnız pazar güncellemesinde (REPL/masaüstü güncellemesinde henüz değil).

Girdi her `plugin.json` alanını taşıyabilir (Claude "Strict mode"): eklentide `plugin.json` yoksa girdi
bildirimdir; varsa o otoritedir ve `strict: true` (varsayılan) iken girdinin `commands`, `agents`,
`skills`, `hooks`, `outputStyles`, `themes` alanları ona eklenir (`hooks` eşleyicileri olay başına yer
değiştirir), `strict: false` iken bileşen alanı taşıyan girdi `has conflicting manifests` hatasıyla
kurulmaz. Girdinin `defaultEnabled` ve görünen alanları (`displayName`, `description`, …) önce gelir,
`version`'da plugin.json kazanır. Girdide dosya yolu/dizi `hooks` desteklenmez. Fusion bunu önbellek
kopyasının `plugin.json`'ına yazar; yerinde yüklenen (yerel pazar) eklentide kaynağa yazılmaz, alanlar
kayıtta saklanıp her taramada bellekte birleştirilir (`plugin update` değişen girdiyi alır). `plugin validate`
göreli yollu girdinin `version`'ı plugin.json'dakiyle çelişirse Claude'un `Entry declares version "x"
but <yol>/plugin.json says "y". At install time, plugin.json wins` uyarısını verir.

`resmi` kısa adı `https://github.com/anthropics/claude-plugins-official` pazarıdır. Keşfet ağa
çıkmaz; git pazarları son ekleme/güncelleme anındaki klondan okunur (`pazar guncelle`). Aynı adlı
başka kaynaklı bir pazar eskisinin yerine geçemez.

Claude'un `workflows/` iş akışları ve `hooks.json` `modules` (mod) bileşenleri desteklenmez; bulunursa
yükleme/doğrulamada "desteklenmiyor" uyarısı verilir.

**Claude Code'dan farklar (Hâlâ eksik):** user kapsamı Fusion'ın kaydıdır (`kayit.json`), Claude'un
`~/.claude/settings.json`'ına yazılmaz; dosyalar tek (user) depodadır; `uninstall --scope project|local`
yalnız o kapsamın `enabledPlugins` girdisini siler, paylaşılan kopyaya dokunmaz. `--plugin-url` ve `.zip` arşivli `--plugin-dir` yok. Managed
kapsam okunmaz; `extraKnownMarketplaces` yalnız project/local'den okunur, `marketplace add` user
ayarına yazmaz, bildirimin kaynağı sonradan değişirse pazar yeniden çekilmez, `autoUpdate` uygulanmaz; `marketplace remove --scope` yok. Kriptografik imza yok: bütünlük sha256 karma +
commit pinidir.

## Sürüm ve güncelleme

Sürüm Claude Code sırasıyla hesaplanır: `plugin.json` `version`, pazar girdisinin `version`'ı, ikisi
de yoksa kaynağın commit SHA'sının ilk 12 karakteri (`git-subdir`'de alt klasör yolu karması eklenir;
git pazarındaki göreli eklentide pazar klonunun commit'i), yerel klasörde `unknown`. `plugin update`
sürümü yeniden hesaplar; kayıttakiyle aynıysa kopyaya dokunmaz ve
`<ad> is already at the latest version (<sürüm>).` der (manifest sürümünü sabitlemek kullanıcıyı o
sürümde tutar). `ad@pazar` kurulum ve güncellemesinden önce git pazarı yenilenir (yerel pazar, son 30
saniyede yenilenen pazar ve `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` atlanır; yenileme başarısızsa
önbellekteki katalogla sürer). Güncellenen ya da kaldırılan eklentinin önceki kopyası
`<eklentiler>/.orphaned/` altına `.orphaned_at` işaretiyle taşınır ve 14 gün sonra silinir.
**Otomatik güncelleme:** REPL açıldıktan sonra rastgele en çok 10 dakikalık gecikmeyle auto-update'i
açık pazarlar arka planda yenilenir ve onlardan kurulan eklentiler güncellenir (açık oturum yüklediği
sürümle sürer; günlüğe `Plugin updated: <ad> · Run /reload-plugins to apply` yazılır). Açık mı:
önce `extraKnownMarketplaces` girdisindeki `autoUpdate`, yoksa varsayılan (Anthropic'in resmî
pazarlarında açık, `knowledge-work-plugins`/`first-party-plugins` ve diğerlerinde kapalı).
`DISABLE_UPDATES`, `DISABLE_AUTOUPDATER`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` kapatır,
`FORCE_AUTOUPDATE_PLUGINS=1` yeniden açar. Güvenlik notu: Claude'daki gibi otomatik güncelleme onay
sormaz. Henüz yok: `/plugin` Marketplaces'teki Enable auto-update anahtarı, resmî pazarın ilk
oturumda kendiliğinden eklenmesi, bildirimin TUI'de gösterilmesi (#394).

## Güven ve bütünlük

- Claude Code gibi karma kilidi yoktur (güvenlik davranışı değişti, #392): kurulumda kaydedilen sha256
  karma yalnız bilgidir; kopya sonradan değişse de eklenti yüklenir. `trust`/`guven` kullanımdan
  kalktı (yalnız karma kaydını yeniler, uyarı verir).
- Kullanıcı kapsamında etkin eklentinin kanca ve MCP sunucuları ek onay istemeden yüklenir (#419).
  Proje kapsamında (`.claude/settings.json`) açılan eklenti yalnız o dosya güvenildiyse (`fusion
  trust`) yüklenir; eklenti MCP kayıtları `unreviewed` güvenle girer.
- CLI `plugin install`/`update` ek soru sormaz (Claude gibi; `--yes` etkisiz kabul edilir). Masaüstü
  ve REPL panelde önizler, kanca/MCP içeren eklentide "Onaylıyorum, kur" / `--yes` ister.
- Onay ekranı kanca satırlarını (`Olay [eşleşen]: komut`), MCP sunucularının tam komutunu (sırlar
  maskeli) ve içerik karmasını gösterir. Onay o karmaya bağlıdır: `fusion eklenti kur X --dry-run`
  karmayı basar, `kur X --yes --karma <karma>` içerik değiştiyse kurmaz; masaüstü ve REPL bunu
  kendiliğinden yapar.
- Pazar girdisi `sha` bildiriyorsa en az 7 onaltılık karakter olmalıdır. Tam (40 karakter) sha o
  commit'i doğrudan çeker (dal ucu ilerlese de); kısa sha dal ucuyla eşleşmelidir.
- Git adresleri yalnız genel https sunucularıdır (iç ağ, kimlik bilgili adres
  yok); klon yönlendirme izlemez, https dışı protokole geçmez ve denetlenen IP'ye sabitlenir.
  Yerel klasör 5 000 dosya / 50 MB sınırını aşıyorsa kopyalanmadan reddedilir.
- Hepsini kapatma: `fusion eklenti kapat --hepsi` ya da `FUSION_PLUGINS=off`.

## İçe aktarma (`/import`)

```
fusion import <claude|codex|gemini|cursor> [--dry-run] [--yes]
/import codex            # önizleme
/import codex --yes      # uygula
```

Masaüstü: Ayarlar › Kişiselleştirme › **Başka araçtan içe aktar** (RPC `ice_aktar.onizle|uygula`).

| Kaynak | Taşınan | Zaten doğrudan okunan |
|--------|---------|-----------------------|
| Claude Code | `~/.claude.json` MCP (kullanıcı + bu projenin yerel kapsamı) | `~/.claude/settings.json` izin/kanca, CLAUDE.md, skills/agents/commands, `.mcp.json` |
| Codex | `config.toml` `[mcp_servers]`, `~/.codex/rules/*.rules` `prefix_rule` → `Bash(…)`, `~/.codex/prompts` → `~/.fusion/commands` | AGENTS.md, `~/.codex/skills`, `~/.agents/skills` |
| Gemini CLI | `settings.json` MCP (`httpUrl`), `tools.allowed/exclude` → izin, `~/.gemini/GEMINI.md` → `~/.fusion/TALIMAT.md` içine `@` başvurusu, `commands/*.toml` → komut | proje GEMINI.md |
| Cursor | `mcp.json` (proje dosyası projenin `.mcp.json`'ına), `cli-config.json` izinleri, `.cursor/rules/*.mdc` (`alwaysApply`/`globs`) → `.fusion/rules`, `commands/*.md` | `.cursorrules`, AGENTS.md |

Kurallar: sır gibi görünen ortam değerleri, argümanlar (`--token x`, `--api-key=x`,
`Authorization: Bearer x`), adres sorgu değerleri (`?api_key=x`) ve `Authorization: Bearer`
başlıkları şifreli depoya gider; `config.yaml`'a yerine `${FUSION_MCP_ENV_<SUNUCU>__<AD>}` başvurusu
yazılır, önizlemede değer görünmez. Kasa adı sunucuya özeldir: iki sunucunun `OPENAI_API_KEY`'i
birbirini ya da Fusion'ın kendi sağlayıcı anahtarını ezmez; alt süreç yine `OPENAI_API_KEY` adıyla
alır. Kullanıcı adı/parolalı ya da yolunda sır taşıyan adres atlanır. Var olan dosyanın üzerine
yazılmaz, aynı adlı MCP/kural "zaten var" olur. Proje dosyalarındaki izin kuralları taşınmaz (depo
genel izin dosyana `Bash(*)` yazdıramaz). SSE taşıması ve Authorization dışındaki başlıklar
gerekçesiyle atlanır. Codex `approval_policy`/`sandbox_mode` bilgi satırıdır (karşılığı onay kipi).

## Sürüm notları

`/release-notes [sürüm|liste]`, `fusion release-notes`, Ayarlar › Güncellemeler › Sürüm notları
(RPC `surum.notlari`). Kaynak deponun `CHANGELOG.md`'sidir; dosyanın bulunmadığı kurulumda
GitHub Releases sayfası gösterilir.
