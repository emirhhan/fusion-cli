"""Üretilen araçlar gerçek kayıt defterine girer.

Denetlendi (6 Eylül): `tools/forge.py` yazıldı ve test edildi ama kayıt defterine
HİÇ bağlanmamıştı — yani model `make_tool` diye bir araç göremiyordu ve üretilmiş
araçlar sonraki turlarda çağrılamıyordu. Modülün var olması, Fusion'ın onu
kullanabildiği anlamına gelmez.

Bu dosya tam da o boşluğu kapatır: araç sunuluyor mu, üretilen araç bir sonraki
turda görünüyor mu.
"""

from __future__ import annotations

from types import SimpleNamespace

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.engine_tools import build_agent_registry
from fusion_cli.tools import build_registry
from fusion_cli.tools.forge import forge_tool


def _deps(tmp_path, **ek):
    temel = {
        "base_registry": build_registry(),
        "tool_context": ToolContext(root=tmp_path),
        "capabilities": None,
        "code_index": None,
        "asker": None,
        "home": None,
        "config": SimpleNamespace(vision=None),
        "publisher": SimpleNamespace(publish=lambda event: None),
    }
    temel.update(ek)
    return SimpleNamespace(**temel)


async def _run_agent(*args, **kwargs):  # pragma: no cover - imza doldurucu
    raise AssertionError("bu testte çağrılmamalı")


def test_make_tool_araci_modele_sunulur(tmp_path):
    registry = build_agent_registry(_deps(tmp_path), depth=0, run_agent=_run_agent)

    assert "make_tool" in registry.names()


def test_uretilen_arac_sonraki_turda_kayitli_gelir(tmp_path):
    context = ToolContext(root=tmp_path)
    forge_tool(
        {"name": "ozet_cikar", "source": "def run(args):\n    return 'ozet'\n"},
        context,
    )

    registry = build_agent_registry(_deps(tmp_path), depth=0, run_agent=_run_agent)

    assert "ozet_cikar" in registry.names()


def test_uretilmis_arac_yoksa_defter_kirlenmez(tmp_path):
    registry = build_agent_registry(_deps(tmp_path), depth=0, run_agent=_run_agent)

    uretilmis = [ad for ad in registry.names() if ad.startswith("ozet_")]
    assert uretilmis == []
