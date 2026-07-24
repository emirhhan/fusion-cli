# Tam-ekran TUI Faz 4 — Renkli Konuşma + Cila Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development
> (önerilen) veya superpowers:executing-plans ile task-task uygula. Adımlar
> checkbox (`- [ ]`) ile izlenir.

**Goal:** Tam-ekran kabukta (a) renkli ANSI konuşmayı tekerlek kaydırmayı
BOZMADAN geri getirmek, ve (b) doğrulanmış küçük hataları kapatmak. Faz 4 bir
**araştırma spike'ı içerir** (Task 2): sonuç olumsuz çıkarsa düz metin kalır ve
karar yazıya dökülür — kapsam sessizce büyütülmez.

**Architecture:** Yalnızca `cli/repl/` (`screen.py`, `ansi_bridge.py`) ve testleri.
Motor/çekirdek katmanına DOKUNULMAZ. Mevcut REPL değişmez (geçiş Faz 5).

**Tech Stack:** Python 3.11, prompt_toolkit 3.0.52, rich, pytest, ruff, mypy.

## Global Constraints

- Kod içi her şey Türkçe (docstring/yorum/log/hata/CLI metni); tanımlayıcılar
  İngilizce + PEP 8.
- Kanıtlanmış reçete değişmez: `full_screen=True`, `mouse_support=False`,
  app-cursor mode `\x1b[?1h\x1b=`, imleç-tabanlı kaydırma (tekerlek = ok tuşu).
- Her task sonunda kalite kapısı: `ruff check` + `mypy` + `pytest` üçü de temiz
  olmadan commit yok. `.venv/bin/python` kullanılır.
- Commit: conventional commit, Türkçe açıklama, faz/adım numarası GEÇMEZ,
  author/co-author eklenmez.
- Görsel/gerçek-terminal davranışı otomatik testle doğrulanamaz; ilgili task'ler
  bir **insan elle-doğrulama** adımı içerir.

---

### Task 1: Modal açıkken kaydırma tuşlarını sustur (düşük risk, testli)

`up/down/pageup/pagedown` bağlamaları `eager=True` ve filtresiz; metin modalı
(`ask_text`) açıkken bu tuşlar giriş imlecini oynatmak yerine arkadaki konuşmayı
kaydırıyor. Bir filtreyle modal-açıkken devre dışı bırakılır.

**Files:**
- Modify: `src/fusion_cli/cli/repl/screen.py`
- Test: `tests/test_screen.py`

**Interfaces:**
- Davranış: `_modal_kind is not None` iken kaydırma bağlamaları çalışmaz.

- [ ] **1. Yaz: başarısız test** — modal "text" açıkken imleci konuşmanın
  ortasına al; kaydırma tuşunu tetikleyen yol modal açıkken imleci OYNATMAMALI.
  (Bağlamayı doğrudan çağırmak yerine, kaydırma mantığını modal filtresine bağlı
  küçük bir yardımcıya çıkarıp onu test et; ya da `KeyBindings.get_bindings_for_keys`
  ile ilgili binding'in filtresinin modal-açıkken False döndüğünü doğrula.)
- [ ] **2. RED çalıştır.**
- [ ] **3. Uygula** — kaydırma bağlamalarına
  `filter=Condition(lambda: self._modal_kind is None)` ekle (mevcut `eager=True`
  korunur). Onay modalı zaten e/h yakalıyor; metin modalında ok tuşları artık
  giriş kutusuna gider.
- [ ] **4. GREEN + kalite kapısı + commit** —
  `fix(repl): modal açıkken kaydırma tuşlarını devre dışı bırak`

---

### Task 2: SPIKE — ANSI'yi çözen + tekerlekle kaydırılabilen konuşma kontrolü

**Bu bir araştırma task'idir; kod üretmek zorunda değil.** Amaç: renkli içeriği
(`FormattedTextControl(ANSI(...))`) gösterirken tekerlek=ok tuşu yoluyla
imleç-tabanlı kaydırmanın çalışıp çalışmadığını gerçek Terminal.app'te ölçmek.

Faz 2 geçmişi (BACKLOG): `FormattedTextControl(ANSI)` + `vertical_scroll` denendi,
tekerlek kaydırmadı → düz `TextArea`'ya dönüldü. Spike'ın sorusu net: **imleç-
tabanlı kaydırmayı** (spike4 reçetesi) `ANSI` içerikli bir kontrolle
birleştirebilir miyiz?

**Yöntem (geçici, ayrı dosyada, commit'siz spike):**
- `AnsiBridge`'i `force_terminal=True` ile renk üretecek şekilde geçici çevir.
- Konuşmayı ANSI çözen bir kontrol/ pencere ile kur; kaydırmayı imleç-tabanlı
  tutmayı dene. Render-zamanı cursor-scroll clamp'i
  (`containers.py::_scroll_when_linewrapping`) manuel kaydırmayı geri çekiyor mu
  gözle; `always_hide_cursor=True` tuzağı atlatıyor mu dene.
- Gerçek Terminal.app'te: tekerlek + ok + PageUp renkli içeriği kaydırıyor mu?
  resize'da çoğalma / scrollback sızması dönüyor mu?

- [ ] **1. Spike'ı kur ve gerçek terminalde ölç (insan).**
- [ ] **2. Sonucu `docs/BACKLOG.md`'ye yaz:** hangi kurulum tekerlekle
  kaydırdı / kaydırmadı, hangi ödünleşim var.
- [ ] **3. Karar noktası:**
  - **Başarılı** → Task 3 (üretimleştir).
  - **Başarısız** → düz metin kalır; Faz 4 renk hedefi kapatılır, gerekçe
    BACKLOG'a yazılır, plan burada biter. Kapsam zorlanmaz.

Spike commit edilmez; öğrenilen BACKLOG'a düşer.

---

### Task 3: Renkli konuşmayı üretimleştir (YALNIZCA Task 2 başarılıysa)

Spike'ta çalıştığı kanıtlanan kurulumu TDD ile kalıcı hale getir.

**Files:**
- Modify: `src/fusion_cli/cli/repl/ansi_bridge.py`, `src/fusion_cli/cli/repl/screen.py`
- Test: `tests/test_screen.py`, `tests/test_ansi_bridge.py`

**Interfaces (spike sonucuna göre kesinleşir):**
- `AnsiBridge` renk üretir (`force_terminal=True` veya eşdeğeri).
- Konuşma kontrolü ANSI çözer; imleç-tabanlı kaydırma ve takip modu korunur.

- [ ] **1. Yaz: başarısız testler** — köprü renge-özgü SGR üretiyor
  (ör. `\x1b[31m`); konuşmaya renkli metin ekleyince kaydırma/takip mantığı
  (satır sayımı, imleç sınırı) bozulmuyor.
- [ ] **2. RED.**
- [ ] **3. Uygula** — spike kurulumunu taşı; reçete escape/mouse ayarları aynen.
- [ ] **4. Elle görsel doğrulama (insan):** `FUSION_FULLSCREEN=1 fusion` →
  markdown/kod/diff renkli görünüyor; tekerlek/ok/PageUp kaydırıyor; resize temiz;
  scrollback sızmıyor. Sorun olursa Task 2'ye dön.
- [ ] **5. Kalite kapısı + commit** —
  `feat(repl): tam-ekran konuşmada renkli ANSI içerik`

---

## Self-Review Notları

- **Sıra bilinçli:** düşük-riskli testli düzeltme (Task 1) önce; belirsiz spike
  (Task 2) izole; üretim (Task 3) yalnızca spike başarılıysa. Faz yarım
  bırakılmaz — spike başarısızsa karar yazılıp faz temiz kapanır.
- **Kapsam dışı (Faz 5):** eski REPL geçişi, ölü Rich-Live/prompter temizliği.
- **Opsiyonel test sağlamlaştırmaları** (sink sırası pini) bu fazda zorunlu değil;
  isteğe bağlı olarak Task 1'e eklenebilir.
- **Reçeteye dokunma:** hiçbir task `mouse_support`/`full_screen`/app-cursor
  escape dizilerini değiştiremez; renk bunların ÜSTÜNE gelir, yerine değil.
