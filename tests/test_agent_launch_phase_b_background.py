"""Aynı gerçek masaüstü sohbetinde iki tur boyunca yaşayan alt ajan."""

from __future__ import annotations

import asyncio

from fusion_cli.appserver import session as app_session
from fusion_cli.engines.agent import loop
from tests.fakes import ScriptedProvider, make_config, model_result, tool_call


class _DelayedProvider(ScriptedProvider):
    def __init__(self):
        super().__init__([model_result("CHILD_FINISHED_MARKER")])
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.finished = asyncio.Event()
        self.cancelled = False

    async def stream(self, request):
        self.started.set()
        try:
            await self.release.wait()
            async for item in super().stream(request):
                yield item
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        finally:
            self.finished.set()


def _scripted_session(tmp_path, monkeypatch):
    config = make_config(memory_dir=tmp_path / "memory", task_model_map={})
    monkeypatch.setattr(app_session, "load_config", lambda: config)
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "denetci.md").write_text(
        "---\nname: denetci\ndescription: inceler\nmodel: sahte/child\n---\nİncele.",
        encoding="utf-8",
    )
    parent = ScriptedProvider(
        [
            model_result(
                tool_calls=(
                    tool_call(
                        "Agent",
                        prompt="Alt görev.",
                        subagent_type="denetci",
                        run_in_background=True,
                    ),
                )
            ),
            model_result("MAIN_FIRST"),
            model_result("MAIN_SECOND"),
        ]
    )
    child = _DelayedProvider()
    monkeypatch.setattr(
        loop,
        "build_provider",
        lambda spec, **kwargs: child if spec.model == "sahte/child" else parent,
    )
    packets = []
    session = app_session.AppSession(packets.append, root=tmp_path, home=tmp_path / "home")
    return session, parent, child, packets


async def test_rpc_iki_tur_arasinda_arka_plan_ajanini_ve_sonucunu_korur(tmp_path, monkeypatch):
    session, parent, child, packets = _scripted_session(tmp_path, monkeypatch)
    try:
        first = await asyncio.wait_for(session._run_turn("İlk turda bilgi ver."), timeout=2.0)
        assert "MAIN_FIRST" in first["metin"]
        await asyncio.wait_for(child.started.wait(), timeout=1.0)
        assert not child.cancelled and not child.finished.is_set()
        owner = session._child_runs
        child.release.set()
        await asyncio.wait_for(child.finished.wait(), timeout=1.0)
        await asyncio.wait_for(owner.drain(), timeout=1.0)
        await session._run_turn("İkinci turda devam et.")
        assert session._child_runs is owner
        assert any(
            "CHILD_FINISHED_MARKER" in message.content for message in parent.seen_messages[-1]
        )
        assert any("SubAgentFinished" in str(packet) for packet in packets)
    finally:
        await session.close()


async def test_rpc_kapanis_tur_sonrasinda_yasayan_ajanin_temizligini_bekler(tmp_path, monkeypatch):
    session, _parent, child, _packets = _scripted_session(tmp_path, monkeypatch)
    try:
        await asyncio.wait_for(session._run_turn("İlk turda bilgi ver."), timeout=2.0)
        await asyncio.wait_for(child.started.wait(), timeout=1.0)
        assert not child.finished.is_set()
    finally:
        await session.close()
    assert child.finished.is_set() and child.cancelled


async def test_rpc_reset_tur_sonrasindaki_ajanlari_kapatir_ve_sahibi_yeniler(tmp_path, monkeypatch):
    session, _parent, child, _packets = _scripted_session(tmp_path, monkeypatch)
    try:
        await asyncio.wait_for(session._run_turn("İlk tur."), timeout=2.0)
        await child.started.wait()
        previous = session._state.child_runs
        result = await session._run_command({"ad": "reset", "arguman": ""})
        assert result["ok"] is True
        assert child.finished.is_set() and child.cancelled
        assert session._state.child_runs is not previous
        assert session._child_runs is session._state.child_runs
        assert session._state.child_runs.persistent
    finally:
        await session.close()


async def test_repl_oturumu_tek_dongude_ayni_gorev_sahibini_turlara_tasir(tmp_path, monkeypatch):
    import io

    from rich.console import Console

    from fusion_cli.cli.repl import loop as repl_loop
    from fusion_cli.core.concurrency import BackgroundTasks
    from fusion_cli.engines import agent
    from fusion_cli.engines.agent.loop import AgentOutcome
    from fusion_cli.memory.factory import null_memory

    seen = []
    started, cleaned = asyncio.Event(), asyncio.Event()

    async def child():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    async def capture(task, deps, **kwargs):
        seen.append((asyncio.get_running_loop(), deps.child_runs))
        if len(seen) == 1:
            deps.child_runs.start("denetci", child)
            await started.wait()
        else:
            assert deps.child_runs.running("denetci") and not cleaned.is_set()
        return AgentOutcome("bitti", [], 0, ok=True)

    async def surface(state, config, console, resume):
        background = BackgroundTasks()
        await repl_loop._agent_turn("İlk tur", state, console, background)
        await repl_loop._agent_turn("İkinci tur", state, console, background)
        return 0

    monkeypatch.setattr(agent, "run_agent", capture)
    monkeypatch.setattr(repl_loop, "_run_surface", surface)
    result = await repl_loop.run_repl(
        make_config(memory_dir=tmp_path / "memory"),
        memory=null_memory(),
        root=tmp_path,
        console=Console(file=io.StringIO()),
    )
    assert result == 0 and len(seen) == 2
    assert seen[0] == seen[1] and seen[0][1].persistent
    assert cleaned.is_set()


async def test_rpc_ajan_iptali_yalniz_gercek_ana_tur_kimligiyle_calısir(tmp_path, monkeypatch):
    from fusion_cli.appserver.protocol import Request

    session, _parent, child, _packets = _scripted_session(tmp_path, monkeypatch)
    try:
        await asyncio.wait_for(session._run_turn("İlk tur."), timeout=2.0)
        await child.started.wait()
        owner = session._state.child_runs
        record = owner.records()[0]
        expected = owner.turn_for(record.agent_id)
        assert expected
        for identifier in ("", "yanlis-tur"):
            result = await session._dispatch(
                Request(
                    "iptal",
                    "ajan.durdur",
                    {
                        "turnId": identifier,
                        "agentId": record.agent_id,
                    },
                )
            )
            assert result["ok"] is False and not child.cancelled
        result = await session._dispatch(
            Request(
                "iptal",
                "ajan.durdur",
                {
                    "turnId": expected,
                    "agentId": record.agent_id,
                },
            )
        )
        assert result["ok"] is True
        assert child.cancelled and child.finished.is_set()
    finally:
        await session.close()
