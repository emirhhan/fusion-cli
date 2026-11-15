"""Tur bitince terminal zili (P-047): `/zil` açıkken ve yalnız terminalde `\\a` yazılır."""

from __future__ import annotations

import io

from rich.console import Console

from fusion_cli.core.events import TurnFinished
from fusion_cli.ui.renderer import ConsoleRenderer


def _renderer(*, bell: bool, terminal: bool) -> tuple[ConsoleRenderer, io.StringIO]:
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=terminal, width=80)
    return ConsoleRenderer(console, show_progress=False, live_progress=False, bell=bell), buffer


def test_zil_acikken_tur_bitince_terminale_bell_karakteri_yazilir():
    renderer, buffer = _renderer(bell=True, terminal=True)
    renderer.handle(TurnFinished())
    assert "\a" in buffer.getvalue()


def test_zil_varsayilan_kapali_hic_bell_yazilmaz():
    renderer, buffer = _renderer(bell=False, terminal=True)
    renderer.handle(TurnFinished())
    assert "\a" not in buffer.getvalue()


def test_zil_boruda_ve_ci_da_sessiz_kalir():
    """Çıktı terminal değilse (boru, günlük dosyası) kontrol karakteri sızmaz."""
    renderer, buffer = _renderer(bell=True, terminal=False)
    renderer.handle(TurnFinished())
    assert "\a" not in buffer.getvalue()
