# Tam-ekran TUI — Faz 4 Öncesi Durum Raporu

Tarih: 2026-07-24. Kaynak: `screen.py`, `ansi_bridge.py`, `screen_turn.py`,
git geçmişi, `docs/BACKLOG.md`.

## Nerede duruyoruz

- **Faz 1 (iskelet), Faz 2 (ANSI köprüsü + gerçek akış), Faz 3 (onay/soru
  modalları) commit'li.** Kalite kapısı bugün tamamen yeşil:
  `ruff check` + `mypy` + `pytest tests/test_screen.py` (6 test) hepsi temiz.
- Kabuk `FUSION_FULLSCREEN=1 fusion` ile açılır; mevcut REPL'e dokunulmadı
  (geçiş hâlâ Faz 5).
- Gerçek motor turu (`run_turn`) hem fusion hem agent motoruna bağlı;
  agent onay/soru turları `ScreenPrompter` üzerinden modala düşüyor.

## Kanıtlanmış reçete (değiştirilmez)

`full_screen=True`, `mouse_support=False`, app-cursor mode (`\x1b[?1h\x1b=`),
imleç-tabanlı kaydırma. Bu bileşim gerçek Terminal.app'te tekerleği ok tuşuna
çevirip scrollback'e kaçışı ve resize'da `❯` çoğalmasını çözen tek bileşim.

## Kalan sorunlar

### 1. Renk kaybı (Faz 4'ün ana problemi)
Tekerlek yalnızca düz metin `TextArea` + imleç kaydırma ile çalışıyor. Bu yüzden
`AnsiBridge` renk üretmiyor (`force_terminal` yok). Markdown/kod/diff renkleri
şu an gitti. Faz 4: ANSI'yi çözen VE tekerlekle (ok tuşu yoluyla) kaydırılabilen
bir kontrol. Bu bir **araştırma spike'ı** — sonucu baştan garanti değil.

### 2. Modal açıkken ok/PageUp tuşları kaydırmayı çalıyor (doğrulanmış kod hatası)
`screen.py` içindeki `up/down/pageup/pagedown` bağlamaları `eager=True` ve
**filtresiz**. `ask_text` modalı açık ve `_modal_input` odaklıyken bu tuşlar
metin girişinin imlecini oynatmak yerine arkadaki konuşmayı kaydırıyor. Test yok.
Faz 4'te: bu bağlamalara `filter=Condition(lambda: self._modal_kind is None)`
eklenmeli ve modal-açık senaryosu için test yazılmalı.

### 3. Yalnızca gerçek terminalde doğrulanabilecekler (insan gözü)
- resize'da `❯` çoğalması YOK.
- yukarı kaydırınca eski shell GÖRÜNMEZ (scrollback izole).
- tekerlek + ok + PageUp konuşmayı kaydırıyor; takip modu (alta yapışma) doğru.
- Ctrl-Q sonrası terminal normale dönüyor (app-cursor mode geri alınıyor).
Bunlar otomatik testle yakalanamaz; her Faz 4 task'i sonunda elle bakılmalı.

### 4. Küçük test boşlukları (BACKLOG'dan, opsiyonel)
- `run_turn` sink sırası (renderer, pump'tan ÖNCE yazmalı) load-bearing ama
  test sırayı değil yalnızca tiplerin varlığını doğruluyor.
- `ansi_bridge` renk testi yalnızca `\x1b[` varlığına bakar; renge-özgü SGR
  assert'i (Faz 4 renk gelince zaten güçlenecek).
