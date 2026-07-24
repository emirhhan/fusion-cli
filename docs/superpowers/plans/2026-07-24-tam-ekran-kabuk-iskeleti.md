# Tam-ekran Kabuk İskeleti (Faz 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fusion için, doğrulanmış reçeteyle çalışan bir tam-ekran (alternatif ekran) prompt_toolkit kabuğunun iskeletini kurmak; basit bir "eko" turuyla uçtan uca çalıştığını göstermek. Mevcut REPL'e DOKUNULMAZ (geçiş Faz 5).

**Architecture:** Yeni `cli/repl/screen.py` modülü, prompt_toolkit `full_screen` Application'ı kurar: banner + kaydırılabilir konuşma alanı + çalışma satırı + çizgili giriş kutusu. Doğrulanmış reçete uygulanır (mouse kapalı, `reset_cursor_key_mode`→`?1h`, imleç-tabanlı kaydırma). Motor katmanına ve mevcut REPL'e dokunulmaz; kabuk ayrı bir giriş noktasından (gizli env bayrağı) elle test edilir.

**Tech Stack:** Python 3.11, prompt_toolkit 3.0.52, pytest, ruff, mypy.

## Global Constraints

- Kod içi her şey Türkçe: docstring, yorum, log, hata ve kullanıcıya görünen CLI metinleri. Tanımlayıcılar İngilizce + PEP 8.
- Motor/çekirdek katmanına (`engines/`, `providers/`, `memory/`, `core/`, `config/`, `tools/`, `observability/`) DOKUNULMAZ.
- Mevcut REPL (`cli/repl/loop.py`, `input.py`) davranışı DEĞİŞMEZ (geçiş Faz 5).
- prompt_toolkit sürümü 3.0.52'ye sabit; reçete bu sürümün iç davranışına dayanır.
- Her task sonunda kalite kapısı: `ruff check` + `mypy` + `pytest` üçü de temiz olmadan commit yok.
- Commit mesajları conventional commit, Türkçe açıklama, faz/adım numarası GEÇMEZ, author/co-author eklenmez.
- Reçete escape dizileri birebir: uygulama modu `\x1b[?1h\x1b=`, geri dönüş `\x1b[?1l\x1b>`.

---

### Task 1: İmleç-modu reçetesi (uygulama imleç/keypad)

Terminal.app'in fare tekerleğini ok tuşuna çevirmesi için uygulama imleç modu şart. prompt_toolkit modu bir kez `?1l` yapar; onu `?1h\x1b=` yapacak şekilde değiştiririz. Tek seferlik — her render'a müdahale metni patlatıyor.

**Files:**
- Create: `src/fusion_cli/cli/repl/screen.py`
- Test: `tests/test_screen.py`

**Interfaces:**
- Produces: `install_app_cursor_mode(app: Any) -> None` — `app.output.reset_cursor_key_mode`'u `\x1b[?1h\x1b=` yayacak şekilde değiştirir.
- Produces: `APP_CURSOR_ON = "\x1b[?1h\x1b="`, `APP_CURSOR_OFF = "\x1b[?1l\x1b>"` sabitleri.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_screen.py
"""Tam-ekran kabuk iskeleti."""

from __future__ import annotations

from types import SimpleNamespace


class _KayitliCikti:
    """write_raw çağrılarını biriktiren sahte prompt_toolkit output."""

    def __init__(self) -> None:
        self.yazilan: list[str] = []

    def write_raw(self, text: str) -> None:
        self.yazilan.append(text)

    def flush(self) -> None:
        pass


def test_imlec_modu_uygulama_moduna_alinir():
    from fusion_cli.cli.repl.screen import APP_CURSOR_ON, install_app_cursor_mode

    cikti = _KayitliCikti()
    app = SimpleNamespace(output=cikti)

    install_app_cursor_mode(app)
    app.output.reset_cursor_key_mode()

    assert cikti.yazilan == [APP_CURSOR_ON]
    assert APP_CURSOR_ON == "\x1b[?1h\x1b="
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_screen.py::test_imlec_modu_uygulama_moduna_alinir -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fusion_cli.cli.repl.screen'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/fusion_cli/cli/repl/screen.py
"""Tam-ekran (alternatif ekran) kabuk — doğrulanmış reçeteyle.

Neden alternatif ekran: normal tamponda terminal resize'ı prompt_toolkit'in bayat
imleç modeliyle yaptığı silmeyi ıskalatıp giriş işareti kopyaları biriktiriyordu
ve yukarı kaydırınca eski shell çıktısı görünüyordu. Ekranı uygulama sahiplenince
bu sınıf hatalar ortadan kalkar.

Reçete (gerçek Terminal.app'te ölçülerek doğrulandı):
- full_screen=True (alternatif ekran)
- mouse_support=False (agresif fare takibi resize'ı bozuyor)
- reset_cursor_key_mode → uygulama imleç modu (tekerlek = ok tuşu, scrollback'e kaçmaz)
"""

from __future__ import annotations

from typing import Any

#: Uygulama imleç + keypad modu (DECCKM + DECKPAM). Terminal.app tekerleği ok
#: tuşuna çevirip uygulamaya yollar; kendi scrollback'ini kaydırmaz.
APP_CURSOR_ON = "\x1b[?1h\x1b="
#: Çıkışta normal imleç/keypad moduna dönüş.
APP_CURSOR_OFF = "\x1b[?1l\x1b>"


def install_app_cursor_mode(app: Any) -> None:
    """prompt_toolkit'in tek seferlik `reset_cursor_key_mode` çağrısını, normal
    mod (`?1l`) yerine uygulama modu (`?1h\x1b=`) yayacak şekilde değiştir.

    Tek seferlik olması kritik: her render'da yeniden yaymak Terminal.app'te metin
    bozulmasına yol açıyor (spike geçmişinde doğrulandı).
    """
    app.output.reset_cursor_key_mode = lambda: app.output.write_raw(APP_CURSOR_ON)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_screen.py::test_imlec_modu_uygulama_moduna_alinir -v`
Expected: PASS

- [ ] **Step 5: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src/fusion_cli/cli/repl/screen.py tests/test_screen.py
.venv/bin/mypy src/fusion_cli/cli/repl/screen.py
.venv/bin/python -m pytest tests/test_screen.py -q
git add src/fusion_cli/cli/repl/screen.py tests/test_screen.py
git commit -m "feat(repl): tam-ekran kabuk için uygulama imleç modu reçetesi"
```

---

### Task 2: Konuşma tamponu — ekleme ve kaydırma

Konuşma alanı salt-okunur, kaydırılabilir bir tampon. Kaydırma imleci hareket ettirerek yapılır (pencere imleci görünür tutar); `vertical_scroll` doğrudan sürülürse imleç sondayken her render'da en alta çekilir.

**Files:**
- Modify: `src/fusion_cli/cli/repl/screen.py`
- Test: `tests/test_screen.py`

**Interfaces:**
- Consumes: (yok)
- Produces: `append_text(buffer: Buffer, text: str) -> None` — metni sona ekler, imleci sona alır.
- Produces: `scroll_lines(buffer: Buffer, delta: int) -> None` — imleci `delta` satır taşır (sınırlar içinde).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_screen.py içine ekle
def _bos_buffer():
    from prompt_toolkit.buffer import Buffer

    return Buffer(read_only=False)


def test_metin_sona_eklenir_ve_imlec_sonda():
    from fusion_cli.cli.repl.screen import append_text

    buf = _bos_buffer()
    append_text(buf, "birinci\n")
    append_text(buf, "ikinci\n")

    assert buf.text == "birinci\nikinci\n"
    assert buf.cursor_position == len(buf.text)


def test_kaydirma_imleci_satir_bazli_tasir_ve_sinirlanir():
    from fusion_cli.cli.repl.screen import append_text, scroll_lines

    buf = _bos_buffer()
    append_text(buf, "\n".join(f"satir-{i}" for i in range(20)))

    scroll_lines(buf, -5)  # 5 satır yukarı
    assert buf.document.cursor_position_row == 19 - 5

    scroll_lines(buf, -1000)  # üst sınır
    assert buf.document.cursor_position_row == 0

    scroll_lines(buf, +1000)  # alt sınır
    assert buf.document.cursor_position_row == 19
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_screen.py -k "eklenir or kaydirma" -v`
Expected: FAIL — `ImportError: cannot import name 'append_text'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/fusion_cli/cli/repl/screen.py — importlara ekle
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
```

```python
# src/fusion_cli/cli/repl/screen.py — sona ekle
def append_text(buffer: Buffer, text: str) -> None:
    """Konuşma tamponuna metin ekle; imleci sona al (takip modu)."""
    new = buffer.text + text
    buffer.set_document(Document(new, cursor_position=len(new)), bypass_readonly=True)


def scroll_lines(buffer: Buffer, delta: int) -> None:
    """İmleci `delta` satır taşı; pencere imleci görünür tutmak için kayar.

    Salt-okunur, odaklı olmayan pencerede `vertical_scroll`'u doğrudan sürmek işe
    yaramaz: imleç sondayken prompt_toolkit her çizimde en alta çeker.
    """
    doc = buffer.document
    row = max(0, min(doc.line_count - 1, doc.cursor_position_row + delta))
    buffer.set_document(
        Document(buffer.text, cursor_position=doc.translate_row_col_to_index(row, 0)),
        bypass_readonly=True,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_screen.py -k "eklenir or kaydirma" -v`
Expected: PASS (iki test)

- [ ] **Step 5: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src/fusion_cli/cli/repl/screen.py tests/test_screen.py
.venv/bin/mypy src/fusion_cli/cli/repl/screen.py
.venv/bin/python -m pytest tests/test_screen.py -q
git add src/fusion_cli/cli/repl/screen.py tests/test_screen.py
git commit -m "feat(repl): konuşma tamponu ekleme ve imleç-tabanlı kaydırma"
```

---

### Task 3: Kabuk kurulumu — layout ve reçete

full_screen Application: banner + konuşma alanı + çalışma satırı + çizgili giriş kutusu. Reçete uygulanır (mouse kapalı, full_screen açık). Eko davranışı bir sonraki task'te bağlanır; şimdilik `on_submit` dışarıdan verilir.

**Files:**
- Modify: `src/fusion_cli/cli/repl/screen.py`
- Test: `tests/test_screen.py`

**Interfaces:**
- Consumes: `append_text`, `scroll_lines` (Task 2).
- Produces: `FusionScreen` sınıfı:
  - `FusionScreen(banner: str, on_submit: Callable[[str], None])`
  - `.application -> Application` (full_screen=True, mouse_support=False)
  - `.append(text: str) -> None` (konuşmaya ekler + invalidate)
  - `.conversation_buffer -> Buffer`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_screen.py içine ekle
def test_kabuk_full_screen_ve_mouse_kapali_kurulur():
    from fusion_cli.cli.repl.screen import FusionScreen

    ekran = FusionScreen(banner="✦ fusion", on_submit=lambda s: None)
    app = ekran.application

    assert app.full_screen is True
    assert app.mouse_support() is False  # Filter çağrılınca False


def test_kabuk_appendi_konusmaya_yazar():
    from fusion_cli.cli.repl.screen import FusionScreen

    ekran = FusionScreen(banner="✦ fusion", on_submit=lambda s: None)
    ekran.append("[ben] merhaba\n")

    assert "[ben] merhaba" in ekran.conversation_buffer.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_screen.py -k "kabuk_full or kabuk_appendi" -v`
Expected: FAIL — `ImportError: cannot import name 'FusionScreen'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/fusion_cli/cli/repl/screen.py — importlara ekle
from collections.abc import Callable

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame, TextArea
```

```python
# src/fusion_cli/cli/repl/screen.py — sona ekle
#: Yukarı/aşağı bir kaydırmada kaç satır (page için katı).
_SCROLL_STEP = 1
_SCROLL_PAGE = 8


class FusionScreen:
    """Tam-ekran kabuk: banner + konuşma + çalışma satırı + giriş kutusu."""

    def __init__(self, banner: str, on_submit: Callable[[str], None]) -> None:
        self._on_submit = on_submit
        self._conversation = TextArea(
            text="",
            read_only=True,
            scrollbar=True,
            focusable=True,
            wrap_lines=True,
        )
        self._work = Window(content=FormattedTextControl(""), height=1)
        self._input = TextArea(height=1, prompt="❯ ", multiline=False, wrap_lines=False)
        self._input.accept_handler = self._handle_submit  # type: ignore[assignment]

        root = HSplit(
            [
                Window(content=FormattedTextControl(banner), height=3),
                Frame(self._conversation, title="konuşma"),
                self._work,
                Frame(self._input, title="mesaj"),
            ]
        )
        self.application: Application = Application(
            layout=Layout(root, focused_element=self._input),
            key_bindings=self._bindings(),
            full_screen=True,
            mouse_support=False,
        )

    @property
    def conversation_buffer(self) -> Buffer:
        return self._conversation.buffer

    def append(self, text: str) -> None:
        append_text(self._conversation.buffer, text)
        self.application.invalidate()

    def _handle_submit(self, _buff: Buffer) -> bool:
        text = self._input.text.strip()
        self._input.text = ""
        if text:
            self._on_submit(text)
        return False

    def _bindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("c-q")
        @kb.add("c-c")
        def _exit(event: Any) -> None:
            event.app.exit()

        @kb.add("up", eager=True)
        def _up(_e: Any) -> None:
            scroll_lines(self._conversation.buffer, -_SCROLL_STEP)
            self.application.invalidate()

        @kb.add("down", eager=True)
        def _down(_e: Any) -> None:
            scroll_lines(self._conversation.buffer, +_SCROLL_STEP)
            self.application.invalidate()

        @kb.add("pageup", eager=True)
        def _pgup(_e: Any) -> None:
            scroll_lines(self._conversation.buffer, -_SCROLL_PAGE)
            self.application.invalidate()

        @kb.add("pagedown", eager=True)
        def _pgdn(_e: Any) -> None:
            scroll_lines(self._conversation.buffer, +_SCROLL_PAGE)
            self.application.invalidate()

        return kb
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_screen.py -k "kabuk_full or kabuk_appendi" -v`
Expected: PASS (iki test)

- [ ] **Step 5: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src/fusion_cli/cli/repl/screen.py tests/test_screen.py
.venv/bin/mypy src/fusion_cli/cli/repl/screen.py
.venv/bin/python -m pytest tests/test_screen.py -q
git add src/fusion_cli/cli/repl/screen.py tests/test_screen.py
git commit -m "feat(repl): tam-ekran kabuk layout ve reçete kurulumu"
```

---

### Task 4: Eko turu bağlama

İskeletin uçtan uca çalıştığını göstermek için: giriş → kullanıcı mesajı + kanned eko konuşmaya yazılır. (Gerçek motor entegrasyonu Faz 2.)

**Files:**
- Modify: `src/fusion_cli/cli/repl/screen.py`
- Test: `tests/test_screen.py`

**Interfaces:**
- Consumes: `FusionScreen` (Task 3).
- Produces: `echo_submit(screen: FusionScreen, text: str) -> None` — konuşmaya `[ben] <text>` ve `[eko] <text>` yazar.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_screen.py içine ekle
def test_eko_turu_kullanici_ve_yaniti_yazar():
    from fusion_cli.cli.repl.screen import FusionScreen, echo_submit

    ekran = FusionScreen(banner="✦ fusion", on_submit=lambda s: None)
    echo_submit(ekran, "vpn nedir")

    metin = ekran.conversation_buffer.text
    assert "[ben] vpn nedir" in metin
    assert "[eko] vpn nedir" in metin
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_screen.py::test_eko_turu_kullanici_ve_yaniti_yazar -v`
Expected: FAIL — `ImportError: cannot import name 'echo_submit'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/fusion_cli/cli/repl/screen.py — sona ekle
def echo_submit(screen: FusionScreen, text: str) -> None:
    """İskelet doğrulaması için basit eko turu. Faz 2'de gerçek motorla değişir."""
    screen.append(f"\n[ben] {text}\n")
    screen.append(f"[eko] {text}\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_screen.py::test_eko_turu_kullanici_ve_yaniti_yazar -v`
Expected: PASS

- [ ] **Step 5: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src/fusion_cli/cli/repl/screen.py tests/test_screen.py
.venv/bin/mypy src/fusion_cli/cli/repl/screen.py
.venv/bin/python -m pytest tests/test_screen.py -q
git add src/fusion_cli/cli/repl/screen.py tests/test_screen.py
git commit -m "feat(repl): iskelet doğrulaması için eko turu"
```

---

### Task 5: Elle çalıştırma girişi (gizli, mevcut REPL'e dokunmaz)

Kabuğu gerçek Terminal.app'te elle test edebilmek için bir çalıştırıcı. Mevcut REPL varsayılan kalır; kabuk yalnızca `FUSION_FULLSCREEN=1` ile açılır. Böylece Faz 1 üründe hiçbir davranışı değiştirmez.

**Files:**
- Modify: `src/fusion_cli/cli/repl/screen.py`
- Modify: `src/fusion_cli/cli/repl/loop.py` (yalnızca giriş dallanması; mevcut yol aynen kalır)
- Test: `tests/test_screen.py`

**Interfaces:**
- Consumes: `FusionScreen`, `echo_submit`, `install_app_cursor_mode`, `APP_CURSOR_OFF`.
- Produces: `run_screen_demo() -> None` — reçeteyi kurup eko kabuğunu çalıştırır, çıkışta modu geri alır.
- Produces (loop.py): `run_repl` başında, `FUSION_FULLSCREEN=1` ise `run_screen_demo()` çağrılıp erken dönülür.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_screen.py içine ekle
def test_demo_calistirici_mevcut(monkeypatch):
    """run_screen_demo çağrılabilir olmalı; app.run yerine sahte konur (headless)."""
    import fusion_cli.cli.repl.screen as screen_mod

    cagrildi = {"run": False, "restore": False}

    class _SahteApp:
        full_screen = True

        def run(self) -> None:
            cagrildi["run"] = True

    def _sahte_screen(*a, **k):
        s = object.__new__(screen_mod.FusionScreen)
        s.application = _SahteApp()  # type: ignore[attr-defined]
        return s

    monkeypatch.setattr(screen_mod, "FusionScreen", _sahte_screen)
    monkeypatch.setattr(screen_mod, "install_app_cursor_mode", lambda app: None)
    monkeypatch.setattr(
        screen_mod.sys.stdout, "write", lambda s: cagrildi.__setitem__("restore", True)
    )

    screen_mod.run_screen_demo()

    assert cagrildi["run"] is True
    assert cagrildi["restore"] is True  # çıkışta mod geri alındı
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_screen.py::test_demo_calistirici_mevcut -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'run_screen_demo'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/fusion_cli/cli/repl/screen.py — importlara ekle
import sys
```

```python
# src/fusion_cli/cli/repl/screen.py — sona ekle
_DEMO_BANNER = "  ✦ fusion — tam-ekran (deneysel) · çıkış: Ctrl-Q"


def run_screen_demo() -> None:
    """Eko kabuğunu gerçek terminalde çalıştır (elle doğrulama).

    Reçete: uygulama imleç modu kurulur; çıkışta normal moda dönülür.
    """
    screen = FusionScreen(banner=_DEMO_BANNER, on_submit=lambda t: None)
    # on_submit kabuğun kendisine ihtiyaç duyduğundan kapanışla bağlanır:
    screen._on_submit = lambda t: echo_submit(screen, t)  # type: ignore[attr-defined]
    install_app_cursor_mode(screen.application)
    try:
        screen.application.run()
    finally:
        sys.stdout.write(APP_CURSOR_OFF)
        sys.stdout.flush()
```

```python
# src/fusion_cli/cli/repl/loop.py — run_repl gövdesinin EN BAŞINA ekle
# (mevcut kod bundan sonra aynen kalır)
    import os

    if os.environ.get("FUSION_FULLSCREEN") == "1":
        from .screen import run_screen_demo

        run_screen_demo()
        return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_screen.py::test_demo_calistirici_mevcut -v`
Expected: PASS

- [ ] **Step 5: Elle görsel doğrulama (gerçek Terminal.app)**

Yeni bir Terminal.app sekmesinde:

```bash
FUSION_FULLSCREEN=1 fusion
```

Kontrol: mesaj yaz + Enter → `[ben]`/`[eko]` konuşmaya akar; ok/PageUp ile kaydır; fare tekerleğiyle kaydır; pencereyi resize et (çoğalma YOK); yukarı kaydır (eski shell GÖRÜNMEZ); Ctrl-Q → terminal geri gelir. Bir sorun varsa Task'e dönülür.

- [ ] **Step 6: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src/fusion_cli/cli/repl/screen.py src/fusion_cli/cli/repl/loop.py tests/test_screen.py
.venv/bin/mypy src/fusion_cli/cli/repl/screen.py src/fusion_cli/cli/repl/loop.py
.venv/bin/python -m pytest -q
git add src/fusion_cli/cli/repl/screen.py src/fusion_cli/cli/repl/loop.py tests/test_screen.py
git commit -m "feat(repl): deneysel tam-ekran kabuk çalıştırıcısı (FUSION_FULLSCREEN)"
```

---

## Self-Review Notları

- **Spec kapsamı (Faz 1):** full_screen + reçete (Task 1, 3), banner/konuşma/çalışma satırı/giriş (Task 3), imleç-tabanlı kaydırma (Task 2, 3), eko turu uçtan uca (Task 4, 5), mevcut REPL'e dokunmama (Task 5 env bayrağı). Karşılandı.
- **Sonraki fazlar:** ANSI köprüsü + gerçek akış (Faz 2), onay/soru modalları (Faz 3), cila + konuşma kırpma (Faz 4), geçiş (Faz 5) — kendi planlarını alacak.
- **Bilinen açık nokta (Faz 2'ye taşınan):** Konuşma alanı Faz 1'de düz metin `TextArea`. ANSI renkli içerik (markdown/kod/ diff) için Faz 2'de `TextArea` yerine ANSI'yi çözen bir kontrol (`FormattedTextControl(ANSI(...))` + kaydırma) gerekebilir; gerekirse ayrı bir spike ile netleşecek.
- **Tip tutarlılığı:** `append_text`/`scroll_lines` `Buffer` alır; `FusionScreen.conversation_buffer` `Buffer` döner; `on_submit: Callable[[str], None]` her yerde tutarlı.
