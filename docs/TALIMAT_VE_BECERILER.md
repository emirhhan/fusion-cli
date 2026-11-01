# Talimat dosyaları ve beceriler

Fusion, Claude Code / Codex kullanıcısının alıştığı talimat ve beceri yüzeylerini aynı
dosyalardan okur; yeni bir ekosistem kurmaz. Bu belge hangi dosyanın ne zaman bağlama
girdiğini, bütçeleri ve kapatma ayarlarını anlatır.

## Talimat hiyerarşisi (Claude Code CLAUDE.md kuralları)

Tur başında şu dosyalar sırayla (genelden özele) okunur ve **birleştirilir** (biri ötekini
ezmez; çalışma dizinine yakın olan en son okunur). İçerik Claude Code'daki gibi uyulacak
talimat olarak sunulur ("Contents of <yol> (…):" başlığıyla); izin ve onay kuralları yine
ayarlarla (`permissions`, kancalar) zorlanır.

| Sıra | Katman | Dosyalar |
|---|---|---|
| 1 | Kurumsal | macOS `/Library/Application Support/ClaudeCode/CLAUDE.md`, Linux/WSL `/etc/claude-code/CLAUDE.md` ve `managed-settings.json` içindeki `claudeMd`. Dışlanamaz |
| 2 | Kullanıcı | `~/.claude/CLAUDE.md` (eski `~/.fusion/TALIMAT.md` bu sürüm boyunca okunur, kullanımdan kalktığı notu düşer; `~/.codex/AGENTS.md` okunmaz) |
| 3 | Proje | Dosya sistemi kökünden çalışma dizinine kadar **her dizinde** `CLAUDE.md`, `.claude/CLAUDE.md`, ardından `CLAUDE.local.md`. `monorepo/packages/web` içinde açınca `monorepo/CLAUDE.md` de yüklenir |
| 4 | Ek dizin | `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1` iken `--add-dir` dizinlerinin `CLAUDE.md`, `.claude/CLAUDE.md`, `CLAUDE.local.md` dosyaları |
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
  gerekir (karar `dis_import_onaylari.json` dosyasında saklanır). Karar verilmemişse yüklenmez
  ve notta "onay bekliyor" görünür; reddedilirse kapalı kalır.
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
  verilmişse yüklenir, yoksa atlanır. `claudeMdExcludes` kural dosyalarına da uygulanır.
- İç içe talimat: alt klasördeki `CLAUDE.md` ve `CLAUDE.local.md` birlikte, o klasörde hiç
  Claude dosyası yoksa `AGENTS.md` okunur (dosya başı 40.000 karakter; `GEMINI.md` ve
  `.cursorrules` okunmaz). `node_modules`/`vendor` gibi dizinler taranmaz.
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
| `allowed-tools` / `izinli-araclar` | O turda yalnız bu araçlar sunulur; virgül **veya** boşlukla ayrılır (`Read, Grep` ve `Read Grep`), `Bash(git add:*, git commit:*)` tek öğedir — araç adı eşlenir, komut deseni uygulanmaz (not düşer). Fusion aracına eşlenmeyen adlar (`TodoWrite`, `Skill`…) yok sayılır; hiçbiri eşlenmezse kısıt uygulanmaz ve not düşer. **Claude Code'dan fark:** Claude Code bu alanı "onaysız kullanılabilir" (ön-onay) sayar ve diğer araçları kaldırmaz; Fusion ise araç listesini **daraltır**. Gerekçe: depo dosyasından gelen bir alanın onay kapısını açması yetki yükseltme yoluydu; daraltma güvenli taraftır. Becerinin düzenleme/kabuk gerektiren adımı varsa alana `Edit`, `Bash` ekle ya da alanı hiç yazma |
| `disable-model-invocation` / `model-cagirmasin` | Beceri dizinine ve `find_skill` sonucuna girmez; yalnız `/ad` ile |
| `user-invocable: false` | Slash komutu olarak sunulmaz (yalnız model `read_skill` ile) |
| `context: fork` / `baglam` | Tur, ana konuşmayı devralan fork alt ajanda koşar (`/subtask` gibi); beceri gövdesi brife, `allowed-tools` araç tavanına geçer |
| `agent` / `ajan` | `context: fork` ile: fork'u bu alt ajan tanımı (`.claude/agents/<ad>.md`) koşar; fork yoksa yok sayılır, not düşer |
| `model` | **Yalnız o tur** bu modelle koşar (`<sağlayıcı>/<model>`, ör. `openrouter/qwen/qwen3-coder`); oturum modeli ve yedekleri zincirde yedek kalır, `task_model_map` o tur uygulanmaz. `inherit`, `sonnet`, `opus`, `haiku` oturum modelini kullanır; başka biçim not düşer. Sonraki tur oturum seçimine döner. Depo kaynaklı (proje) becerinin modeli yalnız `fusion trust` ile güvenilen projede uygulanır; değilse not düşer, efor yine uygulanır |
| `effort` / `efor` | **Yalnız o tur** düşünme yoğunluğu (`low`…`max`, `auto`); tanınmayan değer not düşer |
| `disallowed-tools` / `yasak-araclar` | O turda bu araçlar sunulmaz (kişiliğin yasaklarına eklenir, kaldıramaz); `Bash(rm *)` deseninde aracın tamamı yasaklanır (güvenli taraf) |
| `hooks` | Okunur, beceri kapsamlı kanca olarak uygulanmaz (kancalar `settings.json` ile) |
| Gövdede `` !`cmd` `` ve ` ```! ` bloğu | Claude Code kuralları: satır içi biçim yalnız `!` satır başında ya da boşluktan sonra gelirse tanınır (`KEY=!`cmd`` düz metin kalır); çok satırlı komut ` ```! ` çitiyle yazılır; çıktı yeniden taranmaz. Komut hiç onay sormaz, izin kurallarıyla denetlenir: `deny` eşleşmesi ya da (izinli kip dışında) `allow` olmayan karar **çağrının tamamını iptal eder** (`Shell command permission check failed for pattern "…"`); `allowed-tools` içindeki `Bash(…)` deseni ön onaydır. Sıfır olmayan çıkış kodu da çağrıyı iptal eder (arama/karşılaştırma komutlarının 1 kodu hariç). Zaman aşımı 2 dakika. `disableSkillShellExecution: true` (settings.json) her komutu `[shell command execution disabled by policy]` ile değiştirir (yerleşik/kurumsal beceriler hariç). Fusion'ın ek güvencesi: açık kural olmadan `auto`/`edits`/`bypass` kipinde koşan komut `run_shell` tehlike/risk denetiminden geçer, proje becerisinde yalnız salt-okur komut koşar; çıktı 2.000 karakter, sırlar maskeli |

## Beceri listesi (Claude Code listeleme kuralları)

Kök turda sistem bağlamına **BECERİ DİZİNİ** bloğu girer: beceri başına `ad — açıklama`,
keşif sırasıyla, **tek düz liste** (proje becerileri ayrı blokta ya da güvenilmezlik notuyla
işaretlenmez). Model uygun beceriyi aramadan tanır ve `read_skill('<ad>')` ile gövdeyi yükler.

- Listede **her beceri adı her zaman** bulunur. Bütçe model penceresinin **%1**'idir
  (`skillListingBudgetFraction`, settings.json); `SLASH_COMMAND_TOOL_CHAR_BUDGET` ortam
  değişkeni bütçeyi karakter olarak sabitler. Bütçe aşılınca açıklamalar düşer, adlar kalır.
  Claude az çağrılan becerinin açıklamasını önce düşürür; Fusion çağrı sayısı tutmadığı için
  en düşük öncelikli kaynaktan (listenin sonundan) başlar.
- Giriş başına açıklama (`description` + `when_to_use`) 1.536 karakterde kesilir
  (`skillListingMaxDescChars`).
- Pencere bilinmiyorsa `runtime.skill_index_chars` (4.000) kullanılır; `0` listeyi kapatır.
- `disable-model-invocation: true` olan beceriler listede ve `find_skill` sonucunda
  görünmez; yalnız `/ad` ile çağrılır.
- Liste her turda yeniden kurulur; bağlam sıkıştırması listeyi düşürmez.

## Beceri keşif kökleri

Öncelik sırasıyla (aynı adda ilk bulunan kazanır): `~/.claude/skills`, `~/.claude/plugins`,
proje `.claude/skills`, `.fusion/skills`, `.agents/skills`; `~/.codex/skills`, `~/.agents/skills`
(Codex/ChatGPT açık standardı); `~/.hermes/skills`; `--add-dir` / `/add-dir` ile açılan her kökün
`.claude/skills`, `.agents/skills`, `.fusion/skills` ve `.claude/agents` dizinleri ("ek-kok");
`fusion yetenek kur` repoları; yerleşik beceriler en sonda. Komut dosyaları için
`~/.claude/commands`, `~/.fusion/commands`, proje `.claude/commands`, `.fusion/commands`.

**Monorepo alt paketleri (tembel keşif):** model alt klasördeki bir dosyayı okuyunca ya da
düzenleyince (iç içe talimatların yüklendiği an), o klasörden köke kadar (kök hariç)
`<alt>/.claude/skills` ve `<alt>/.agents/skills` dizinleri kataloğa eklenir ve yeni beceriler
modele tek satırlık bir notla duyurulur (`ad (yol) — açıklama`, en fazla 12). Bunlar "proje"
kaynağıdır: depo içeriği bloğunda listelenir, `` !`cmd` `` yalnız salt-okur koşar. Aynı adda
kök/kullanıcı becerisi varsa o kazanır; `node_modules`, `dist`, gizli klasörler taranmaz.
Keşfedilen beceri REPL'de `/ad` olarak da çağrılabilir; masaüstü yetenek kataloğunda da listelenir ve katalog yenilense ya da `/config capabilities.*` değişse de oturum boyunca korunur. `runtime.nested_instructions: false`
bu keşfi de kapatır.

## Katalog yaşam döngüsü

| Yüzey | Ne yapar |
|---|---|
| `/skills reload` (`yenile`) · masaüstü **Yenile** · `yetenek.yenile` | Kataloğu diskten yeniden tarar. Yeni klasör eklenip silindiğinde kök dizinin mtime'ı değiştiği için bir sonraki turda **kendiliğinden** yenilenir; var olan bir SKILL.md'nin içeriği değiştiyse `reload` gerekir. |
| `/skills doctor`, `/skill-doctor` · masaüstü **Teşhis** · `yetenek.teshis` | Eksik `description`, ön maddesiz dosya, aynı adın birden çok kaynakta farklı içerikle bulunması (kazanan/gölgelenen), tek sayfaya sığmayan gövde, ev dizini dışına çıkan sembolik bağ. |
| `/skills new <ad>` · `/agents new <ad>` | Modele `.claude/skills/<ad>/SKILL.md` ya da `.claude/agents/<ad>.md` yazdırır; önce `ask_user` ile kapsam ve araç kısıtını sorar, mevcut dosyanın üzerine yazmaz. |
| `/agents` | Güncel Claude Code gibi yalnız hatırlatma basar: Fusion'a sor ya da `.claude/agents/` ve `~/.claude/agents/` dosyalarını düzenle. Eski `/agents <arama>` ve `/agents new <ad>` biçimleri bir sürüm boyunca çalışır. |
| `capabilities.disabled: [ad, ad@kaynak:kimlik]` (config.yaml) | Her oturumda kapalı tutulan beceri/ajanlar; masaüstündeki oturumluk kapatmayla birleşir. |
| `capabilities.overrides: {ad: görünürlük}` (config.yaml; Claude Code `skillOverrides`) | Beceri başına görünürlük: `on` (olağan), `name-only` / `yalniz-ad` (dizinde yalnız ad, açıklama bağlam harcamaz), `user-invocable-only` / `yalniz-kullanici` (model dizinde ve `find_skill`'de görmez, `read_skill` gövdeyi reddeder; yalnız `/ad` ile — ek dosyaları `read_skill(file=…)` ile okunabilir; aynı kural `disable-model-invocation: true` için de geçerli), `off` / `kapali`. Anahtar düz ad ya da `ad@kaynak:kimlik` (nitelikli kimlik önce gelir). Masaüstü kataloğunda ayrıntıda "Görünürlük" satırı görünür; `off` öğe kapalı listelenir. |

## `/init` ve `/doctor prompt`

- `/init [agents|claude]` (REPL, TUI, masaüstü komut paleti) ve terminalde `fusion init
  [--format agents|claude] [--mode edits]`: Fusion depodan ölçtüğü olguları (proje türü,
  keşfedilen lint/test komutları, mevcut talimat dosyaları) göreve koyar; model depoyu inceleyip
  `AGENTS.md` (varsayılan) ya da `CLAUDE.md` yazar — bölümler: Proje, Kurulum ve çalıştırma,
  Doğrulama, Kod kuralları, Dikkat; 3.000 karakter sınırı, uzun kurallar `@docs/…md` ile.
  Dosya zaten varsa üzerine yazmaz; eksik bölümleri `ask_user` ile sorar.
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
