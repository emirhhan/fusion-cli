"""Alt ajan ekibi: kişilik, kimlik, paralel dalgalar ve yazma alanı."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from fusion_cli.core.errors import PathAccessError
from fusion_cli.core.events import StatusChanged, SubAgentFinished, SubAgentStarted
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps
from fusion_cli.engines.agent.team import (
    GENERIC_PERSONA,
    ScopedPublisher,
    SubTask,
    derive_sub_context,
    resolve_persona,
    run_team,
    schedule_waves,
    spawn_agents_tool,
)
from fusion_cli.tools.capabilities import CapabilityRegistry
from fusion_cli.tools.files import writable_path
from tests.agent_harness import Publisher
from tests.fakes import AlwaysApprove, RecordingSink, make_config


def _deps(tmp_path, sink, **runtime):
    return AgentDeps(
        config=make_config(runtime=runtime) if runtime else make_config(),
        publisher=Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        capabilities=CapabilityRegistry(tmp_path / "ev", tmp_path),
    )


def test_salt_okuyanlar_ve_ayrik_alanlar_ayni_dalgada_kosar():
    gorevler = [
        SubTask("ara", read_only=True),
        SubTask("css", write_scope=("site/css",)),
        SubTask("js", write_scope=("site/js",)),
        SubTask("oku", read_only=True),
    ]

    assert schedule_waves(gorevler) == [[0, 1, 2, 3]]


def test_cakisan_alan_yeni_dalga_acar():
    gorevler = [
        SubTask("a", write_scope=("site",)),
        SubTask("b", write_scope=("site/index.html",)),
    ]

    assert schedule_waves(gorevler) == [[0], [1]]


def test_alani_belirsiz_yazan_tek_basina_kosar():
    gorevler = [
        SubTask("oku", read_only=True),
        SubTask("her yere yazabilir"),
        SubTask("oku 2", read_only=True),
    ]

    assert schedule_waves(gorevler) == [[0], [1], [2]]


def test_kapsamli_yayinci_ic_kimligi_ezmez():
    sink = RecordingSink()
    dis = ScopedPublisher(Publisher(sink), "dis")
    ic = ScopedPublisher(dis, "ic")

    ic.publish(StatusChanged("x"))
    dis.publish(StatusChanged("y"))

    assert [olay.agent_id for olay in sink.events] == ["ic", "dis"]


def test_yerlesik_ekip_uyesi_kisiligiyle_cozulur(tmp_path):
    kutuphane = CapabilityRegistry(tmp_path / "ev", tmp_path)

    tasarimci = resolve_persona(kutuphane, "tasarimci")
    arastirmaci = resolve_persona(kutuphane, "arastirmaci")

    assert tasarimci.title == "Arayüz Tasarımcısı"
    assert tasarimci.avatar == "tasarimci"
    assert "CSS değişkeni" in tasarimci.prompt
    assert arastirmaci.tools is not None and "write_file" not in arastirmaci.tools


def test_kullanicinin_ayni_adli_ajani_yerlesigi_ezer(tmp_path):
    ajanlar = tmp_path / ".claude" / "agents"
    ajanlar.mkdir(parents=True)
    (ajanlar / "tasarimci.md").write_text(
        "---\nname: tasarimci\ndescription: d\nunvan: Benim Tasarımcım\navatar: ozel\n---\n"
        "kendi talimatım\n",
        encoding="utf-8",
    )

    kisi = resolve_persona(CapabilityRegistry(tmp_path / "ev", tmp_path), "tasarimci")

    assert kisi.title == "Benim Tasarımcım"
    assert kisi.prompt.strip() == "kendi talimatım"


def test_bilinmeyen_uye_genel_yardimciya_duser(tmp_path):
    assert resolve_persona(CapabilityRegistry(tmp_path, tmp_path), "yok-boyle") == GENERIC_PERSONA


def test_yazma_alani_disina_yazilamaz(tmp_path):
    baglam = derive_sub_context(
        ToolContext(root=tmp_path), SubTask("css", write_scope=("site/css",))
    )

    assert writable_path(baglam, "site/css/ana.css") == tmp_path / "site/css/ana.css"
    with pytest.raises(PathAccessError, match="yazma alanı dışında"):
        writable_path(baglam, "site/index.html")


def test_alani_olmayan_baglam_her_yere_yazar(tmp_path):
    assert writable_path(ToolContext(root=tmp_path), "x.txt") == tmp_path / "x.txt"


async def test_ekip_ayni_dalgadaki_uyeleri_gercekten_es_zamanli_kosar(tmp_path):
    sink = RecordingSink()
    deps = _deps(tmp_path, sink)
    baslayan = 0
    hepsi_basladi = asyncio.Event()
    gorulen_araclar: list[set[str] | None] = []

    async def _sahte_ajan(task, sub_deps, **kwargs):
        nonlocal baslayan
        gorulen_araclar.append(kwargs.get("allowed_tools"))
        sub_deps.publisher.publish(StatusChanged(f"{task} çalışıyor"))
        baslayan += 1
        if baslayan == 2:
            hepsi_basladi.set()
        # İkisi de başlamadan hiçbiri bitemez: sıralı koşu burada kilitlenirdi.
        await asyncio.wait_for(hepsi_basladi.wait(), timeout=2)
        return SimpleNamespace(final_text=f"{task} bitti", ok=True, tool_calls_made=1)

    sonuclar = await run_team(
        deps,
        [
            SubTask("ara", persona="arastirmaci", read_only=True),
            SubTask("tasarla", persona="x", write_scope=("site",)),
        ],
        depth=0,
        run_agent=_sahte_ajan,
    )

    assert [sonuc.text for sonuc in sonuclar] == ["ara bitti", "tasarla bitti"]
    basladi = [olay for olay in sink.events if isinstance(olay, SubAgentStarted)]
    bitti = [olay for olay in sink.events if isinstance(olay, SubAgentFinished)]
    assert len({olay.sub_id for olay in basladi}) == 2
    assert {olay.group_size for olay in basladi} == {2}
    assert {olay.sub_id for olay in bitti} == {olay.sub_id for olay in basladi}
    durumlar = [olay for olay in sink.events if isinstance(olay, StatusChanged)]
    assert {olay.agent_id for olay in durumlar} == {olay.sub_id for olay in basladi}
    # Salt okuyan üyeye değiştirici araç sunulmaz.
    assert gorulen_araclar[0] is not None and "write_file" not in gorulen_araclar[0]


async def test_es_zamanlilik_tavani_asilmaz(tmp_path):
    sink = RecordingSink()
    deps = _deps(tmp_path, sink, max_parallel_agents=2)
    aktif = 0
    en_cok = 0

    async def _sahte_ajan(task, sub_deps, **kwargs):
        nonlocal aktif, en_cok
        aktif += 1
        en_cok = max(en_cok, aktif)
        await asyncio.sleep(0.01)
        aktif -= 1
        return SimpleNamespace(final_text="ok", ok=True, tool_calls_made=0)

    await run_team(
        deps, [SubTask(f"g{i}", read_only=True) for i in range(5)], depth=0, run_agent=_sahte_ajan
    )

    assert en_cok == 2


async def test_spawn_agents_araci_birlesik_rapor_doner(tmp_path):
    sink = RecordingSink()
    deps = _deps(tmp_path, sink)

    async def _sahte_ajan(task, sub_deps, **kwargs):
        return SimpleNamespace(final_text=f"{task}: sonuç", ok=True, tool_calls_made=0)

    arac = spawn_agents_tool(deps, depth=0, run_agent=_sahte_ajan)
    sonuc = await arac.run(
        {"gorevler": [{"task": "a", "uzman": "mimar", "salt_okunur": True}, {"task": "b"}]},
        deps.tool_context,
    )

    assert "## Mimar" in sonuc.output
    assert "a: sonuç" in sonuc.output and "b: sonuç" in sonuc.output


async def test_spawn_agents_alt_ajanda_derinlik_sinirina_takilir(tmp_path):
    deps = _deps(tmp_path, RecordingSink())

    async def _hic(*_args, **_kwargs):
        raise AssertionError("çağrılmamalı")

    # Varsayılan `max_agent_depth` 3 (Claude Code): derinlik 3'teki ajan yeni ajan açamaz.
    arac = spawn_agents_tool(deps, depth=3, run_agent=_hic)
    sonuc = await arac.run({"gorevler": [{"task": "a"}]}, deps.tool_context)

    assert "derinlik" in sonuc.output


def test_bos_kimlikli_olay_tel_uzerinde_kimlik_tasimaz():
    from fusion_cli.appserver.serialize import event_to_dict

    assert "agent_id" not in event_to_dict(StatusChanged("x"))
    assert event_to_dict(replace(StatusChanged("x"), agent_id="k"))["agent_id"] == "k"


async def test_child_exception_does_not_cancel_independent_sibling(tmp_path):
    sink = RecordingSink()
    deps = _deps(tmp_path, sink)

    async def run(task, sub_deps, **kwargs):
        if task == "broken":
            raise ValueError("fixture failure")
        await asyncio.sleep(0)
        return SimpleNamespace(final_text="verified sibling", ok=True, tool_calls_made=1)

    results = await run_team(
        deps,
        [SubTask("broken", read_only=True), SubTask("healthy", read_only=True)],
        depth=0,
        run_agent=run,
    )
    assert [result.ok for result in results] == [False, True]
    started = [event for event in sink.events if isinstance(event, SubAgentStarted)]
    finished = [event for event in sink.events if isinstance(event, SubAgentFinished)]
    assert len(started) == len(finished) == 2
    assert {event.sub_id for event in started} == {event.sub_id for event in finished}


async def test_cancelled_parent_closes_every_started_child(tmp_path):
    sink = RecordingSink()
    deps = _deps(tmp_path, sink)
    entered = asyncio.Event()
    count = 0

    async def run(task, sub_deps, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            entered.set()
        await asyncio.Event().wait()

    parent = asyncio.create_task(
        run_team(
            deps,
            [SubTask("a", read_only=True), SubTask("b", read_only=True)],
            depth=0,
            run_agent=run,
        )
    )
    await entered.wait()
    parent.cancel()
    with pytest.raises(asyncio.CancelledError):
        await parent
    finished = [event for event in sink.events if isinstance(event, SubAgentFinished)]
    assert len(finished) == 2
    assert all(not event.ok for event in finished)


async def test_child_closes_its_optional_question_before_return(tmp_path):
    from fusion_cli.engines.agent.team import run_subagent

    sink = RecordingSink()
    deps = _deps(tmp_path, sink)
    entered, cancelled = asyncio.Event(), asyncio.Event()
    owners = []

    async def answer():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def run(task, sub_deps, **kwargs):
        owners.append(sub_deps.questions)
        sub_deps.questions.start(answer())
        await entered.wait()
        return SimpleNamespace(final_text="sonuç", ok=True, tool_calls_made=0)

    await run_subagent(deps, SubTask("oku", read_only=True), depth=0, run_agent=run)
    try:
        assert cancelled.is_set()
    finally:
        for owner in owners:
            await owner.close()


async def test_readonly_child_does_not_inherit_parent_mutation_evidence(tmp_path, monkeypatch):
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
    from fusion_cli.engines.agent.loop import run_agent
    from fusion_cli.engines.agent.team import run_subagent
    from tests.agent_harness import install_provider
    from tests.fakes import ScriptedProvider, model_result

    text = (
        "İnceleme sonucu: mevcut yaklaşım tutarlı. Bu görev yalnız açıklamayı değerlendirdi; "
        "dosya veya dış sistem değişikliği gerektirmedi. "
        "Bulgular değerlendirme kapsamında tamamlandı."
    )
    install_provider(monkeypatch, ScriptedProvider([model_result(text)] * 4))
    deps = _deps(tmp_path, RecordingSink())
    deps.execution = ExecutionPolicy(
        is_web=False,
        requires_tool_evidence=True,
        required_effect="workspace_mutation",
    )
    result = await run_subagent(
        deps,
        SubTask("Bu açıklamayı değerlendir", read_only=True),
        depth=0,
        run_agent=run_agent,
    )
    assert result.ok
    assert "dosya veya dış sistem" in result.text


def test_scoped_child_cannot_use_unbounded_shell_or_remote_mutations(tmp_path):
    from fusion_cli.core.tools import Tool, ToolEffect, ToolResult
    from fusion_cli.engines.agent.team import _allowed_tools
    from fusion_cli.tools.registry import ToolRegistry

    def run(args, context):
        return ToolResult("fixture")

    deps = _deps(tmp_path, RecordingSink())
    registry = ToolRegistry()
    for tool in [
        Tool("write_file", "", {}, run, mutating=True),
        Tool("run_shell", "", {}, run, mutating=True),
        Tool("offline__write", "", {}, run, mutating=True, effect=ToolEffect.REMOTE_WRITE),
        Tool("read_file", "", {}, run),
    ]:
        registry.register(tool)
    deps.base_registry = registry
    allowed = _allowed_tools(deps, GENERIC_PERSONA, SubTask("yaz", write_scope=("src",)))
    assert allowed == {"write_file", "read_file"}


async def test_persona_exception_does_not_cancel_sibling(tmp_path, monkeypatch):
    from fusion_cli.engines.agent import team

    original = team.resolve_persona

    def resolve(library, name):
        if name == "broken":
            raise ValueError("fixture")
        return original(library, name)

    monkeypatch.setattr(team, "resolve_persona", resolve)
    sink = RecordingSink()

    async def run(task, sub_deps, **kwargs):
        return SimpleNamespace(final_text="sonuç", ok=True, tool_calls_made=0)

    results = await run_team(
        _deps(tmp_path, sink),
        [SubTask("a", persona="broken", read_only=True), SubTask("b", read_only=True)],
        depth=0,
        run_agent=run,
    )
    assert [result.ok for result in results] == [False, True]
    assert len([event for event in sink.events if isinstance(event, SubAgentFinished)]) == 2


async def test_child_write_evidence_does_not_claim_sibling_paths(tmp_path):
    sink = RecordingSink()
    deps = _deps(tmp_path, sink)
    entered = asyncio.Event()
    count = 0

    async def run(task, sub_deps, **kwargs):
        nonlocal count
        sub_deps.tool_context.touched.add(tmp_path / task)
        count += 1
        if count == 2:
            entered.set()
        await entered.wait()
        assert sub_deps.tool_context.touched == {tmp_path / task}
        return SimpleNamespace(final_text="sonuç", ok=True, tool_calls_made=1)

    results = await run_team(
        deps,
        [SubTask("a", write_scope=("a",)), SubTask("b", write_scope=("b",))],
        depth=0,
        run_agent=run,
    )
    assert all(result.ok for result in results)
    assert deps.tool_context.touched == {tmp_path / "a", tmp_path / "b"}
    assert [result.changed_paths for result in results] == [("a",), ("b",)]


async def test_local_child_cancellation_returns_terminal_without_losing_sibling(tmp_path):
    async def run(task, sub_deps, **kwargs):
        if task == "cancelled":
            raise asyncio.CancelledError
        return SimpleNamespace(final_text="sonuç", ok=True, tool_calls_made=0)

    results = await run_team(
        _deps(tmp_path, RecordingSink()),
        [SubTask("cancelled", read_only=True), SubTask("healthy", read_only=True)],
        depth=0,
        run_agent=run,
    )
    assert [result.ok for result in results] == [False, True]


@pytest.mark.parametrize("barrier", ["question", "steering"])
async def test_child_cannot_bypass_parent_mutation_barrier(tmp_path, monkeypatch, barrier):
    from fusion_cli.core.steering import SteeringQueue
    from fusion_cli.engines.agent.loop import run_agent
    from fusion_cli.engines.agent.team import run_subagent
    from tests.agent_harness import install_provider
    from tests.fakes import ScriptedProvider, model_result, tool_call

    install_provider(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    "", tool_calls=(tool_call("write_file", path="new.py", content="x = 1"),)
                ),
                model_result(
                    "Görev değerlendirmesi tamamlandı. Dosya yazımı güven sınırına göre "
                    "değerlendirildi; sonuç gerçek araç kaydına bağlıdır."
                ),
            ]
        ),
    )
    deps = _deps(tmp_path, RecordingSink())
    if barrier == "question":
        deps.questions.start(asyncio.Event().wait())
    else:
        deps.steering = SteeringQueue()
        deps.steering.push("Dosya yazmayı durdur")
    try:
        await run_subagent(deps, SubTask("new.py dosyasını oluştur"), depth=0, run_agent=run_agent)
        assert not (tmp_path / "new.py").exists()
    finally:
        await deps.questions.close()


async def test_model_delegation_runs_real_child_and_serializes_live_lifecycle(
    tmp_path, monkeypatch
):
    """Modelin devri gerçek alt döngü, araç ve tel olaylarıyla görünür kalır."""
    from fusion_cli.appserver.serialize import event_to_dict
    from fusion_cli.engines.agent import loop as agent_loop
    from fusion_cli.engines.agent.loop import run_agent
    from fusion_cli.providers.eventing import EventingProvider
    from tests.fakes import ScriptedProvider, model_result, tool_call

    (tmp_path / "bilgi.txt").write_text("doğrulanan içerik", encoding="utf-8")
    summary = "İnceleme tamamlandı: bilgi.txt dosyası okundu ve doğrulanan içerik bulundu."
    provider = ScriptedProvider(
        [
            model_result(
                "",
                tool_calls=(
                    tool_call(
                        "spawn_agent",
                        task="bilgi.txt dosyasını oku ve içeriğini bildir",
                        salt_okunur=True,
                    ),
                ),
            ),
            model_result("", tool_calls=(tool_call("read_file", path="bilgi.txt"),)),
            model_result(summary),
            model_result(summary),
        ]
    )
    monkeypatch.setattr(
        agent_loop,
        "build_provider",
        lambda spec, **kwargs: EventingProvider(
            provider,
            publisher=kwargs["publisher"],
            role="agent",
            channel=kwargs["channel"],
        ),
    )
    sink = RecordingSink()
    outcome = await run_agent(
        "Dosyayı bir alt ajana incelet ve sonucu bildir", _deps(tmp_path, sink)
    )
    wire = [event_to_dict(event) for event in sink.events]
    started = next(event for event in wire if event["olay"] == "SubAgentStarted")
    child_id = started["sub_id"]
    child_events = [event for event in wire if event.get("agent_id") == child_id]
    finished = next(event for event in wire if event["olay"] == "SubAgentFinished")

    assert outcome.ok
    assert provider.calls == 4
    assert [event["olay"] for event in child_events].count("ToolStarted") == 1
    assert any(
        event["olay"] == "ToolExecuted"
        and event["name"] == "read_file"
        and "doğrulanan içerik" in event["output"]
        for event in child_events
    )
    assert any(event["olay"] == "ModelCallStarted" for event in child_events)
    assert finished["sub_id"] == child_id
    assert finished["status"] == "completed"
    assert finished["ok"] is True
    assert finished["tool_calls"] == 1
    assert finished["summary"] == summary
    assert wire.index(started) < wire.index(child_events[0]) < wire.index(finished)


def test_salt_okunur_zayif_model_degerleriyle_yazma_yetkisi_vermez():
    """Ölçüldü (29 Ekim): `is True` yüzünden "true"/1/"evet" yazma yetkisi veriyordu (A4-09)."""
    from fusion_cli.engines.agent.team import _parse_subtask

    for deger in (True, "true", "True", " evet ", 1, "yes", ["x"]):
        sonuc = _parse_subtask({"task": "a", "salt_okunur": deger})
        assert not isinstance(sonuc, str) and sonuc.read_only is True, deger
    for deger in (None, False, "false", "hayır", 0):
        sonuc = _parse_subtask({"task": "a", "salt_okunur": deger})
        assert not isinstance(sonuc, str) and sonuc.read_only is False, deger
    assert _parse_subtask({"task": "a"}).read_only is False  # type: ignore[union-attr]


async def test_alt_ajanlar_web_sohbeti_icin_ayri_conversation_id_alir(tmp_path):
    """P1-31: aynı sistem istemli paralel alt ajanlar tek sohbeti çekiştirmesin."""
    sink = RecordingSink()
    deps = replace(_deps(tmp_path, sink), conversation_id="oturum-1")
    gorulen: list[str] = []

    async def _sahte_ajan(task, sub_deps, **kwargs):
        gorulen.append(sub_deps.conversation_id)
        return SimpleNamespace(final_text="ok", ok=True, tool_calls_made=0)

    await run_team(
        deps,
        [SubTask("a", read_only=True), SubTask("b", read_only=True)],
        depth=0,
        run_agent=_sahte_ajan,
    )

    assert len(set(gorulen)) == 2
    assert all(kimlik.startswith("oturum-1/") for kimlik in gorulen)


# --- Derinlik, bütçe ve ağaç (P-035) ------------------------------------------- #


async def test_derinlik_tavani_yapilandirmadan_okunur(tmp_path):
    """Ölçüldü (31 Ekim): `MAX_AGENT_DEPTH = 1` sabitti; alt ajan alt ajan açamazdı."""
    sink = RecordingSink()
    deps = _deps(tmp_path, sink, max_agent_depth=3)

    async def _sahte_ajan(task, sub_deps, **kwargs):
        return SimpleNamespace(final_text=f"{task} bitti", ok=True, tool_calls_made=0)

    arac = spawn_agents_tool(deps, depth=1, run_agent=_sahte_ajan)
    sonuc = await arac.run({"gorevler": [{"task": "a", "salt_okunur": True}]}, deps.tool_context)

    assert "derinlik" not in sonuc.output and "a bitti" in sonuc.output
    basladi = [olay for olay in sink.events if isinstance(olay, SubAgentStarted)]
    assert basladi and basladi[0].depth == 2

    kapali = spawn_agents_tool(deps, depth=3, run_agent=_sahte_ajan)
    sonuc = await kapali.run({"gorevler": [{"task": "b"}]}, deps.tool_context)
    assert "derinlik" in sonuc.output


async def test_tur_basina_alt_ajan_butcesi_dolunca_spawn_reddedilir(tmp_path):
    sink = RecordingSink()
    deps = _deps(tmp_path, sink, max_subagents_per_turn=2)
    kosan: list[str] = []

    async def _sahte_ajan(task, sub_deps, **kwargs):
        kosan.append(task)
        return SimpleNamespace(final_text="ok", ok=True, tool_calls_made=0)

    sonuclar = await run_team(
        deps, [SubTask(f"g{i}", read_only=True) for i in range(3)], depth=0, run_agent=_sahte_ajan
    )

    assert kosan == ["g0", "g1"]
    assert sonuclar[2].status == "budget" and "bütçesi doldu" in sonuclar[2].text


def test_cocuk_adim_butcesi_derinlikle_yarilanmaz_maxturns_aynen_uygulanir(tmp_path):
    """Claude Code'da derinlik adım bütçesini yarılamaz; `maxTurns` olduğu gibi uygulanır
    (#29, #36). Kullanıcının `agent_max_steps` tavanı yine aşılmaz."""
    from fusion_cli.engines.agent.team import child_step_limit

    deps = _deps(tmp_path, RecordingSink(), agent_max_steps=64)

    assert child_step_limit(deps, 0) is None
    assert child_step_limit(deps, 1) is None
    assert child_step_limit(deps, 2) is None
    assert child_step_limit(deps, 1, requested=5) == 5
    assert child_step_limit(deps, 2, requested=40) == 40
    assert child_step_limit(deps, 0, requested=500) == 64


def test_varsayilan_derinlik_uc_kat_ve_eszamanlilik_yirmi(tmp_path):
    from fusion_cli.config.models import RuntimeConfig
    from fusion_cli.engines.agent.team import depth_limit_reached

    deps = _deps(tmp_path, RecordingSink())
    assert RuntimeConfig.__dataclass_fields__["max_agent_depth"].default == 3
    assert RuntimeConfig.__dataclass_fields__["max_parallel_agents"].default == 20
    assert RuntimeConfig.__dataclass_fields__["max_subagents_per_turn"].default == 0
    assert not depth_limit_reached(deps, 2) and depth_limit_reached(deps, 3)


def test_claude_derinlik_ve_eszamanlilik_ortam_degiskenleri_okunur(tmp_path):
    from dataclasses import replace

    from fusion_cli.config.agent_launch_compat import read_agent_launch
    from fusion_cli.config.agent_launch_settings import AgentLaunchConfig
    from fusion_cli.engines.agent.team import concurrent_limit, depth_limit_reached

    loaded = read_agent_launch(
        AgentLaunchConfig(),
        home=tmp_path / "ev",
        root=tmp_path,
        environ={
            "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": "1",
            "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS": "5",
        },
    )
    deps = _deps(tmp_path, RecordingSink())
    deps = replace(deps, config=replace(deps.config, agent_launch=loaded))

    assert depth_limit_reached(deps, 1) and not depth_limit_reached(deps, 0)
    assert concurrent_limit(deps) == 5


def test_yerlesik_explore_ve_plan_ajanlari_salt_okur(tmp_path):
    """P-053: Claude Code'un Explore/Plan karşılığı yerleşik ekipte; ikisi de yazmaz."""
    kutuphane = CapabilityRegistry(tmp_path / "ev", tmp_path)

    explore = resolve_persona(kutuphane, "explore")
    plan = resolve_persona(kutuphane, "plan")

    assert explore is not GENERIC_PERSONA and explore.title == "Kâşif"
    assert explore.tools is not None and explore.tools.isdisjoint({"write_file", "edit_file"})
    assert plan is not GENERIC_PERSONA and plan.title == "Planlayıcı"
    # Claude Code: Plan da Explore gibi salt okur araçlar + Bash; plan kipi değiştireni engeller.
    assert plan.tools is not None and plan.tools.isdisjoint({"write_file", "edit_file"})
    assert "run_shell" in plan.tools
    assert plan.permission_mode == "plan"


async def test_maxturns_sinirina_ulasan_alt_ajan_kismi_isaretlenir(tmp_path):
    """Claude Code: `maxTurns`'e ulaşan alt ajanın çıktısı 'kısmi' döner, sürdürülebilir (#36)."""
    from fusion_cli.engines.agent.team import run_subagent

    deps = _deps(tmp_path, RecordingSink())

    async def _yarim(task, sub_deps, **kwargs):
        return SimpleNamespace(
            final_text="ilk yarı", ok=True, tool_calls_made=3, hit_step_limit=True, messages=[]
        )

    run = await run_subagent(deps, SubTask("uzun iş"), depth=0, run_agent=_yarim)

    assert run.status == "partial" and run.ok
    assert "ilk yarı" in run.text and "maxTurns" in run.text


async def test_sendmessage_alan_alt_ajan_adli_kardes_listesini_gorur(tmp_path):
    """Claude Code: SendMessage'i olan fork olmayan alt ajana `main` ve adlı ajanlar listelenir."""
    from fusion_cli.core.agent_runtime_state import AgentRunState
    from fusion_cli.engines.agent.team import run_subagent

    deps = _deps(tmp_path, RecordingSink())
    deps.child_runs.remember(
        AgentRunState(
            "arastirmaci-1",
            deps.child_runs.session_id,
            str(tmp_path),
            "x",
            True,
            name="arastirmaci",
        ),
        (),
    )
    gorulen: dict[str, str] = {}

    async def _ajan(task, sub_deps, **kwargs):
        gorulen["extra"] = kwargs.get("extra_system") or ""
        return SimpleNamespace(final_text="tamam", ok=True, tool_calls_made=0, messages=[])

    await run_subagent(deps, SubTask("iş", name="yazar"), depth=0, run_agent=_ajan)

    assert "main" in gorulen["extra"] and "arastirmaci" in gorulen["extra"]
    assert "SendMessage" in gorulen["extra"]
