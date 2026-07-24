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
