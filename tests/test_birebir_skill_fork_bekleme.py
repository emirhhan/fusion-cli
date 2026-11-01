"""`context: fork` becerisinin arka plan istisnaları (Claude Code #141).

Belge (code.claude.com/docs/en/skills, "Run skills in a subagent"): fork varsayılan olarak
arka planda koşar; `background: false` olmasa da Claude Code şu durumlarda sonucu BEKLER:
etkileşimsiz kip, `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, aynı becerinin önceki çağrısı
hâlâ sürerken ve oturumun zamanlanmış görevi beceriyi istem olarak ateşlediğinde.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from fusion_cli.core.tools import ToolContext, ToolResult
from fusion_cli.engines.agent import agent_runtime_tools, skill_fork_runs, skill_tool, team
from fusion_cli.engines.agent.approval import ApprovalMode
from fusion_cli.engines.agent.child_runs import ChildRuns
from fusion_cli.tools.capabilities import CapabilityRegistry

from .fakes import make_config


def _skill(home: Path, name: str, front: str, body: str) -> None:
    folder = home / ".claude" / "skills" / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(f"---\nname: {name}\n{front}---\n{body}", encoding="utf-8")


def _label(task: str) -> str:
    """Görev metninden kısa etiket: `tara <n>` ya da `baska`."""
    for number in "123":
        if f"tara: {number}" in task:
            return f"tara {number}"
    return "baska" if "başka iş" in task else task


def _receipt(agent_id: str) -> ToolResult:
    return ToolResult(json.dumps({"status": "async_launched", "agentId": agent_id}))


def test_ayni_beceri_suruyorsa_ikinci_cagri_bekler(tmp_path: Path, monkeypatch) -> None:
    home, root = tmp_path / "ev", tmp_path / "proje"
    root.mkdir()
    _skill(home, "tara", "context: fork\n", "tara: $ARGUMENTS")
    _skill(home, "baska", "context: fork\n", "başka iş")
    runs = ChildRuns()
    deps = SimpleNamespace(
        config=make_config(),
        approval_mode=lambda: ApprovalMode.AUTO,
        home=home,
        interactive=True,
        child_runs=runs,
    )
    seen: list[str] = []
    gate = asyncio.Event()

    async def fake_launch(deps, subtask, args, *, depth, run_agent):  # type: ignore[no-untyped-def]
        identifier = f"a-{len(seen)}"
        seen.append(f"arka:{_label(subtask.task)}")

        async def work() -> None:
            await gate.wait()

        runs.launch(identifier, work())
        return _receipt(identifier)

    async def fake_subagent(deps, subtask, *, depth, run_agent):  # type: ignore[no-untyped-def]
        seen.append(f"bekle:{_label(subtask.task)}")
        return SimpleNamespace(text="beklendi")

    monkeypatch.setattr(agent_runtime_tools, "launch_agent", fake_launch)
    monkeypatch.setattr(team, "run_subagent", fake_subagent)
    monkeypatch.setattr(team, "depth_limit_reached", lambda _deps, _depth: False)
    library = CapabilityRegistry(home, root)
    tool = skill_tool.build_skill_tool(library, deps, depth=0, run_agent=None)  # type: ignore[arg-type]
    context = ToolContext(root=root)

    async def senaryo() -> list[str]:
        await tool.run({"skill": "tara", "args": "1"}, context)
        ikinci = await tool.run({"skill": "tara", "args": "2"}, context)
        assert ikinci.output == "beklendi"
        await tool.run({"skill": "baska"}, context)
        gate.set()
        await runs.drain()
        await tool.run({"skill": "tara", "args": "3"}, context)
        await runs.drain()
        await runs.close()
        return seen

    sonuc = asyncio.run(senaryo())

    assert sonuc == ["arka:tara 1", "bekle:tara 2", "arka:baska", "arka:tara 3"]


def test_kullanici_fork_turu_ayni_beceri_surerken_bekler(monkeypatch) -> None:
    from fusion_cli.cli.repl.state import PendingExtras
    from fusion_cli.engines.agent import team_fork

    runs = ChildRuns()
    seen: list[str] = []
    gate = asyncio.Event()

    async def fake_launch(deps, subtask, args, *, depth, run_agent):  # type: ignore[no-untyped-def]
        seen.append("arka")

        async def work() -> None:
            await gate.wait()

        runs.launch("k-1", work())
        return _receipt("k-1")

    async def fake_subagent(deps, subtask, *, depth, run_agent):  # type: ignore[no-untyped-def]
        seen.append("bekle")
        return SimpleNamespace(text="bitti", ok=True, tool_calls=0)

    monkeypatch.setattr(agent_runtime_tools, "launch_agent", fake_launch)
    monkeypatch.setattr(team, "run_subagent", fake_subagent)
    runner = PendingExtras(fresh_fork=True, fork_background=True, fork_skill="tara").fork_runner(
        team_fork.run_forked_turn
    )
    deps = SimpleNamespace(live_history=None, interactive=True, child_runs=runs)

    async def senaryo() -> None:
        await runner("bir", deps, history=[])
        await runner("iki", deps, history=[])
        gate.set()
        await runs.drain()
        await runs.close()

    asyncio.run(senaryo())

    assert seen == ["arka", "bekle"]


def test_kayit_simple_namespace_ve_bos_adla_patlamaz() -> None:
    deps = SimpleNamespace(child_runs=SimpleNamespace())

    skill_fork_runs.remember(deps, "x", json.dumps({"status": "async_launched", "agentId": "a"}))
    skill_fork_runs.remember(SimpleNamespace(), "x", "makbuz değil")

    assert skill_fork_runs.previous_running(deps, "x") is False
    assert skill_fork_runs.previous_running(SimpleNamespace(), "") is False


def test_zamanlanmis_beceri_satiri_fork_u_bekletir(tmp_path: Path) -> None:
    from fusion_cli.cli.repl.skill_commands import skill_handler
    from fusion_cli.cli.repl.state import ReplState

    home = tmp_path / "ev"
    _skill(home, "kuyruk", "context: fork\n", "iş")
    state = ReplState(config=make_config(), memory=None, root=tmp_path, home=home)  # type: ignore[arg-type]
    state.capabilities = CapabilityRegistry(home, tmp_path)

    state.scheduled_fire = True
    assert state.take_scheduled_turn_only() is False
    skill_handler("kuyruk")(state, "")
    assert state.take_pending_extras().fork_background is False

    # Sıradaki (kullanıcının yazdığı) satır zamanlanmış değil: varsayılan arka plan.
    assert state.take_scheduled_turn_only() is False
    skill_handler("kuyruk")(state, "")
    extras = state.take_pending_extras()
    assert extras.fork_background is True and extras.fork_skill == "kuyruk"


async def test_masaustu_zamanlanmis_beceri_komutu_fork_u_bekletir(tmp_path: Path, monkeypatch):
    from fusion_cli.appserver.protocol import Request
    from fusion_cli.appserver.session import AppSession

    monkeypatch.setenv("HOME", str(tmp_path / "ev"))
    _skill(tmp_path / "ev", "kuyruk", "context: fork\n", "iş")
    oturum = AppSession(lambda _satir: None, root=tmp_path, home=tmp_path / "ev")

    oturum._cron_fire_prompt = "/kuyruk"
    await oturum.handle(Request("1", "komut.calistir", {"ad": "kuyruk", "arguman": ""}))
    zamanlanmis = oturum._state.take_pending_extras()
    await oturum.handle(Request("2", "komut.calistir", {"ad": "kuyruk", "arguman": ""}))
    kullanici = oturum._state.take_pending_extras()

    assert zamanlanmis.fresh_fork is True and zamanlanmis.fork_background is False
    assert kullanici.fork_background is True and kullanici.fork_skill == "kuyruk"
