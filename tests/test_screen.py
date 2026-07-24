"""Tam-ekran kabuk — kanıtlanmış reçete (spike4 modeli)."""

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


def test_konusma_kopruden_beslenir():
    from fusion_cli.cli.repl.screen import FusionScreen

    ekran = FusionScreen(banner="✦ fusion", on_submit=lambda s: None)
    ekran.bridge.console.print("merhaba")
    ekran.after_event()

    assert "merhaba" in ekran.conversation_text


def test_takip_modunda_imlec_sona_alinir():
    from fusion_cli.cli.repl.screen import FusionScreen

    ekran = FusionScreen(banner="✦ fusion", on_submit=lambda s: None)
    ekran.bridge.console.print("birinci satır")
    ekran.after_event()

    buf = ekran._conversation.buffer
    # Takip modu açık: yeni içerik gelince imleç sona yapışır (pencere alta iner).
    assert buf.cursor_position == len(buf.text)


def test_calisma_satiri_ayarlanir_ve_temizlenir():
    from fusion_cli.cli.repl.screen import FusionScreen

    ekran = FusionScreen(banner="✦ fusion", on_submit=lambda s: None)
    ekran.set_work("hazırlanıyor…")
    assert "hazırlanıyor" in ekran.work_text
    ekran.clear_work()
    assert ekran.work_text == ""


def test_kabuk_full_screen_ve_mouse_kapali_kurulur():
    from fusion_cli.cli.repl.screen import FusionScreen

    ekran = FusionScreen(banner="✦ fusion", on_submit=lambda s: None)
    app = ekran.application

    assert app.full_screen is True
    # Kanıtlanmış reçete: fare desteği KAPALI; tekerlek ?1h ile ok tuşuna çevrilir.
    assert app.mouse_support() is False


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
    assert cagrildi["restore"] is True  # çıkışta mod geri alındı
