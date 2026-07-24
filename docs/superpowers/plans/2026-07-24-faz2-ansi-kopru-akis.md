# Faz 2 — ANSI Köprüsü + Gerçek Akış Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gerçek motor turlarını (fusion + agent) tam-ekran kabuğa, Rich biçimlendirmesini koruyan bir ANSI köprüsüyle akıtmak.

**Architecture:** `ConsoleRenderer`'ın Rich çıktısı bir tamponlu `Console`'a (`StringIO`, `force_terminal=True`) yönlendirilir; üretilen ANSI deltası konuşma alanının `FormattedTextControl(ANSI(...))` kontrolüne akıtılır. Çalışma satırı ayrı bir olay dinleyicisiyle beslenir; Rich `Live` bridged renderer'da kapatılır. Kabuk hâlâ `FUSION_FULLSCREEN=1` arkasında; motor katmanı ve mevcut REPL yolu değişmez.

**Tech Stack:** Python 3.11, prompt_toolkit 3.0.52, Rich, pytest, ruff, mypy.

## Global Constraints

- Kod içi her şey Türkçe: docstring, yorum, log, hata ve kullanıcıya görünen metinler. Tanımlayıcılar İngilizce + PEP 8.
- Motor/çekirdek katmanına DOKUNULMAZ: `engines/`, `providers/`, `memory/`, `core/`, `config/`, `tools/`, `observability/`. `ui/renderer.py`'nin Rich render **mantığı** değişmez (yalnızca Live'ı kapatan bir bayrak eklenir).
- Mevcut normal-tampon REPL yolu (`FUSION_FULLSCREEN` bayrağı YOKken) DEĞİŞMEZ.
- prompt_toolkit sürümü 3.0.52'ye sabit.
- Python komutları `.venv/bin/python` ile çalıştırılır.
- Her task sonunda kalite kapısı: `.venv/bin/ruff check <dosyalar>` + `.venv/bin/mypy <dosyalar>` + `.venv/bin/python -m pytest -q` üçü de temiz olmadan commit yok.
- Commit mesajları conventional commit, Türkçe açıklama, faz/adım numarası GEÇMEZ, author/co-author eklenmez.
- `main` üzerinde çalışılır; yeni branch, force push, hard reset yapılmaz.

---

### Task 1: `AnsiBridge` — ANSI köprüsü (saf çekirdek)

`ConsoleRenderer`'ın yazacağı tamponlu bir Rich `Console` kurar; her olaydan sonra `drain()` ile StringIO'da biriken yeni ANSI'yi okuyup `text`'e ekler. Terminal gerektirmez.

**Files:**
- Create: `src/fusion_cli/cli/repl/ansi_bridge.py`
- Test: `tests/test_ansi_bridge.py`

**Interfaces:**
- Consumes: (yok)
- Produces:
  - `AnsiBridge()` — köprü.
  - `AnsiBridge.console -> rich.console.Console` (property) — renderer'a verilecek tamponlu console.
  - `AnsiBridge.drain() -> str` — StringIO'da biriken yeni delta'yı döndürür ve `text`'e ekler.
  - `AnsiBridge.text -> str` (property) — o ana kadar birikmiş tüm ANSI.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ansi_bridge.py
"""ANSI köprüsü — Rich çıktısını ANSI olarak biriktirir."""

from __future__ import annotations


def test_kopru_baslangicta_bostur():
    from fusion_cli.cli.repl.ansi_bridge import AnsiBridge

    kopru = AnsiBridge()
    assert kopru.text == ""
    assert kopru.drain() == ""


def test_drain_yeni_deltayi_dondurur_ve_biriktirir():
    from fusion_cli.cli.repl.ansi_bridge import AnsiBridge

    kopru = AnsiBridge()
    kopru.console.print("merhaba")
    delta1 = kopru.drain()
    assert "merhaba" in delta1
    assert kopru.text == delta1

    kopru.console.print("dünya")
    delta2 = kopru.drain()
    assert "dünya" in delta2
    assert "merhaba" not in delta2  # delta yalnızca YENİ kısım
    assert kopru.text == delta1 + delta2


def test_konsol_renk_uretir():
    from fusion_cli.cli.repl.ansi_bridge import AnsiBridge

    kopru = AnsiBridge()
    kopru.console.print("[red]hata[/red]")
    delta = kopru.drain()
    assert "\x1b[" in delta  # ANSI kaçış dizisi üretildi (force_terminal)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_ansi_bridge.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fusion_cli.cli.repl.ansi_bridge'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/fusion_cli/cli/repl/ansi_bridge.py
"""ANSI köprüsü — Rich render mantığını yeniden yazmadan tam-ekrana taşır.

`ConsoleRenderer` bir Rich `Console`'a yazar. Burada o console'u stdout yerine bir
`StringIO`'ya bağlarız ve `force_terminal=True` ile renk üretmesini sağlarız.
Böylece tüm biçimlendirme (markdown, kod, tablo, renkli diff) ANSI olarak birikir
ve konuşma alanına akıtılabilir.
"""

from __future__ import annotations

import io

from rich.console import Console


class AnsiBridge:
    """Rich çıktısını ANSI metnine çeviren tamponlu köprü."""

    def __init__(self) -> None:
        self._buffer = io.StringIO()
        # force_terminal: StringIO'da bile renk üret. soft_wrap: satırları Rich
        # kendisi sarmasın; sarma prompt_toolkit tarafında yapılır.
        self._console = Console(file=self._buffer, force_terminal=True, soft_wrap=True)
        self._text = ""
        self._okundu = 0

    @property
    def console(self) -> Console:
        return self._console

    @property
    def text(self) -> str:
        return self._text

    def drain(self) -> str:
        """StringIO'da biriken yeni delta'yı döndür ve toplam metne ekle."""
        tumu = self._buffer.getvalue()
        delta = tumu[self._okundu :]
        self._okundu = len(tumu)
        self._text += delta
        return delta
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_ansi_bridge.py -q`
Expected: PASS (3 test)

- [ ] **Step 5: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src/fusion_cli/cli/repl/ansi_bridge.py tests/test_ansi_bridge.py
.venv/bin/mypy src/fusion_cli/cli/repl/ansi_bridge.py
.venv/bin/python -m pytest -q
git add src/fusion_cli/cli/repl/ansi_bridge.py tests/test_ansi_bridge.py
git commit -m "feat(repl): Rich çıktısını ANSI'ye çeviren köprü"
```

---

### Task 2: `ConsoleRenderer`'da Live'ı kapatma bayrağı

Bridged console `force_terminal=True` olduğu için `WorkIndicator` `is_terminal` görür ve Rich `Live` başlatır; bu, spinner/imleç dizilerini konuşma tamponuna sızdırır. `ConsoleRenderer`'a Live'ı kapatan bir bayrak eklenir. Render mantığı değişmez.

**Files:**
- Modify: `src/fusion_cli/ui/renderer.py:66-88` (kurucu + `WorkIndicator` kurulumu)
- Test: `tests/test_renderer_live_bayragi.py`

**Interfaces:**
- Consumes: (yok)
- Produces: `ConsoleRenderer(console, *, ..., live_progress: bool = True)` — `live_progress=False` iken içteki `WorkIndicator` `enabled=False` kurulur (Live hiç başlamaz).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_renderer_live_bayragi.py
"""Bridged renderer'da Rich Live kapatılabilmeli (buffer'a sızmasın)."""

from __future__ import annotations

import io

from rich.console import Console


def _tamponlu_console() -> Console:
    return Console(file=io.StringIO(), force_terminal=True, soft_wrap=True)


def test_live_progress_false_ise_gosterge_devre_disi():
    from fusion_cli.ui.renderer import ConsoleRenderer

    renderer = ConsoleRenderer(_tamponlu_console(), live_progress=False)
    # WorkIndicator enabled=False olmalı: force_terminal olsa bile Live başlamaz.
    assert renderer._work._enabled is False


def test_varsayilan_live_progress_acik():
    from fusion_cli.ui.renderer import ConsoleRenderer

    renderer = ConsoleRenderer(_tamponlu_console())
    # Varsayılan davranış korunur: terminal console'da gösterge açık.
    assert renderer._work._enabled is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_renderer_live_bayragi.py -q`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'live_progress'`

- [ ] **Step 3: Write minimal implementation**

`src/fusion_cli/ui/renderer.py` kurucusuna `live_progress` parametresini ekle ve `WorkIndicator`'a geçir. Mevcut satırlar (`66-88`) şu hâle gelir:

```python
    def __init__(
        self,
        console: Console | None = None,
        *,
        show_progress: bool = True,
        show_all_answers: bool = False,
        show_call_details: bool = False,
        live_progress: bool = True,
    ) -> None:
        self._console = console or Console()
        self._show_progress = show_progress
        self._show_all_answers = show_all_answers
        # Fusion'da hangi adayın ne kadar sürdüğü bilgi verir; agent'ta her adım
        # için satır basmak tur özetiyle çakışır ve gürültü olur.
        self._show_call_details = show_call_details
        self._line_open = False
        self._active_channel: Channel | None = None
        # Kanal başına ham akış tamponu. Düşünme bloklarının kapanışını beklemek
        # için ham metni saklamak zorundayız; görünür kısmı ondan türetiriz.
        self._raw: dict[Channel, str] = {}
        self._shown: dict[Channel, int] = {}
        # Model çalışırken görünen canlı satır. Ekrana bir şey basılmadan önce
        # daima duraklatılır; akan metnin üstüne binmez. Tam-ekran köprüsünde
        # `live_progress=False` verilir: Live yerine layout çalışma satırı beslenir.
        self._work = WorkIndicator(self._console, enabled=live_progress)
        #: Basılmayı bekleyen durum satırı — bkz. `_status`.
        self._pending_status: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_renderer_live_bayragi.py -q`
Expected: PASS (2 test)

- [ ] **Step 5: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src/fusion_cli/ui/renderer.py tests/test_renderer_live_bayragi.py
.venv/bin/mypy src/fusion_cli/ui/renderer.py
.venv/bin/python -m pytest -q
git add src/fusion_cli/ui/renderer.py tests/test_renderer_live_bayragi.py
git commit -m "feat(ui): renderer'a canlı göstergeyi kapatan bayrak"
```

---

### Task 3: `WorkLineSink` — olay beslemeli çalışma satırı

Rich `Live` kapalı olduğundan görünür çalışma satırını ayrı bir olay dinleyicisi besler. Model başlar/biter olaylarından "hazırlanıyor… Ns · token · model" metnini üretir ve bir geri çağrıya iletir. Spinner yok (animasyon Faz 4 cilası); süre/token/model olaylarla güncellenir.

**Files:**
- Create: `src/fusion_cli/cli/repl/work_line.py`
- Test: `tests/test_work_line.py`

**Interfaces:**
- Consumes: `format_tokens` (`fusion_cli/ui/work.py`), `format_duration` (`fusion_cli/ui/text.py`), olay tipleri (`fusion_cli/core/events.py`).
- Produces:
  - `WorkLineSink(on_update: Callable[[str], None], on_clear: Callable[[], None])`
  - `.handle(event) -> None` — `EventSink` protokolüne uyar; ilgili olaylarda `on_update`/`on_clear` çağırır.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_work_line.py
"""Olay beslemeli çalışma satırı — model olaylarından metin üretir."""

from __future__ import annotations

from fusion_cli.core.events import (
    ModelCallFinished,
    ModelCallStarted,
    TurnFinished,
)
from fusion_cli.core.types import CompletionResult, TokenUsage


def _bitti(tokens: int) -> ModelCallFinished:
    sonuc = CompletionResult(
        text="x", usage=TokenUsage(total_tokens=tokens), ok=True
    )
    return ModelCallFinished(role="nemotron", result=sonuc, background=False)


def test_model_baslayinca_calisma_satiri_guncellenir():
    from fusion_cli.cli.repl.work_line import WorkLineSink

    satirlar: list[str] = []
    temizlendi: list[bool] = []
    sink = WorkLineSink(satirlar.append, lambda: temizlendi.append(True))

    sink.handle(ModelCallStarted(role="nemotron", background=False))

    assert satirlar, "başlangıçta bir çalışma satırı yayınlanmalı"
    assert "nemotron" in satirlar[-1]


def test_token_bilgisi_satira_yansir():
    from fusion_cli.cli.repl.work_line import WorkLineSink

    satirlar: list[str] = []
    sink = WorkLineSink(satirlar.append, lambda: None)

    sink.handle(ModelCallStarted(role="nemotron", background=False))
    sink.handle(_bitti(1200))

    assert "1.2k" in satirlar[-1]  # format_tokens: 1200 → 1.2k


def test_tur_bitince_satir_temizlenir():
    from fusion_cli.cli.repl.work_line import WorkLineSink

    temizlendi: list[bool] = []
    sink = WorkLineSink(lambda s: None, lambda: temizlendi.append(True))

    sink.handle(ModelCallStarted(role="nemotron", background=False))
    sink.handle(TurnFinished())

    assert temizlendi == [True]
```

> **Doğrulama notu (implementer):** `ModelCallStarted`, `ModelCallFinished`,
> `TurnFinished`, `CompletionResult`, `TokenUsage`'ın gerçek alan adlarını
> `src/fusion_cli/core/events.py` ve `src/fusion_cli/core/types.py`'dan teyit et;
> testteki kurucu çağrılarını gerçek imzalara göre düzelt (ör. `total_tokens`
> alanının adı farklıysa). Olay→satır davranışı aynı kalır.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_work_line.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fusion_cli.cli.repl.work_line'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/fusion_cli/cli/repl/work_line.py
"""Olay beslemeli çalışma satırı.

Tam-ekranda Rich `Live` kullanılamaz (spinner/imleç dizileri konuşma tamponuna
sızar). Bunun yerine bu dinleyici, model olaylarından layout çalışma satırının
metnini üretir: "hazırlanıyor…  Ns · token · model". Spinner yoktur; süre/token
olaylarla güncellenir (animasyon Faz 4 cilasıdır).
"""

from __future__ import annotations

import time
from collections.abc import Callable

from ...core.events import Event, ModelCallFinished, ModelCallStarted, TurnFinished
from ...ui import messages
from ...ui.text import format_duration
from ...ui.work import format_tokens


class WorkLineSink:
    """Model olaylarını dinleyip çalışma satırı metnini besler."""

    def __init__(
        self, on_update: Callable[[str], None], on_clear: Callable[[], None]
    ) -> None:
        self._on_update = on_update
        self._on_clear = on_clear
        self._model = ""
        self._tokens = 0
        self._started_at = 0.0

    def handle(self, event: Event) -> None:
        if isinstance(event, ModelCallStarted):
            if event.background:
                return
            self._model = event.role
            self._tokens = 0
            self._started_at = time.monotonic()
            self._yayınla()
        elif isinstance(event, ModelCallFinished):
            if event.background:
                return
            self._tokens += event.result.usage.total_tokens
            self._yayınla()
        elif isinstance(event, TurnFinished):
            self._on_clear()

    def _yayınla(self) -> None:
        elapsed_ms = int((time.monotonic() - self._started_at) * 1000)
        parcalar = [format_duration(elapsed_ms)]
        if self._tokens:
            parcalar.append(messages.WORK_TOKENS.format(count=format_tokens(self._tokens)))
        if self._model:
            parcalar.append(self._model)
        detay = " · ".join(parcalar)
        self._on_update(f"  {messages.WORK_THINKING}  {detay}")
```

> **Doğrulama notu (implementer):** `event.result.usage.total_tokens` ve
> `event.role`/`event.background` alan adlarını gerçek olay tanımından teyit et;
> farklıysa düzelt. `messages.WORK_TOKENS`/`WORK_THINKING`'in var olduğunu
> `ui/messages.py`'dan doğrula (renderer bunları kullanıyor).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_work_line.py -q`
Expected: PASS (3 test)

- [ ] **Step 5: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src/fusion_cli/cli/repl/work_line.py tests/test_work_line.py
.venv/bin/mypy src/fusion_cli/cli/repl/work_line.py
.venv/bin/python -m pytest -q
git add src/fusion_cli/cli/repl/work_line.py tests/test_work_line.py
git commit -m "feat(repl): olay beslemeli çalışma satırı dinleyicisi"
```

---

### Task 4: ANSI konuşma kontrolü + kaydırma (risk noktası)

`FusionScreen`'in konuşma alanı düz `TextArea`'dan, `AnsiBridge` metnini renkli gösteren `FormattedTextControl(ANSI(...))` sarılı kaydırılabilir bir `Window`'a döner. Kaydırma imleç yerine `window.vertical_scroll` ile yapılır; temel takip modu eklenir. Faz 1'in buffer-tabanlı `append_text`/`scroll_lines`/`echo_submit` yolları ve testleri bu yeni modele göre güncellenir. **Bu, planın işaret ettiği risk noktasıdır; kendi elle görsel doğrulamasını alır.**

**Files:**
- Modify: `src/fusion_cli/cli/repl/screen.py` (konuşma kontrolü, kaydırma, çalışma satırı API'si; eski buffer yolları kaldırılır)
- Test: `tests/test_screen.py` (buffer-tabanlı testler kaldırılır/uyarlanır; kaydırma matematiği testleri eklenir)

**Interfaces:**
- Consumes: `AnsiBridge` (Task 1).
- Produces:
  - `clamp_scroll(vertical_scroll: int, delta: int, max_scroll: int) -> int` — saf kaydırma sınırlama fonksiyonu; `[0, max_scroll]` içinde.
  - `FusionScreen(banner: str, on_submit: Callable[[str], None])` — artık içinde bir `AnsiBridge` tutar.
  - `FusionScreen.bridge -> AnsiBridge`
  - `FusionScreen.after_event() -> None` — köprüyü drain eder, takip modundaysa en alta çeker, `invalidate` çağırır.
  - `FusionScreen.set_work(text: str) -> None` / `FusionScreen.clear_work() -> None`
  - `FusionScreen.conversation_text -> str` (property; `bridge.text`)

- [ ] **Step 1: Write the failing test**

`tests/test_screen.py`'daki Faz 1 buffer testlerini (`test_metin_sona_eklenir_ve_imlec_sonda`, `test_kaydirma_imleci_satir_bazli_tasir_ve_sinirlanir`, `test_eko_turu_kullanici_ve_yaniti_yazar`, `_bos_buffer`) ve `append_text`/`scroll_lines`/`echo_submit`'e dayanan importları **kaldır**. Yerine kaydırma matematiği ve yeni konuşma API'si testlerini ekle:

```python
def test_clamp_scroll_sinirlar_icinde_kalir():
    from fusion_cli.cli.repl.screen import clamp_scroll

    assert clamp_scroll(5, -2, 10) == 3
    assert clamp_scroll(5, -100, 10) == 0    # üst sınır
    assert clamp_scroll(5, +100, 10) == 10   # alt sınır (max_scroll)
    assert clamp_scroll(0, +3, 0) == 0       # kaydırılacak yer yoksa 0


def test_konusma_kopruden_beslenir():
    from fusion_cli.cli.repl.screen import FusionScreen

    ekran = FusionScreen(banner="✦ fusion", on_submit=lambda s: None)
    ekran.bridge.console.print("merhaba")
    ekran.after_event()

    assert "merhaba" in ekran.conversation_text


def test_calisma_satiri_ayarlanir_ve_temizlenir():
    from fusion_cli.cli.repl.screen import FusionScreen

    ekran = FusionScreen(banner="✦ fusion", on_submit=lambda s: None)
    ekran.set_work("hazırlanıyor…")
    assert "hazırlanıyor" in ekran.work_text
    ekran.clear_work()
    assert ekran.work_text == ""
```

Faz 1'den korunacak testler: `test_imlec_modu_uygulama_moduna_alinir`, `test_kabuk_full_screen_ve_mouse_kapali_kurulur` (mouse/full_screen değişmedi).

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_screen.py -q`
Expected: FAIL — `ImportError: cannot import name 'clamp_scroll'` (ve kaldırılan fonksiyonlara bağlı testler artık yok)

- [ ] **Step 3: Write minimal implementation**

`screen.py`'da şu değişiklikler yapılır:

1. Importları güncelle: `Buffer`/`Document`/`TextArea` kaldır (artık kullanılmıyor); ekle:

```python
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.containers import ConditionalContainer, HSplit, Window
from prompt_toolkit.widgets import Frame

from .ansi_bridge import AnsiBridge
```

2. `append_text`, `scroll_lines`, `echo_submit` fonksiyonlarını ve `_SCROLL_STEP`/`_SCROLL_PAGE` dışındaki buffer yardımcılarını **kaldır**. Yerine saf kaydırma fonksiyonu ekle:

```python
def clamp_scroll(vertical_scroll: int, delta: int, max_scroll: int) -> int:
    """Dikey kaydırmayı `[0, max_scroll]` aralığında tutarak `delta` kadar taşı."""
    return max(0, min(max_scroll, vertical_scroll + delta))
```

3. `FusionScreen`'i ANSI köprüsüne göre yeniden kur. Konuşma alanı artık köprü metnini gösteren salt-okunur, kaydırılabilir bir `Window`. Çalışma satırı ayrı bir `Window`. Takip modu: kullanıcı en alttaysa yeni içerik alta yapışır.

```python
class FusionScreen:
    """Tam-ekran kabuk: banner + konuşma (ANSI) + çalışma satırı + giriş kutusu."""

    def __init__(self, banner: str, on_submit: Callable[[str], None]) -> None:
        self._on_submit = on_submit
        self._bridge = AnsiBridge()
        self._work_text = ""
        # Kullanıcı en alttaysa yeni içerik takip edilir; yukarı kaydırdıysa yerinde kalır.
        self._follow = True

        self._conversation_window = Window(
            content=FormattedTextControl(lambda: ANSI(self._bridge.text)),
            wrap_lines=True,
            always_hide_cursor=True,
        )
        self._work_window = Window(
            content=FormattedTextControl(lambda: ANSI(self._work_text)), height=1
        )
        self._input = TextAreaInput(on_submit=self._handle_submit)  # bkz. aşağıdaki not

        root = HSplit(
            [
                Window(content=FormattedTextControl(banner), height=3),
                Frame(self._conversation_window, title="konuşma"),
                self._work_window,
                Frame(self._input.control_container, title="mesaj"),
            ]
        )
        self.application: Application[Any] = Application(
            layout=Layout(root, focused_element=self._input.control_container),
            key_bindings=self._bindings(),
            full_screen=True,
            mouse_support=False,
        )

    @property
    def bridge(self) -> AnsiBridge:
        return self._bridge

    @property
    def conversation_text(self) -> str:
        return self._bridge.text

    @property
    def work_text(self) -> str:
        return self._work_text

    def set_work(self, text: str) -> None:
        self._work_text = text
        self.application.invalidate()

    def clear_work(self) -> None:
        self._work_text = ""
        self.application.invalidate()

    def after_event(self) -> None:
        """Motor olayından sonra: köprüyü drain et, takip modundaysa en alta çek."""
        self._bridge.drain()
        if self._follow:
            self._scroll_to_bottom()
        self.application.invalidate()

    def _scroll_to_bottom(self) -> None:
        info = self._conversation_window.render_info
        if info is None:
            return
        self._conversation_window.vertical_scroll = max(
            0, info.content_height - info.window_height
        )

    def _handle_submit(self, text: str) -> None:
        stripped = text.strip()
        if stripped:
            self._on_submit(stripped)
```

> **Uyarlama notu (implementer):** Yukarıdaki `TextAreaInput` sözde bir sarmalayıcıdır;
> Faz 1'de giriş kutusu doğrudan `TextArea(height=1, prompt="❯ ", multiline=False)`
> ve `accept_handler`'dı. O deseni AYNEN koru — yeni bir sarmalayıcı UYDURMA. Yani:
> `self._input = TextArea(height=1, prompt="❯ ", multiline=False, wrap_lines=False)`,
> `self._input.accept_handler = self._handle_submit_pt`, layout'ta `Frame(self._input, ...)`,
> ve `_handle_submit_pt(buff: Buffer) -> bool` içinde `text=self._input.text; self._input.text=""`
> yapıp `False` döndür. `focused_element=self._input`. Bu not, ANSI konuşma kontrolü
> dışındaki her şeyin Faz 1'deki gibi kalmasını sağlamak içindir.

4. `_bindings` içindeki kaydırma tuşlarını yeni modele bağla (imleç yerine `vertical_scroll`):

```python
    def _bindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("c-q")
        @kb.add("c-c")
        def _exit(event: Any) -> None:
            event.app.exit()

        def _kaydir(delta: int) -> None:
            info = self._conversation_window.render_info
            max_scroll = 0 if info is None else max(0, info.content_height - info.window_height)
            self._conversation_window.vertical_scroll = clamp_scroll(
                self._conversation_window.vertical_scroll, delta, max_scroll
            )
            # Kullanıcı en alttan ayrıldıysa takip modunu kapat; alta döndüyse aç.
            self._follow = self._conversation_window.vertical_scroll >= max_scroll
            self.application.invalidate()

        @kb.add("up", eager=True)
        def _up(_e: Any) -> None:
            _kaydir(-_SCROLL_STEP)

        @kb.add("down", eager=True)
        def _down(_e: Any) -> None:
            _kaydir(+_SCROLL_STEP)

        @kb.add("pageup", eager=True)
        def _pgup(_e: Any) -> None:
            _kaydir(-_SCROLL_PAGE)

        @kb.add("pagedown", eager=True)
        def _pgdn(_e: Any) -> None:
            _kaydir(+_SCROLL_PAGE)

        return kb
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_screen.py -q`
Expected: PASS (korunan + yeni testler)

- [ ] **Step 5: Elle görsel doğrulama (gerçek Terminal.app)**

Bu task henüz gerçek turu bağlamadığından, kontrolün ANSI gösterdiğini geçici bir kod parçasıyla değil, **Task 6 sonundaki uçtan uca doğrulamada** teyit edeceğiz. Şimdilik yalnızca birim testleri + kalite kapısı yeterli. (Kaydırma/renk görsel doğrulaması Task 6'da yapılır; bu not bilinçlidir.)

- [ ] **Step 6: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src/fusion_cli/cli/repl/screen.py tests/test_screen.py
.venv/bin/mypy src/fusion_cli/cli/repl/screen.py
.venv/bin/python -m pytest -q
git add src/fusion_cli/cli/repl/screen.py tests/test_screen.py
git commit -m "feat(repl): konuşma alanını ANSI kontrolüne ve vertical_scroll kaydırmaya taşı"
```

---

### Task 5: Tur koşucusu + etkileşimsiz prompter

Girişten gelen metni, bridged renderer + çalışma satırı + drain-pompası dinleyicileriyle motor turuna (fusion/agent) bağlayan koşucu. Full-screen'de stdin okunamayacağından onay/soru için **etkileşimsiz prompter** kullanılır (`confirm→False`, `ask→cevap yok`); gerçek modal Faz 3.

**Files:**
- Create: `src/fusion_cli/cli/repl/screen_turn.py`
- Test: `tests/test_screen_turn.py`

**Interfaces:**
- Consumes: `FusionScreen` (Task 4), `AnsiBridge`, `ConsoleRenderer(live_progress=False)` (Task 2), `WorkLineSink` (Task 3), `run_task`/`run_agent_task` (`cli/session.py`).
- Produces:
  - `NonInteractivePrompter` — `async confirm(request) -> bool` (False), `async ask(question) -> str` (`messages.NO_ANSWER_AVAILABLE`).
  - `PumpSink(on_event: Callable[[], None])` — her olayda `on_event` çağırır (drain + invalidate + follow).
  - `async run_turn(line: str, state: ReplState, screen: FusionScreen) -> None` — motoru seçip turu çalıştırır; çıktı konuşmaya akar.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_screen_turn.py
"""Tur koşucusu — olayları konuşmaya pompalar, onayları etkileşimsiz karşılar."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_etkilesimsiz_prompter_reddeder():
    from fusion_cli.cli.repl.screen_turn import NonInteractivePrompter

    prompter = NonInteractivePrompter()
    assert await prompter.confirm(object()) is False
    cevap = await prompter.ask("emin misin?")
    assert isinstance(cevap, str)


def test_pump_her_olayda_geri_cagirir():
    from fusion_cli.cli.repl.screen_turn import PumpSink

    sayac = {"n": 0}
    pump = PumpSink(lambda: sayac.__setitem__("n", sayac["n"] + 1))
    pump.handle(object())
    pump.handle(object())
    assert sayac["n"] == 2
```

> **Doğrulama notu (implementer):** `run_turn`'ün gerçek motor entegrasyonu saf
> birim testinde çalıştırılamaz (ağ/model gerekir). Bu yüzden `run_turn` için
> testte `run_task`/`run_agent_task`'i monkeypatch ederek yalnızca **doğru motorun
> seçildiğini ve sinks demetinin `renderer, work, pump`'ı içerdiğini** doğrula.
> `ReplState.engine` (`Engine.FUSION`/`Engine.AGENT`) alanını `state.py`'dan teyit et.
> Gerçek akış Step 5'te elle doğrulanır.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_screen_turn.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fusion_cli.cli.repl.screen_turn'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/fusion_cli/cli/repl/screen_turn.py
"""Tur koşucusu — girişi motora bağlar, çıktıyı tam-ekran konuşmaya akıtır.

Faz 2 kapsamı: fusion + agent turları akar. Onay/soru full-screen'de terminal
devralınamadığından etkileşimsiz karşılanır (reddet / cevap yok); gerçek modal
Faz 3'te eklenir.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ...core.events import Event
from ...ui import messages
from ...ui.renderer import ConsoleRenderer
from ..session import run_agent_task, run_task
from .state import Engine
from .work_line import WorkLineSink

if TYPE_CHECKING:  # pragma: no cover
    from .screen import FusionScreen
    from .state import ReplState


class NonInteractivePrompter:
    """Full-screen'de stdin okunamaz: onayı reddeder, soruya cevap yok döner."""

    async def confirm(self, request: Any) -> bool:
        return False

    async def ask(self, question: str) -> str:
        return messages.NO_ANSWER_AVAILABLE


class PumpSink:
    """Her olaydan sonra bir geri çağrı tetikler (drain + invalidate + follow)."""

    def __init__(self, on_event: Callable[[], None]) -> None:
        self._on_event = on_event

    def handle(self, event: Event) -> None:
        self._on_event()


async def run_turn(line: str, state: "ReplState", screen: "FusionScreen") -> None:
    renderer = ConsoleRenderer(
        screen.bridge.console, live_progress=False, show_call_details=True
    )
    work = WorkLineSink(screen.set_work, screen.clear_work)
    pump = PumpSink(screen.after_event)
    sinks = (renderer, work, pump, state.cost)

    if state.engine is Engine.FUSION:
        await run_task(
            line,
            state.config,
            sinks=sinks,
            task_type=state.task_type,
            synthesis=state.synthesis,
            memory=state.memory,
        )
    else:
        await run_agent_task(
            line,
            state.config,
            sinks=sinks,
            prompter_factory=lambda _drain: NonInteractivePrompter(),
            mode=state.approval,
            root=state.root,
            interactive=False,
            memory=state.memory,
        )
```

> **Doğrulama notu (implementer):** `ReplState`'in `cost`, `task_type`, `synthesis`,
> `memory`, `approval`, `root`, `engine` alanlarının gerçek adlarını `state.py` ve
> `loop.py`'daki mevcut `_fusion_turn`/`_agent_turn` kullanımından teyit et; farklıysa
> düzelt. `run_agent_task`'in `mode` parametresi `ApprovalMode` alır — `state.approval`'ın
> tipi buysa doğrudan geç, değilse dönüşümü `loop.py`'daki mevcut çağrıdan kopyala.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_screen_turn.py -q`
Expected: PASS (3 test — asyncio işareti dahil)

> **Not:** Testte `@pytest.mark.asyncio` kullanılıyor; projenin `pytest.ini`/
> `pyproject.toml`'unda `asyncio_mode` ayarını kontrol et (mevcut async testler
> nasıl işaretleniyorsa aynısını uygula; gerekiyorsa işareti kaldır).

- [ ] **Step 5: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src/fusion_cli/cli/repl/screen_turn.py tests/test_screen_turn.py
.venv/bin/mypy src/fusion_cli/cli/repl/screen_turn.py
.venv/bin/python -m pytest -q
git add src/fusion_cli/cli/repl/screen_turn.py tests/test_screen_turn.py
git commit -m "feat(repl): motor turunu tam-ekran konuşmaya bağlayan koşucu"
```

---

### Task 6: Kabuğa bağlama + gerçek çalıştırıcı (uçtan uca)

Giriş `accept_handler` turu arka plan görevi olarak başlatır; Ctrl-C çalışan turu keser. `run_screen_demo` eko yerine gerçek turu çalıştırır (hâlâ `FUSION_FULLSCREEN=1` arkasında). Mevcut `run_repl` yolu değişmez. Uçtan uca elle görsel doğrulama burada yapılır.

**Files:**
- Modify: `src/fusion_cli/cli/repl/screen.py` (gerçek çalıştırıcı; `run_turn` bağlanışı)
- Test: `tests/test_screen.py`

**Interfaces:**
- Consumes: `run_turn` (Task 5), `install_app_cursor_mode`, `APP_CURSOR_OFF` (Faz 1).
- Produces: `async run_screen_repl(state: ReplState) -> int` — reçeteyi kurar, `FusionScreen`'i `run_turn` ile bağlar, `app.run_async()` await eder, çıkışta modu geri alır.
- Değişir: `run_screen_demo` yerini `run_screen_repl` alır; `loop.py`'daki dallanma onu çağırır (aşağıdaki not).

- [ ] **Step 1: Write the failing test**

Faz 1'in `test_demo_calistirici_calisan_loop_icinde_await_edilir` testini `run_screen_repl`'e uyarla: artık `ReplState` alır ve `run_turn` bağlanır; `app.run_async` sahtelenir, çıkışta modun geri alındığı doğrulanır.

```python
def test_screen_repl_calisan_loop_icinde_await_edilir():
    """run_screen_repl zaten çalışan event loop'tan await edilebilmeli; mod geri alınmalı."""
    import asyncio

    import fusion_cli.cli.repl.screen as screen_mod

    cagrildi = {"run": False, "restore": False}

    class _SahteApp:
        full_screen = True

        async def run_async(self) -> None:
            cagrildi["run"] = True

    _gercek_screen = screen_mod.FusionScreen

    def _sahte_screen(*a, **k):
        s = object.__new__(_gercek_screen)
        s.application = _SahteApp()  # type: ignore[attr-defined]
        return s

    async def _senaryo(mp) -> None:
        mp.setattr(screen_mod, "FusionScreen", _sahte_screen)
        mp.setattr(screen_mod, "install_app_cursor_mode", lambda app: None)
        mp.setattr(
            screen_mod.sys.stdout, "write", lambda s: cagrildi.__setitem__("restore", True)
        )
        await screen_mod.run_screen_repl(state=None)  # type: ignore[arg-type]

    from _pytest.monkeypatch import MonkeyPatch

    mp = MonkeyPatch()
    try:
        asyncio.run(_senaryo(mp))
    finally:
        mp.undo()

    assert cagrildi["run"] is True
    assert cagrildi["restore"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_screen.py::test_screen_repl_calisan_loop_icinde_await_edilir -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'run_screen_repl'`

- [ ] **Step 3: Write minimal implementation**

1. `FusionScreen._handle_submit_pt` içinde, `on_submit` çağrısı turu arka plan görevi olarak başlatacak şekilde bağla (koşucu `run_screen_repl`'de sağlanır). Giriş temizleme davranışı Faz 1'deki gibi kalır.

2. `screen.py` sonuna gerçek çalıştırıcıyı ekle:

```python
async def run_screen_repl(state: ReplState) -> int:
    """Tam-ekran kabuğu gerçek motorla çalıştır (elle doğrulama / deneysel yol).

    Reçete: uygulama imleç modu kurulur; çıkışta normal moda dönülür. Faz 1
    regresyonu: zaten çalışan event loop içinde `run_async()` await edilir.
    """
    import asyncio

    from .screen_turn import run_turn

    screen = FusionScreen(banner=_DEMO_BANNER, on_submit=lambda t: None)

    def _baslat(text: str) -> None:
        # Turu arka plan görevi yap: giriş kutusu bloklanmasın, çıktı akarken çizilsin.
        asyncio.ensure_future(run_turn(text, state, screen))

    screen._on_submit = _baslat
    install_app_cursor_mode(screen.application)
    try:
        await screen.application.run_async()
    finally:
        sys.stdout.write(APP_CURSOR_OFF)
        sys.stdout.flush()
    return 0
```

3. `run_screen_demo`'yu kaldır (yerini `run_screen_repl` aldı). `ReplState` importunu ekle (tip için; döngüsel importa dikkat — gerekiyorsa `TYPE_CHECKING` altında).

4. `loop.py`'daki dallanmayı güncelle:

```python
# src/fusion_cli/cli/repl/loop.py — mevcut FUSION_FULLSCREEN dalını değiştir
    if os.environ.get("FUSION_FULLSCREEN") == "1":
        from .screen import run_screen_repl

        state = ReplState(config=config, memory=memory, root=root)
        return await run_screen_repl(state)
```

> **Uyarlama notu (implementer):** `ReplState` kurucusunun gerçek imzasını mevcut
> `run_repl` gövdesindeki `ReplState(config=..., memory=..., root=...)` çağrısından
> kopyala (satır ~60). Bayrak YOKken çalışan mevcut yol (state/registry/reader/…)
> AYNEN kalır; yalnızca bayraklı dal `run_screen_repl`'e gider.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_screen.py -q`
Expected: PASS

- [ ] **Step 5: Elle görsel doğrulama (gerçek Terminal.app)**

Yeni bir Terminal.app sekmesinde:

```bash
FUSION_FULLSCREEN=1 fusion
```

Kontrol: gerçek bir soru yaz + Enter → çalışma satırı "hazırlanıyor… · token · model" olarak güncellenir; cevap **renkli** (markdown/kod) olarak konuşmaya akar; içerik taşınca ok/PageUp/tekerlek ile kaydır (takip modu: alttayken yeni içerik takip eder, yukarı kaydırınca durur); resize'da bozulma yok; **Ctrl-C** çalışan turu keser; Ctrl-Q temiz çıkış. Bir sorun varsa ilgili task'e dönülür (özellikle Task 4 kaydırma/renk).

- [ ] **Step 6: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src/fusion_cli/cli/repl/screen.py src/fusion_cli/cli/repl/loop.py tests/test_screen.py
.venv/bin/mypy src/fusion_cli/cli/repl/screen.py src/fusion_cli/cli/repl/loop.py
.venv/bin/python -m pytest -q
git add src/fusion_cli/cli/repl/screen.py src/fusion_cli/cli/repl/loop.py tests/test_screen.py
git commit -m "feat(repl): tam-ekran kabuğu gerçek motor turuna bağla (deneysel)"
```

---

## Self-Review Notları

- **Spec kapsamı:** ANSI köprüsü (Task 1), Live kapatma (Task 2), olay-beslemeli çalışma satırı (Task 3), ANSI konuşma kontrolü + kaydırma/takip (Task 4), her iki motor + etkileşimsiz onay (Task 5), uçtan uca bağlama + gerçek çalıştırıcı (Task 6). Spec'in tüm Faz 2 birimleri karşılandı.
- **Kapsam dışı (sonraki fazlar):** onay/soru modalları (Faz 3), içerik kırpma + gelişmiş takip/cila (Faz 4), eski REPL geçişi + ölü Rich-Live/prompter temizliği (Faz 5).
- **Bilinen risk (Task 4):** `FormattedTextControl(ANSI(...))` + `vertical_scroll` kaydırma yalnızca gerçek terminalde tam doğrulanır. Uçtan uca görsel doğrulama Task 6'da; kırılırsa Task 4 tek noktada düzeltilir.
- **Doğrulama notları:** Task 3/5'te olay alan adları ve `ReplState` alanları gerçek koddan teyit edilmeli (planda notlandı); plan bu adları mevcut `loop.py` kullanımından kopyalamayı şart koşar, uydurmayı değil.
- **Tip tutarlılığı:** `AnsiBridge.console`/`.text`/`.drain()` her yerde aynı; `FusionScreen.bridge`/`after_event`/`set_work`/`clear_work`/`conversation_text` Task 4'te üretilir, Task 5/6'da tüketilir; `run_turn(line, state, screen)` imzası Task 5→6 tutarlı.
