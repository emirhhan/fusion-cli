# Talimat dosyaları ve beceriler

Fusion, Claude Code / Codex kullanıcısının alıştığı talimat ve beceri yüzeylerini aynı
dosyalardan okur; yeni bir ekosistem kurmaz. Bu belge hangi dosyanın ne zaman bağlama
girdiğini, bütçeleri ve kapatma ayarlarını anlatır.

## Talimat hiyerarşisi (Claude Code CLAUDE.md kuralları)

Tur başında şu dosyalar sırayla (genelden özele) okunur ve **birleştirilir** (biri ötekini
ezmez; çalışma dizinine yakın olan en son okunur). İçerik Claude Code'daki gibi uyulacak
talimat olarak sunulur ("Contents of <yol> (…):" başlığıyla) ve Claude Code'daki gibi sistem
isteminin içine değil, sistem isteminden **sonra ayrı bir kullanıcı mesajı** olarak verilir
(her turda aynı yerde, tek kopya); izin ve onay kuralları yine
ayarlarla (`permissions`, kancalar) zorlanır.

| Sıra | Katman | Dosyalar |
|---|---|---|
| 1 | Kurumsal | macOS `/Library/Application Support/ClaudeCode/CLAUDE.md`, Linux/WSL `/etc/claude-code/CLAUDE.md` ve `managed-settings.json` içindeki `claudeMd`. Dışlanamaz |
| 2 | Kullanıcı | `~/.claude/CLAUDE.md` (eski `~/.fusion/TALIMAT.md` bu sürüm boyunca okunur, kullanımdan kalktığı notu düşer; `~/.codex/AGENTS.md` okunmaz) |
| 3 | Proje | Dosya sistemi kökünden çalışma dizinine kadar **her dizinde** `CLAUDE.md`, `.claude/CLAUDE.md`, ardından `CLAUDE.local.md`. `monorepo/packages/web` içinde açınca `monorepo/CLAUDE.md` de yüklenir |
| 4 | Ek dizin | `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1` iken `--add-dir` dizinlerinin `CLAUDE.md`, `.claude/CLAUDE.md`, `CLAUDE.local.md` ve `.claude/rules/*.md` (`paths`'siz) dosyaları |
| — | İç içe | Alt klasördeki talimat, o klasördeki dosyaya erişince (`runtime.nested_instructions`) |

- **AGENTS.md**: varsayılan (`claude-md-or-agents-md`) — çalışma dizininde ya da üstünde hiç
  `CLAUDE.md`, `.claude/CLAUDE.md` veya `CLAUDE.local.md` yoksa (`~/.claude/CLAUDE.md` sayılmaz)
  her dizinin `AGENTS.md` ve `.claude/AGENTS.md` dosyası okunur. **Project instructions**
  ayarı `~/.claude/settings.json` (ya da kurumsal ayar) içinde
  `pluginConfigs."cc-plugin-agents-md@builtin".options.instructionFiles` ile değişir:
  `claude-md-and-agents-md`, `claude-md`, `managed-only`. `AGENTS.override.md`,
  `AGENTS.local.md`, `.agents/`, `GEMINI.md` ve `.cursorrules` okunmaz.
- Boyut: her dosya **4 MiB'a kadar bütünüyle** yüklenir; daha büyüğü hiç yüklenmez (notta
  görünür). 200 satırı aşan dosya için yalnız kısaltma önerisi düşer; birleşik sınır yoktur.
  `runtime.instruction_max_chars` artık etkisizdir.
- Çitli kod dışındaki blok HTML yorumları (`<!-- bakım notu -->`) bağlama girmeden silinir.
- `claudeMdExcludes` (settings.json; kullanıcı, proje, yerel ve kurumsal katmanlarda dizi
  olarak birleşir) mutlak yola glob olarak uygulanır; kurumsal CLAUDE.md dışlanamaz.
- Aynı içerikli iki dosya (`CLAUDE.md → AGENTS.md` sembolik bağı) **bir kez** okunur.
- Masaüstünde **Ayarlar › Kişiselleştirme › Kalıcı talimat** yüklenen dosyaları, kuralları
  (kapsamıyla) ve notları listeler (`ayar.talimat` → `katmanlar`, `notlar`).
- `runtime.instruction_merge: false` talimat yüklemesini tamamen kapatır.

## `@yol` içe aktarma

Talimat dosyasının içinde satır başında ya da boşluktan sonra `@docs/kurallar.md` yazımı o
dosyayı bağlama alır (Claude Code sözdizimi).

- Göreli yol içeren dosyaya göredir; mutlak ve `~/` yollar da olur. Uzantı kısıtı yoktur
  (`@README`, `@package.json`); ikili dosya atlanır. Boşluklu yol `\ ` ile yazılır
  (`@Design\ Docs/api.md`).
- Özyinelemeli, en çok **dört adım**; döngü korumalı; kod bloklarında (` ``` ` ve `` `…` ``)
  yok sayılır. E-posta (`ali@ornek.com`) import sayılmaz.
- Proje dosyasında çalışma dizini **dışına** çıkan import "dış"tır: proje başına bir kez onay
  gerekir (karar `dis_import_onaylari.json` dosyasında saklanır). Claude Code'daki gibi dış import
  ilk görüldüğünde dosyaları listeleyen bir onay sorusu açılır: terminalde oturum başında `[e/H]`,
  TUI'de uygulama içi seçim, masaüstünde Kişiselleştirme → Kalıcı talimat kartında "İzin ver" /
  "Reddet". Reddedilirse importlar kapalı kalır ve soru bir daha görünmez; Esc ile kapatılırsa
  (TUI) karar verilmemiş sayılır ve notta "onay bekliyor" görünür.
- Markdown bağlantıları (`[metin](RULES.md)`) izlenmez; kuralı içe almak için `@RULES.md` yaz.

## `.claude/rules/` kural dosyaları

`~/.claude/rules/**/*.md` (kullanıcı) ve projede `.claude/rules/**/*.md` özyinelemeli
keşfedilir (yalnız `.md`). Eski `.fusion/rules` kökü bu sürüm boyunca okunur, kullanımdan
kalktığı uyarısı düşer.

- `paths:` frontmatter'ı **olmayan** kurallar tur başında, CLAUDE.md gibi bütünüyle (4 MiB'a
  kadar) yüklenir; karakter bütçesi yoktur.
- `paths:` olanlar yalnız model eşleşen dosyayı okuyup/düzenleyince, o turda bir kez, iç içe
  talimat notuyla aynı mesajda gelir; dosya başı sınır 40.000 karakter, adet sınırı yoktur.
  Desenler kuralın taban dizinine (proje kökü) görelidir: `*.md` yalnız kökteki `.md`
  dosyalarına uyar, `**/*.md` her yerdekine. `[abc]` / `[!a]` köşeli ayraç ifadeleri ve
  `*.{ts,tsx}` brace açılımı geçerlidir (kural başına en çok 1.000 açılmış desen). Okunan
  frontmatter alanı yalnız `paths` (eski `yollar` uyarıyla okunur; `globs` okunmaz).
- Kök dışını gösteren proje kuralı sembolik bağı dış import gibidir: projede dış import onayı
  verilmişse yüklenir, yoksa atlanır; onay sorusunda bu bağların hedefleri de listelenir. `claudeMdExcludes` kural dosyalarına da uygulanır.
- İç içe talimat: model alt klasörde bir dosyayı okuyunca/yazınca/düzenleyince (kabukla tek
  dosyalı `cat`/`head`/`tail` okuması dahil) o klasörün `CLAUDE.md` ve `CLAUDE.local.md`'si
  birlikte, hiç Claude dosyası yoksa `AGENTS.md`'si ve o klasörün `.claude/rules/*.md` dosyaları
  (`paths` deseni o klasöre göreli) yüklenir. Dosya başı sınır 200K pencerede 40.000, 1M
  pencerede 150.000 karakter; `GEMINI.md` ve `.cursorrules` okunmaz. Nokta ile başlayan
  klasörler (`.github`) taranır; `.git`, `node_modules`, `vendor` gibi dizinler taranmaz.
- Masaüstü **Beceriler › Talimatlar** sekmesi kullanıcı katmanını, proje talimatlarını ve
  kuralları (kapsamıyla) listeler; `yetenek.detay {tur: "talimat", ad}` yalnız bu listedeki
  dosyayı okur.
- `runtime.instruction_merge: false` kuralları da kapatır.

## Beceri ve komutları slash ile çağırma: `/<beceri> argüman`

Keşfedilen her `SKILL.md` becerisi ve `.claude/commands/**/*.md` komut dosyası terminalde,
TUI'de ve masaüstü yazı kutusunda **Beceri** grubunda bir slash komutu olur
(`/help` ve `komut.listele` listeler). Claude Code gibi aynı adlı beceri yerleşik komutun
yerine geçer, takma adlarının yerine geçmez (`dev` adlı beceri `/development`'ın takma adı
`/dev`'i gölgelemez).

- `/rapor ekim` → `SKILL.md` gövdesi `$ARGUMENTS` ile şablonlanıp `<beceri>` bloğu olarak
  sıradaki turun sistem bağlamına girer; kullanıcı mesajı `ekim` (argüman yoksa
  "`rapor` becerisini bu görev için uygula.").
- `.claude/commands/git/commit.md` → `/git:commit <bağlam>`: şablonlanan gövde doğrudan görev
  metnidir. Ad yalnız dosya yolundan gelir (Claude Code gibi komut dosyasındaki `name` yok
  sayılır). Komut kökleri: `~/.claude/commands` ve projede `.claude/commands`.
  `~/.fusion/commands` ve `.fusion/commands` kullanımdan kalktı: bu sürüm boyunca okunur, ilk
  görüldüğünde uyarı düşer — dosyaları `.claude/commands` altına taşı.
- Beceri yalnız mesaj başındaki `/` ile çağrılır; eski Codex yazımı `$rapor` artık düz mesajdır.
- Şablon değişkenleri (Claude Code ile aynı): `$ARGUMENTS`, `$ARGUMENTS[N]` ve kısaltması `$N`
  (**0 tabanlı**: `$0` ilk, `$1` ikinci argüman), `arguments:` alanındaki adlar (`$issue`),
  `${CLAUDE_SKILL_DIR}`, `${CLAUDE_PROJECT_DIR}`, `${CLAUDE_SESSION_ID}`, `${CLAUDE_EFFORT}`;
  `\$` kaçışı. Hiçbir yer tutucu argüman almıyorsa argüman `ARGUMENTS: <değer>` satırı olarak
  sona eklenir. Eski `${FUSION_SKILL_DIR}`, `${FUSION_PROJECT_DIR}`, `${FUSION_SESSION_ID}` ve
  `{SKILL_DIR}` bu sürüm boyunca çalışır, kullanımdan kalktığı notu düşer.

### SKILL.md frontmatter alanları

Alan adları Claude Code'daki İngilizce adlardır. Eski Türkçe takma adlar (`izinli-araclar`,
`yasak-araclar`, `model-cagirmasin`, `kullanici-cagirabilir`, `efor`/`caba`, `baglam`, `ajan`,
`arguman-ipucu`, `ne-zaman`…) bu sürüm boyunca okunur; ilk görüldüğünde bir kez uyarı düşer.

| Alan (eski Türkçe takma ad) | Fusion'da etkisi |
|---|---|
| `description`, `when_to_use` | Arama, beceri dizini ve `/help` satırı. `description` yoksa gövdenin ilk dolu satırı kullanılır |
| `arguments` | `$ad` yerleştirmesinde konumlara sırayla eşlenen adlar (boşluklu metin ya da YAML listesi) |
| `shell` | `` !`cmd` `` ve ` ```! ` kabuğu: `bash` (varsayılan) ya da `powershell` |
| `argument-hint` / `arguman-ipucu` | `/help` ve tamamlamada `/ad [ipucu]` |
| `allowed-tools` / `izinli-araclar` | Claude Code ile aynı: beceri etkinken listedeki araçlar ve desenler (`Bash(git add *)`, `Read`) **onay sorulmadan** kullanılır; diğer araçlar kaldırılmaz, olağan izin akışına kalır. Virgül **veya** boşlukla ayrılır. Ön onay kullanıcının sonraki mesajında kalkar; kullanıcının `deny`/`ask` kuralı becerinin ön onayını yener. Depo kaynaklı (proje) beceride ön onay yalnız `fusion trust` ile güvenilen projede geçerlidir (güvenlik davranışı değişti, #142) |
| `disable-model-invocation` / `model-cagirmasin` | Beceri dizinine ve `find_skill` sonucuna girmez; yalnız `/ad` ile |
| `user-invocable: false` | Slash komutu olarak sunulmaz (yalnız model `Skill` aracıyla) |
| `context: fork` / `baglam` | Claude Code ile aynı: beceri alt ajanda koşar ve alt ajan konuşma geçmişini **görmez** (gövde kendi başına yetmeli); ana konuşmaya yalnız sonuç eklenir. Model `Skill` ile çağırınca da aynı. Etkileşimli oturumda fork varsayılan olarak arka planda koşar (`background: true`), sonuç tamamlanınca konuşmaya gelir; `background: false` turda bekletir; etkileşimsiz kipte (`-p`) ve arka plan görevleri kapalıyken her zaman beklenir. `model`/`effort` fork'ta alt ajanın modelini/eforunu belirler |
| `agent` / `ajan` | `context: fork` ile: fork'u bu alt ajan tanımı (`.claude/agents/<ad>.md`) koşar; fork yoksa yok sayılır, not düşer |
| `model` | **Yalnız o tur** bu modelle koşar (`<sağlayıcı>/<model>`, ör. `openrouter/qwen/qwen3-coder`); oturum modeli ve yedekleri zincirde yedek kalır, `task_model_map` o tur uygulanmaz. `sonnet`, `opus`, `haiku` gibi kısa adlar Claude Code'daki gibi o modele geçirir (eşleme: `agent_launch.model_aliases` ya da `ANTHROPIC_DEFAULT_<AD>_MODEL`); eşleme yoksa ve `inherit`te oturum modeli kullanılır; başka biçim not düşer. Model beceriyi `Skill` aracıyla tur ortasında çağırırsa model/efor turun **kalanına** uygulanır; sonraki kullanıcı mesajında oturum seçimine dönülür. Sonraki tur oturum seçimine döner. Depo kaynaklı (proje) becerinin modeli yalnız `fusion trust` ile güvenilen projede uygulanır; değilse not düşer, efor yine uygulanır |
| `effort` / `efor` | **Yalnız o tur** düşünme yoğunluğu (`low`…`max`, `auto`); tanınmayan değer not düşer |
| `disallowed-tools` / `yasak-araclar` | Claude Code: "Tools removed from Claude's available pool while this skill is active"; kullanıcının sonraki mesajında kalkar. `/ad` turunda araç sunulmaz; model `Skill` ile tur ortasında çağırınca aynı araçlar `deny` kuralıyla düşer. `Bash(rm *)` deseninde aracın tamamı yasaklanır (belge desen anlamı tanımlamıyor; güvenli taraf) |
| `paths` | Claude Code ile aynı: glob desenleri (virgüllü metin ya da YAML liste, çalışma dizinine göreli, yola özel kurallarla aynı biçim). Beceri, model eşleşen bir dosyaya erişene kadar beceri listesine girmez; erişimde etkinleşir, listeye katılır ve kısa bir duyuru düşer. Çalışma dizini dışındaki dosya eşleşmez |
| `background` | Yalnız `context: fork` ile: `false` fork sonucunu turda bekletir; varsayılan `true` (arka plan) |
| `hooks` | Claude Code'daki gibi beceri çağrıldığında (`/ad` ya da `Skill` aracı) oturumun kancalarına kaydedilir ve oturum boyunca çalışır; aynı beceri ikinci kez çağrılınca çiftlenmez, `/clear` kayıtları siler. Depo kaynaklı becerinin kancası yalnız güvenilen projede kaydedilir; `disableAllHooks` beceri kancalarını da kapatır. |
| Gövdede `` !`cmd` `` ve ` ```! ` bloğu | Claude Code kuralları: satır içi biçim yalnız `!` satır başında ya da boşluktan sonra gelirse tanınır (`KEY=!`cmd`` düz metin kalır); çok satırlı komut ` ```! ` çitiyle yazılır; çıktı yeniden taranmaz. Komut hiç onay sormaz, izin kurallarıyla denetlenir: `deny` eşleşmesi ya da (izinli kip dışında) `allow` olmayan karar **çağrının tamamını iptal eder** (`Shell command permission check failed for pattern "…"`); `allowed-tools` içindeki `Bash(…)` deseni ön onaydır. Sıfır olmayan çıkış kodu da çağrıyı iptal eder (arama/karşılaştırma komutlarının 1 kodu hariç). Zaman aşımı 2 dakika. `disableSkillShellExecution: true` (settings.json) her komutu `[shell command execution disabled by policy]` ile değiştirir (yerleşik/kurumsal beceriler hariç). Fusion'ın ek güvencesi: açık kural olmadan `auto`/`edits`/`bypass` kipinde koşan komut `run_shell` tehlike/risk denetiminden geçer, proje becerisinde yalnız salt-okur komut koşar; çıktı 2.000 karakter, sırlar maskeli |

### Tek mesajda beceri yığma

Claude Code'daki gibi mesaj başında birden çok beceri yığılabilir: `/testler /duzelt 123` iki
beceriyi aynı turda açar ve kalan metin (`123`) ikisine de `$ARGUMENTS` olur. İlk beceriden sonra
en çok beş beceri daha açılır; açılım satır içi (fork olmayan), kullanıcının çağırabileceği beceri
olmayan ilk belirteçte durur, o belirteç ve sonrası argümandır. `context: fork` becerisi yığına
girmez. Yığılan her becerinin gövdesi sonraki turlarda da bağlamda kalır.

## Beceri listesi (Claude Code listeleme kuralları)

Kök turda sistem bağlamına **BECERİ DİZİNİ** bloğu girer: beceri başına `ad — açıklama`,
keşif sırasıyla, **tek düz liste** (proje becerileri ayrı blokta ya da güvenilmezlik notuyla
işaretlenmez). Model uygun beceriyi aramadan tanır ve Claude Code'daki gibi `Skill(skill, args)` aracıyla çağırır: gövde kullanıcının `/ad` çağrısıyla aynı yoldan işlenir (argümanlar, `!`cmd``, `allowed-tools` ön onayı, `disallowed-tools`), sonuç araç çıktısı olarak konuşmada kalır; `context: fork` becerisi geçmişsiz alt ajanda koşar ve sonucunu döner. `read_skill` ek dosyalar ve sayfalı okuma için kalır. Kullanıcının `/ad` ile çağırdığı becerinin gövdesi Claude Code'daki gibi sonraki turlarda da bağlamda kalır: sohbet başına her becerinin son çağrısı her turun bağlamına yeniden konur (beceri başına ilk 5.000 token, toplam 25.000 token, en yeni önce), geçmiş sıkıştırılsa da kaybolmaz; `/clear` ve başka sohbete geçiş sıfırlar.

- Listede **her beceri adı her zaman** bulunur. Bütçe model penceresinin **%1**'idir
  (`skillListingBudgetFraction`, settings.json); `SLASH_COMMAND_TOOL_CHAR_BUDGET` ortam
  değişkeni bütçeyi karakter olarak sabitler. Bütçe aşılınca açıklamalar düşer, adlar kalır.
  Claude Code'daki gibi en az çağrılan becerinin açıklaması önce düşer (çağrı sayıları
  `/ad` ve `Skill` çağrılarından `beceri_cagrilari.json`'da tutulur; eşitlikte listenin sonundan).
- Giriş başına açıklama (`description` + `when_to_use`) 1.536 karakterde kesilir
  (`skillListingMaxDescChars`).
- Pencere bilinmiyorsa `runtime.skill_index_chars` (4.000) kullanılır; `0` listeyi kapatır.
- `disable-model-invocation: true` olan beceriler listede ve `find_skill` sonucunda
  görünmez; yalnız `/ad` ile çağrılır.
- Liste her turda yeniden kurulur; bağlam sıkıştırması listeyi düşürmez.

## Beceri keşif kökleri

Claude Code ile aynı öncelik sırası (aynı adda ilk bulunan kazanır): kurumsal (yönetilen dizinin
`.claude/skills`'i, ör. macOS'ta `/Library/Application Support/ClaudeCode/.claude/skills`),
`~/.claude/skills`, proje `.claude/skills` ve depo köküne kadar üst dizinlerinki, iç içe
dizinler, eklentiler (yalnız etkin eklentiler, `eklenti:ad` adıyla; `~/.claude/plugins` önbellekleri
ham taranmaz). **Kullanımdan kalktı:** `.fusion/skills`, `.agents/skills`, `~/.codex/skills`,
`~/.agents/skills` ve `~/.hermes/skills` Claude Code'da okunmaz; bu sürüm boyunca okunur ve kök
başına bir kez uyarı loglanır, becerileri `~/.claude/skills` ya da `.claude/skills` altına taşı.
`--add-dir` / `/add-dir` ile açılan her kökün
`.claude/skills`, `.agents/skills`, `.fusion/skills` ve `.claude/agents` dizinleri ("ek-kok");
`fusion yetenek kur` repoları; yerleşik beceriler en sonda. Komut dosyaları için
`~/.claude/commands`, `~/.fusion/commands`, proje `.claude/commands`, `.fusion/commands`.

**Üst dizinler:** Claude Code'daki gibi başlangıç dizininin üstlerinden depo köküne (`.git`
olan dizin, dahil) kadar her dizinin `.claude/skills`'i oturum başında yüklenir;
`packages/frontend`'de açınca kökün becerileri de gelir. Depo dışında üst dizin taranmaz.

**Monorepo alt paketleri (tembel keşif):** model alt klasördeki bir dosyayı okuyunca ya da
düzenleyince (iç içe talimatların yüklendiği an), o klasörden köke kadar (kök hariç)
`<alt>/.claude/skills` ve `<alt>/.agents/skills` dizinleri kataloğa eklenir ve yeni beceriler
modele tek satırlık bir notla duyurulur (`ad (yol) — açıklama`, en fazla 12). Bunlar "proje"
kaynağıdır: depo içeriği bloğunda listelenir, `` !`cmd` `` yalnız salt-okur koşar. Aynı adda
kök becerisi varsa ikisi de kalır: `/deploy` kök beceriyi, `/apps/web:deploy` iç içe olanı
çalıştırır ve açıklaması uygulandığı dizini söyler; `node_modules`, `dist`, gizli klasörler taranmaz.
Keşfedilen beceri REPL'de `/ad` olarak da çağrılabilir; masaüstü yetenek kataloğunda da listelenir ve katalog yenilense ya da `/config capabilities.*` değişse de oturum boyunca korunur. `runtime.nested_instructions: false`
bu keşfi de kapatır.

## Katalog yaşam döngüsü

| Yüzey | Ne yapar |
|---|---|
| `/reload-skills` · `/skills reload` · masaüstü **Yenile** · `yetenek.yenile` | Beceri ve komut dizinlerini yeniden tarar; `/reload-skills` eklenen/çıkarılan sayısını söyler. Claude Code gibi var olan bir SKILL.md'nin ya da komut dosyasının düzenlenmesi, klasör ekleme/silme de bir sonraki sorguda **kendiliğinden** algılanır. |
| `/skills doctor`, `/skill-doctor` · masaüstü **Teşhis** · `yetenek.teshis` | Eksik `description`, ön maddesiz dosya, aynı adın birden çok kaynakta farklı içerikle bulunması (kazanan/gölgelenen), tek sayfaya sığmayan gövde, ev dizini dışına çıkan sembolik bağ. |
| `/skills new <ad>` · `/agents new <ad>` | Modele `.claude/skills/<ad>/SKILL.md` ya da `.claude/agents/<ad>.md` yazdırır; önce `ask_user` ile kapsam ve araç kısıtını sorar, mevcut dosyanın üzerine yazmaz. |
| `/agents` | Güncel Claude Code gibi yalnız hatırlatma basar: Fusion'a sor ya da `.claude/agents/` ve `~/.claude/agents/` dosyalarını düzenle. Eski `/agents <arama>` ve `/agents new <ad>` biçimleri bir sürüm boyunca çalışır. |
| `capabilities.disabled: [ad, ad@kaynak:kimlik]` (config.yaml) | Her oturumda kapalı tutulan beceri/ajanlar; masaüstündeki oturumluk kapatmayla birleşir. |
| `skillOverrides: {ad: görünürlük}` (`settings.json` katmanları, Claude Code ile aynı; eklenti becerilerini etkilemez) ve eski `capabilities.overrides` (config.yaml; ikisi birden varsa `skillOverrides` kazanır) | Beceri başına görünürlük: `on` (olağan), `name-only` / `yalniz-ad` (dizinde yalnız ad, açıklama bağlam harcamaz), `user-invocable-only` / `yalniz-kullanici` (model dizinde ve `find_skill`'de görmez, `read_skill` gövdeyi reddeder; yalnız `/ad` ile — ek dosyaları `read_skill(file=…)` ile okunabilir; aynı kural `disable-model-invocation: true` için de geçerli), `off` / `kapali`. Anahtar düz ad ya da `ad@kaynak:kimlik` (nitelikli kimlik önce gelir). Masaüstü kataloğunda ayrıntıda "Görünürlük" satırı görünür; `off` öğe kapalı listelenir. |

## `/init` ve `/doctor prompt`

- `/init [claude|agents]` (REPL, TUI, masaüstü komut paleti) ve terminalde `fusion init
  [--format claude|agents] [--mode edits]`: Claude Code `/init` ile aynı — model kod tabanını
  inceleyip kökte `CLAUDE.md` (varsayılan; `agents` ile `AGENTS.md`) yazar: derleme/test/lint
  komutları, büyük resim mimarisi, depoya özgü kurallar; sabit bölüm ya da karakter sınırı yok.
  Fusion depodan ölçtüğü olguları (proje türü, keşfedilen komutlar, mevcut talimat dosyaları)
  göreve ekler. `.cursor/rules`, `.cursorrules`, `.github/copilot-instructions.md` varsa içeriği
  katılır; `AGENTS.md`/`.codex`/`GEMINI.md` bulunursa `/import codex|gemini` önerilir.
  `CLAUDE_CODE_NEW_INIT=1` çok aşamalı akışı açar (yapıt seçimi, alt ajanla inceleme, eksikleri
  sorma, yazmadan önce öneriyi gösterme). Dosya zaten varsa üzerine yazmaz, iyileştirme önerir.
- `/doctor prompt` (argümansız `/doctor` da aynı rapor + `fusion doctor` hatırlatması):
  yüklenen katmanlar ve karakterleri, kırpılan miktar, kök dışı import notları, depo
  talimatında onay/izin kurallarını değiştirmeye ya da sır sızdırmaya çalışan şüpheli satırlar
  ("onay sorma", "bypass", "ignore previous rules", "print the API key"… — "sırları commit
  etme" gibi zararsız güvenlik kuralları işaretlenmez; Fusion şüpheli satırları uygulamaz,
  dosyanın kaynağını gözden geçir), öneriler (talimat yoksa `/init`, bütçenin %70'i dolduysa
  kısalt, doğrulama komutu yoksa `## Doğrulama` bölümü).
- Masaüstü **Ayarlar › Kişiselleştirme › Kalıcı talimat**: öneriler listelenir; **Talimat
  oluştur (/init)** ve **Talimatı denetle** düğmeleri aynı komutları çalıştırır
  (`ayar.talimat` → `oneriler`, `supheli`).
