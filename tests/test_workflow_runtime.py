"""Dinamik iş akışları (P-062): DSL, plan açılımı, çalışma zamanı, depo ve araç."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from fusion_cli.core.orchestration_events import WorkflowProgress
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps
from fusion_cli.engines.agent.orchestration_runs import BudgetedRuns, ScopeGate
from fusion_cli.engines.agent.orchestration_tools import orchestration_task_kinds
from fusion_cli.engines.agent.workflow_plan import agents_in, bind_inputs, expand
from fusion_cli.engines.agent.workflow_runtime import run_workflow
from fusion_cli.engines.agent.workflow_spec import WorkflowError, parse_workflow
from fusion_cli.engines.agent.workflow_store import RunRecord, WorkflowStore
from fusion_cli.engines.agent.workflow_tools import workflow_run_tool
from fusion_cli.tools.capabilities import CapabilityRegistry
from tests.agent_harness import Publisher
from tests.fakes import AlwaysApprove, RecordingSink, make_config


@pytest.fixture(autouse=True)
def _kullanici_dizini(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


def _deps(tmp_path, sink, asker=None, **runtime):
    return AgentDeps(
        config=make_config(runtime=runtime) if runtime else make_config(),
        publisher=Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        capabilities=CapabilityRegistry(tmp_path / "ev", tmp_path),
        asker=asker,
    )


def _ok(text):
    return SimpleNamespace(final_text=text, ok=True, tool_calls_made=1)


async def _calistir(deps, tanim, girdiler=None, run_agent=None):
    spec = parse_workflow(tanim)
    inputs = bind_inputs(spec, girdiler)
    plan = expand(spec, inputs)
    store = WorkflowStore(deps.tool_context.root)
    return await run_workflow(
        deps, spec, plan, inputs, depth=0, run_agent=run_agent, store=store
    ), store


# --------------------------------------------------------------------------- #
# DSL ve plan
# --------------------------------------------------------------------------- #


def test_ingilizce_anahtarlar_es_anlamli_kabul_edilir():
    spec = parse_workflow(
        {"name": "x", "steps": [{"phase": "Keşif", "steps": [{"parallel": ["a", "b"]}]}]}
    )

    assert [ajan.prompt for ajan in agents_in(expand(spec, {}))] == ["a", "b"]
    assert {ajan.phase for ajan in agents_in(expand(spec, {}))} == {"Keşif"}


def test_her_dugumu_girdi_listesini_ogelere_acar():
    spec = parse_workflow(
        {
            "girdiler": {"dosyalar": ["a.py", "b.py"]},
            "adimlar": [{"her": "{girdi.dosyalar}", "id": "inc", "ajan": "{oge_no}: {oge} incele"}],
        }
    )

    ajanlar = agents_in(expand(spec, bind_inputs(spec, None)))

    assert [ajan.prompt for ajan in ajanlar] == ["1: a.py incele", "2: b.py incele"]
    assert len(agents_in(expand(spec, bind_inputs(spec, {"dosyalar": ["x"] * 5})))) == 5


@pytest.mark.parametrize(
    ("tanim", "hata"),
    [
        ({"adimlar": [{"ajan": "x {sonuc.yok}"}]}, "bu kimlikte adım yok"),
        ({"adimlar": [{"ajan": "{oge}"}]}, "yalnız 'her'"),
        ({"adimlar": [{"ajan": "a", "paralel": ["b"]}]}, "tam olarak biri"),
        ({"adimlar": [{"ajan": "a", "id": "x"}, {"ajan": "b", "id": "x"}]}, "iki kez"),
        ({"adimlar": []}, "en az bir adım"),
        ({"adimlar": [{"ajan": "a {girdi.y}"}]}, "girdiler"),
        ("{bozuk", "geçerli JSON"),
    ],
)
def test_gecersiz_tanim_anlasilir_hatayla_reddedilir(tanim, hata):
    with pytest.raises(WorkflowError, match=hata):
        parse_workflow(tanim)


def test_istemdeki_baska_suslu_parantez_dokunulmadan_kalir():
    spec = parse_workflow({"adimlar": ["const x = {a: 1}; {onceki}"]})

    assert agents_in(expand(spec, {}))[0].prompt == "const x = {a: 1}; {onceki}"


def test_bilinmeyen_girdi_reddedilir():
    spec = parse_workflow({"girdiler": {"a": "1"}, "adimlar": ["x"]})

    with pytest.raises(WorkflowError, match="Bilinmeyen girdi"):
        bind_inputs(spec, {"b": "2"})


# --------------------------------------------------------------------------- #
# Çalışma zamanı
# --------------------------------------------------------------------------- #


async def test_paralel_adimlar_es_zamanli_sira_onceki_ciktiyi_gecirir(tmp_path):
    sink = RecordingSink()
    deps = _deps(tmp_path, sink)
    gorulen: list[str] = []
    ikisi_basladi = asyncio.Event()

    async def _ajan(task, sub_deps, **kwargs):
        gorulen.append(task)
        if task in {"ara-1", "ara-2"}:
            if sum(t in {"ara-1", "ara-2"} for t in gorulen) == 2:
                ikisi_basladi.set()
            await asyncio.wait_for(ikisi_basladi.wait(), timeout=2)
        return _ok(f"<{task}>")

    sonuc, store = await _calistir(
        deps,
        {
            "ad": "deneme",
            "adimlar": [
                {
                    "paralel": [
                        {"ajan": "ara-1", "id": "a", "salt_okunur": True},
                        {"ajan": "ara-2", "id": "b", "salt_okunur": True},
                    ]
                },
                {"sira": [{"ajan": "birlestir {sonuc.a}|{sonuc.b}"}, "son: {onceki}"]},
            ],
        },
        run_agent=_ajan,
    )

    assert sonuc.status == "tamam"
    assert "birlestir <ara-1>|<ara-2>" in gorulen
    assert "son: <birlestir <ara-1>|<ara-2>>" in gorulen
    assert sonuc.agents == 4
    kayit = store.run(sonuc.run_id)
    assert kayit is not None and kayit.status == "tamam" and "Son çıktı" in kayit.report
    ilerleme = [olay for olay in sink.events if isinstance(olay, WorkflowProgress)]
    assert ilerleme[0].status == "calisiyor" and ilerleme[-1].status == "tamam"
    assert {dugum.status for dugum in ilerleme[-1].nodes} == {"tamam"}


async def test_eszamanlilik_tavani_ve_yazma_alani_kapisi_uyulur(tmp_path):
    deps = _deps(tmp_path, RecordingSink(), max_parallel_agents=3)
    aktif: list[str] = []
    cakisma: list[tuple[str, ...]] = []
    en_cok = 0

    async def _ajan(task, sub_deps, **kwargs):
        nonlocal en_cok
        aktif.append(task)
        en_cok = max(en_cok, len(aktif))
        if sum(t.startswith("site") for t in aktif) > 1:
            cakisma.append(tuple(aktif))
        await asyncio.sleep(0.02)
        aktif.remove(task)
        return _ok(task)

    adimlar = [
        {"ajan": "site-1", "yazma_alani": ["site"]},
        {"ajan": "site-2", "yazma_alani": ["site/index.html"]},
        *({"ajan": f"oku-{i}", "salt_okunur": True} for i in range(4)),
    ]
    sonuc, _ = await _calistir(deps, {"adimlar": [{"paralel": adimlar}]}, run_agent=_ajan)

    assert sonuc.status == "tamam"
    assert en_cok == 3
    assert cakisma == []


async def test_plan_ajan_tavanini_asarsa_hic_baslamaz(tmp_path):
    deps = _deps(tmp_path, RecordingSink(), dynamic_workflow_max_agents=3)
    basladi = 0

    async def _ajan(task, sub_deps, **kwargs):
        nonlocal basladi
        basladi += 1
        return _ok(task)

    with pytest.raises(WorkflowError, match="4 ajan başlatacak; tavan 3"):
        await _calistir(deps, {"adimlar": [{"paralel": ["a", "b", "c", "d"]}]}, run_agent=_ajan)
    assert basladi == 0


async def test_is_akisi_butcesi_tur_butcesinden_ayridir(tmp_path):
    deps = _deps(tmp_path, RecordingSink(), max_subagents_per_turn=2)

    async def _ajan(task, sub_deps, **kwargs):
        return _ok(task)

    sonuc, _ = await _calistir(deps, {"adimlar": [{"paralel": list("abcde")}]}, run_agent=_ajan)

    assert sonuc.status == "tamam" and sonuc.agents == 5


async def test_iptal_isareti_kosan_akisi_durdurur(tmp_path):
    deps = _deps(tmp_path, RecordingSink())
    store = WorkflowStore(tmp_path)
    basladi = asyncio.Event()

    async def _ajan(task, sub_deps, **kwargs):
        basladi.set()
        await asyncio.sleep(30)
        return _ok(task)

    spec = parse_workflow({"adimlar": ["uzun", "sonraki"]})
    plan = expand(spec, {})

    async def _iptal_et():
        await basladi.wait()
        kosu = store.runs()[0]
        assert store.request_cancel(kosu.run_id)

    iptalci = asyncio.create_task(_iptal_et())
    sonuc = await asyncio.wait_for(
        run_workflow(deps, spec, plan, {}, depth=0, run_agent=_ajan, store=store), timeout=5
    )
    await iptalci

    assert sonuc.status == "iptal"
    kayit = store.run(sonuc.run_id)
    assert kayit is not None and [d.status for d in kayit.nodes] == ["iptal", "atlandi"]
    assert not store.cancel_requested(sonuc.run_id)


async def test_kapsam_kapisi_belirsiz_yazari_tek_basina_kosturur():
    kapi = ScopeGate()
    sira: list[str] = []

    async def _yaz(ad, alan):
        async with kapi.hold(alan):
            sira.append(f"+{ad}")
            await asyncio.sleep(0.01)
            sira.append(f"-{ad}")

    await asyncio.gather(_yaz("belirsiz", None), _yaz("okur", ()))

    assert sira in (
        ["+belirsiz", "-belirsiz", "+okur", "-okur"],
        ["+okur", "-okur", "+belirsiz", "-belirsiz"],
    )


async def test_butceli_kosu_sahibi_kendi_sayacini_tutar_ust_sahibe_devreder():
    from fusion_cli.engines.agent.child_runs import ChildRuns

    ust = ChildRuns()
    kosu = BudgetedRuns(ust)

    async def _is():
        return _ok("x")

    gorev = kosu.start("a", _is)
    await gorev
    kosu.detach("a", gorev)

    assert kosu.started_total == 1 and ust.started_total == 1


# --------------------------------------------------------------------------- #
# Depo ve araç
# --------------------------------------------------------------------------- #


def test_sureci_kapanmis_kosu_yarim_gorunur(tmp_path):
    store = WorkflowStore(tmp_path)
    store.write_run(RunRecord("abc123", "x", "calisiyor", 1.0, pid=999_999_999))

    kayit = store.run("abc123")

    assert kayit is not None and kayit.status == "yarim"
    assert store.run("../etc") is None


def test_proje_tanimi_kullanici_tanimini_golgeler(tmp_path):
    kullanici = tmp_path / "kullanici"
    store = WorkflowStore(tmp_path, kullanici)
    store.save(parse_workflow({"ad": "rapor", "aciklama": "proje", "adimlar": ["a"]}))
    store.save(
        parse_workflow({"ad": "rapor", "aciklama": "kullanici", "adimlar": ["a"]}),
        scope="kullanici",
    )
    store.save(parse_workflow({"ad": "diger", "adimlar": ["a"]}), scope="kullanici")

    tanimlar = {kayit.name: (kayit.scope, kayit.description) for kayit in store.definitions()}

    assert tanimlar == {"diger": ("kullanici", ""), "rapor": ("proje", "proje")}


async def test_arac_kaydeder_ve_ad_ile_yeniden_calistirir(tmp_path):
    deps = _deps(tmp_path, RecordingSink())

    async def _ajan(task, sub_deps, **kwargs):
        return _ok(f"yaptım: {task}")

    arac = workflow_run_tool(deps, depth=0, run_agent=_ajan)
    ilk = await arac.run(
        {
            "tanim": {
                "ad": "selam",
                "girdiler": {"kim": "dünya"},
                "adimlar": ["selam {girdi.kim}"],
            },
            "kaydet": "true",
        },
        deps.tool_context,
    )
    ikinci = await arac.run(
        {"ad": "selam", "girdiler": json.dumps({"kim": "ay"})}, deps.tool_context
    )

    assert ilk.ok and "Kaydedildi" in ilk.output
    assert (tmp_path / ".fusion/workflows/selam.json").is_file()
    assert ikinci.ok and "yaptım: selam ay" in ikinci.output


async def test_buyuk_kosu_kullaniciya_sorulur_red_ajan_baslatmaz(tmp_path):
    sorular: list[str] = []

    class _Sorucu:
        async def ask(self, question, options=(), recommended=None):
            sorular.append(question)
            return "Vazgeç"

    deps = _deps(tmp_path, RecordingSink(), asker=_Sorucu(), dynamic_workflow_confirm_agents=2)
    basladi = 0

    async def _ajan(task, sub_deps, **kwargs):
        nonlocal basladi
        basladi += 1
        return _ok(task)

    sonuc = await workflow_run_tool(deps, depth=0, run_agent=_ajan).run(
        {"tanim": {"adimlar": [{"paralel": ["a", "b"]}]}}, deps.tool_context
    )

    assert not sonuc.ok and "başlatmadı" in sonuc.output
    assert basladi == 0 and "2 alt ajan" in sorular[0]


async def test_kapali_ayarda_arac_calismaz(tmp_path):
    deps = _deps(tmp_path, RecordingSink(), dynamic_workflows=False)

    sonuc = await workflow_run_tool(deps, depth=0, run_agent=None).run(
        {"tanim": {"adimlar": ["a"]}}, deps.tool_context
    )

    assert not sonuc.ok and "kapalı" in sonuc.output


def test_is_akisi_araci_yalniz_ilgili_istekte_sunulur(tmp_path):
    from fusion_cli.engines.agent.engine_tools import build_agent_registry
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
    from fusion_cli.engines.agent.loop import _permitted

    deps = _deps(tmp_path, RecordingSink())
    registry = build_agent_registry(deps, depth=0, run_agent=None)
    alt = build_agent_registry(deps, depth=1, run_agent=None)

    assert "workflow_run" in registry.names() and "workflow_run" not in alt.names()
    assert "workflow_run" not in _permitted(None, registry, ExecutionPolicy(is_web=False))
    acik = _permitted(None, registry, ExecutionPolicy(is_web=False), {"is_akisi"})
    assert "workflow_run" in acik
    assert orchestration_task_kinds("İŞ AKIŞI kur: 20 dosyayı incele") == {"is_akisi"}
    assert orchestration_task_kinds("ultracode ile yap") == {"is_akisi"}
    assert orchestration_task_kinds("bu dosyayı düzelt") == set()
