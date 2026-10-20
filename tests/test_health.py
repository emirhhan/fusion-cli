"""Circuit breaker ve güvenilirlik skoru — saf state machine testleri.

Zaman enjekte edilir: cooldown gerçek beklemeyle değil, sahte saat ilerletilerek
sınanır.
"""

from __future__ import annotations

from fusion_cli.core.health import CircuitPhase, HealthRegistry, ModelHealth


class _MutableClock:
    """monotonic() elle ilerletilebilen sahte saat."""

    def __init__(self) -> None:
        self.t = 0.0

    def monotonic(self) -> float:
        return self.t

    def now(self) -> float:
        return self.t


def _health(clock, *, threshold=3, cooldown=60.0, alpha=0.3):
    return ModelHealth(failure_threshold=threshold, cooldown_s=cooldown, alpha=alpha, clock=clock)


def test_yeni_model_kapali_ve_izinli():
    saglik = _health(_MutableClock())
    assert saglik.phase is CircuitPhase.CLOSED
    assert saglik.allow() is True


def test_esik_kadar_arizada_devre_acilir():
    saglik = _health(_MutableClock(), threshold=3)
    for _ in range(3):
        saglik.record(ok=False)
    assert saglik.phase is CircuitPhase.OPEN
    assert saglik.allow() is False


def test_esigin_altinda_devre_kapali_kalir():
    saglik = _health(_MutableClock(), threshold=3)
    saglik.record(ok=False)
    saglik.record(ok=False)
    assert saglik.phase is CircuitPhase.CLOSED
    assert saglik.allow() is True


def test_basari_ardisik_sayaci_sifirlar():
    saglik = _health(_MutableClock(), threshold=3)
    saglik.record(ok=False)
    saglik.record(ok=False)
    saglik.record(ok=True)
    saglik.record(ok=False)
    assert saglik.phase is CircuitPhase.CLOSED


def test_cooldown_dolunca_yari_acik_denemeye_izin():
    clock = _MutableClock()
    saglik = _health(clock, threshold=1, cooldown=60.0)
    saglik.record(ok=False)
    assert saglik.allow() is False
    clock.t = 60.0
    assert saglik.allow() is True
    assert saglik.phase is CircuitPhase.HALF_OPEN


def test_yari_acik_basari_devreyi_kapatir():
    clock = _MutableClock()
    saglik = _health(clock, threshold=1, cooldown=60.0)
    saglik.record(ok=False)
    clock.t = 60.0
    saglik.allow()
    saglik.record(ok=True)
    assert saglik.phase is CircuitPhase.CLOSED
    assert saglik.allow() is True


def test_yari_acik_ariza_devreyi_yeniden_acar():
    clock = _MutableClock()
    saglik = _health(clock, threshold=1, cooldown=60.0)
    saglik.record(ok=False)
    clock.t = 60.0
    saglik.allow()
    saglik.record(ok=False)
    assert saglik.phase is CircuitPhase.OPEN
    assert saglik.allow() is False


def test_skor_arizayla_duser_basariyla_toparlar():
    saglik = _health(_MutableClock(), alpha=0.5)
    baslangic = saglik.score
    saglik.record(ok=False)
    dusuk = saglik.score
    assert dusuk < baslangic
    saglik.record(ok=True)
    assert saglik.score > dusuk


def test_yeni_model_iyimser_baslar():
    assert _health(_MutableClock()).score == 1.0


def test_registry_ayni_model_ayni_kaydi_verir():
    registry = HealthRegistry(
        failure_threshold=3, cooldown_s=60.0, alpha=0.3, clock=_MutableClock()
    )
    a = registry.for_model("p/m")
    b = registry.for_model("p/m")
    assert a is b


def test_registry_snapshot_skora_gore_siralar():
    registry = HealthRegistry(
        failure_threshold=3, cooldown_s=60.0, alpha=0.5, clock=_MutableClock()
    )
    registry.for_model("iyi").record(ok=True)
    kotu = registry.for_model("kotu")
    kotu.record(ok=False)
    kotu.record(ok=False)
    snapshot = registry.snapshot()
    assert snapshot[0][0] == "kotu"  # en düşük skor önce
