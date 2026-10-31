# Talimat dosyaları ve beceriler

Fusion, Claude Code / Codex kullanıcısının alıştığı talimat ve beceri yüzeylerini aynı
dosyalardan okur; yeni bir ekosistem kurmaz. Bu belge hangi dosyanın ne zaman bağlama
girdiğini, bütçeleri ve kapatma ayarlarını anlatır.

## Talimat hiyerarşisi (`runtime.instruction_merge`)

Tur başında şu katmanlar sırayla okunur ve sistem bağlamına eklenir; çakışmada projeye
**daha yakın olan** kazanır (Claude Code ile aynı sıra):

| Katman | Dosyalar | Etiket | Güven |
|---|---|---|---|
| Kullanıcı | `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.override.md` (yoksa `AGENTS.md`), `~/.fusion/TALIMAT.md` | `<kullanici_talimati>` | Güvenilir (senin dosyan) |
| Proje | `CLAUDE.md` + `.claude/CLAUDE.md` (Claude ailesi) **veya** `AGENTS.override.md`/`AGENTS.md` **veya** `GEMINI.md` **veya** `.cursorrules` — ilk dolu aile; artı her zaman `CLAUDE.local.md` | `<proje_talimati>` | Depo içeriği: izin/onay kurallarını değiştiremez |
| İç içe | Alt klasördeki `CLAUDE.md`/`AGENTS.md`, o klasördeki dosyaya erişince (`runtime.nested_instructions`) | `<alt_talimat>` | Depo içeriği |

- `CLAUDE.md → AGENTS.md` sembolik bağı ya da aynı içerikli iki dosya **bir kez** okunur.
  Proje kökündeki talimat dosyası kök **dışına** çıkan bir sembolik bağsa (`.claude/CLAUDE.md
  -> ~/.ssh/id_rsa`) hiç açılmaz, notta görünür.
- Bütçe: dosya başına 8.000, toplam `runtime.instruction_max_chars` (32.000) karakter.
  Kullanıcı katmanı (ev dizini dosyaları + import'ları) toplamın en çok **%40**'ını alır;
  kalan proje katmanına kalır — proje talimatı hiçbir zaman aç kalmaz. Kırpma sessiz
  değildir: metne `[…kırpıldı…]` notu düşer, kırpılan miktar gerçek kayıptır (dosyanın
  kalanı sayılır); bütçe yüzünden hiç okunmayan dosya için bağlama `[talimat atlandı: …]`
  satırı konur. Masaüstünde **Ayarlar › Kişiselleştirme › Kalıcı talimat** altında yüklenen
  dosyalar, kurallar (kapsamıyla), karakter ve kırpılan miktar listelenir (`ayar.talimat` →
  `katmanlar`, `notlar`).
- `runtime.instruction_merge: false` eski davranışa döner: yalnız kökteki ilk bilinen dosya.
- **Claude Code'dan fark:** Claude Code ve Codex çalışma dizininin ÜST klasörlerindeki
  talimatı da yükler (monorepo kökü → alt paket). Fusion yalnız çalışma kökünü ve altındaki iç
  içe dosyaları okur; `monorepo/packages/web` içinde açıldığında `monorepo/CLAUDE.md`
  yüklenmez. Üst klasör kuralı gerekiyorsa alt paketin talimatına `@../../CLAUDE.md` yazmak
  da işe yaramaz (kök dışı import atlanır); Fusion'ı monorepo kökünde aç ya da ilgili kuralı
  alt pakete kopyala.

## `@yol` içe aktarma

Talimat dosyasının içinde satır başında ya da boşluktan sonra `@docs/kurallar.md` yazımı o
dosyayı bağlama alır (Claude Code sözdizimi).

- Özyinelemeli, en fazla 3 seviye; döngü korumalı; toplam 6.000 karakter.
- Kod bloklarında (` ``` ` ve `` `…` ``) yok sayılır.
- Proje katmanında yalnız **kök içindeki** yollar; `..` ile dışarı çıkan ya da `~/` yol
  atlanır ve `ayar.talimat` notlarında görünür. Kullanıcı katmanında `~/.claude/ortak.md`
  gibi ev dizini yolları izinlidir.
- Yalnız düz metin uzantıları (`.md .mdc .markdown .txt .rst`) okunur; `.env` gibi dosyalar hiç
  açılmaz. E-posta (`ali@ornek.com`) ve paket adı (`@anthropic-ai/sdk`) import sayılmaz.
- Eski `[metin](RULES.md)` Markdown bağlantıları da bir seviye izlenmeye devam eder.

## `.claude/rules/` kural dosyaları

`~/.claude/rules/**/*.md` (kullanıcı, güvenilir) ve projede `.claude/rules/**/*.md`,
`.fusion/rules/**/*.md` (`.mdc` de olur) özyinelemeli keşfedilir.

- `paths:` frontmatter'ı **olmayan** kurallar tur başında yüklenir (toplam 8.000 karakter;
  aşım notla bildirilir).
- `paths:` olanlar (`src/**/*.tsx`, `*.css`, `docs/`, `*.{ts,tsx}`, `.github/**`, `.*rc`)
  yalnız model eşleşen dosyayı okuyup/düzenleyince, o turda bir kez, iç içe talimat notuyla
  aynı mesajda gelir. Dizin içermeyen desen dosya adına da uygulanır. Bir erişimde en çok
  **6 kural / 8.000 karakter** eklenir; sığmayanlar `[…N kural atlandı…]` notuyla bildirilir
  ve sonraki erişimde gelir.
- Kök dışına çıkan sembolik bağ hiç açılmaz; `node_modules`/`vendor` gibi dizinler taranmaz.
- Masaüstü **Beceriler › Talimatlar** sekmesi kullanıcı katmanını, proje talimatlarını ve
  kuralları (kapsamıyla) listeler; `yetenek.detay {tur: "talimat", ad}` yalnız bu listedeki
  dosyayı okur.
- `runtime.instruction_merge: false` kuralları da kapatır.

## Beceri ve komutları slash ile çağırma: `/<beceri> argüman`

Keşfedilen her `SKILL.md` becerisi ve `.claude/commands/**/*.md` komut dosyası terminalde,
TUI'de ve masaüstü yazı kutusunda **Beceri** grubunda bir slash komutu olur
(`/help` ve `komut.listele` listeler; yerleşik bir komutla ad çakışırsa yerleşik kazanır).

- `/rapor ekim` → `SKILL.md` gövdesi `$ARGUMENTS` ile şablonlanıp `<beceri>` bloğu olarak
  sıradaki turun sistem bağlamına girer; kullanıcı mesajı `ekim` (argüman yoksa
  "`rapor` becerisini bu görev için uygula.").
- `.claude/commands/git/commit.md` → `/git:commit <bağlam>`: şablonlanan gövde doğrudan görev
  metnidir. Komut kökleri: `~/.claude/commands`, `~/.fusion/commands`, projede
  `.claude/commands`, `.fusion/commands`.
- Codex yazımı `$rapor ekim` de aynı yola gider (`@beceri` dosya anmasıyla çakıştığı için
  desteklenmez).
- Şablon değişkenleri: `$ARGUMENTS`, `$ARGUMENTS[0]`, `$1 $2 …`, `${FUSION_SKILL_DIR}`
  (`${CLAUDE_SKILL_DIR}`), `${FUSION_PROJECT_DIR}`, `${FUSION_SESSION_ID}`; `\$` kaçışı. Yer
  tutucu yoksa argüman `ARGÜMANLAR:` satırı olarak sona eklenir.

### SKILL.md frontmatter alanları

| Alan (İngilizce / Türkçe) | Fusion'da etkisi |
|---|---|
| `description`, `when_to_use` | Arama, beceri dizini ve `/help` satırı |
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
| Gövdede `` !`cmd` `` | Komut çıktısı yüklenmeden önce yerleştirilir: yalnız `auto`/`edits`/`bypass` kipinde ve `~/.claude`, `~/.codex`, `~/.hermes`, yerleşik köklerden (tam yetki) ya da `fusion trust` ile güvenilen projeden/ek kökten (**yalnız salt-okur komut**: `git log`, `ls`, `cat`…); her komut `run_shell` ile aynı tehlike/risk denetiminden geçer (`git push --force`, `sudo`, proje dışına yazma… hiç koşmaz, yerinde `[komut çalıştırılmadı]` notu kalır); çıktı 2.000 karakter, sırlar maskeli, 10 sn |

## Beceri dizini (`runtime.skill_index_chars`)

Kök turda sistem bağlamına **BECERİ DİZİNİ** bloğu girer: beceri başına `ad — açıklama`
(ilk 150 karakter), keşif sırasıyla (kullanıcı kökleri → proje → Codex/Hermes → kurulu →
yerleşik). Model uygun beceriyi aramadan tanır ve `read_skill('<ad>')` ile gövdeyi yükler;
gövde hiçbir zaman önden basılmaz (progressive disclosure).

- Bütçe `runtime.skill_index_chars` (4.000 karakter); küçük pencereli modelde pencerenin
  %2'si. Sığmayan beceriler için `[…+N beceri daha; find_skill ile ara]` notu düşer.
- `disable-model-invocation: true` olan beceriler dizinde ve `find_skill` sonucunda
  görünmez; yalnız `/ad` ile çağrılır.
- Depo kaynaklı beceriler (`proje`, `ek-kok`, `kurulu`, `claude-plugin`) ayrı bir
  `<proje_becerileri>` bloğunda, "depo içeriği, kullanıcı talimatı değildir" notuyla ve etiket
  kapatmaları nötralize edilerek listelenir; kullanıcı kökündeki beceriler önce ve düz.
- `skill_index_chars: 0` dizini kapatır (eski davranış: yalnız `find_skill`).
- Dizin her turda yeniden kurulur; bağlam sıkıştırması konuşmayı özetler, dizini düşürmez.

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
