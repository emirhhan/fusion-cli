"""`team_run(arka_plan=true)` (P-061 + P-048): ekip arka plan işçisinde koşar, lider sürer.

Ölçüldü (1 Kasım): ekip `team_run` çağrısının içinde koşuyordu; lider üyeler bitene kadar
sohbete devam edemiyordu.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps
from fusion_cli.engines.agent.team_board import TeamBoard, TeamMember, TeamMessage, TeamStore
from fusion_cli.engines.agent.team_session import TeamSession
from fusion_cli.engines.agent.team_tools import team_run_tool
from fusion_cli.tools import agent_tasks
from fusion_cli.tools.capabilities import CapabilityRegistry
from tests.agent_harness import Publisher
from tests.fakes import AlwaysApprove, RecordingSink, make_config


@pytest.fixture
def baslatilan(monkeypatch):
    """İşçi süreci açılmaz: görev kaydı yazılır, 'sırada' kalır."""
    gorevler: list = []

    def _launch(store, task, launcher=None):
        gorevler.append(task)
        return task

    monkeypatch.setattr(agent_tasks, "_launch", _launch)
    return gorevler


def _deps(tmp_path, conversation_id: str = "sohbet-1") -> AgentDeps:
    return AgentDeps(
        config=make_config(runtime={"agent_team_confirm": False}, memory_dir=tmp_path / "bellek"),
        publisher=Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        capabilities=CapabilityRegistry(tmp_path / "ev", tmp_path),
        conversation_id=conversation_id,
    )


def _istek(**extra) -> dict:
    return {
        "ad": "site",
        "hedef": "Açılış sayfası",
        "uyeler": [{"ad": "kod"}],
        "gorevler": [{"baslik": "Sayfa"}],
        "arka_plan": True,
        **extra,
    }


async def _calismamali(task, sub_deps, **kwargs):  # pragma: no cover - çağrılırsa test düşer
    raise AssertionError("üye ön planda koşmamalı")


async def test_arka_plan_ekibi_isciye_devreder_hemen_doner(tmp_path, baslatilan):
    deps = _deps(tmp_path)

    sonuc = await team_run_tool(deps, depth=0, run_agent=_calismamali).run(
        _istek(), deps.tool_context
    )

    assert sonuc.ok and "arka planda başladı" in sonuc.output
    gorev = baslatilan[0]
    assert (gorev.name, gorev.owner, gorev.origin) == ("ekip-site", "sohbet-1", "arac")
    assert gorev.options.config_overrides == ("runtime.agent_team_confirm=false",)
    argumanlar = json.loads(gorev.prompt.split("(JSON):\n", 1)[1])
    assert "arka_plan" not in argumanlar and argumanlar["ad"] == "site"
    # Pano lider tarafında kurulmaz; işçi kurar.
    assert TeamStore(tmp_path).load("site") is None


async def test_isci_arka_plan_bayragini_yok_sayip_ekibi_kendisi_kosturur(tmp_path, baslatilan):
    deps = _deps(tmp_path, conversation_id="arka-1a2b3c4d")
    kosular: list[str] = []

    async def _ajan(task, sub_deps, **kwargs):
        kosular.append(task)
        return SimpleNamespace(final_text="bitti", ok=True, tool_calls_made=0)

    sonuc = await team_run_tool(deps, depth=0, run_agent=_ajan).run(_istek(), deps.tool_context)

    assert baslatilan == [] and kosular and "Ekip 'site'" in sonuc.output


async def test_kosan_arka_plan_ekibine_mesaj_kutuya_yazilir_ikinci_kosu_acilmaz(
    tmp_path, baslatilan
):
    deps = _deps(tmp_path)
    arac = team_run_tool(deps, depth=0, run_agent=_calismamali)
    await arac.run(_istek(), deps.tool_context)
    # İşçinin kurduğu pano (işçi süreci yerine elle).
    TeamStore(tmp_path).save(TeamBoard("site", "Açılış sayfası", (TeamMember("kod"),)))

    mesaj = await arac.run(
        {"ad": "site", "mesajlar": [{"kime": "kod", "metin": "renkleri koyulaştır"}]},
        deps.tool_context,
    )
    yeni_gorev = await arac.run(
        {"ad": "site", "gorevler": [{"baslik": "ek"}], "arka_plan": True}, deps.tool_context
    )

    assert mesaj.ok and "iletildi" in mesaj.output
    kutu = TeamStore(tmp_path).inbox("site", "kod")
    assert [(m.sender, m.text) for m in kutu] == [("lider", "renkleri koyulaştır")]
    assert not yeni_gorev.ok and "yalnız mesajlar" in yeni_gorev.output
    assert len(baslatilan) == 1


async def test_bostaki_uye_baska_surecin_yazdigi_mesajla_uyanir(tmp_path):
    store = TeamStore(tmp_path)
    board = TeamBoard("site", "x", (TeamMember("kod"), TeamMember("tasarim")))
    store.save(board)
    session = TeamSession(store, board, Publisher(RecordingSink()), lambda: 0.0, inbox_poll_s=0.01)
    await session.member_started("tasarim")  # biri çalışıyor: ekip boşa düşmedi
    await session.member_idle("kod", sub_id="", summary="")

    bekleyen = asyncio.ensure_future(session.wait_for_work("kod"))
    await asyncio.sleep(0.05)
    assert not bekleyen.done()
    await asyncio.to_thread(store.append, "site", TeamMessage("lider", "kod", "bak", 1.0))

    assert await asyncio.wait_for(bekleyen, 2) is True
