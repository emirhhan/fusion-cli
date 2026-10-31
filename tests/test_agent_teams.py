"""Ajan ekipleri (P-061): paylaşımlı görev listesi, posta kutusu, boşta bekleme, araçlar."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from fusion_cli.core.orchestration_events import TeamBoardChanged
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps
from fusion_cli.engines.agent.team_board import TeamStore
from fusion_cli.engines.agent.team_tools import team_run_tool
from fusion_cli.tools.capabilities import CapabilityRegistry
from tests.agent_harness import Publisher
from tests.fakes import AlwaysApprove, RecordingSink, make_config


def _deps(tmp_path, sink, asker=None, **runtime):
    return AgentDeps(
        config=make_config(runtime={"agent_team_confirm": False, **runtime}),
        publisher=Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        capabilities=CapabilityRegistry(tmp_path / "ev", tmp_path),
        asker=asker,
    )


async def _arac(sub_deps, ad, **args):
    tool = sub_deps.base_registry.get(ad)
    assert tool is not None, f"{ad} üyeye sunulmadı"
    return await tool.run(args, sub_deps.tool_context)


def _yeni_ekip(**extra):
    return {
        "ad": "site",
        "hedef": "Açılış sayfasını yap",
        "uyeler": [
            {"ad": "tasarim", "uzman": "tasarimci", "yazma_alani": ["site/css"]},
            {"ad": "kod", "uzman": "kodcu", "yazma_alani": ["site/js"]},
        ],
        "gorevler": [
            {"baslik": "Renk paleti", "atanan": "tasarim"},
            {"baslik": "Etkileşim", "atanan": "kod"},
            {"baslik": "Son kontrol", "bagimli": ["Renk paleti", "g2"]},
        ],
        **extra,
    }


async def test_uyeler_gorevleri_paylasir_bagimlilik_bitince_sonraki_alinir(tmp_path):
    sink = RecordingSink()
    deps = _deps(tmp_path, sink)
    gorulen_araclar: list[set[str] | None] = []

    async def _ajan(task, sub_deps, **kwargs):
        gorulen_araclar.append(kwargs.get("allowed_tools"))
        while True:
            alindi = await _arac(sub_deps, "team_task", eylem="al")
            if not alindi.ok:
                return SimpleNamespace(final_text="iş kalmadı", ok=True, tool_calls_made=1)
            kimlik = alindi.output.split()[0]
            await asyncio.sleep(0.01)
            await _arac(sub_deps, "team_task", eylem="bitir", id=kimlik, sonuc=f"{kimlik} bitti")

    sonuc = await team_run_tool(deps, depth=0, run_agent=_ajan).run(_yeni_ekip(), deps.tool_context)

    assert sonuc.ok, sonuc.output
    assert "Ekip 'site': bitti — 3/3 görev tamam" in sonuc.output
    pano = TeamStore(tmp_path).load("site")
    assert pano is not None and {g.status for g in pano.tasks} == {"tamam"}
    assert pano.task("g3").depends_on == ("g1", "g2")
    olaylar = [olay for olay in sink.events if isinstance(olay, TeamBoardChanged)]
    assert olaylar[-1].status == "bitti"
    # Rol kısıtlı kişilik (`tools:` listeli tasarimci/kodcu) de pano araçlarını görür.
    assert all(a is None or {"team_task", "team_board", "team_send"} <= a for a in gorulen_araclar)


async def test_bosta_uye_mesaj_gelince_uyanir_ve_okur(tmp_path):
    deps = _deps(tmp_path, RecordingSink())
    okunan: list[str] = []

    async def _ajan(task, sub_deps, **kwargs):
        pano = (await _arac(sub_deps, "team_board")).output
        if "b (sen)" in pano:
            okunan.append(pano)
            return SimpleNamespace(final_text="okudum", ok=True, tool_calls_made=1)
        await _arac(sub_deps, "team_task", eylem="al")
        await _arac(sub_deps, "team_send", kime="b", metin="paleti bitirdim, bak")
        await _arac(sub_deps, "team_task", eylem="bitir", id="g1", sonuc="ok")
        await _arac(sub_deps, "team_send", kime="lider", metin="hepsi tamam")
        return SimpleNamespace(final_text="bitirdim", ok=True, tool_calls_made=4)

    sonuc = await team_run_tool(deps, depth=0, run_agent=_ajan).run(
        {
            "ad": "ikili",
            "hedef": "deneme",
            "uyeler": [{"ad": "a"}, {"ad": "b", "salt_okunur": True}],
            "gorevler": [{"baslik": "palet", "atanan": "a"}],
        },
        deps.tool_context,
    )

    assert sonuc.ok, sonuc.output
    # b'nin başta işi yoktu (görev a'ya atanmış): boşta bekledi, mesaj gelince uyandı.
    assert len(okunan) == 1 and "a: paleti bitirdim, bak" in okunan[0]
    assert "## Lidere gelen mesajlar\n- a: hepsi tamam" in sonuc.output
    assert "- b: 1 koşu" in sonuc.output


async def test_yarim_birakilan_gorev_panoya_doner_uyanma_siniri_asilmaz(tmp_path):
    deps = _deps(tmp_path, RecordingSink(), agent_team_max_wakes=1)
    kosular = 0

    async def _ajan(task, sub_deps, **kwargs):
        nonlocal kosular
        kosular += 1
        await _arac(sub_deps, "team_task", eylem="al")
        return SimpleNamespace(final_text="yarım bıraktım", ok=True, tool_calls_made=1)

    sonuc = await team_run_tool(deps, depth=0, run_agent=_ajan).run(
        {"ad": "tek", "hedef": "x", "uyeler": [{"ad": "a"}], "gorevler": [{"baslik": "iş"}]},
        deps.tool_context,
    )

    assert kosular == 2
    assert "durdu — 0/1 görev tamam" in sonuc.output
    assert "- g1 bekliyor: iş" in sonuc.output


async def test_ayni_adla_cagri_kaldigi_yerden_surer_ve_mesaj_iletir(tmp_path):
    deps = _deps(tmp_path, RecordingSink())
    gelen: list[str] = []

    async def _bitiren(task, sub_deps, **kwargs):
        pano = await _arac(sub_deps, "team_board")
        gelen.append(pano.output)
        alindi = await _arac(sub_deps, "team_task", eylem="al")
        if alindi.ok:
            await _arac(
                sub_deps, "team_task", eylem="bitir", id=alindi.output.split()[0], sonuc="ok"
            )
        return SimpleNamespace(final_text="tamam", ok=True, tool_calls_made=2)

    arac = team_run_tool(deps, depth=0, run_agent=_bitiren)
    await arac.run(
        {"ad": "surer", "hedef": "x", "uyeler": [{"ad": "a"}], "gorevler": [{"baslik": "bir"}]},
        deps.tool_context,
    )
    ikinci = await arac.run(
        {
            "ad": "surer",
            "gorevler": [{"baslik": "iki", "bagimli": ["g1"]}],
            "mesajlar": [{"kime": "a", "metin": "ikinciyi de yap"}],
        },
        deps.tool_context,
    )

    assert "2/2 görev tamam" in ikinci.output
    assert any("lider: ikinciyi de yap" in metin for metin in gelen)


@pytest.mark.parametrize(
    ("args", "hata"),
    [
        ({"ad": "yeni", "hedef": "x"}, "'hedef', 'uyeler'"),
        ({"ad": "Kötü Ad"}, "küçük harf"),
        ({"ad": "lider"}, "ayrılmış"),
        (
            {"ad": "x", "hedef": "h", "uyeler": [{"ad": "a"}] * 2, "gorevler": [{"baslik": "g"}]},
            "benzersiz",
        ),
        (
            {
                "ad": "x",
                "hedef": "h",
                "uyeler": [{"ad": "a"}],
                "gorevler": [{"baslik": "g", "bagimli": ["yok"]}],
            },
            "Bağımlılık bulunamadı",
        ),
    ],
)
async def test_gecersiz_ekip_istegi_anlasilir_hatayla_doner(tmp_path, args, hata):
    deps = _deps(tmp_path, RecordingSink())

    sonuc = await team_run_tool(deps, depth=0, run_agent=None).run(args, deps.tool_context)

    assert not sonuc.ok and hata in sonuc.output


async def test_uye_tavani_ve_kapali_ayar(tmp_path):
    deps = _deps(tmp_path, RecordingSink(), agent_team_max_members=1)
    kapali = _deps(tmp_path, RecordingSink(), agent_teams=False)

    fazla = await team_run_tool(deps, depth=0, run_agent=None).run(_yeni_ekip(), deps.tool_context)
    yok = await team_run_tool(kapali, depth=0, run_agent=None).run(
        _yeni_ekip(), kapali.tool_context
    )

    assert not fazla.ok and "en fazla 1 üye" in fazla.output
    assert not yok.ok and "kapalı" in yok.output


async def test_yeni_ekip_maliyet_uyarisiyla_sorulur_red_uye_baslatmaz(tmp_path):
    sorular: list[str] = []

    class _Sorucu:
        async def ask(self, question, options=(), recommended=None):
            sorular.append(question)
            return "Vazgeç"

    deps = _deps(tmp_path, RecordingSink(), asker=_Sorucu(), agent_team_confirm=True)

    sonuc = await team_run_tool(deps, depth=0, run_agent=None).run(_yeni_ekip(), deps.tool_context)

    assert not sonuc.ok and "başlatmadı" in sonuc.output
    assert "2 üyeyle" in sorular[0]
    assert TeamStore(tmp_path).load("site") is None


def test_ekip_araci_yalniz_ekip_isteginde_ve_ana_ajanda(tmp_path):
    from fusion_cli.engines.agent.engine_tools import build_agent_registry
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
    from fusion_cli.engines.agent.loop import _permitted
    from fusion_cli.engines.agent.orchestration_tools import orchestration_task_kinds

    deps = _deps(tmp_path, RecordingSink())
    registry = build_agent_registry(deps, depth=0, run_agent=None)

    assert "team_run" in registry.names()
    assert "team_board" not in registry.names()
    assert "team_run" not in build_agent_registry(deps, depth=1, run_agent=None).names()
    assert "team_run" not in _permitted(None, registry, ExecutionPolicy(is_web=False))
    assert "team_run" in _permitted(None, registry, ExecutionPolicy(is_web=False), {"ekip"})
    assert orchestration_task_kinds("3 kişilik bir ajan ekibi kur") == {"ekip"}
    assert orchestration_task_kinds("Takım halinde çalışın") == {"ekip"}
