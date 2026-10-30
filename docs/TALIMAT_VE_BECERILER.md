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
- Bütçe: dosya başına 8.000, toplam `runtime.instruction_max_chars` (32.000) karakter.
  Kırpma sessiz değildir: metne `[…kırpıldı…]` notu düşer; masaüstünde
  **Ayarlar › Kişiselleştirme › Kalıcı talimat** altında yüklenen dosyalar, karakter ve kırpılan
  miktar listelenir (`ayar.talimat` → `katmanlar`, `notlar`).
- `runtime.instruction_merge: false` eski davranışa döner: yalnız kökteki ilk bilinen dosya.

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
- `paths:` olanlar (`src/**/*.tsx`, `*.css`, `docs/`, `*.{ts,tsx}`) yalnız model eşleşen
  dosyayı okuyup/düzenleyince, o turda bir kez, iç içe talimat notuyla aynı mesajda gelir.
  Dizin içermeyen desen dosya adına da uygulanır.
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
| `allowed-tools` / `izinli-araclar` | O turda yalnız bu araçlar sunulur (`Bash(git *)` deseninin araç adı eşlenir, komut deseni uygulanmaz; not düşer) |
| `disable-model-invocation` / `model-cagirmasin` | Beceri dizinine ve `find_skill` sonucuna girmez; yalnız `/ad` ile |
| `user-invocable: false` | Slash komutu olarak sunulmaz (yalnız model `read_skill` ile) |
| `context: fork` | Okunur; şimdilik ana turda çalışır, not düşer |
| `model`, `effort` | Okunur; bu turda uygulanmaz (`/model`, `/effort` ile seç), not düşer |
| Gövdede `` !`cmd` `` | Komut çıktısı yüklenmeden önce yerleştirilir: yalnız `~/.claude`, `~/.codex`, `~/.hermes`, yerleşik köklerden ya da `fusion trust` ile güvenilen projeden ve `auto`/`edits`/`bypass` kipinde; çıktı 2.000 karakter, sırlar maskeli, 10 sn |

## Beceri dizini (`runtime.skill_index_chars`)

Kök turda sistem bağlamına **BECERİ DİZİNİ** bloğu girer: beceri başına `ad — açıklama`
(ilk 150 karakter), keşif sırasıyla (kullanıcı kökleri → proje → Codex/Hermes → kurulu →
yerleşik). Model uygun beceriyi aramadan tanır ve `read_skill('<ad>')` ile gövdeyi yükler;
gövde hiçbir zaman önden basılmaz (progressive disclosure).

- Bütçe `runtime.skill_index_chars` (4.000 karakter); küçük pencereli modelde pencerenin
  %2'si. Sığmayan beceriler için `[…+N beceri daha; find_skill ile ara]` notu düşer.
- `disable-model-invocation: true` olan beceriler dizinde ve `find_skill` sonucunda
  görünmez; yalnız `/ad` ile çağrılır.
- `skill_index_chars: 0` dizini kapatır (eski davranış: yalnız `find_skill`).
- Dizin her turda yeniden kurulur; bağlam sıkıştırması konuşmayı özetler, dizini düşürmez.

## Beceri keşif kökleri

Öncelik sırasıyla (aynı adda ilk bulunan kazanır): `~/.claude/skills`, `~/.claude/plugins`,
proje `.claude/skills`, `.fusion/skills`, `.agents/skills`; `~/.codex/skills`, `~/.agents/skills`
(Codex/ChatGPT açık standardı); `~/.hermes/skills`; `--add-dir` / `/add-dir` ile açılan her kökün
`.claude/skills`, `.agents/skills`, `.fusion/skills` ve `.claude/agents` dizinleri ("ek-kok");
`fusion yetenek kur` repoları; yerleşik beceriler en sonda. Komut dosyaları için
`~/.claude/commands`, `~/.fusion/commands`, proje `.claude/commands`, `.fusion/commands`.

## Katalog yaşam döngüsü

| Yüzey | Ne yapar |
|---|---|
| `/skills reload` (`yenile`) · masaüstü **Yenile** · `yetenek.yenile` | Kataloğu diskten yeniden tarar. Yeni klasör eklenip silindiğinde kök dizinin mtime'ı değiştiği için bir sonraki turda **kendiliğinden** yenilenir; var olan bir SKILL.md'nin içeriği değiştiyse `reload` gerekir. |
| `/skills doctor`, `/skill-doctor` · masaüstü **Teşhis** · `yetenek.teshis` | Eksik `description`, ön maddesiz dosya, aynı adın birden çok kaynakta farklı içerikle bulunması (kazanan/gölgelenen), tek sayfaya sığmayan gövde, ev dizini dışına çıkan sembolik bağ. |
| `/skills new <ad>` · `/agents new <ad>` | Modele `.claude/skills/<ad>/SKILL.md` ya da `.claude/agents/<ad>.md` yazdırır; önce `ask_user` ile kapsam ve araç kısıtını sorar, mevcut dosyanın üzerine yazmaz. |
| `capabilities.disabled: [ad, ad@kaynak:kimlik]` (config.yaml) | Her oturumda kapalı tutulan beceri/ajanlar; masaüstündeki oturumluk kapatmayla birleşir. |

## `/init` ve `/doctor prompt`

- `/init [agents|claude]` (REPL, TUI, masaüstü komut paleti) ve terminalde `fusion init
  [--format agents|claude] [--mode edits]`: Fusion depodan ölçtüğü olguları (proje türü,
  keşfedilen lint/test komutları, mevcut talimat dosyaları) göreve koyar; model depoyu inceleyip
  `AGENTS.md` (varsayılan) ya da `CLAUDE.md` yazar — bölümler: Proje, Kurulum ve çalıştırma,
  Doğrulama, Kod kuralları, Dikkat; 3.000 karakter sınırı, uzun kurallar `@docs/…md` ile.
  Dosya zaten varsa üzerine yazmaz; eksik bölümleri `ask_user` ile sorar.
- `/doctor prompt` (argümansız `/doctor` da aynı rapor + `fusion doctor` hatırlatması):
  yüklenen katmanlar ve karakterleri, kırpılan miktar, kök dışı import notları, depo
  talimatında izin/onay/sır kurallarına dokunan şüpheli satırlar (Fusion bunları uygulamaz;
  dosyanın kaynağını gözden geçir), öneriler (talimat yoksa `/init`, bütçenin %70'i dolduysa
  kısalt, doğrulama komutu yoksa `## Doğrulama` bölümü).
- Masaüstü **Ayarlar › Kişiselleştirme › Kalıcı talimat**: öneriler listelenir; **Talimat
  oluştur (/init)** ve **Talimatı denetle** düğmeleri aynı komutları çalıştırır
  (`ayar.talimat` → `oneriler`, `supheli`).
