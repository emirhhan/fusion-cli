"""Ekip kanca kapıları (P-061 + P-009): TaskCreated, TaskCompleted, TeammateIdle.

Ölçüldü (1 Kasım): üç olay `CLAUDE_ONLY_EVENTS` listesindeydi; tanımları "Fusion bu olayı
tetiklemiyor" diye atlanıyor, ekip görevi kancasız ekleniyor/bitiyordu. Claude Code'daki
gibi çıkış 2 artık görevi eklemez, bitirmez ya da üyeyi boşa düşürmez.
"""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path
from types import SimpleNamespace

from fusion_cli.core.hooks.events import HookCommand, HookEvent, HookSet
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps
from fusion_cli.engines.agent.team_board import TeamStore
from fusion_cli.engines.agent.team_tools import team_run_tool
from fusion_cli.engines.hooks.session import HookSession
from fusion_cli.tools.capabilities import CapabilityRegistry
from tests.agent_harness import Publisher
from tests.fakes import AlwaysApprove, RecordingSink, make_config


def _kanca(tmp_path: Path, event: HookEvent, body: str) -> HookCommand:
    """Yükü `<olay>.jsonl`'e yazar, sonra `body`'yi çalıştırır (`n` = kaçıncı çağrı)."""
    kayit = tmp_path / f"{event.value}.jsonl"
    script = tmp_path / f"kanca_{event.value}.py"
    script.write_text(
        "import json, sys\n"
        "data = json.load(sys.stdin)\n"
        f"kayit = open({str(kayit)!r}, 'a+', encoding='utf-8')\n"
        "kayit.seek(0); n = len(kayit.readlines()) + 1\n"
        "kayit.write(json.dumps(data) + '\\n'); kayit.close()\n" + body,
        encoding="utf-8",
    )
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"
    return HookCommand(event, "", command, 20.0, "test", "")


def _yukler(tmp_path: Path, event: HookEvent) -> list[dict]:
    path = tmp_path / f"{event.value}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _deps(tmp_path: Path, *commands: HookCommand, **runtime) -> AgentDeps:
    deps = AgentDeps(
        config=make_config(runtime={"agent_team_confirm": False, **runtime}),
        publisher=Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        capabilities=CapabilityRegistry(tmp_path / "ev", tmp_path),
    )
    deps.hooks = HookSession(root=tmp_path, loader=lambda: HookSet(tuple(commands)))
    return deps


async def _arac(sub_deps, ad, **args):
    tool = sub_deps.base_registry.get(ad)
    assert tool is not None
    return await tool.run(args, sub_deps.tool_context)


def _tek_ekip() -> dict:
    return {"ad": "tek", "hedef": "x", "uyeler": [{"ad": "a"}], "gorevler": [{"baslik": "iş"}]}


async def _calistir(deps: AgentDeps, ajan, istek: dict | None = None):
    return await team_run_tool(deps, depth=0, run_agent=ajan).run(
        istek or _tek_ekip(), deps.tool_context
    )


async def test_taskcreated_cikis_2_gorevi_eklemez_gerekce_uyeye_doner(tmp_path):
    hook = _kanca(
        tmp_path,
        HookEvent.TASK_CREATED,
        "if 'yasak' in data['task_subject']:\n    sys.stderr.write('başlık kurala uymuyor')\n"
        "    sys.exit(2)\n",
    )
    deps = _deps(tmp_path, hook)
    eklemeler: list = []

    async def _ajan(task, sub_deps, **kwargs):
        eklemeler.append(await _arac(sub_deps, "team_task", eylem="ekle", baslik="yasak iş"))
        await _arac(sub_deps, "team_task", eylem="al")
        await _arac(sub_deps, "team_task", eylem="bitir", id="g1", sonuc="ok")
        return SimpleNamespace(final_text="bitti", ok=True, tool_calls_made=3)

    sonuc = await _calistir(deps, _ajan)

    assert sonuc.ok, sonuc.output
    assert not eklemeler[0].ok and "başlık kurala uymuyor" in eklemeler[0].output
    pano = TeamStore(tmp_path).load("tek")
    assert pano is not None and [g.title for g in pano.tasks] == ["iş"]
    yukler = _yukler(tmp_path, HookEvent.TASK_CREATED)
    # Liderin görevi de kapıdan geçer (teammate_name yazılmaz); üyeninki adıyla.
    assert yukler[0]["task_subject"] == "iş" and "teammate_name" not in yukler[0]
    assert (yukler[1]["teammate_name"], yukler[1]["team_name"], yukler[1]["task_id"]) == (
        "a",
        "tek",
        "g2",
    )
    assert yukler[1]["hook_event_name"] == "TaskCreated"


async def test_taskcreated_lider_gorevini_engellerse_team_run_gerekceyle_doner(tmp_path):
    hook = _kanca(tmp_path, HookEvent.TASK_CREATED, "sys.stderr.write('kimlik yok'); sys.exit(2)\n")
    deps = _deps(tmp_path, hook)

    async def _ajan(task, sub_deps, **kwargs):  # pragma: no cover - üye başlamamalı
        raise AssertionError("üye çalışmamalı")

    sonuc = await _calistir(deps, _ajan)

    assert not sonuc.ok and "kimlik yok" in sonuc.output


async def test_taskcompleted_cikis_2_gorevi_uyede_birakir_geri_bildirim_verir(tmp_path):
    hook = _kanca(
        tmp_path,
        HookEvent.TASK_COMPLETED,
        "if n == 1:\n    sys.stderr.write('önce testleri koş')\n    sys.exit(2)\n",
    )
    deps = _deps(tmp_path, hook)
    bitirmeler: list = []

    async def _ajan(task, sub_deps, **kwargs):
        await _arac(sub_deps, "team_task", eylem="al")
        bitirmeler.append(await _arac(sub_deps, "team_task", eylem="bitir", id="g1", sonuc="x"))
        pano = (await _arac(sub_deps, "team_board")).output
        bitirmeler.append(pano)
        bitirmeler.append(await _arac(sub_deps, "team_task", eylem="bitir", id="g1", sonuc="y"))
        return SimpleNamespace(final_text="bitti", ok=True, tool_calls_made=4)

    sonuc = await _calistir(deps, _ajan)

    ilk, pano, ikinci = bitirmeler
    assert not ilk.ok and "önce testleri koş" in ilk.output and "g1" in ilk.output
    assert "g1 calisiyor sahip: a" in pano
    assert ikinci.ok and "1/1 görev tamam" in sonuc.output
    yuk = _yukler(tmp_path, HookEvent.TASK_COMPLETED)[0]
    assert (yuk["task_id"], yuk["task_subject"], yuk["teammate_name"]) == ("g1", "iş", "a")


async def test_basarisiz_bitirme_taskcompleted_tetiklemez(tmp_path):
    hook = _kanca(tmp_path, HookEvent.TASK_COMPLETED, "sys.exit(2)\n")
    deps = _deps(tmp_path, hook)

    async def _ajan(task, sub_deps, **kwargs):
        await _arac(sub_deps, "team_task", eylem="al")
        await _arac(sub_deps, "team_task", eylem="bitir", id="g1", basarili=False, sonuc="olmadı")
        return SimpleNamespace(final_text="bitti", ok=True, tool_calls_made=2)

    await _calistir(deps, _ajan)

    assert _yukler(tmp_path, HookEvent.TASK_COMPLETED) == []


async def test_teammateidle_cikis_2_uyeyi_gerekceyle_yeniden_kosturur(tmp_path):
    hook = _kanca(
        tmp_path,
        HookEvent.TEAMMATE_IDLE,
        "if n == 1:\n    sys.stderr.write('önce lidere rapor yaz')\n    sys.exit(2)\n",
    )
    deps = _deps(tmp_path, hook)
    istemler: list[str] = []

    async def _ajan(task, sub_deps, **kwargs):
        istemler.append(task)
        if len(istemler) == 1:
            await _arac(sub_deps, "team_task", eylem="al")
            await _arac(sub_deps, "team_task", eylem="bitir", id="g1", sonuc="ok")
        else:
            await _arac(sub_deps, "team_send", kime="lider", metin="rapor: tamam")
        return SimpleNamespace(final_text="bitti", ok=True, tool_calls_made=2)

    sonuc = await _calistir(deps, _ajan)

    assert len(istemler) == 2 and "önce lidere rapor yaz" in istemler[1]
    assert "- a: rapor: tamam" in sonuc.output and "- a: 2 koşu" in sonuc.output
    yuk = _yukler(tmp_path, HookEvent.TEAMMATE_IDLE)[0]
    assert (yuk["teammate_name"], yuk["team_name"]) == ("a", "tek") and "task_id" not in yuk


async def test_teammateidle_engeli_uyanma_tavanini_asmaz(tmp_path):
    hook = _kanca(tmp_path, HookEvent.TEAMMATE_IDLE, "sys.stderr.write('sürdür'); sys.exit(2)\n")
    deps = _deps(tmp_path, hook, agent_team_max_wakes=1)
    kosular = 0

    async def _ajan(task, sub_deps, **kwargs):
        nonlocal kosular
        kosular += 1
        return SimpleNamespace(final_text="bitti", ok=True, tool_calls_made=0)

    await _calistir(deps, _ajan)

    assert kosular == 2


async def test_continue_false_uyeyi_durdurur_yeniden_uyandirilmaz(tmp_path):
    hook = _kanca(
        tmp_path,
        HookEvent.TASK_CREATED,
        "if 'teammate_name' in data:\n"
        "    print(json.dumps({'continue': False, 'stopReason': 'kota doldu'}))\n",
    )
    deps = _deps(tmp_path, hook)
    sonuclar: list = []

    async def _ajan(task, sub_deps, **kwargs):
        sonuclar.append(await _arac(sub_deps, "team_task", eylem="ekle", baslik="yeni"))
        return SimpleNamespace(final_text="durdum", ok=True, tool_calls_made=1)

    sonuc = await _calistir(deps, _ajan)

    assert not sonuclar[0].ok and "kota doldu" in sonuclar[0].output
    # Görev panoda bekliyor ama üye durduruldu: yeniden koşmadı.
    assert len(sonuclar) == 1 and "- a: 1 koşu" in sonuc.output
