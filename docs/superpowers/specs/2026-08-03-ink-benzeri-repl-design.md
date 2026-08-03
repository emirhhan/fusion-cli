# Tasarım: Ink-benzeri tek yol REPL (Claude Code modeli)

Tarih: 2026-08-03
Durum: Onaylandı (kullanıcı: "Claude Code Ink nasılsa öyle yap, tek yol").

## Amaç

fusion REPL'ini Claude Code'un (Ink) modeline getirmek ve satır-içi/tam-ekran **mod
ayrımını kaldırmak**. Tek yol:

- **Normal tampon** — alternatif ekran YOK; çıkışta konuşma scrollback'te kalır.
- Altta **pinli çerçeveli girdi kutusu** (`> `), hemen altında **durum satırı**
  (mod + kısayol ipuçları). Auto/plan/security modu prompt'un içinden çıkıp buraya iner.
- Motor çıktısı (banner, kullanıcı yankısı, cevap akışı, araç kartı, diff, spinner)
  girdinin **üstüne**, gerçek terminale akar.
- **Canlı tuşlar** — tur çalışırken tuşlar okunur: **esc turu keser** (Ctrl-C de),
  shift-tab mod döndürür, Enter gönderir.

## Neden mevcut iki yol da yetmiyor

- Satır-içi (`prompt_async`): tur sırasında tuş okumaz → esc kesemez; çerçeve/durum-altta
  prompt_toolkit #1933 resize hatasını geri getirir.
- Tam-ekran (`FusionScreen`, `full_screen=True`): alternatif ekran kullanır → çıkışta
  scrollback silinir; Claude bunu yapmaz.

Doğru model: `Application(full_screen=False)` — normal tamponda pinli alt-çrome, çıktı
`run_in_terminal`/`patch_stdout` ile üstte akar.

## Mimari

Yeni tek modül `cli/repl/tui.py` → `FusionTui`:

- **Alt-chrome layout** (yalnızca bunlar app tarafından çizilir, en altta pinli):
  1. çalışma/spinner satırı (dinamik; boşsa yer kaplamaz),
  2. çerçeveli girdi kutusu (`Frame(TextArea(height=1), ...)`, prompt `> `),
  3. durum satırı (`⏵ auto · shift-tab ile mod · esc ile durdur`).
- **Çıktı**: `run_in_terminal(fn)` ile app UI'ı geçici gizlenir, Rich çıktı gerçek
  stdout'a basılır, sonra alt-chrome yeniden çizilir. Renderer gerçek konsola bağlıdır.
- **Tur**: gönderilen satır bir asyncio görevinde koşar; `escape`/`c-c` görevi iptal eder
  (`renderer.abort()` ile spinner durur). Ortak `ReplState`, komut kayıt defteri ve
  motorlar (`run_task`/`run_agent_task`) korunur.
- **Onay/soru**: mevcut modal köprüsü korunur (Float), ya da alt-chrome içinde satır.

## Fazlar (her faz: `ruff` + `mypy` + `pytest` temiz → commit)

- **A1** — `FusionTui` alt-chrome (girdi kutusu + altında durum + çalışma satırı) ve tuş
  bağları (enter/esc/c-c/c-q/s-tab) enjekte edilmiş callback'lerle (TTY'siz test edilebilir).
- **A2** — Çıktının üstte akıtılması (`run_in_terminal`/`patch_stdout`) + renderer bağı.
- **A3** — Tur yürütme entegrasyonu (agent/fusion), esc ile iptal, durum güncelleme.
- **A4** — Tek varsayılan yap; `run_repl` gövdesi buna döner; `FUSION_FULLSCREEN`/inline
  ayrımı ve eski `screen*`/inline giriş yolu kaldırılır; testler taşınır.
- **A5** — Seçiciler (`/model`, `/level` …) bu tek yolda argümansız da çalışır.

## Kapsam dışı (YAGNI)

- Mouse, fare kaydırma inceliği (tuş kaydırma yeter).
- Tam Ink kare-diff motoru; satır granülaritesinde akış yeterli.

## Risk ve azaltma

- Token akışının pinli girdinin üstünde düzgün akması en hassas kısım. Azaltma: spinner
  alt-chrome'da kalır (akışa girmez); metin/araç kartı/diff satır granülaritesinde `run_in_terminal`
  ile basılır. Her faz commit'li; eski yol A4'e kadar çalışır durumda kalır, geçiş kanıtlanınca silinir.
