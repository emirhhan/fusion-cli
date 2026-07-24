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


def test_kabuk_full_screen_ve_mouse_acik_kurulur():
    from fusion_cli.cli.repl.screen import FusionScreen

    ekran = FusionScreen(banner="✦ fusion", on_submit=lambda s: None)
    app = ekran.application

    assert app.full_screen is True
    # Fare desteği açık: tekerlek konuşmayı kaydırır. Filter çağrılınca True.
    assert app.mouse_support() is True


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


def test_konusma_penceresi_dikey_alani_doldurur():
    """Konuşma penceresi greedy yükseklikte (min=1, üst sınır yok) olmalı.

    Yoksa pencere içerik yüksekliğine çöker; HSplit ekranı doldurmaz, full_screen
    boyanmayan alt bölgeyi bırakır ve eski terminal içeriği (scrollback) sızar,
    resize'da giriş satırı kayar. TextArea (Faz 1'in temiz konuşma alanı) tam da
    bu yüzden height=D(min=1) kullanıyordu.
    """
    from prompt_toolkit.layout.dimension import to_dimension

    from fusion_cli.cli.repl.screen import FusionScreen

    ekran = FusionScreen(banner="✦ fusion", on_submit=lambda s: None)

    # Buggy hâlde height=None'dı: Window içerik yüksekliğine çöküyordu. Açık bir
    # Dimension(min=1) verilmeli ki mevcut dikey alanı doldursun (TextArea gibi).
    assert ekran._conversation_window.height is not None
    boyut = to_dimension(ekran._conversation_window.height)
    assert boyut.min == 1
