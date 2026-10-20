"""Toplu sayma/filtreleme dilinin araç kanıtına bağlandığının regresyon testi.

17 Eylül denetiminde ölçüldü: 74 bin karakterlik bir ürün dökümünde "Motoplus
tedarikçili, sayımı 0 olan kaç ürün var?" sorusuna model metni gözüyle tarayıp
5 dedi; doğrusu 3'tü ve tedarikçisi farklı iki ürünü de listeye katmıştı.
Çırağın elinde zaten `run_shell` (`grep -c`, `wc -l`) ve `search_code` vardı —
eksik olan kanıt zorunluluğuydu. Bu dosya iki şeyi kilitler: (1) sayma/filtreleme
dili deterministik olarak bir etki üretir ve kanıt kapısını açar, (2) model
araç çağırmadan sayı söylerse tur BAŞARISIZ ilan edilir.
"""

from __future__ import annotations

from fusion_cli.core.tools import ToolContext
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.execution_policy import policy_for
from fusion_cli.engines.agent.loop import AgentDeps, run_agent
from fusion_cli.engines.effects.detect import required_effect_for

from .fakes import AlwaysApprove, RecordingSink, ScriptedProvider, make_config, model_result

_SAYMA_ISTEGI = "bu dosyada kaç tane TODO var, listele"
#: Gerçek denetimde ölçülen istek — "dosya"/"listele" gibi başka hiçbir
#: tetikleyici kelime taşımıyordu, yalnızca "kaç <nesne> var" kalıbı vardı.
_DENETIM_ISTEGI = "Motoplus tedarikçili, sayımı 0 olan kaç ürün var?"


class _Publisher:
    def __init__(self, sink):
        self._sink = sink

    def publish(self, event):
        self._sink.handle(event)


def _config():
    return make_config(
        agent=ModelSpec(name="agent", model="nvidia_nim/test-model"),
        task_model_map={},
    )


def _deps(tmp_path, sink):
    return AgentDeps(
        config=_config(),
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )


def _patch_provider(monkeypatch, provider):
    from fusion_cli.engines.agent import loop as agent_loop

    monkeypatch.setattr(agent_loop, "build_provider", lambda *a, **k: provider)


def test_sayma_dili_kanit_gerektirir():
    """Sayma/filtreleme dili `required_effect_for`'dan `None` DÖNMEMELİ."""
    assert required_effect_for(_SAYMA_ISTEGI) is not None
    assert required_effect_for(_DENETIM_ISTEGI) is not None

    policy = policy_for(_config(), _config().agent, _SAYMA_ISTEGI)
    assert policy.requires_tool_evidence is True

    policy_denetim = policy_for(_config(), _config().agent, _DENETIM_ISTEGI)
    assert policy_denetim.requires_tool_evidence is True
    # Sayma bir dosyayı değiştirmiyor; `_MUTATING_EFFECTS`e girmemeli.
    assert policy_denetim.complex_task is False


def test_sohbet_sorulari_kanit_kapisina_girmez():
    """Dar desen: sıradan "kaç" soruları yanlışlıkla kanıt kapısına girmemeli."""
    assert required_effect_for("kaç yaşındasın") is None
    assert required_effect_for("kaç para eder bu ürün") is None
    assert required_effect_for("saat kaç") is None


async def test_sayma_gorevinde_arac_cagrisi_olmadan_sayi_soylenirse_reddedilir(
    monkeypatch, tmp_path
):
    """Model araç çağırmadan sayı söylerse mevcut kanıt kapısı turu reddeder."""
    sink = RecordingSink()
    provider = ScriptedProvider(
        [
            model_result("Dosyada 5 tane TODO var."),
            model_result("Yine 5 tane var."),
        ]
    )
    _patch_provider(monkeypatch, provider)

    result = await run_agent(_SAYMA_ISTEGI, _deps(tmp_path, sink))

    assert result.ok is False
    assert result.tool_calls_made == 0
    assert "İşlem tamamlanmadı" in result.final_text


def test_sistem_promptu_sayma_talimati_icerir():
    """`system.md` sayma/filtreleme isteğinde deterministik araç kullanımını önerir.

    `test_tool_protokolleri_system_promptta_tekrar_edilmez`
    (`tests/test_system_prompt_diet.py`) sistem promptunda somut araç adı
    (`run_shell` gibi) geçmesini YASAKLIYOR — araç şemaları ayrı sunulur, sistem
    promptu araçtan bağımsız kalır. Bu yüzden madde araç adı yerine "gözle tahmin
    etme, araçla say/filtrele" ilkesini genel biçimde ifade eder.
    """
    from pathlib import Path

    system_md = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "fusion_cli"
        / "engines"
        / "agent"
        / "prompts"
        / "system.md"
    ).read_text(encoding="utf-8")

    sayma_satiri = next(
        (
            line
            for line in system_md.splitlines()
            if "say" in line.lower() and "filtrele" in line.lower()
        ),
        "",
    )
    assert sayma_satiri, "system.md içinde sayma/filtreleme maddesi bulunamadı"
    assert "gözle" in sayma_satiri.lower() or "gözle" in system_md.lower()
    # Somut araç adı YASAK (bkz. yukarıdaki gerekçe); madde bunu ihlal etmemeli.
    assert "run_shell" not in system_md
