"""Yerleşik araç aile haritası eksiksiz olmalı: aile, plan kapsamı, onay kartı ve uzak durum
sayacını yönetir; haritada olmayan `desktop_*` aracı EXTERNAL sayılıp hepsinde yanlış çalışır.

Ölçüldü (31 Ekim): `desktop_mouse` ve `desktop_displays` haritada yoktu; plan adımı
`allowed_tool_families=['desktop']` iken `desktop_mouse` kapalı kalıyor, onay kartı
'“desktop_mouse” aracı çalıştırılsın mı?' diyor, `remote_epoch` artmıyordu.
"""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import ToolFamily, tool_family
from fusion_cli.engines.agent.loop import _acts_on_remote_state
from fusion_cli.tools.builtin import build_registry


def _builtin_names(prefix: str) -> list[str]:
    return [name for name in build_registry().names() if name.startswith(prefix)]


@pytest.mark.parametrize("name", _builtin_names("desktop_"))
def test_her_desktop_araci_desktop_ailesinde(name: str) -> None:
    assert tool_family(name) is ToolFamily.DESKTOP, name
    assert _acts_on_remote_state(name)


@pytest.mark.parametrize("name", _builtin_names("chrome_") + _builtin_names("browser_"))
def test_her_tarayici_araci_browser_ailesinde(name: str) -> None:
    assert tool_family(name) is ToolFamily.BROWSER, name
