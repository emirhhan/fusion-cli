"""Telefon ekranı kendi beyanıyla açamaz; güven masaüstünden ve sürelidir (WP08, R1-02).

Ölçüldü (29 Ekim): `screen.request` isteğine `confirmed: true` ekleyen telefon,
masaüstünde hiçbir onay olmadan ekranı izlemeye başlıyordu; hesapla giriş yapan her
telefon varsayılan olarak `desktop.observe` alıyor. Kullanıcı kararı (29 Ekim): ilk
açılış masaüstünde onaylanır; "hatırla" seçilirse cihaza süreli güven verilir.
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.remote.constants import SCREEN_TRUST_SECONDS
from fusion_cli.remote.devices import DeviceRegistry

from .test_remote_approval_receipts import make_service


async def test_telefon_beyani_ekran_acmaz_masaustu_onayi_gerekir(tmp_path: Path) -> None:
    service, registry, _backend, _clock = make_service(tmp_path)
    phone = registry.add("Tel", "signed", frozenset({"desktop.observe"}))

    istek = await service.call(phone, "screen.request", {"remember": True, "confirmed": True})

    assert istek.data == {"state": "pending", "remembered": False}
    assert service.approve_screen(phone.device_id)
    assert (await service.call(phone, "screen.status", {})).data["state"] == "active"


async def test_hatirlanan_guven_sureli_ve_kalici(tmp_path: Path) -> None:
    service, registry, _backend, clock = make_service(tmp_path)
    phone = registry.add("Tel", "signed", frozenset({"desktop.observe"}))
    await service.call(phone, "screen.request", {"remember": True})
    service.approve_screen(phone.device_id)

    reloaded = DeviceRegistry(tmp_path / "devices.json", clock)
    assert reloaded.has_screen_trust(phone.device_id)
    clock.value += 7201  # oturum süresi doldu, güven sürüyor
    assert (await service.call(phone, "screen.request", {})).data["state"] == "active"

    clock.value += SCREEN_TRUST_SECONDS
    sonra = await service.call(phone, "screen.request", {"confirmed": True})
    assert sonra.data["state"] == "pending"


async def test_durdur_guveni_hemen_kaldirir(tmp_path: Path) -> None:
    service, registry, _backend, _clock = make_service(tmp_path)
    phone = registry.add("Tel", "signed", frozenset({"desktop.observe"}))
    await service.call(phone, "screen.request", {"remember": True})
    service.approve_screen(phone.device_id)

    await service.call(phone, "screen.stop", {})

    assert not registry.has_screen_trust(phone.device_id)
    assert (await service.call(phone, "screen.request", {})).data["state"] == "pending"


async def test_eski_hatirla_istegi_sonraki_onaya_tasinmaz(tmp_path: Path) -> None:
    service, registry, _backend, _clock = make_service(tmp_path)
    phone = registry.add("Tel", "signed", frozenset({"desktop.observe"}))
    await service.call(phone, "screen.request", {"remember": True})
    await service.call(phone, "screen.request", {})

    service.approve_screen(phone.device_id)

    assert not registry.has_screen_trust(phone.device_id)
