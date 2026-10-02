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
        "---\nname: tasarimci\nunvan: Benim Tasarımcım\navatar: ozel\n---\nkendi talimatım\n",
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

    arac = spawn_agents_tool(deps, depth=1, run_agent=_hic)
    sonuc = await arac.run({"gorevler": [{"task": "a"}]}, deps.tool_context)

    assert "derinlik" in sonuc.output


def test_bos_kimlikli_olay_tel_uzerinde_kimlik_tasimaz():
    from fusion_cli.appserver.serialize import event_to_dict

    assert "agent_id" not in event_to_dict(StatusChanged("x"))
    assert event_to_dict(replace(StatusChanged("x"), agent_id="k"))["agent_id"] == "k"
