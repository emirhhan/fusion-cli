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
  `<eklentiler>/plugin-configs.json` (`pluginConfigs`), hassaslar Claude gibi güvenli depoya: Fusion'ın
  şifreli sır deposu biçiminde (ana anahtar Keychain/yerel kasada) `<eklentiler>/.plugin-secrets.enc`.
  Ana anahtar yoksa yalnız sahibinin okuyabildiği (0600) `<eklentiler>/.credentials.json` yedektir;
  eski sürümün bu dosyadaki değerleri okunur ve ilk yazımda şifreli depoya taşınır. Kaydetme kilit
  altındadır (CLI ve masaüstü aynı anda yazınca değer kaybolmaz). `${user_config.KEY}` MCP yapılandırmasında ve
  beceri/ajan içeriğinde çözülür (içerikte hassas değer yer tutucu olur); kanca süreçleri her seçeneği
  `CLAUDE_PLUGIN_OPTION_<KEY>` olarak alır. `plugin install --config key=value` (tekrarlanabilir)
  değerleri kurulumda aynı yoldan doğrulayıp kaydeder; biri geçersizse kurulum geri alınır;
  `<sunucu>.<anahtar>` (.mcpb) Fusion'da yoktur. Ayarlanmamış zorunlu seçenek kalırsa kurulum
  `fusion plugin configure <id>` ipucu verir. `plugin validate` geçersiz `userConfig` şemasını hata
  sayar. Eklenti son kapsamından kaldırılınca seçenekleri ve sırları da silinir. Henüz yok:
  etkinleştirmede soru penceresi, `channels`, `/config` satırları.
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
  Projeden (`.claude/settings.json`) açılan ya da kaynağı proje klasöründe yerinde duran eklenti depo
  içeriğidir: proje becerisi gibi yalnız güvenilen projede ve yalnız salt-okur komut koşar.
- MCP sunucuları Claude Code adıyla `plugin:<eklenti>:<sunucu>` (büyük/küçük harf ve tire korunur;
  araç adı MCP kayıt kuralıyla `mcp__plugin_<eklenti>_<sunucu>__<araç>`), `unreviewed` güvenle eklenir;
  eski `plugin_<eklenti>_<sunucu>` adı kalktı (proje eklentisi sunucuları bir kez yeniden
  `fusion trust` ister); araç çağrıları
  onay ister, hiçbir ayar dosyasına yazılmaz ve güven kararı kalıcı tutulmaz (`fusion mcp remove`
  yerine eklentiyi kapat). Eklentiyi kapatmak/kaldırmak sunucuyu çalışan oturumdan da çıkarır
  (masaüstünde canlı bağlantı hemen kapanır). Desteklenmeyen alan taşıyan sunucu (`type: sse`, `cwd`,
  Authorization dışı başlık…) uyarıyla atlanır, eklentinin geri kalanı kurulur;
  `Authorization: Bearer ${VAR}` başlığı desteklenir (taşıma ve başlık desteği MCP yapılandırmasının
  ortak ayrıştırıcısından gelir). Aynı tam adlı iki sunucuda ada göre ilk eklenti kazanır.
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
reddedilir. Resmî/topluluk/dizin adlarının kendisi yalnız `github.com/anthropics/` altındaki github/git
kaynağından gelen pazara serbesttir (`marketplace add resmi` böyle eklenir); taklitler her kaynakta
reddedilir. Göreli kaynak `./` ile başlar (`.` tek başına pazar köküdür); çıplak ad yalnız
`metadata.pluginRoot` altında ve `/` içermeden geçerlidir. `sha` tam 40 karakter küçük harf commit
olmalıdır. Eklenti kaynağındaki `git` türü kullanımdan kalktı (Claude adı `url`).

## Komutlar

```
fusion plugin install rapor@ekip [--scope user|project|local] [--config k=v] [--json]  # kayıtlı pazardan
fusion plugin install rapor --marketplace <yol|sahip/repo|https…>  # pazar yoksa önce eklenir
fusion plugin install <kaynak> --dry-run       # yalnız doğrula ve özetle
fusion plugin list [--json] [--available] [--data-size [ad]]  # --data-size: dataDirSize {bytes,human}
fusion plugin init|new <ad> [--author] [--author-email] [--description] [-f] [--with skills agents hooks mcp lsp output-style channel]
fusion plugin tag [yol] [--dry-run] [-f] [-m "%s"] [--push] [--remote origin]   # <ad>--v<sürüm> etiketi
fusion plugin configure <ad@pazar> [--values-stdin] [--json]
fusion plugin details <ad|ad@pazar>            # bileşen envanteri + öngörülen token maliyeti
fusion plugin prune [--dry-run] [-y]           # (autoremove) artık gerekmeyen kendiliğinden kurulmuş bağımlılıklar
fusion plugin validate <yol|ad> [--strict] [--json]   # plugin.json ya da marketplace.json; çıkış 0/1/2
fusion plugin enable|disable <ad|ad@pazar> [--scope user|project|local]  ·  disable --all
fusion plugin uninstall <ad|ad@pazar> [--keep-data] [--scope user|project|local]  # kopya .orphaned_at ile 14 gün kalır
fusion plugin update <ad|ad@pazar>             # önce pazar yenilenir; sürüm aynıysa değişmez
fusion eklenti kesfet [pazar]                  # kullanımdan kalktı → plugin list --json --available
fusion plugin marketplace add <./klasör|./pazar.json|owner/repo[#ref|@ref]|user@host:yol|http(s)://…> [--scope user|project|local] [--sparse <yollar…>] [--json]
fusion plugin marketplace list  ·  marketplace update [ad]   # ad yoksa hepsi
fusion plugin marketplace remove <ad>          # o pazardan kurulan eklentiler de kaldırılır
```

`fusion --plugin-dir <yol|x.zip> …` (tekrarlanabilir; ortam değişkeni `CLAUDE_CODE_PLUGIN_DIRS`) ve
`fusion --plugin-url <adres>` (.zip indirir) eklentiyi kurmadan yalnız o oturum için `<ad>@inline`
olarak yükler (arşiv içerik karmasıyla `<veri>/eklentiler/.gecici/oturum/` altına güvenli açılır;
`..`, mutlak yol ve sembolik bağ reddedilir, sınır 20.000 girdi / 256 MiB); eklenti klasörlerini tutan bir klasör
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
öncelik managed (kuruluşun `managed-settings.json`'ı: macOS `/Library/Application
Support/ClaudeCode`, Linux `/etc/claude-code`, Windows `C:\Program Files\ClaudeCode`) > local
(`.claude/settings.local.json`) > project (`.claude/settings.json`) > user (`~/.claude/settings.json`,
Claude Code ile ortak). Managed değer başka kapsamda değiştirilemez (`managed_settings_override` /
`plugin_policy_blocked`). user kapsamında `install`, `enable`, `disable` (ve `disable --all`),
`uninstall` Claude gibi `~/.claude/settings.json` `enabledPlugins`'e yazar; anahtar yoksa Fusion
kaydının eski `etkin` değeri geçerlidir. `marketplace add` (user) pazarı `~/.claude/settings.json`
`extraKnownMarketplaces`'e bildirir ("user ayarlarında bildirildi"; CLI, REPL ve masaüstü),
`marketplace remove` bildirimi user/project/local'den siler. `--scope`
verilmezse local, project, user sırasıyla eklentiyi anan ilk kapsam kullanılır; ilan edilenden düşük
öncelikli kapsam "… kapsamında kurulu, … değil" hatası verir, yüksek öncelikli kapsama geçersiz
kılma yazılır. Güvenlik: `fusion trust` sonrası değişmiş (güvenilmeyen) proje dosyasındaki `true`
eklenti açmaz; `false` her zaman uygulanır. Fusion'ın yazdığı güvenilir dosya güvenilir kalır.
Kurulum kapsamları kayıtta izlenir (`user`, `project:<kök>`, `local:<kök>`). `install --scope
project|local` dosyaları ortak depoya kurar, user kaydını kapalı başlatır ve o kapsamın dosyasına
`enabledPlugins["ad@pazar"] = true` yazar; yalnız projede kurulu eklenti `install` (user) ile user
kapsamına da kurulur. `uninstall` (varsayılan user; eklenti yalnız bu projede kuruluysa o kapsam)
kapsamı düşürür; eklenti SON kapsamından kalkınca Claude gibi kopya `.orphaned_at` ile emekliye
ayrılır, userConfig değerleri ve sırları silinir, `${CLAUDE_PLUGIN_DATA}` klasörü silinir
(`--keep-data` yalnız veriyi korur). Başka kapsam kullanıyorsa paylaşılan kopya ve veri kalır. `install`, `uninstall`, `enable`,
`disable` `--json` ile son satıra `{"command","outcome":"ok|failed","message",…}` nesnesini basar.
`install <yol|URL|owner/repo>` Claude gibi kurmaz: `… yapılandırılmış hiçbir pazarda yok` (çıkış 1);
yerel deneme için `--plugin-dir`, pazar için `--marketplace`. Eski `kur` adı doğrudan kaynak kurulumunu
bir sürüm boyunca uyarıyla sürdürür.

**Bildirilen pazarlar (`extraKnownMarketplaces`):** depo `.claude/settings.json` ya da
`.claude/settings.local.json` içinde `{"extraKnownMarketplaces": {"ad": {"source": {...}}}}`
(takma ad `additionalMarketplaces`; ikisi birden varsa asıl anahtar) ile bildirilen ve henüz
bilinmeyen pazar, klasöre güvenildiyse Claude Code gibi kaydedilir: REPL açılışında arka planda,
`plugin install`/`plugin list`/`plugin marketplace list` öncesinde. Güvenilmeyen klasörde girdiler
sessizce yok sayılır; aynı adlı girdide local, project'in girdisini bütünüyle ezer. Kaynak türleri:
`github` (`repo`, isteğe bağlı `ref`), `git` (`url`), `directory`/`file` (`path`, göreli ise depo
köküne göre), `url` (`url`: marketplace.json adresi). `settings` türü Fusion'da yok, uyarıyla atlanır. `~/.claude/settings.json`'daki bildirimler de
(en düşük öncelik, güven onayı istemez) okunur. Kayıtlı pazarın bildirilen kaynağı değişirse pazar
Claude gibi yeni kaynaktan yeniden çekilir; kurulu eklentiler kalır.
`marketplace add --scope project|local` pazarı o kapsamın dosyasına
`extraKnownMarketplaces[<ad>] = {"source": {...}}` olarak bildirir ("project ayarlarında
bildirildi"); `marketplace remove` bildirimi project/local dosyalarından da siler.
Projenin güvenilen `.claude/settings.json`/`.claude/settings.local.json` dosyasında
`enabledPlugins["ad@pazar"] = true` olan ama bu makinede kurulmamış eklenti, pazar girdisi göreli
yollu ise kurulum kaydı yazılmadan pazarın kendisinden yüklenir; dış kaynaklı girdi yüklenmez ve
`Plugin "<ad>" is enabled in project settings but isn't installed here` günlüğe yazılır.

**Kimlik `ad@pazar`:** Claude Code gibi farklı pazarlardan aynı adlı eklentiler birlikte kurulur.
İlk kurulum kayıtta `ad` anahtarını ve `<eklentiler>/ad/` klasörünü, sonraki pazardan gelen aynı adlı
eklenti `ad@pazar` anahtarını ve `<eklentiler>/ad@pazar/` klasörünü alır (eski kayıtlar değişmez).
`enable`/`disable`/`uninstall`/`update`/`details` iki biçimi de alır; yalnız `ad` birden çok kuruluma
uyuyorsa kimlikleri listeleyen "belirsiz" hatası verir. Kurma anahtarı pazar girdisinin adıdır,
bileşenler bildirimdeki adla öneklenir.

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
sürüm boyunca okunur ve süreç başına bir kez uyarır (Claude karşılığı `disable --all`). `details`, `prune`
(`autoremove`), `configure`, `init` (`new`), `tag` var. `test` Claude Code modları içindir (Fusion'da mod
sistemi yok; açık hata). Henüz yok: `eval`.

`plugin init <ad>` Claude Code gibi `~/.claude/skills/<ad>/` altına `.claude-plugin/plugin.json`
(`$schema`, `version: 0.1.0`, `author`, `skills: ["./"]`) ve kök `SKILL.md` yazar; `--with` ek iskelet
kurar; var olan `.claude-plugin/` `--force` ister; ayrılmış ad, yol ayırıcı ve boşluk reddedilir.
Bu klasörler kurulmadan `<ad>@skills-dir` olarak yüklenir (`plugin list`: "Skills-directory plugins
(.claude/skills/*):"; `disable <ad>@skills-dir` `~/.claude/settings.json` `enabledPlugins`'e yazar);
düz beceri olarak taranmazlar. `plugin tag` plugin.json sürümünü ve onu gösteren pazar girdisini
karşılaştırır, kirli çalışma ağacını ve var olan etiketi `--force` olmadan reddeder, `<ad>--v<sürüm>`
açıklamalı etiketini HEAD'e koyar (`--push` ile gönderir).

REPL'de argümansız `/plugin` (`/plugins`) Claude gibi paneli **Discover** sekmesinde açar:
Discover (eklenti seç → ayrıntı + "Senin için / bu depodaki herkes için / yalnız senin için, bu depoda"
kapsam seçimi → kurulum), Installed (aç/kapat, yapılandır, güncelle, ayrıntı, kaldır), Marketplaces
(güncelle, kaldır, **Enable/Disable auto-update**), Errors (yüklenemeyen eklentiler). TUI'de
uygulama-içi modal, satır-içi REPL'de ok tuşlu seçici; terminal değilse kurulu liste basılır.
Alt komutlar: `help`, `list [--enabled|--disabled]` (`ls`), `manage`, `install <ad>` (bayraksız
panel açar; `--scope` ile doğrudan), `enable|disable|uninstall`, `configure`, `validate`, `details`,
`update`, `tag`, `marketplace` (`market`) `add|list|update|remove|rm`; `/marketplace` takma adı.
Türkçe alt komutlar (`kur`, `ac`, `kapat`, `kaldir`, `guncelle`, `dogrula`, `kesfet`, `pazar`)
kullanımdan kalktı uyarısıyla bir sürüm daha çalışır. Masaüstünde Beceriler ekranındaki **Eklentiler** düğmesi Kurulu · Keşfet ·
Pazarlar sekmelerini açar; her eklentide Güncelle/Doğrula; pazar kaldırma önce o pazardan kurulan
bütün eklentilerin, ayarlarının ve verilerinin de silineceğini söyleyip onay ister ve kaldırılanları
bildirir (RPC: `eklenti.*`, `eklenti.guncelle|dogrula|pazar_guncelle`, `eklenti.pazar_kaldir` →
`kaldirilan`; `eklenti.pazar_guncelle` `renames` bildirimlerini `notlar` alanında döndürür). Masaüstünde
sunucusu açılışında REPL gibi bildirilen pazar eşitlemesi, `renames` eşlemesi ve gecikmeli otomatik
güncelleme arka planda başlar. Masaüstü panelinde Claude `/plugin` karşılıkları: kurulum kapsamı
seçici (Senin için / bu depodaki herkes için / yalnız senin için, bu depoda → `eklenti.kur` `kapsam`),
pazar başına Enable/Disable auto-update anahtarı (`eklenti.pazar_otomatik`), arka plan güncelleme
bildirimleri (`eklenti.listele` `bildirimler`), kurulmadan yüklenen `@inline`/`@skills-dir`
eklentiler (`oturumluk`), pazardan kaldırılan Flagged eklentiler (`isaretli`) ve pazar komutu onay
kartı (`komut_onayi_gerekli` → `komut_onayi`). Eklenti işlemleri `kimlik` (`ad@pazar`) ile yapılır.
`/reload-plugins` karşılığı gerekmez: masaüstü kurulum/aç/kapat sonrası oturumu yeniler. Claude'un
`/plugin` Stats sekmesi (özellik bayrağıyla açılan kullanım raporu) yok.

Yerel klasörden eklenmiş bir pazarın göreli yollu (`./plugins/x`) eklentileri Claude Code gibi
kopyalanmaz, kaynak klasöründen yerinde yüklenir: kaynakta yapılan düzenleme sürüm artırmadan sonraki
oturumda ya da `/reload-plugins`'te geçerli olur, `CLAUDE_PLUGIN_ROOT` kaynak klasörü gösterir,
`plugin list --json` `readFromFolder`/`folderVersion` verir; kaldırma kaynak klasöre dokunmaz.

Pazar kaynağı Claude Code tablosuyla çözülür: `owner/repo`, `owner/repo#ref`/`@ref` (GitHub), SSH
(`user@host:path`), `.git` ile biten ya da `/_git/` içeren http(s) adresi, github.com/gitlab.com
adresi, başka her http(s) adresi doğrudan `marketplace.json` (url türü; indirilir, göreli yollu
eklentileri kurulamaz), klasör ya da `.json` dosyası (dosya türü yerinde okunur). `--sparse <yollar…>`
git sparse-checkout ile yalnız o klasörleri çeker ve güncellemede korunur. **Güvenlik davranışı
değişti:** kullanıcının verdiği pazar kaynağı Claude gibi yerel git kimlik bilgileri ve SSH
anahtarlarıyla, iç ağ adresleri dahil klonlanır (etkileşimsiz: `BatchMode=yes`, yönlendirme
izlenmez). Pazar GİRDİSİNDEKİ git eklenti kaynakları hâlâ yalnız genel https ile klonlanır.
`--claudeai` claude.ai hesabı gerektirir; Fusion'da açık hata verir.

Pazar girdisinin kaynağı göreli yol (`./…`), `github` (`repo`), `url`, `git-subdir` (`url` tam git
adresi ya da `owner/repo`, `path` depodaki eklenti klasörü; yalnız o klasör kurulur), `archive`,
`npm` ya da `command` olabilir (Claude Code şemasıyla doğrulanır; bozuk girdi atlanıp uyarılır):

- `archive`: `url` https zip (loopback, link-local ve bulut meta veri adresi reddedilir; yönlendirme
  her adımda yeniden denetlenir), isteğe bağlı `sha256` (64 hex; her indirmede doğrulanır, uyuşmazsa
  kurulmaz; plugin.json/girdi sürümü yoksa ilk 12 karakteri sürümdür). Arşivin tepesindeki ya da tek
  sarmalayıcı klasördeki eklenti kökü alınır; güvenli açma sınırları `--plugin-dir .zip` ile aynıdır.
  Girdinin `headers`'ı indirmeye eklenir; `headersHelper` (stdout'a JSON başlık nesnesi basan komut)
  girdinin `strict: false` olmasını ister ve çalışmadan önce gösterilip onaylanır. `headers` /
  `headersHelper` archive dışı girdide uyarı verir.
- `npm`: `package` (ad, adres ya da yerel yol), `version` (sürüm/aralık), `registry`. Paket
  `npm pack --ignore-scripts` ile indirilir (paket betikleri çalışmaz), sürüm `unknown`.
- `command`: stdout'a tek satır mutlak eklenti klasörü yolu basan kabuk komutu (≤500 yazdırılabilir
  ASCII, 4+ boşluk dizisi yok), `timeout` 1-600 sn (varsayılan 60), `mode` `copy` (kopyalanır, içerik
  karması sürümdür) ya da `link` (klasör yerinde yüklenir). Ev klasöründen çalışır.

**Pazar komutu onayı (güvenlik davranışı değişti):** command kaynağı ve headersHelper Claude Code gibi
ancak komut gösterilip onaylanınca çalışır: terminalde sorulur (reddedince `Aborted.`); `-y/--yes`
gösterilen komutu, `--accept-command <sha256>` yalnız önceki `--json` çıktısındaki
`shownCommand.sha256` özetli komutu (eklenti, komut, kip/arşiv adresi ve katalog sürümü) onaylar;
terminal yoksa ve onay verilmediyse kurulum `failureCode: command_source_refused` ve `shownCommand`
ile reddedilir. `-y` ile `--accept-command` birlikte kullanılamaz. Onaylanan komut kayıtta tutulur:
`update` aynı komutu yeniden sormaz, değişen komut yeniden onay ister. `--json` hata satırları Claude
kodlarını taşır: `not_installed`, `not_found`, `ambiguous_marketplace`, `already_in_goal_state`,
`not_installed_at_scope`, `command_source_refused`, `command_source_declined`. Claude'un `<paket>@npm`
doğrudan npm pazarı ve command kaynağının oturum başında arka planda yeniden çalıştırılması yok.

`plugin marketplace update` sonrasında pazarın `renames` haritası uygulanır (zincir en eski addan
izlenir): yeniden adlandırılan kurulum yeni girdi adıyla sürer, project/local `enabledPlugins`
anahtarı yeni ada yazılır ve `Renamed to "<yeni>" in the "<pazar>" marketplace` basılır; `null`
eşlemede anahtar düşer (`Removed from the "<pazar>" marketplace`). `forceRemoveDeletedPlugins: true`
iken girdilerde ve `renames`'te olmayan kurulum kaldırılır. Claude gibi her oturum başında (REPL
açılışında arka planda; bildirim sonraki turda basılır) ve CLI/REPL/masaüstü pazar güncellemesinden
sonra uygulanır. Yerinde yüklenen eklentinin klasörü yeni girdinin kaynağına taşınır.

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

Resmî pazar `claude-plugins-official` Claude gibi ilk etkileşimli (terminal) oturumda kendiliğinden
eklenir; sonra kaldırılırsa yeniden eklenmez. Eski `resmi` kısa adı kullanımdan kalktı uyarısıyla
`anthropics/claude-plugins-official`'a çözülür. Keşfet ağa
çıkmaz; git pazarları son ekleme/güncelleme anındaki klondan okunur (`pazar guncelle`). Aynı adlı
başka kaynaklı bir pazar eskisinin yerine geçemez.

Claude'un `workflows/` iş akışları ve `hooks.json` `modules` (mod) bileşenleri desteklenmez; bulunursa
yükleme/doğrulamada "desteklenmiyor" uyarısı verilir. Etkin eklentinin `bin/` klasörü Claude gibi
ajanın kabuk aracının (`run_shell`) PATH'ine eklenir.

**Bağımlılıklar (`dependencies`):** eklenti kurulurken `plugin.json` `dependencies` girdileri
(`"ad"`, `"ad@pazar"`, `{name, marketplace}`) aynı pazardan kendiliğinden kurulur ve açılır
("Bağımlılık kuruldu/açıldı"); başka pazardaki bağımlılık yalnız kök pazarın
`allowCrossMarketplaceDependenciesOn` listesinde o pazar varsa kurulur. Kendiliğinden kurulanlar
artık hiçbir eklentiye gerekmeyince `plugin prune` (`autoremove`, `--dry-run`) ya da
`uninstall --prune` ile kaldırılır; elle kurulan eklenti budanmaz. `version` aralığı yok sayılır
(güncel sürüm kurulur).

**Claude Code'dan farklar (Hâlâ eksik):** kurulum kayıtları ve kopyalar Fusion'ın kendi deposundadır
(`<veri>/eklentiler/kayit.json`); Claude'un `~/.claude/plugins/installed_plugins.json`'ı yalnız
okunur (#377). `--settings` bayrağı kapsamı ve `managed-settings.d` parçaları okunmaz. Bağımlılık sürüm aralıkları
(`<ad>--v<sürüm>` etiketinden çözüm), `lspServers`/`monitors`/`themes`/`channels`, `plugin eval` ve `.mcpb` paketleri yok. Kriptografik imza yok: bütünlük sha256 karma + commit
pinidir.

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
sürümle sürer; `Plugin updated: <ad> · Run /reload-plugins to apply` günlüğe yazılır ve REPL/TUI'de
sonraki turda basılır). Açık mı: önce `extraKnownMarketplaces` girdisindeki `autoUpdate`, sonra
`/plugin` Marketplaces'teki Enable/Disable auto-update anahtarının kaydı, yoksa varsayılan (Anthropic'in resmî
pazarlarında açık, `knowledge-work-plugins`/`first-party-plugins` ve diğerlerinde kapalı).
`DISABLE_UPDATES`, `DISABLE_AUTOUPDATER`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` kapatır,
`FORCE_AUTOUPDATE_PLUGINS=1` yeniden açar. Güvenlik notu: Claude'daki gibi otomatik güncelleme onay
sormaz.

## Güven ve bütünlük

- Claude Code gibi karma kilidi yoktur (güvenlik davranışı değişti, #392): kurulumda kaydedilen sha256
  karma yalnız bilgidir; kopya sonradan değişse de eklenti yüklenir. `trust`/`guven` kullanımdan
  kalktı (yalnız karma kaydını yeniler, uyarı verir).
- Eski sürümün kaydında (`kayit.json` `surum: 1`) kopyası kurulumdan sonra değişmiş eklenti yükseltmede
  bir kez kapatılır ve günlüğe `fusion plugin enable <ad>` ile açılması yazılır (eski 'değişmiş'
  kilidinin reddettiği içerik sessizce çalışmasın diye; güvenlik davranışı değişti).
- Kullanıcı kapsamında etkin eklentinin kanca ve MCP sunucuları ek onay istemeden yüklenir (#419).
  Proje kapsamında (`.claude/settings.json`) açılan eklenti yalnız o dosya güvenildiyse (`fusion
  trust`) yüklenir. Claude'daki gibi kancaları klasör güveniyle çalışır; MCP sunucuları ise projenin
  `.mcp.json`'ı gibi ayrıca onaylanır: `fusion trust` sunucu tanımlarını kaydeder, tanım sonradan
  değişirse sunucu yeniden onaylanana dek başlatılmaz. Eklenti MCP kayıtları `unreviewed` güvenle girer.
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
  Kopyalanan eklenti Claude'un kopyalama sınırını (20.000 dosya / 256 MiB) aşıyorsa reddedilir.
- Hepsini kapatma: `fusion plugin disable --all` (eski `FUSION_PLUGINS=off` uyarıyla okunur).

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
