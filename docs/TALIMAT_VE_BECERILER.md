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
