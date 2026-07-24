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
