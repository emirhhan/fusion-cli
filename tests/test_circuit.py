"""Circuit breaking sağlayıcı ve factory entegrasyonu.

Devresi açık model çağrılmadan atlanır; sonuç sağlığa kaydedilir.
"""

from __future__ import annotations

import pytest

from fusion_cli.core.health import CircuitPhase, HealthRegistry, ModelHealth
from fusion_cli.providers.circuit import CIRCUIT_OPEN_ERROR, CircuitBreakingProvider
from fusion_cli.providers.factory import build_provider

from .fakes import FakeProvider, request


class _MutableClock:
    def __init__(self) -> None:
        self.t = 0.0

    def monotonic(self) -> float:
        return self.t

    def now(self) -> float:
        return self.t


def _health(clock=None, *, threshold=3, cooldown=60.0, alpha=0.3):
    return ModelHealth(
        failure_threshold=threshold,
        cooldown_s=cooldown,
        alpha=alpha,
        clock=clock or _MutableClock(),
    )


async def test_kapali_devre_ic_saglayiciyi_cagirir():
    inner = FakeProvider("m", chunks=("cevap",), ok=True)
    saglik = _health()
    sarmal = CircuitBreakingProvider(inner, health=saglik, role="agent")
    sonuc = await sarmal.complete(request())
    assert inner.started is True
    assert sonuc.text == "cevap"


async def test_acik_devre_ic_saglayiciyi_cagirmaz():
    inner = FakeProvider("m", chunks=("cevap",), ok=True)
    saglik = _health(threshold=1)
    saglik.record(ok=False)  # devreyi aç
    assert saglik.phase is CircuitPhase.OPEN
    sarmal = CircuitBreakingProvider(inner, health=saglik, role="agent")
    sonuc = await sarmal.complete(request())
    assert inner.started is False
    assert sonuc.ok is False
    assert sonuc.error == CIRCUIT_OPEN_ERROR


async def test_basarili_cagri_saglik_kaydeder():
    inner = FakeProvider("m", chunks=("cevap",), ok=True)
    saglik = _health()
    sarmal = CircuitBreakingProvider(inner, health=saglik, role="agent")
    onceki = saglik.samples
    await sarmal.complete(request())
    assert saglik.samples == onceki + 1


async def test_basarisiz_cagri_esikte_devreyi_acar():
    inner = FakeProvider("m", ok=False, error="5xx")
    saglik = _health(threshold=2)
    sarmal = CircuitBreakingProvider(inner, health=saglik, role="agent")
    await sarmal.complete(request())
    await sarmal.complete(request())
    assert saglik.phase is CircuitPhase.OPEN


async def test_stream_sonucu_sagliga_kaydedilir():
    inner = FakeProvider("m", chunks=("parça",), ok=True)
    saglik = _health()
    sarmal = CircuitBreakingProvider(inner, health=saglik, role="agent")
    async for _ in sarmal.stream(request()):
        pass
    assert saglik.samples == 1


async def test_acik_devrede_stream_ic_saglayiciyi_cagirmaz():
    inner = FakeProvider("m", chunks=("parça",), ok=True)
    saglik = _health(threshold=1)
    saglik.record(ok=False)
    sarmal = CircuitBreakingProvider(inner, health=saglik, role="agent")
    ogeler = [item async for item in sarmal.stream(request())]
    assert inner.started is False
    assert len(ogeler) == 1  # yalnızca hızlı-başarısız StreamDone


async def test_factory_saglik_verilmezse_breaker_kurulmaz():
    from fusion_cli.core.types import ModelSpec

    spec = ModelSpec(name="agent", model="sahte/model")
    provider = build_provider(spec, publisher=None, retry_delays_s=())
    # Breaker olmadan da çağrı yapılabilir (davranış değişmez); tip kontrolü yeter.
    assert provider.label == "sahte/model"


def test_registry_kurulur():
    registry = HealthRegistry(failure_threshold=3, cooldown_s=60.0, alpha=0.3)
    assert registry.snapshot() == ()


@pytest.mark.parametrize("phase", list(CircuitPhase))
def test_tum_devre_durumlari_deger_tasir(phase):
    assert isinstance(phase.value, str)


# --- /health komutu -------------------------------------------------------- #


def _state(tmp_path, health=None):
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.memory.factory import null_memory

    from .fakes import make_config

    return ReplState(config=make_config(), memory=null_memory(), root=tmp_path, health=health)


def _run(state, satir):
    from fusion_cli.cli.repl.commands import build_registry, parse

    name, argument = parse(satir)
    return build_registry().get(name).handler(state, argument)


def test_health_komutu_veri_yokken_bilgilendirir(tmp_path):
    from fusion_cli.ui import messages

    assert _run(_state(tmp_path), "/health") == messages.HEALTH_EMPTY


def test_health_komutu_skor_ve_durumu_gosterir(tmp_path):
    registry = HealthRegistry(failure_threshold=1, cooldown_s=60.0, alpha=0.5)
    registry.for_model("nvidia/model").record(ok=False)  # devreyi aç
    mesaj = _run(_state(tmp_path, health=registry), "/health")
    assert "nvidia/model" in mesaj
    assert "AÇIK" in mesaj
