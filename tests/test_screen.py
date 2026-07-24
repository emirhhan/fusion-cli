"""Tam-ekran kabuk iskeleti."""

from __future__ import annotations


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
    # Fare desteği açık: prompt_toolkit tekerleği yerleşik Window kaydırmasına çevirir.
    assert app.mouse_support() is True


def test_screen_repl_calisan_loop_icinde_await_edilir():
    """run_screen_repl zaten çalışan event loop'tan await edilebilmeli (Faz 1 regresyonu)."""
    import asyncio

    import fusion_cli.cli.repl.screen as screen_mod

    cagrildi = {"run": False}

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
        await screen_mod.run_screen_repl(state=None)  # type: ignore[arg-type]

    from _pytest.monkeypatch import MonkeyPatch

    mp = MonkeyPatch()
    try:
        asyncio.run(_senaryo(mp))
    finally:
        mp.undo()

    assert cagrildi["run"] is True


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
