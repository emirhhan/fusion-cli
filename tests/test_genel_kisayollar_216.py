"""#216 genel kısayollar: Ctrl+O transcript, Ctrl+V görüntü, Option+P/T/O, `:emoji:`,
istem önerileri (tam ekran TUI ve satır içi REPL)."""

from __future__ import annotations

import asyncio
import contextlib
import subprocess
from collections import deque
from pathlib import Path

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from fusion_cli.cli.repl import (
    clipboard_image,
    emoji_codes,
    option_keys,
    prompt_suggestion,
    transcript_view,
)
from fusion_cli.cli.repl.clipboard_image import ImageChips
from fusion_cli.cli.repl.completion import ReplCompleter
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.cli.repl.tui import FusionTui
from fusion_cli.cli.repl.tui_loop import _TuiSession
from fusion_cli.core.events import FollowupsSuggested
from fusion_cli.core.types import Message, ToolCall
from fusion_cli.memory.factory import null_memory

from .fakes import make_config

PNG = b"\x89PNG\r\n\x1a\nveri"


def _state(tmp_path: Path) -> ReplState:
    return ReplState(config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path)


# -- Ctrl+V görüntü yapıştırma ------------------------------------------------ #


def test_linux_panosundaki_png_dosyaya_yazilir(tmp_path):
    def runner(command, **_kwargs):
        assert command[0] == "wl-paste"
        return subprocess.CompletedProcess(command, 0, stdout=PNG, stderr=b"")

    target = tmp_path / "p" / "image-1.png"
    ok = clipboard_image.read_clipboard_image(
        target, runner=runner, which=lambda name: name, platform="linux"
    )
    assert ok and target.read_bytes() == PNG


def test_panoda_goruntu_yoksa_false(tmp_path):
    def runner(command, **_kwargs):
        return subprocess.CompletedProcess(command, 0, stdout=b"metin", stderr=b"")

    target = tmp_path / "image-1.png"
    assert not clipboard_image.read_clipboard_image(
        target, runner=runner, which=lambda name: name, platform="linux"
    )
    assert not clipboard_image.read_clipboard_image(
        target, runner=runner, which=lambda _name: None, platform="darwin"
    )


def test_macos_osascript_dosya_yolunu_arguman_alir(tmp_path):
    seen: list[list[str]] = []

    def runner(command, **_kwargs):
        seen.append(command)
        Path(command[-1]).write_bytes(PNG)
        return subprocess.CompletedProcess(command, 0, stdout=b"tamam", stderr=b"")

    target = tmp_path / "image-1.png"
    assert clipboard_image.read_clipboard_image(
        target, runner=runner, which=lambda name: name, platform="darwin"
    )
    assert seen[0][0] == "osascript" and seen[0][-1] == str(target)


def test_cip_numaralanir_ve_gonderimde_veri_uri_olur(tmp_path):
    def reader(target: Path) -> bool:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(PNG)
        return True

    chips = ImageChips(tmp_path, reader)
    assert chips.paste() == "[Image #1]"
    assert chips.paste() == "[Image #2]"
    images = chips.take("bunu incele [Image #2]")
    assert len(images) == 1 and images[0].startswith("data:image/png;base64,")
    assert chips.take("[Image #2]") == ()  # kullanılan çip bir kez gider
    assert ImageChips(tmp_path, lambda _target: False).paste() is None


async def test_tui_ctrl_v_cip_ekler_ya_da_uyarir(tmp_path):
    tui = FusionTui(
        on_submit=lambda _t: None,
        on_interrupt=lambda: None,
        on_exit=lambda: None,
        on_cycle_mode=lambda: None,
    )
    tui._paste_image()
    assert tui._flash.startswith("Panoda görüntü yok")
    tui.extras.image_chips = ImageChips(tmp_path, lambda target: target.write_bytes(PNG) > 0)
    tui._paste_image()
    assert tui._input.buffer.text == "[Image #1]"


def test_varsayilan_tuslar_ve_claude_eylemleri(tmp_path):
    from fusion_cli.config.claude_keybindings import translate_action
    from fusion_cli.config.keybindings import load_keymap

    keymap = load_keymap(tmp_path / "yok.json", tmp_path / "yok-claude.json")
    giris, tui = keymap.contexts["giris"], keymap.contexts["tui"]
    assert giris["c-v"] == tui["c-v"] == "gorsel_yapistir"
    assert giris["c-o"] == tui["c-o"] == "transkript"
    assert giris["escape p"] == tui["escape p"] == "model_sec"
    assert giris["escape t"] == "dusunme" and giris["escape o"] == "hizli_kip"
    # Ctrl+T tek uygulama: görev listesi görünümü (`task_view`, #330); Claude app:toggleTodos.
    assert giris["c-t"] == tui["c-t"] == "gorev_listesi" and giris["?"] == "kisayollar"
    assert translate_action("app:toggleTodos") == "gorev_listesi"
    assert translate_action("chat:imagePaste") == "gorsel_yapistir"
    assert translate_action("app:toggleTranscript") == "transkript"
    assert translate_action("chat:modelPicker") == "model_sec"
    assert translate_action("chat:thinkingToggle") == "dusunme"
    assert translate_action("chat:fastMode") == "hizli_kip"


# -- Ctrl+O transcript ------------------------------------------------------- #


def _history() -> list[Message]:
    return [
        Message("system", "gizli sistem"),
        Message("user", "dosyayı oku"),
        Message(
            "assistant",
            "okuyorum",
            tool_calls=(ToolCall("1", "read_file", '{"path": "a.py"}'),),
        ),
        Message("tool", "\n".join(f"satır {i}" for i in range(100)), name="read_file", ok=True),
        Message("assistant", "bitti"),
    ]


def test_transcript_arac_cagrisini_ve_sonucunu_gosterir():
    text = transcript_view.render(_history(), width=100)
    assert "gizli sistem" not in text
    assert "read_file" in text and '"path": "a.py"' in text
    assert "satır 59" in text and "satır 60" not in text
    assert "40 satır daha" in text
    full = transcript_view.render(_history(), width=100, show_all=True)
    assert "satır 99" in full and "bütün konuşma" in full


def test_transcript_son_mesajlari_gosterir_ctrl_e_hepsi():
    history = [Message("user", f"mesaj {i}") for i in range(40)]
    text = transcript_view.render(history, width=80)
    assert "mesaj 39" in text and "mesaj 5\n" not in text and "10 önceki mesaj gizli" in text
    assert "mesaj 0" in transcript_view.render(history, width=80, show_all=True)


def test_tui_ctrl_o_gorunume_girer_esc_ve_q_cikar(tmp_path):
    session = _TuiSession(_state(tmp_path))
    session._state.history = _history()
    tui = session._tui
    tui._toggle_transcript()
    assert tui.extras.viewing and "read_file" in tui._visible_text()
    tui._cancel_or_interrupt()  # Esc görünümden çıkar, turu kesmez
    assert not tui.extras.viewing
    tui._toggle_transcript()
    tui._toggle_transcript()  # ikinci Ctrl+O kapatır
    assert not tui.extras.viewing
    tui._toggle_transcript()
    tui._ctrl_c_pressed()
    assert not tui.extras.viewing


# -- Option+P/T/O ------------------------------------------------------------ #


class _Key:
    def __init__(self, key: str) -> None:
        self.key = key


class _App:
    def __init__(self, *keys: str) -> None:
        self.key_processor = type("KP", (), {"input_queue": deque(_Key(k) for k in keys)})()


def test_esc_ile_ayni_okumadaki_harf_option_eylemidir():
    bindings = {"escape p": "model_sec", "escape t": "dusunme"}
    app = _App("p")
    assert option_keys.take_meta_action(app, bindings) == "model_sec"
    assert not app.key_processor.input_queue
    assert option_keys.take_meta_action(_App(), bindings) is None
    assert option_keys.take_meta_action(_App("x"), bindings) is None


@contextlib.asynccontextmanager
async def _running(make):
    """Uygulama oturum bağlamında kurulmalı: `FusionTui` girdi/çıktıyı kurulurken alır."""
    from prompt_toolkit.application import create_app_session
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        tui = make()
        task = asyncio.create_task(tui.application.run_async())
        await asyncio.sleep(0.2)
        try:
            yield pipe
        finally:
            with contextlib.suppress(Exception):
                tui.application.exit()
            await asyncio.sleep(0.1)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


async def test_tam_ekranda_option_p_kesmez_model_secicisini_acar():
    olaylar: list[str] = []

    def make() -> FusionTui:
        tui = FusionTui(
            on_submit=lambda _t: None,
            on_interrupt=lambda: olaylar.append("kes"),
            on_exit=lambda: None,
            on_cycle_mode=lambda: None,
        )
        tui.extras.option_handler = olaylar.append
        return tui

    async with _running(make) as pipe:
        pipe.send_text("\x1bp")
        await asyncio.sleep(0.3)
        assert olaylar == ["model_sec"]
        pipe.send_text("\x1b")  # tek Esc ayrıştırıcı zaman aşımından sonra gelir
        for _ in range(30):
            await asyncio.sleep(0.1)
            if "kes" in olaylar:
                break
        assert olaylar == ["model_sec", "kes"]


def test_option_komutlari(tmp_path):
    session = _TuiSession(_state(tmp_path))
    sent: list[str] = []
    session._shortcuts._submit = sent.append
    session._shortcuts.option("model_sec")
    session._shortcuts.option("dusunme")
    session._shortcuts.option("hizli_kip")
    assert sent == ["/model", "/thinking"]
    assert "hızlı kip" in session.tui.transcript


# -- :emoji: ve istem önerileri ---------------------------------------------- #


def test_emoji_kisa_kodu_tab_ile_emoji_olur():
    completer = ReplCompleter([], ())
    found = list(completer.get_completions(Document("harika :tad"), CompleteEvent()))
    assert found and found[0].text == "🎉" and found[0].start_position == -4
    assert emoji_codes.shortcode_prefix(":t") is None
    assert list(completer.get_completions(Document("saat 10:30"), CompleteEvent())) == []


def test_istem_onerisi_ayari_ve_ortam_degiskeni(tmp_path):
    assert prompt_suggestion.enabled(tmp_path, tmp_path, {})
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text('{"promptSuggestionEnabled": false}')
    assert not prompt_suggestion.enabled(tmp_path, tmp_path, {})
    env = {prompt_suggestion.ENV_KEY: "1"}
    assert prompt_suggestion.enabled(tmp_path, tmp_path, env)


def test_oneri_bos_girdide_gorunur_tab_alir_yazmak_kaldirir():
    sink = prompt_suggestion.SuggestionSink()
    sink.handle(FollowupsSuggested((("Testleri çalıştır", "pytest -q çalıştır"),)))
    text = sink.take()
    assert text == "pytest -q çalıştır" and sink.take() == ""
    buffer = Buffer()
    assert prompt_suggestion.offer(buffer, text) and prompt_suggestion.available(buffer)
    assert prompt_suggestion.accept(buffer) and buffer.text == text
    other = Buffer()
    prompt_suggestion.offer(other, text)
    other.insert_text("x")
    assert not prompt_suggestion.available(other)
    assert not prompt_suggestion.offer(other, text)


def test_tui_tur_sonunda_oneri_konur(tmp_path):
    session = _TuiSession(_state(tmp_path))
    sink = session._shortcuts.begin_turn()
    sink.handle(FollowupsSuggested((("etiket", "değişiklikleri incele"),)))
    session._shortcuts.finish_turn()
    buffer = session._tui._input.buffer
    assert buffer.suggestion is not None and buffer.suggestion.text == "değişiklikleri incele"


def test_satir_ici_kisayollar_taslagi_korur(tmp_path):
    from fusion_cli.cli.repl.inline_shortcuts import InlineShortcuts
    from fusion_cli.cli.repl.input import ReplInput

    state = _state(tmp_path)
    reader = ReplInput(tmp_path / "h", [], mode=state.approval)
    shortcuts = InlineShortcuts(state, None)  # type: ignore[arg-type]
    actions = shortcuts.actions(reader)
    assert {"transkript", "gorsel_yapistir", "model_sec", "kisayollar"} <= set(actions)
    buffer = Buffer()
    buffer.insert_text("yarım taslak")
    event = type("E", (), {"current_buffer": buffer})()
    buffer.validate_and_handle = lambda: None  # type: ignore[method-assign]
    actions["model_sec"](event)
    assert reader._bound_command == "/model" and reader._restore_draft == "yarım taslak"
    actions["kisayollar"](event)
    assert buffer.text.endswith("?")
    # Satır içi Ctrl+T `input.py` `gorev_listesi` eylemindedir (task_view, #330).
    assert "gorevler" not in actions
