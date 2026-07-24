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
