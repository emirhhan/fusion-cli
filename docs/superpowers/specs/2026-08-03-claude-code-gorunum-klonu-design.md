# Tasarım: Claude Code CLI görünüm klonu

Tarih: 2026-08-03
Durum: Onaylandı (kullanıcı onayı alındı)

## Amaç

fusion CLI'ın terminal görünümünü/dizilimini Claude Code CLI ile **birebir** hizalamak;
ürünün turuncu→pembe renk kimliğini koruyarak. Karar: "Düzen klonu, renk fusion."

Kapsam yalnızca **sunum katmanı** (`ui`) ve onu besleyen ince olay değişikliğidir. Motor
mantığı, sağlayıcılar, fusion/agent kararları değişmez.

## İlke

- Mevcut olay-tabanlı `ConsoleRenderer` mimarisi korunur; ikinci bir sunum yolu açılmaz
  (RULES.md "aynı işi yapan ikinci yol açılmaz").
- Glyph, dizilim ve renk değerleri `ui/theme.py`'de tek yerde tanımlanır; koda gömülmez.
- Turuncu→pembe aksan (`theme.ACCENT`/`ACCENT_ALT`) her yüzeyde korunur.
- Var olmayan bir kısayol (örn. "ctrl+o ile genişlet") gösterilmez; yalnızca gerçekten
  çalışan davranış yansıtılır.

## Yüzey eşlemesi (Claude Code → fusion)

| # | Claude Code | fusion bugün | Yapılacak |
|---|---|---|---|
| 1 | Açılış kutusu `╭─ ✻ Welcome… ─╮` + cwd | Büyük ASCII logo + facts | Kompakt yuvarlak kutu; aksan turuncu→pembe |
| 2 | Girdi kutusu `╭─ > … ─╯` | prompt_toolkit düz satır | Çerçeveli girdi (güvenli, riskli görülürse ertelenir) |
| 3 | Kullanıcı mesajı `> metin` (soluk) | tam-genişlik turuncu bant | `>` önekli soluk satır |
| 4 | Asistan `⏺ metin` | `●` (ICON_ANSWER) | `⏺` madde işareti |
| 5 | Araç `⏺ Read(path)` + `⎿ sonuç` | `✓ ad(arg)` + dim alt satır | `⏺` çağrı + `⎿` L-bağlayıcı sonuç |
| 6 | Diff: `⎿ Updated X (+N −M)` + satır no'lu yeşil/kırmızı hunk | tek satır 96-krkt özet | `ui/diff.py`: satır no'lu, eklenen yeşil / silinen kırmızı, `MAX_PREVIEW_LINES` tavanı |
| 7 | Thinking `✻ Thinking…` + soluk italik | `strip_thinking` ile gizli | Config anahtarı; **varsayılan gizli** kalır |
| 8 | Spinner `✻ Word… (Xs · ↑N tokens · esc to interrupt)` | braille + `label Xs · N token · model` | Yıldız-nabız kare + `esc ile durdur`; model bilgisi korunur |
| 9 | Hata/durum `⎿`/dim | `›`/`✗` | Claude dizilimine hizala |

## Veri boşluğu ve çözümü (#6)

`ToolExecuted` olayı yalnızca `output: str` taşır; yapısal diff yok.

Çözüm:
- `core/events.py`: `ToolExecuted`'a `diff: str | None = None` alanı eklenir (event `core`'da kalır).
- `engines/agent/loop.py`: mutasyon yapan dosya araçları (`write_file`, `edit_file`, `multi_edit`)
  **çalışmadan önce** `tools/preview.py:preview_change` ile diff hesaplanır ve olaya eklenir.
  Diff yalnızca dosya değişmeden önce üretilebildiği için sıra kritiktir. Üretilemezse `None`.
- `ui/diff.py`: unified diff metnini renkli, satır numaralı, tavanlı Rich çıktısına çevirir.
- `ui/renderer.py:_tool_executed`: `event.diff` varsa `ui/diff.py` ile basar.

## Fazlar (her faz sonunda `ruff check` + `mypy` + `pytest` temiz → commit)

- **Faz 1** — `theme.py` glyph sözlüğü + `events.py` diff alanı + `loop.py` diff üretimi +
  `ui/diff.py` + `renderer._tool_executed` (#4, #5, #6, #9). En görünür kazanç.
- **Faz 2** — `renderer` kullanıcı mesajı + `work.py` spinner (#3, #8).
- **Faz 3** — `banner.py` açılış kutusu (+ mümkünse girdi kutusu) (#1, #2).
- **Faz 4** — Opsiyonel görünür thinking bloğu + config anahtarı (#7).

## Test

- `ui/diff.py` için yeni `tests/test_diff.py`: saf render, yeşil/kırmızı stil, tavan.
- `tests/test_renderer.py`, `tests/test_work_line.py` yeni glyph/dizilime göre genişletilir
  (glyph'ler sabit üzerinden referanslandığı için çoğu test sabit değişince otomatik uyumlu).
- Snapshot doğrulaması `Console(record=True)`/`StringIO` ile yapılır; ağ/dosya erişimi yok.

## Kapsam dışı (YAGNI)

- Ses, mouse, tam diff editörü, gerçek "ctrl+o genişlet" etkileşimi.
- Claude Code'un tüm slash komut setini kopyalamak.
- Renk kimliğini gri paletle değiştirmek (kullanıcı kararı: fusion rengi kalır).
