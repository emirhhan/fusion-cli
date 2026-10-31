"""`/loop`, cron_* araçları, kalıcı kayıt ve vade tetiklemesi (P-038).

Ölçüldü (31 Ekim): `/schedule` yalnız tek seferlik hatırlatma basıyordu; `/loop`,
`cron_create/list/delete`, `schedule_wakeup` ve vadesi gelen görevin tur olarak
kuyruğa alınması yoktu.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from fusion_cli.cli.repl import cron_store, loop_command
from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.core.session_cron import SessionCron
from fusion_cli.core.tools import ToolContext
from fusion_cli.memory.factory import null_memory
from fusion_cli.tools.cron_tools import cron_tools
from fusion_cli.ui import messages

from .fakes import make_config


class _Clock:
    def __init__(self, now: float) -> None:
        self.value = now

    def now(self) -> float:
        return self.value

    def monotonic(self) -> float:
        return self.value


@pytest.fixture
def state(tmp_path: Path) -> ReplState:
    return ReplState(
        config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )


def _loop(state: ReplState, argument: str) -> str:
    command = build_registry().get("loop")
    assert command is not None and command.group == "Makro"
    return command.handler(state, argument)


# --- /loop ------------------------------------------------------------------------ #


def test_loop_aralikli_gorev_kurar(state: ReplState) -> None:
    cikti = _loop(state, "5m testleri koştur")
    tasks = state.cron.list()
    assert len(tasks) == 1 and tasks[0].every_s == 300 and tasks[0].prompt == "testleri koştur"
    assert tasks[0].id in cikti and "5m" in cikti


def test_loop_araliksiz_gorev_varsayilan_aralikla_kurulur(state: ReplState) -> None:
    _loop(state, "/verify")
    (task,) = state.cron.list()
    assert task.prompt == "/verify"
    assert task.every_s == 600


def test_loop_argumansiz_bakim_dosyasini_okur_yoksa_yerlesik(state: ReplState) -> None:
    _loop(state, "")
    assert state.cron.list()[0].prompt == loop_command.DEFAULT_MAINTENANCE_PROMPT
    state.cron.clear()
    (state.root / ".claude").mkdir()
    (state.root / ".claude" / "loop.md").write_text("Projeye özel bakım.\n", encoding="utf-8")
    _loop(state, "")
    assert state.cron.list()[0].prompt == "Projeye özel bakım."


def test_loop_list_ve_stop(state: ReplState) -> None:
    assert _loop(state, "list") == messages.LOOP_EMPTY
    _loop(state, "5m a")
    _loop(state, "10m b")
    liste = _loop(state, "list")
    assert "2 zamanlanmış görev" in liste and "her 5 dk" in liste
    task_id = state.cron.list()[0].id
    assert _loop(state, f"stop {task_id}") == messages.LOOP_STOPPED.format(id=task_id)
    assert _loop(state, "stop yok") == messages.LOOP_NOT_FOUND.format(id="yok")
    assert _loop(state, "stop all") == messages.LOOP_STOPPED_ALL.format(count=1)
    assert state.cron.list() == ()


def test_loop_kisa_aralik_turkce_hata_ve_kullanim(state: ReplState) -> None:
    cikti = _loop(state, "30s a")
    assert "en az 1 dakika" in cikti and messages.LOOP_USAGE in cikti
    assert state.cron.list() == ()


# --- Araçlar ---------------------------------------------------------------------- #


def _context(tmp_path: Path, cron: SessionCron | None) -> ToolContext:
    return ToolContext(root=tmp_path, cron=cron)


def _tool(name: str, clock: _Clock):
    return next(tool for tool in cron_tools(clock) if tool.name == name)


async def test_cron_create_list_delete_araclari(tmp_path: Path) -> None:
    clock = _Clock(1_000_000.0)
    cron = SessionCron()
    context = _context(tmp_path, cron)
    create, list_tool, delete = (
        _tool(n, clock) for n in ("cron_create", "cron_list", "cron_delete")
    )

    sonuc = await _run(create, {"prompt": "stok kontrol", "every": "15m"}, context)
    assert sonuc.ok and "her 15 dk" in sonuc.output
    (task,) = cron.list()
    assert task.next_due == 1_000_000.0 + 900

    listed = await _run(list_tool, {}, context)
    assert task.id in listed.output

    assert (await _run(delete, {"id": task.id}, context)).ok
    assert not (await _run(delete, {"id": task.id}, context)).ok
    assert "Zamanlanmış görev yok" in (await _run(list_tool, {}, context)).output


async def test_cron_create_tek_zamanlama_ister_ve_cron_ifadesi_kabul_eder(tmp_path: Path) -> None:
    clock = _Clock(1_000_000.0)
    context = _context(tmp_path, SessionCron())
    create = _tool("cron_create", clock)
    assert not (await _run(create, {"prompt": "x"}, context)).ok
    assert not (await _run(create, {"prompt": "x", "every": "5m", "in": "5m"}, context)).ok
    assert (await _run(create, {"prompt": "x", "cron": "*/30 * * * *"}, context)).ok
    assert not (await _run(create, {"prompt": "x", "cron": "bozuk"}, context)).ok


async def test_schedule_wakeup_tek_seferlik_not_kurar(tmp_path: Path) -> None:
    clock = _Clock(1_000_000.0)
    cron = SessionCron()
    sonuc = await _run(
        _tool("schedule_wakeup", clock),
        {"in": "10m", "note": "CI bitti mi bak"},
        _context(tmp_path, cron),
    )
    assert sonuc.ok
    (task,) = cron.list()
    assert task.prompt == "CI bitti mi bak" and task.next_due == 1_000_000.0 + 600
    assert cron.due(1_000_000.0 + 600) == (task,)


async def test_zamanlayici_yoksa_araclar_aciklayici_hata_verir(tmp_path: Path) -> None:
    clock = _Clock(0.0)
    sonuc = await _run(_tool("cron_list", clock), {}, _context(tmp_path, None))
    assert not sonuc.ok and "zamanlayıcı yok" in sonuc.output


async def _run(tool, args, context):
    result = tool.run(args, context)
    return await result if asyncio.iscoroutine(result) else result


# --- Kayıt ------------------------------------------------------------------------ #


def test_kayit_yazilir_okunur_bos_listede_silinir(tmp_path: Path) -> None:
    cron = SessionCron()
    task = cron.create_interval("a", "5m", now=100.0)
    cron_store.save(tmp_path, "sohbet/1", cron)
    yol = cron_store.store_path(tmp_path, "sohbet/1")
    assert yol.exists() and yol.parent == tmp_path / "oturum-cron"
    assert [t.id for t in cron_store.load(tmp_path, "sohbet/1").list()] == [task.id]
    cron_store.save(tmp_path, "sohbet/1", SessionCron())
    assert not yol.exists()
    assert cron_store.load(tmp_path, "yok").list() == ()


def test_bozuk_kayit_bos_liste_verir(tmp_path: Path) -> None:
    yol = cron_store.store_path(tmp_path, "s")
    yol.parent.mkdir(parents=True)
    yol.write_text("{bozuk", encoding="utf-8")
    assert cron_store.load(tmp_path, "s").list() == ()


# --- Tetikleme (REPL) -------------------------------------------------------------- #


async def test_vadesi_gelen_gorev_istem_beklerken_satir_olarak_girer(
    state: ReplState, monkeypatch
) -> None:
    from rich.console import Console

    from fusion_cli.cli.repl import loop as repl_loop

    class _Reader:
        def __init__(self) -> None:
            self.injected: list[str] = []
            self.waiting = True

        def inject(self, line: str) -> bool:
            if not self.waiting:
                return False
            self.injected.append(line)
            return True

    reader = _Reader()
    task = state.cron.create_interval("testleri koştur", "5m", now=0.0)
    monkeypatch.setattr(repl_loop, "CRON_POLL_S", 0.0)
    monkeypatch.setattr(repl_loop.time, "time", lambda: 301.0)
    console = Console(record=True, width=200, force_terminal=False, no_color=True)

    watcher = asyncio.ensure_future(repl_loop._cron_watcher(state, reader, console))
    for _ in range(20):
        await asyncio.sleep(0)
        if reader.injected:
            break
    state.running = False
    await asyncio.wait_for(watcher, 1)

    assert reader.injected == ["testleri koştur"]
    guncel = state.cron.get(task.id)
    assert guncel is not None and guncel.runs == 1 and guncel.next_due == 601.0
    assert task.id in console.export_text()


async def test_istem_acik_degilken_gorev_dusmez(state: ReplState, monkeypatch) -> None:
    from rich.console import Console

    from fusion_cli.cli.repl import loop as repl_loop

    class _Reader:
        def inject(self, line: str) -> bool:
            return False

    task = state.cron.create_interval("a", "5m", now=0.0)
    monkeypatch.setattr(repl_loop, "CRON_POLL_S", 0.0)
    monkeypatch.setattr(repl_loop.time, "time", lambda: 301.0)
    watcher = asyncio.ensure_future(
        repl_loop._cron_watcher(state, _Reader(), Console(record=True, force_terminal=False))
    )
    for _ in range(5):
        await asyncio.sleep(0)
    state.running = False
    await asyncio.wait_for(watcher, 1)
    assert state.cron.get(task.id) is not None and state.cron.get(task.id).runs == 0  # type: ignore[union-attr]


# --- Motor kayıt defteri ve masaüstü RPC ------------------------------------------ #


def test_cron_araclari_yalniz_zamanlayicili_baglamda_sunulur(tmp_path: Path) -> None:
    from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
    from fusion_cli.engines.agent.engine_tools import build_agent_registry
    from fusion_cli.engines.agent.loop import AgentDeps

    from .fakes import AlwaysApprove

    class _Pub:
        def publish(self, event) -> None:
            pass

    async def _run(*args, **kwargs):  # pragma: no cover - çağrılmaz
        raise AssertionError

    def _deps(context: ToolContext) -> AgentDeps:
        return AgentDeps(
            config=make_config(),
            publisher=_Pub(),
            policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
            tool_context=context,
        )

    with_cron = build_agent_registry(
        _deps(_context(tmp_path, SessionCron())), depth=0, run_agent=_run
    )
    without = build_agent_registry(_deps(_context(tmp_path, None)), depth=0, run_agent=_run)
    for name in ("cron_create", "cron_list", "cron_delete", "schedule_wakeup"):
        assert with_cron.get(name) is not None
        assert without.get(name) is None


async def test_masaustu_cron_rpc_listeler_siler_ve_vadesi_gelenleri_bir_kez_verir(
    tmp_path: Path, monkeypatch
) -> None:
    import json

    from fusion_cli.appserver.protocol import Request
    from fusion_cli.appserver.session import AppSession

    monkeypatch.setenv("FUSION_KEYCHAIN", "off")
    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")
    baslangic = 1_800_000_000.0
    monkeypatch.setattr("fusion_cli.appserver.session.time.time", lambda: baslangic)
    task = oturum._state.cron.create_interval("stok kontrol", "5m", now=baslangic)

    async def rpc(kimlik: str, ad: str, veri: dict | None = None) -> dict:
        await oturum.handle(Request(id=kimlik, name=ad, data=veri or {}))
        for satir in reversed(satirlar):
            paket = json.loads(satir)
            if paket.get("tip") == "sonuc" and paket.get("id") == kimlik:
                return paket["veri"]
        raise AssertionError(f"sonuç yok: {kimlik}")

    liste = await rpc("1", "cron.listele")
    assert liste["ok"] is True and [g["id"] for g in liste["gorevler"]] == [task.id]

    monkeypatch.setattr("fusion_cli.appserver.session.time.time", lambda: baslangic + 301)
    vade = await rpc("2", "cron.vadesi_gelenler")
    assert vade["gorevler"] == [{"id": task.id, "gorev": "stok kontrol"}]
    assert (await rpc("3", "cron.vadesi_gelenler"))["gorevler"] == []

    sil = await rpc("4", "cron.sil", {"id": task.id})
    assert sil["ok"] is True and sil["silinen"] == 1
    assert (await rpc("5", "cron.sil", {"id": task.id}))["ok"] is False
