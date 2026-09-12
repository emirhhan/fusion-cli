"""`web.arac_olc` bağlaması — ölçüm sonucunu dosya yazma iznine çeviren tek yol.

Ölçüm gerçek çağrı yapar; burada sonda sahtelenir (ağ yok, kota harcanmaz).
"""

from __future__ import annotations

import pytest

from fusion_cli.appserver import tool_measure
from fusion_cli.config.models import WebSessionConfig
from fusion_cli.core.errors import FusionError
from fusion_cli.engines.emulation_probe import ProbeReport, ProbeSample
from fusion_cli.tools.emulation_eval import EmulationEvalScore

from .fakes import make_config


def _config(**overrides):
    alanlar = {
        "model": "chatgpt_web/main/auto",
        "provider": "chatgpt_web",
        "account": "main",
        "transport": "browser",
        "tool_support": "emulated",
    }
    alanlar.update(overrides)
    return make_config(web_sessions=(WebSessionConfig(**alanlar),))


def _rapor(score: EmulationEvalScore, *, ham: str = "") -> ProbeReport:
    return ProbeReport(
        score=score,
        samples=(
            ProbeSample(
                prompt="oku",
                expected_tool="read_file",
                raw_output=ham,
                parsed_tool=None,
                parse_errors=(),
            ),
        ),
    )


def _kusursuz() -> EmulationEvalScore:
    return EmulationEvalScore(
        tool_selection=1.0,
        schema_validity=1.0,
        argument_preservation=1.0,
        no_false_calls=1.0,
        tool_selection_measured=4,
        schema_validity_measured=4,
        argument_preservation_measured=4,
        no_false_calls_measured=1,
    )


def _sonda(monkeypatch, sonuc) -> list[str]:
    """Sondayı sahtele; ölçülen model kimliğini kaydet."""
    gorulen: list[str] = []

    async def _probe(config, model, **kwargs):
        gorulen.append(model)
        if isinstance(sonuc, Exception):
            raise sonuc
        return sonuc

    monkeypatch.setattr(tool_measure, "probe_emulation", _probe)
    return gorulen


def _yazimi_yakala(monkeypatch) -> list[bool]:
    yazilan: list[bool] = []

    def _yaz(config, provider, account, passed):
        yazilan.append(passed)
        return config

    monkeypatch.setattr(tool_measure, "set_tool_eval_passed", _yaz)
    return yazilan


async def test_esigi_gecen_olcum_izni_acar(monkeypatch):
    gorulen = _sonda(monkeypatch, _rapor(_kusursuz()))
    yazilan = _yazimi_yakala(monkeypatch)

    sonuc = await tool_measure.measure_tool_support(_config(), "chatgpt_web")

    assert sonuc["ok"] and sonuc["gecti"]
    assert yazilan == [True]
    assert gorulen == ["chatgpt_web/main/auto"]


async def test_hic_olculemeyen_yetenek_izin_almaz(monkeypatch):
    """Payda sıfırken oranlar 1.0 döner; bu "geçti" DEĞİLDİR.

    Ölçülmemiş bir yeteneğe dosya yazma izni verilemez: model hiç araç bloğu
    üretmediğinde de dört metrik %100 görünür.
    """
    bos = EmulationEvalScore(
        tool_selection=0.0,
        schema_validity=1.0,
        argument_preservation=1.0,
        no_false_calls=1.0,
    )
    _sonda(monkeypatch, _rapor(bos, ham="Üzgünüm, dosya sistemine erişimim yok."))
    yazilan = _yazimi_yakala(monkeypatch)

    sonuc = await tool_measure.measure_tool_support(_config(), "chatgpt_web")

    assert sonuc["ok"] and not sonuc["gecti"]
    assert yazilan == [False]
    assert "hiç araç bloğu üretmedi" in sonuc["metin"]


async def test_isaret_gorunup_ayristirilamayan_cikti_ayri_soylenir(monkeypatch):
    bos = EmulationEvalScore(
        tool_selection=0.0, schema_validity=1.0, argument_preservation=1.0, no_false_calls=1.0
    )
    _sonda(monkeypatch, _rapor(bos, ham='<tool_call>{"name":}</tool_call>'))
    _yazimi_yakala(monkeypatch)

    sonuc = await tool_measure.measure_tool_support(_config(), "chatgpt_web")

    assert "ayrıştırılamadı" in sonuc["metin"]


async def test_dusen_metrik_adiyla_bildirilir(monkeypatch):
    zayif = EmulationEvalScore(
        tool_selection=0.5,
        schema_validity=1.0,
        argument_preservation=1.0,
        no_false_calls=1.0,
        tool_selection_measured=4,
        schema_validity_measured=2,
        argument_preservation_measured=2,
        no_false_calls_measured=1,
    )
    _sonda(monkeypatch, _rapor(zayif))
    yazilan = _yazimi_yakala(monkeypatch)

    sonuc = await tool_measure.measure_tool_support(_config(), "chatgpt_web")

    assert not sonuc["gecti"]
    assert "araç seçimi" in sonuc["metin"]
    assert yazilan == [False]


async def test_olcum_yapilamadiysa_bayrak_hic_yazilmaz(monkeypatch):
    """Oran sınırı bir sonuç değildir: false yazmak geçmiş ölçümü siler."""
    _sonda(monkeypatch, FusionError("Sağlayıcı oran sınırına takıldı; ölçüm durduruldu."))
    yazilan = _yazimi_yakala(monkeypatch)

    sonuc = await tool_measure.measure_tool_support(_config(), "chatgpt_web")

    assert not sonuc["ok"]
    assert "oran sınırına takıldı" in sonuc["metin"]
    assert yazilan == []


@pytest.mark.parametrize("hesap", ["", "main"])
async def test_hesap_verilmezse_ana_hesap_olculur(monkeypatch, hesap):
    gorulen = _sonda(monkeypatch, _rapor(_kusursuz()))
    _yazimi_yakala(monkeypatch)

    await tool_measure.measure_tool_support(_config(), "chatgpt_web", hesap)

    assert gorulen == ["chatgpt_web/main/auto"]
