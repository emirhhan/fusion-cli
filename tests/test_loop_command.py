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
    assert vade["gorevler"] == [{"id": task.id, "gorev": "stok kontrol", "kaynak": "kullanici"}]
    assert (await rpc("3", "cron.vadesi_gelenler"))["gorevler"] == []

    sil = await rpc("4", "cron.sil", {"id": task.id})
    assert sil["ok"] is True and sil["silinen"] == 1
    assert (await rpc("5", "cron.sil", {"id": task.id}))["ok"] is False


# --- Ajan görevi komut değil turdur (inceleme bulgusu, yüksek) --------------------- #


def test_loop_onay_kipini_degistiren_komutu_zamanlamaz(state: ReplState) -> None:
    for satir in ("5m /bypass", "/auto", "10m /mode hizli", "/loop 5m x"):
        cikti = _loop(state, satir)
        assert "zamanlanmış görev olamaz" in cikti, satir
    assert len(state.cron) == 0
    # `/verify` gibi zararsız komutlar zamanlanabilir.
    assert "döngü kuruldu" in _loop(state, "5m /verify")


def test_loop_yasakli_komutun_takma_adini_da_zamanlamaz(state: ReplState) -> None:
    """Ölçüldü (31 Ekim): yasak ham ada bakıyordu; `/loop 5m /dikte` (voice takma adı)
    kuruluyor, mikrofon zamanlayıcıdan açılabiliyordu (`/q`, `/dev`, `/manuel` de geçiyordu)."""
    for satir in ("5m /dikte", "/q", "5m /dev", "5m /manuel", "5m /rc", "5m /remote-control"):
        cikti = _loop(state, satir)
        assert "zamanlanmış görev olamaz" in cikti, satir
    assert len(state.cron) == 0


async def test_cron_create_araci_gorevi_ajan_kaynagiyla_kurar(tmp_path: Path) -> None:
    from fusion_cli.core.session_cron import Source

    cron = SessionCron()
    context = _context(tmp_path, cron)
    create = _tool("cron_create", _Clock(0.0))
    wakeup = _tool("schedule_wakeup", _Clock(0.0))
    create.run({"prompt": "/bypass", "in": "1m"}, context)
    wakeup.run({"in": "2m", "note": "/auto"}, context)
    assert [task.source for task in cron.list()] == [Source.AGENT, Source.AGENT]
    # Kullanıcının `/loop`u ise kullanıcı kaynaklıdır.
    assert cron.create_interval("a", "5m", now=0.0).source is Source.USER


async def test_ajan_gorevi_vadesi_gelince_yalniz_tur_isareti_koyar(
    state: ReplState, monkeypatch
) -> None:
    from rich.console import Console

    from fusion_cli.cli.repl import loop as repl_loop
    from fusion_cli.core.session_cron import Source

    class _Reader:
        def __init__(self) -> None:
            self.injected: list[str] = []
            self.isaretler: list[bool] = []

        def inject(self, line: str) -> bool:
            self.injected.append(line)
            self.isaretler.append(state.scheduled_turn_only)
            return True

    reader = _Reader()
    state.cron.create_once("/bypass", "1m", now=0.0, source=Source.AGENT)
    monkeypatch.setattr(repl_loop, "CRON_POLL_S", 0.0)
    monkeypatch.setattr(repl_loop.time, "time", lambda: 61.0)
    watcher = asyncio.ensure_future(
        repl_loop._cron_watcher(state, reader, Console(record=True, force_terminal=False))
    )
    for _ in range(20):
        await asyncio.sleep(0)
        if reader.injected:
            break
    state.running = False
    await asyncio.wait_for(watcher, 1)
    assert reader.injected == ["/bypass"] and reader.isaretler == [True]

    # Kullanıcı görevi işaret koymaz.
    state.running = True
    state.cron.create_once("/verify", "1m", now=0.0)
    reader2 = _Reader()
    watcher = asyncio.ensure_future(
        repl_loop._cron_watcher(state, reader2, Console(record=True, force_terminal=False))
    )
    for _ in range(20):
        await asyncio.sleep(0)
        if reader2.injected:
            break
    state.running = False
    await asyncio.wait_for(watcher, 1)
    assert reader2.isaretler == [False]


async def test_repl_ajan_zamanlamasi_slash_satirini_komut_olarak_calistirmaz(
    state: ReplState, monkeypatch
) -> None:
    from rich.console import Console

    from fusion_cli.cli.repl import loop as repl_loop
    from fusion_cli.core.concurrency import BackgroundTasks
    from fusion_cli.engines.agent.approval import ApprovalMode

    turlar: list[str] = []

    async def sahte_tur(line, state, console, background, *, mode=None):
        turlar.append(line)

    async def sahte_kart(*args, **kwargs):
        return None

    monkeypatch.setattr(repl_loop, "_run_turn", sahte_tur)
    monkeypatch.setattr(repl_loop, "_offer_plan_card", sahte_kart)

    class _Reader:
        mode = state.approval
        interactive = False

    console = Console(record=True, force_terminal=False)
    registry = build_registry()
    state.scheduled_turn_only = True
    await repl_loop._handle("/edits", state, registry, _Reader(), console, BackgroundTasks())
    assert turlar == ["/edits"] and state.approval is not ApprovalMode.ACCEPT_EDITS
    assert state.scheduled_turn_only is False

    # İşaret yokken aynı satır komuttur (kullanıcının elle yazdığı /edits; /bypass
    # Claude gibi bypass'sız oturumda açılmaz).
    await repl_loop._handle("/edits", state, registry, _Reader(), console, BackgroundTasks())
    assert turlar == ["/edits"] and state.approval is ApprovalMode.ACCEPT_EDITS


async def test_tui_ajan_zamanlamasi_slash_satirini_tur_olarak_calistirir(
    state: ReplState, monkeypatch
) -> None:
    from fusion_cli.cli.repl import tui_loop
    from fusion_cli.cli.repl.tui_loop import _TuiSession
    from fusion_cli.core.session_cron import Source
    from fusion_cli.engines.agent.approval import ApprovalMode

    session = _TuiSession(state)
    turlar: list[str] = []
    komutlar: list[str] = []

    async def sahte_tur(line: str, *, mode=None) -> None:
        turlar.append(line)

    async def sahte_komut(line: str) -> None:
        komutlar.append(line)

    session._turn = sahte_tur  # type: ignore[method-assign]
    session._command = sahte_komut  # type: ignore[method-assign]
    state.cron.create_once("/bypass", "1m", now=0.0, source=Source.AGENT)
    monkeypatch.setattr(tui_loop, "CRON_POLL_S", 0.0)
    monkeypatch.setattr(tui_loop.time, "time", lambda: 61.0)

    watcher = asyncio.ensure_future(session._cron_watcher())
    for _ in range(20):
        await asyncio.sleep(0)
        if turlar or komutlar:
            break
    state.running = False
    await asyncio.wait_for(watcher, 1)
    if session._task is not None:
        await session._task
    assert turlar == ["/bypass"] and komutlar == []
    assert state.approval is not ApprovalMode.BYPASS


# --- Gerçek ReplInput.inject (prompt_toolkit) ------------------------------------- #


async def _gercek_istem(tmp_path: Path, monkeypatch):
    """Gerçek ReplInput istemini borulu girdiyle aç."""
    from fusion_cli.cli.repl.input import ReplInput
    from fusion_cli.engines.agent.approval import ApprovalMode

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setenv("TERM", "xterm-256color")
    reader = ReplInput(tmp_path / "history", ["/help"], mode=ApprovalMode.AUTO)
    assert reader.interactive
    ready = asyncio.Event()
    reader._session.app.pre_run_callables.append(ready.set)
    prompt = asyncio.ensure_future(reader.prompt())
    await asyncio.wait_for(ready.wait(), 2)
    return reader, prompt


async def test_gercek_istem_bosken_inject_satiri_verir(tmp_path: Path, monkeypatch) -> None:
    from prompt_toolkit.application import create_app_session
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        reader, prompt = await _gercek_istem(tmp_path, monkeypatch)
        assert reader.inject("testleri koştur") is True
        assert await asyncio.wait_for(prompt, 2) == "testleri koştur"


async def test_gercek_istem_doluyken_inject_yazilani_silmez(tmp_path: Path, monkeypatch) -> None:
    """Ölçüldü (31 Ekim): yarım yazılmış satır varken vade gelince `app.exit` tamponu
    atıyor, kullanıcının yazdığı kayboluyordu."""
    from prompt_toolkit.application import create_app_session
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        reader, prompt = await _gercek_istem(tmp_path, monkeypatch)
        received = asyncio.Event()

        def text_changed(buffer) -> None:
            if buffer.text == "yarım mesaj":
                received.set()

        reader._session.default_buffer.on_text_changed += text_changed
        pipe.send_text("yarım mesaj")
        await asyncio.wait_for(received.wait(), 2)
        assert reader.inject("testleri koştur") is False
        assert not prompt.done()
        pipe.send_text(" bitti\r")
        assert await asyncio.wait_for(prompt, 2) == "yarım mesaj bitti"


# --- Masaüstü RPC: geri verme, meşgul, sohbet değişimi (inceleme bulgusu) --------- #


def _app_oturumu(tmp_path: Path, monkeypatch, simdi: list[float]):
    import json

    from fusion_cli.appserver.protocol import Request
    from fusion_cli.appserver.session import AppSession

    monkeypatch.setenv("FUSION_KEYCHAIN", "off")
    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")
    monkeypatch.setattr("fusion_cli.appserver.session.time.time", lambda: simdi[0])
    sayac = iter(range(1000))

    async def rpc(ad: str, veri: dict | None = None) -> dict:
        kimlik = f"r{next(sayac)}"
        await oturum.handle(Request(id=kimlik, name=ad, data=veri or {}))
        for satir in reversed(satirlar):
            paket = json.loads(satir)
            if paket.get("tip") == "sonuc" and paket.get("id") == kimlik:
                return paket["veri"]
        raise AssertionError(f"sonuç yok: {ad}")

    return oturum, rpc


async def test_masaustu_gonderilemeyen_gorev_geri_verilir(tmp_path: Path, monkeypatch) -> None:
    """Ölçüldü (31 Ekim): `cron.vadesi_gelenler` görevi göndermeden ilerletiyordu;
    arayüz gönderemezse (sekme meşgul) o vade boşa gidiyor, tek seferlik görev
    tamamen kayboluyordu."""
    simdi = [1_800_000_000.0]
    oturum, rpc = _app_oturumu(tmp_path, monkeypatch, simdi)
    tek = oturum._state.cron.create_once("uyan", "2m", now=simdi[0])
    simdi[0] += 121
    vade = await rpc("cron.vadesi_gelenler")
    assert [g["id"] for g in vade["gorevler"]] == [tek.id]
    assert oturum._state.cron.get(tek.id) is None

    geri = await rpc("cron.geri_ver", {"id": tek.id})
    assert geri["ok"] is True
    assert (await rpc("cron.vadesi_gelenler"))["gorevler"][0]["id"] == tek.id
    # Verilmemiş görev geri verilemez; ikinci geri verme reddedilir.
    assert (await rpc("cron.geri_ver", {"id": "yok"}))["ok"] is False


async def test_masaustu_tur_surerken_bos_liste_verir(tmp_path: Path, monkeypatch) -> None:
    simdi = [1_800_000_000.0]
    oturum, rpc = _app_oturumu(tmp_path, monkeypatch, simdi)
    gorev = oturum._state.cron.create_interval("a", "5m", now=simdi[0])
    simdi[0] += 301
    oturum._turn = asyncio.get_running_loop().create_future()
    try:
        cevap = await rpc("cron.vadesi_gelenler")
    finally:
        oturum._turn.set_result(None)
    assert cevap["gorevler"] == [] and cevap["mesgul"] is True
    assert oturum._state.cron.get(gorev.id).runs == 0  # type: ignore[union-attr]


async def test_kimliksiz_oturum_gorevleri_sohbet_kimligine_tasinir(
    tmp_path: Path, monkeypatch
) -> None:
    """Ölçüldü (31 Ekim): sohbet kimliği gelmeden kurulan görev, kimlik gelince
    `cron_store.load` ile değiştirilip düşüyordu."""
    import time

    # Gerçek saat: yükleme bayat kayıt süpürmesini dosya zamanına göre yapar.
    simdi = [time.time()]
    oturum, rpc = _app_oturumu(tmp_path, monkeypatch, simdi)
    gorev = oturum._state.cron.create_interval("stok", "5m", now=simdi[0])
    oturum._cron_save()
    memory_dir = oturum._state.config.memory_dir
    assert cron_store.store_path(memory_dir, "app").exists()

    await rpc("oturum.baslat", {"sohbet_id": "sohbet-1"})

    assert oturum._state.cron.get(gorev.id) is not None
    assert cron_store.load(memory_dir, "sohbet-1").get(gorev.id) is not None
    assert not cron_store.store_path(memory_dir, "app").exists()


def test_bayat_kayitlar_temizlenir_tazeler_kalir(tmp_path: Path) -> None:
    """Terminal REPL'i her açılışta yeni kimlik ürettiğinden kayıtlar birikiyordu."""
    import os

    from fusion_cli.core.session_cron import MAX_AGE_S

    simdi = 1_800_000_000.0
    taze = SessionCron()
    taze.create_interval("a", "5m", now=simdi)
    cron_store.save(tmp_path, "taze", taze)
    cron_store.save(tmp_path, "bayat", taze)
    bayat = cron_store.store_path(tmp_path, "bayat")
    os.utime(bayat, (simdi - MAX_AGE_S - 10, simdi - MAX_AGE_S - 10))
    os.utime(cron_store.store_path(tmp_path, "taze"), (simdi, simdi))

    assert cron_store.sweep_stale(tmp_path, now=simdi) == 1
    assert not bayat.exists() and cron_store.store_path(tmp_path, "taze").exists()


def test_yukleme_bayat_kayitlari_supurur(tmp_path: Path) -> None:
    import os
    import time

    from fusion_cli.core.session_cron import MAX_AGE_S

    cron = SessionCron()
    cron.create_interval("a", "5m", now=time.time())
    cron_store.save(tmp_path, "eski-repl", cron)
    eski = cron_store.store_path(tmp_path, "eski-repl")
    gecmis = time.time() - MAX_AGE_S - 60
    os.utime(eski, (gecmis, gecmis))

    assert len(cron_store.load(tmp_path, "yeni-repl")) == 0
    assert not eski.exists()


# --- Kendi tempolu döngü (P-038 kalanı) --------------------------------------- #


def test_loop_araliksiz_metin_gorevi_kendi_tempolu_ve_hemen_vadeli(state: ReplState) -> None:
    """Ölçüldü (31 Ekim): aralıksız `/loop <görev>` sabit 10 dk'ydı; tempo ajanın olmalı."""
    from fusion_cli.core.session_cron import Kind

    cikti = _loop(state, "CI'ı izle")
    (task,) = state.cron.list()
    assert task.kind is Kind.SELF_PACED
    assert "kendi tempolu" in cikti
    assert state.cron.due(task.created_at) == (task,)
    istem = loop_command.fire_prompt(task)
    assert "CI'ı izle" in istem and f'loop_id="{task.id}"' in istem


def test_kendi_tempolu_dongu_ajanin_sectigi_gecikmeyle_yeniden_kurulur(state: ReplState) -> None:
    from fusion_cli.core.session_cron import SELF_PACED_FALLBACK_S, SELF_PACED_MAX_S

    saat = _Clock(1_000_000.0)
    task = state.cron.create_self_paced("CI'ı izle", now=saat.value)
    sonraki = state.cron.complete(task.id, now=saat.value)
    assert sonraki is not None and sonraki.next_due == saat.value + SELF_PACED_FALLBACK_S

    araclar = {tool.name: tool for tool in cron_tools(saat)}
    baglam = ToolContext(root=state.root, cron=state.cron)
    sonuc = araclar["schedule_wakeup"].run({"in": "3m", "loop_id": task.id}, baglam)
    assert sonuc.ok
    assert state.cron.get(task.id).next_due == saat.value + 180  # type: ignore[union-attr]
    araclar["schedule_wakeup"].run({"in": "5h", "loop_id": task.id}, baglam)
    assert state.cron.get(task.id).next_due == saat.value + SELF_PACED_MAX_S  # type: ignore[union-attr]
    assert len(state.cron) == 1, "loop_id yeni görev açmamalı"


def test_schedule_wakeup_loop_id_yalniz_kendi_tempolu_gorevde(state: ReplState) -> None:
    saat = _Clock(1_000_000.0)
    sabit = state.cron.create_interval("a", "5m", now=saat.value)
    araclar = {tool.name: tool for tool in cron_tools(saat)}
    sonuc = araclar["schedule_wakeup"].run(
        {"in": "3m", "loop_id": sabit.id}, ToolContext(root=state.root, cron=state.cron)
    )
    assert not sonuc.ok
