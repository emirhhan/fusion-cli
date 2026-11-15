"""Eşleştirme yanıtı ağda kaybolsa hayalet cihaz ya da ikinci kayıt oluşmaz (WP08).

Ölçüldü (29 Ekim): `claim` cihaz sırrını TEK SEFER veriyordu. Yanıt kaybolursa telefon
yeniden sorunca "kod geçersiz" alıyor; sırrı hiçbir telefona ulaşmamış cihaz listede
kalıyor ve kullanıcı yeniden eşleşince ikinci bir kayıt doğuyordu.

Yeni sözleşme: telefon kodu gönderirken bir teslim anahtarı da gönderir; aynı anahtarla
`claim` teslim süresi boyunca tekrarlanabilir ve aynı cihazı döndürür. Telefonun ilk
imzalı isteği teslimi onaylar; teslim süresi dolduğu hâlde hiç kullanılmamış cihaz
iptal edilir.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.remote.constants import PAIRING_CLAIM_TTL_SECONDS
from fusion_cli.remote.devices import DeviceRegistry
from fusion_cli.remote.pairing import PairingError, PairingService

from .test_remote_service import FakeClock

_ANAHTAR = "a" * 32


def _kur(tmp_path: Path) -> tuple[PairingService, DeviceRegistry, FakeClock, str]:
    clock = FakeClock()
    registry = DeviceRegistry(tmp_path / "d.json", clock)
    service = PairingService(registry, clock, require_approval=lambda: False)
    code, _ = service.begin(None)
    service.submit(code, "Telefon", channel="signed", claim_key=_ANAHTAR)
    return service, registry, clock, code


def test_kaybolan_yanit_ayni_anahtarla_ayni_cihazi_yeniden_alir(tmp_path):
    service, registry, _clock, code = _kur(tmp_path)

    ilk = service.claim(code, claim_key=_ANAHTAR)
    tekrar = service.claim(code, claim_key=_ANAHTAR)

    assert ilk is not None and tekrar is not None
    assert tekrar.device_id == ilk.device_id and tekrar.secret_hex == ilk.secret_hex
    assert len(registry.list_devices()) == 1


def test_anahtari_bilmeyen_sirri_alamaz(tmp_path):
    service, _registry, _clock, code = _kur(tmp_path)
    service.claim(code, claim_key=_ANAHTAR)

    with pytest.raises(PairingError):
        service.claim(code, claim_key="b" * 32)
    with pytest.raises(PairingError):
        service.claim(code)


def test_hic_kullanilmayan_hayalet_cihaz_teslim_suresi_dolunca_iptal_edilir(tmp_path):
    service, registry, clock, code = _kur(tmp_path)
    cihaz = service.claim(code, claim_key=_ANAHTAR)
    assert cihaz is not None

    clock.value += PAIRING_CLAIM_TTL_SECONDS + 1
    service.begin(None)  # bekleyenler temizlenir

    assert registry.active(cihaz.device_id) is None


def test_ilk_imzali_istek_teslimi_onaylar_ve_cihaz_kalir(tmp_path):
    service, registry, clock, code = _kur(tmp_path)
    cihaz = service.claim(code, claim_key=_ANAHTAR)
    assert cihaz is not None

    service.acknowledge(cihaz.device_id)
    clock.value += PAIRING_CLAIM_TTL_SECONDS + 1
    service.begin(None)

    assert registry.active(cihaz.device_id) is not None
    with pytest.raises(PairingError):
        service.claim(code, claim_key=_ANAHTAR)


def test_anahtarsiz_eski_istemci_tek_sefer_alir(tmp_path):
    clock = FakeClock()
    service = PairingService(
        DeviceRegistry(tmp_path / "d.json", clock), clock, require_approval=lambda: False
    )
    code, _ = service.begin(None)
    service.submit(code, "Eski", channel="signed")

    assert service.claim(code) is not None
    with pytest.raises(PairingError):
        service.claim(code)


def test_son_saniyede_onaylanan_kodun_teslim_suresi_kod_suresinden_bagimsiz(tmp_path):
    from fusion_cli.remote.constants import PAIRING_CODE_TTL_SECONDS

    clock = FakeClock()
    registry = DeviceRegistry(tmp_path / "d.json", clock)
    service = PairingService(registry, clock, require_approval=lambda: False)
    code, _ = service.begin(None)
    clock.value += PAIRING_CODE_TTL_SECONDS - 1
    service.submit(code, "Geç", channel="signed", claim_key=_ANAHTAR)
    clock.value += 5  # kodun süresi doldu, teslim süresi sürüyor

    cihaz = service.claim(code, claim_key=_ANAHTAR)

    assert cihaz is not None and registry.active(cihaz.device_id) is not None


def test_onaylanmis_eslesmeyi_reddetmek_cihazi_birakmaz(tmp_path):
    service, registry, _clock, code = _kur(tmp_path)
    cihaz = service.claim(code, claim_key=_ANAHTAR)
    assert cihaz is not None

    assert service.reject(code)

    assert registry.active(cihaz.device_id) is None
