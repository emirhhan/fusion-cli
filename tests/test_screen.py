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


def test_eko_turu_kullanici_ve_yaniti_yazar():
    from fusion_cli.cli.repl.screen import FusionScreen, echo_submit

    ekran = FusionScreen(banner="✦ fusion", on_submit=lambda s: None)
    echo_submit(ekran, "vpn nedir")

    metin = ekran.conversation_buffer.text
    assert "[ben] vpn nedir" in metin
    assert "[eko] vpn nedir" in metin


def test_demo_calistirici_mevcut(monkeypatch):
    """run_screen_demo çağrılabilir olmalı; app.run yerine sahte konur (headless)."""
    import fusion_cli.cli.repl.screen as screen_mod

    cagrildi = {"run": False, "restore": False}

    class _SahteApp:
        full_screen = True

        def run(self) -> None:
            cagrildi["run"] = True

    _gercek_screen = screen_mod.FusionScreen

    def _sahte_screen(*a, **k):
        s = object.__new__(_gercek_screen)
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
