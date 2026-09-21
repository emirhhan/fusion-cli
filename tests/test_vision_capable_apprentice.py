"""Görsel çırak — ekli görsellerde gerçek yetenek (Faz 3, Görev 3, C4).

Kök neden: `config/eligibility.py::capability_from_spec` `ModelCapability.vision`
alanını hiçbir zaman doldurmuyordu ve `defaults.yaml`'da hiçbir agent adayında
`vision` etiketi yoktu; bu yüzden mesaja doğrudan eklenen bir görsel, model hiç
çağrılmadan `ConfigError` ile ölüyordu (`select_compatible_model`).

22 Eylül'de canlı ölçüldü (`LiteLlmProvider`, gerçek görsel + gerçek araç
şeması): `nvidia_nim/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` HEM doğru
araç çağrısı yaptı (6.13s) HEM 200x200 düz kırmızı bir PNG'nin rengini doğru
söyledi (3.11s, "kırmızı"); OpenRouter ücretsiz kopyası da aynı sonucu verdi
(6.34s / 3.51s). Bu modül şu ikisini doğrular: (1) `vision` etiketi artık
`ModelCapability.vision`'a gerçekten yansıyor, (2) görsel gerektiren bir görevde
bu etiketli aday seçilebiliyor. `view_image` aracının (ayrı `config.vision`
rolü) BOZULMADIĞI da regresyon olarak kilitlenir.
"""

from __future__ import annotations

import pytest

from fusion_cli.config.eligibility import capability_from_spec
from fusion_cli.config.loader import load_config
from fusion_cli.core.errors import ConfigError
from fusion_cli.core.types import ModelSpec
from fusion_cli.providers.capabilities import TaskRequirements, select_compatible_model


def _spec(*tags):
    return ModelSpec(name="m", model="p/m", tags=tuple(tags))


def test_vision_tag_capability_vision_alanini_true_yapar():
    assert capability_from_spec(_spec("agent", "vision")).vision is True


def test_vision_etiketsiz_model_capability_vision_false_kalir():
    assert capability_from_spec(_spec("agent", "code")).vision is False


def test_gorsel_gorevde_vision_tagli_model_secilir():
    havuz = (
        _spec("agent", "code"),
        _spec("agent", "vision"),
    )
    requirements = TaskRequirements(images=True)

    secilen = select_compatible_model(havuz, requirements)

    assert "vision" in secilen.tags


def test_gorsel_gorevde_hic_vision_tagli_model_yoksa_acik_hata_verir():
    havuz = (_spec("agent", "code"), _spec("agent", "reasoning"))
    requirements = TaskRequirements(images=True)

    with pytest.raises(ConfigError, match="görsel"):
        select_compatible_model(havuz, requirements)


def test_zincirde_gercek_bir_vision_tagli_aday_var():
    """Ölçülen modelin gerçekten `defaults.yaml`'a girdiğini doğrula (regresyon)."""
    config = load_config()

    vision_adaylari = [
        candidate
        for candidate in (config.agent, *config.candidates)
        if "vision" in candidate.tags
    ]

    assert vision_adaylari, "hiçbir agent adayında ölçülmüş vision etiketi yok"
    assert any(
        "nemotron-3-nano-omni" in candidate.model for candidate in vision_adaylari
    ), "ölçülen vision modeli zincirde/havuzda yok"


async def test_view_image_araci_vision_tagsiz_agentta_da_calisir(tmp_path, monkeypatch):
    """Regresyon: `_view_image_tool` ayrı `config.vision` rolünü kullanır; agent
    modelinin kendisi `vision` etiketi taşımasa bile diskteki bir görseli
    inceleyebilmeye devam eder — C4 çözümü bu yolu BOZMAZ."""
    import base64

    from fusion_cli.core.tools import ToolContext
    from fusion_cli.core.types import ModelResult
    from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
    from fusion_cli.engines.agent.engine_tools import build_agent_registry
    from fusion_cli.engines.agent.loop import AgentDeps

    from .fakes import AlwaysApprove, make_config

    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8"
        "BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    (tmp_path / "gorsel.png").write_bytes(png)

    class _Publisher:
        def publish(self, event):
            del event

    class _GorenSaglayici:
        @property
        def label(self):
            return "sahte-goz"

        async def complete(self, request):
            return ModelResult(
                name="goz", model="sahte", text="kırmızı bir kare", latency_ms=1, ok=True
            )

    def _build(spec, **kwargs):
        del spec, kwargs
        return _GorenSaglayici()

    monkeypatch.setattr("fusion_cli.providers.factory.build_provider", _build)

    # `agent:` rolü BİLİNÇLİ olarak `vision` etiketi TAŞIMAZ — asıl senaryo bu.
    config = make_config(
        agent=ModelSpec(name="agent", model="sahte/agent", tags=("agent", "code")),
        vision=ModelSpec(name="goz", model="sahte/vl"),
    )
    deps = AgentDeps(
        config=config,
        publisher=_Publisher(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )

    async def _hicbir_alt_ajan(*args, **kwargs):  # pragma: no cover - çağrılmaz
        raise AssertionError("alt ajan çalışmamalı")

    registry = build_agent_registry(deps, depth=0, run_agent=_hicbir_alt_ajan)
    sonuc = await registry.execute("view_image", {"path": "gorsel.png"}, deps.tool_context)

    assert sonuc.ok is True
    assert "kırmızı" in sonuc.output
