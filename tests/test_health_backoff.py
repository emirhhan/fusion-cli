"""Kota hatası, sıradan bir arızadan farklı davranır.

Kota/hız sınırı geçici bir arıza değildir: sağlayıcı "şimdi olmaz" diyor ve aynı
soğuma süresiyle hemen yeniden denemek turu yakar. Ölçüldü (web koşuları): kota
dolduğunda tur, aynı sağlayıcıya art arda çarparak bütçesini bitiriyordu.

Geri çekilme ARTAN olur ve üst sınırı vardır; sınırsız büyüyen bir bekleme,
sağlayıcı toparlansa bile modeli oturum boyunca dışlardı.
"""

from __future__ import annotations

from fusion_cli.core.health import CircuitPhase, ModelHealth


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now


def _health(clock: _Clock) -> ModelHealth:
    return ModelHealth(failure_threshold=3, cooldown_s=10.0, alpha=0.3, clock=clock)


def test_kota_hatasi_devreyi_hemen_acar():
    """Eşik beklenmez: sağlayıcı zaten 'şimdi olmaz' dedi."""
    clock = _Clock()
    health = _health(clock)

    health.record(False, rate_limited=True)

    assert health.phase is CircuitPhase.OPEN
    assert not health.allow()


def test_kota_sogumasi_normalden_uzun():
    clock = _Clock()
    health = _health(clock)

    health.record(False, rate_limited=True)
    clock.now = 11.0  # normal cooldown dolmuş olurdu

    assert not health.allow()


def test_kota_sogumasi_tekrarlarda_artar():
    clock = _Clock()
    health = _health(clock)

    health.record(False, rate_limited=True)
    clock.now = 100.0
    assert health.allow()  # ilk bekleme doldu
    health.record(False, rate_limited=True)
    clock.now = 130.0

    assert not health.allow()  # ikinci bekleme daha uzun


def test_basarili_cagri_kota_gerilimini_sifirlar():
    clock = _Clock()
    health = _health(clock)

    health.record(False, rate_limited=True)
    clock.now = 100.0
    health.allow()
    health.record(True, latency_ms=10)
    health.record(False, rate_limited=True)
    clock.now = 100.0 + 31.0

    assert health.allow()  # gerilim sıfırlandığı için yine ilk seviye bekleme (30 sn)


def test_siradan_ariza_davranisi_degismez():
    clock = _Clock()
    health = _health(clock)

    health.record(False)
    health.record(False)

    assert health.phase is CircuitPhase.CLOSED  # eşik 3

    health.record(False)
    assert health.phase is CircuitPhase.OPEN
    clock.now = 10.0
    assert health.allow()
