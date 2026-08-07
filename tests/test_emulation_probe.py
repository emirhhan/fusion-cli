"""Araç yeteneği ölçümü — web modeline dosya değiştirme izni veren tek kapı.

Ölçüm gerçek çağrı yapar; bu dosya sahte bir sağlayıcıyla çalışır (ağ yok).
"""

from __future__ import annotations

import pytest

from fusion_cli.config.models import WebSessionConfig
from fusion_cli.core.errors import FusionError
from fusion_cli.core.tool_emulation import PAYLOAD_SENTINEL
from fusion_cli.core.types import ModelResult
from fusion_cli.engines.emulation_probe import PROBE_SCENARIOS, probe_emulation

from .fakes import make_config

MODEL = "chatgpt_web/main/auto"


class _ScriptedProvider:
    """Senaryo sırasına göre ham metin döndüren sahte sağlayıcı."""

    def __init__(self, outputs: list[str]) -> None:
        self._outputs = list(outputs)
        self.seen: list[str] = []

    @property
    def label(self) -> str:
        return MODEL

    async def complete(self, request):
        self.seen.append(request.messages[-1].content)
        text = self._outputs.pop(0) if self._outputs else ""
        return ModelResult(name=MODEL, model=MODEL, text=text, latency_ms=1, ok=True)


class _Registry:
    """Sonda hangi OTURUM YAPILANDIRMASIYLA sağlayıcı kurduğunu kaydeder.

    Eski sahte yalnızca `build(model)` sunuyordu ve model kimliği hiç değişmediği
    için sondanın araç desteğini kapatmayı unuttuğunu göremiyordu.
    """

    def __init__(self, provider) -> None:
        self._provider = provider
        self.built_session = None

    def build_session(self, session, **kwargs):
        self.built_session = session
        return self._provider

    def build(self, model, **kwargs):
        raise AssertionError("sonda oturum yapılandırmasıyla kurmalı, model kimliğiyle değil")


def _config(**overrides):
    alanlar = {
        "model": MODEL,
        "provider": "chatgpt_web",
        "account": "main",
        "transport": "browser",
        "tool_support": "emulated",
    }
    alanlar.update(overrides)
    return make_config(web_sessions=(WebSessionConfig(**alanlar),))


def _kusursuz_ciktilar() -> list[str]:
    """Sözleşmeye harfiyen uyan bir modelin üreteceği çıktılar."""
    kod = 'def greet(name):\n    return "Hello!"'
    return [
        '<tool_call>{"name":"read_file","arguments":{"path":"src/app.py"}}</tool_call>',
        '<tool_call>{"name":"run_shell","arguments":'
        '{"command":"python3 -m pytest -q"}}</tool_call>',
        (
            '<tool_payload id="f1" lines="2">\n```python\n'
            f"{PAYLOAD_SENTINEL}\n{kod}\n```\n</tool_payload>\n"
            '<tool_call>{"name":"write_file","arguments":'
            '{"path":"greet.py","content":{"$ref":"f1"}}}</tool_call>'
        ),
        '<tool_call>{"name":"search_code","arguments":{"pattern":"TODO"}}</tool_call>',
        "Liste değiştirilebilir, demet değiştirilemez.",
    ]


async def test_sozlesmeye_uyan_model_esigi_gecer():
    provider = _ScriptedProvider(_kusursuz_ciktilar())

    rapor = await probe_emulation(_config(), MODEL, registry=_Registry(provider))
    score = rapor.score

    assert score.passes()
    assert len(provider.seen) == len(PROBE_SCENARIOS)


async def test_yanlis_arac_secen_model_esigi_gecemez():
    ciktilar = _kusursuz_ciktilar()
    ciktilar[0] = '<tool_call>{"name":"list_dir","arguments":{"path":"."}}</tool_call>'

    rapor = await probe_emulation(
        _config(), MODEL, registry=_Registry(_ScriptedProvider(ciktilar))
    )
    score = rapor.score

    assert score.tool_selection < 1.0
    assert not score.passes()


async def test_gereksiz_arac_cagiran_model_esigi_gecemez():
    """Açıklama istenen senaryoda araç çağırmak sahte çağrıdır."""
    ciktilar = _kusursuz_ciktilar()
    ciktilar[-1] = '<tool_call>{"name":"read_file","arguments":{"path":"x.py"}}</tool_call>'

    rapor = await probe_emulation(
        _config(), MODEL, registry=_Registry(_ScriptedProvider(ciktilar))
    )
    score = rapor.score

    assert score.no_false_calls < 1.0
    assert not score.passes()


async def test_bozuk_payload_semayi_dusurur():
    """Satır sayısı tutmayan payload çağrıyı hiç oluşturmaz."""
    ciktilar = _kusursuz_ciktilar()
    ciktilar[2] = ciktilar[2].replace('lines="2"', 'lines="9"')

    rapor = await probe_emulation(
        _config(), MODEL, registry=_Registry(_ScriptedProvider(ciktilar))
    )
    score = rapor.score

    assert not score.passes()


async def test_saglayici_hatasi_olcumu_sessizce_gecirmez():
    class _Bozuk:
        label = MODEL

        async def complete(self, request):
            return ModelResult(
                name=MODEL, model=MODEL, text="", latency_ms=1, ok=False, error="oturum düştü"
            )

    with pytest.raises(FusionError, match="oturum düştü"):
        await probe_emulation(_config(), MODEL, registry=_Registry(_Bozuk()))


async def test_etkin_web_oturumu_yoksa_olcum_yapilmaz():
    with pytest.raises(FusionError, match="etkin bir web oturumu yok"):
        await probe_emulation(_config(enabled=False), MODEL, registry=_Registry(None))


async def test_ham_cikti_teshis_icin_saklanir():
    """Puan tek başına yetmez: "araç seçimi %0" hem reddi hem yutulmuş bloğu anlatır."""
    ciktilar = _kusursuz_ciktilar()
    ciktilar[0] = "Üzgünüm, dosya sistemine erişimim yok."

    rapor = await probe_emulation(
        _config(), MODEL, registry=_Registry(_ScriptedProvider(ciktilar))
    )

    ilk = rapor.samples[0]
    assert ilk.parsed_tool is None
    assert ilk.has_call_markers is False
    assert "erişimim yok" in ilk.raw_output


async def test_olculemeyen_metrik_sayaci_sifir_kalir():
    """Payda sıfırken oran 1.0 döner; sayaç bunun ölçülmediğini söyler."""
    ciktilar = ["düz metin"] * 5

    rapor = await probe_emulation(
        _config(), MODEL, registry=_Registry(_ScriptedProvider(ciktilar))
    )

    assert rapor.score.schema_validity == 1.0
    assert rapor.score.schema_validity_measured == 0
    assert rapor.score.tool_selection_measured == 4
    assert not rapor.score.passes()


async def test_sonda_ham_cikti_icin_arac_destegini_kapatir():
    """Regresyon: sonda ayrıştırılmış değil HAM çıktı almalı.

    Ölçüldü (Gemini web): sonda emulated adaptörle kuruluyordu, adaptör araç
    bloklarını metinden çıkarıyor ve geriye boş string kalıyordu. Model geçerli
    çağrılar ürettiği hâlde ölçüm "hiç araç üretmedi" diyordu.
    """
    registry = _Registry(_ScriptedProvider(_kusursuz_ciktilar()))

    await probe_emulation(_config(), MODEL, registry=registry)

    assert registry.built_session is not None
    assert registry.built_session.tool_support == "none"
    assert registry.built_session.model == MODEL


async def test_kayit_defteri_oturum_yapilandirmasiyla_kurabilir():
    """`build_session` orijinali değil VERİLEN yapılandırmayı kullanmalı."""
    from fusion_cli.core.model_capability import ToolSupport
    from fusion_cli.providers.web_registry import WebSessionRegistry

    oturum = WebSessionConfig(
        model=MODEL, provider="custom", account="main",
        transport="http", endpoint="https://uc/v1/chat/completions",
        tool_support="emulated",
    )
    registry = WebSessionRegistry((oturum,), environ={})

    from dataclasses import replace as _replace

    saglayici = registry.build_session(_replace(oturum, tool_support="none"))

    assert saglayici._tool_support is ToolSupport.NONE
