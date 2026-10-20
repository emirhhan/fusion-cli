"""Hesapla cihaz kaydı ve geçici 401'lerin eşleşmeyi/kilidi bozmaması."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx
import pytest

from fusion_cli.remote.account_login import AccountLogin
from fusion_cli.remote.asgi import RemoteApp
from fusion_cli.remote.scopes import DEFAULT_SCOPES
from fusion_cli.remote.signing import SignatureVerifier
from tests.test_remote_service import Rig

PASSWORD = "cok-gizli-parola-123"  # gitleaks:allow


def _login_rig(rig: Rig, *, enabled: bool = True) -> None:
    login = AccountLogin(
        authenticate=lambda identifier, password: identifier == "emir" and password == PASSWORD,
        registry=rig.registry,
        limiter=rig.limiter,
    )
    rig.app = RemoteApp(
        service=rig.service,
        registry=rig.registry,
        pairing=rig.pairing,
        verifier=SignatureVerifier(rig.clock),
        limiter=rig.limiter,
        account_login=login if enabled else None,
    )
    rig.client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=rig.app), base_url="http://127.0.0.1"
    )


async def _post(rig: Rig, path: str, payload: dict[str, Any]) -> httpx.Response:
    return await rig.client.post(path, json=payload)


@pytest.fixture
async def rig(tmp_path: Path) -> Any:
    instance = Rig(tmp_path)
    yield instance
    await instance.service.aclose()


async def test_guvenli_kanal_degilse_hesap_girisi_kapali(rig: Rig) -> None:
    _login_rig(rig, enabled=False)
    assert (await _post(rig, "/v1/auth/options", {})).json() == {"accountLogin": False}
    denied = await _post(rig, "/v1/auth/login", {"identifier": "emir", "password": PASSWORD})
    assert denied.status_code == 403 and not rig.registry.list_devices()


async def test_hesapla_giris_ekran_izleme_isteyebilir_ama_yazma_yetkisi_almaz(rig: Rig) -> None:
    _login_rig(rig)
    assert (await _post(rig, "/v1/auth/options", {})).json() == {"accountLogin": True}
    response = await _post(
        rig,
        "/v1/auth/login",
        {"identifier": " emir ", "password": PASSWORD, "deviceName": "iPhone"},
    )
    body = response.json()
    assert response.status_code == 200 and body["state"] == "onaylandi"
    assert set(body["scopes"]) == set(DEFAULT_SCOPES) | {"desktop.observe"}
    assert not {"desktop.control", "project.write", "production.deploy"} & set(body["scopes"])
    device = rig.registry.active(body["deviceId"])
    assert device is not None and device.name == "iPhone"
    # Verilen sır gerçekten çalışır: imzalı RPC kabul edilir.
    ok = await rig.rpc(body["deviceId"], bytes.fromhex(body["secret"]), "service.status")
    assert ok.status_code == 200

    pending = await rig.rpc(body["deviceId"], bytes.fromhex(body["secret"]), "screen.request")
    assert pending.json()["ok"] is True
    assert body["deviceId"] in rig.service.screen_gate.pending()
    assert body["deviceId"] not in rig.service.screen_gate.active()
    frame = await rig.rpc(body["deviceId"], bytes.fromhex(body["secret"]), "screen.frame")
    assert frame.json()["ok"] is False  # Masaüstü onayı olmadan görüntü verilmez.


async def test_yanlis_parola_genel_mesaj_verir_ve_kilitler(rig: Rig) -> None:
    _login_rig(rig)
    for _ in range(5):
        bad = await _post(rig, "/v1/auth/login", {"identifier": "emir", "password": "yanlis"})
        assert bad.status_code == 401 and bad.json()["error"] == "kimlik_hatali"
    locked = await _post(rig, "/v1/auth/login", {"identifier": "emir", "password": PASSWORD})
    assert locked.status_code == 429  # doğru parola da kilit süresince reddedilir
    assert not rig.registry.list_devices()
    rig.clock.value += 901
    again = await _post(rig, "/v1/auth/login", {"identifier": "emir", "password": PASSWORD})
    assert again.status_code == 200


async def test_olmayan_kullanici_ile_yanlis_parola_ayni_cevap(rig: Rig) -> None:
    _login_rig(rig)
    first = await _post(rig, "/v1/auth/login", {"identifier": "yok", "password": "x"})
    second = await _post(rig, "/v1/auth/login", {"identifier": "emir", "password": "x"})
    assert first.json() == second.json() and first.status_code == second.status_code == 401


async def test_parola_loglanmaz(rig: Rig, caplog: pytest.LogCaptureFixture) -> None:
    _login_rig(rig)
    with caplog.at_level(logging.DEBUG):
        await _post(rig, "/v1/auth/login", {"identifier": "emir", "password": PASSWORD})
        await _post(rig, "/v1/auth/login", {"identifier": "emir", "password": "yanlis-parola-9"})
    text = " ".join(record.getMessage() for record in caplog.records)
    assert PASSWORD not in text and "yanlis-parola-9" not in text
    assert PASSWORD not in (rig.registry._path).read_text()  # type: ignore[attr-defined]


async def test_gecersiz_girdi_reddedilir(rig: Rig) -> None:
    _login_rig(rig)
    assert (
        await _post(rig, "/v1/auth/login", {"identifier": "", "password": "x"})
    ).status_code == 400
    long = "a" * 2000
    assert (
        await _post(rig, "/v1/auth/login", {"identifier": "emir", "password": long})
    ).status_code == 400


async def test_iptal_edilen_cihaz_cihaz_iptal_nedeniyle_reddedilir(rig: Rig) -> None:
    device_id, secret = rig.pair()
    rig.registry.revoke(device_id)
    response = await rig.rpc(device_id, secret, "service.status")
    assert response.status_code == 401 and response.json()["reason"] == "cihaz_iptal"


async def test_eski_sira_gecici_hatadir_ve_cihazi_kilitlemez(rig: Rig) -> None:
    device_id, secret = rig.pair()
    assert (await rig.rpc(device_id, secret, "service.status", sequence=100)).status_code == 200
    for index in range(10):  # eşzamanlı isteklerin ters sırada ulaşması
        late = await rig.rpc(
            device_id, secret, "service.status", sequence=50 + index, nonce=f"x{index}"
        )
        assert late.status_code == 401 and late.json()["reason"] == "sira_eski"
    fresh = await rig.rpc(device_id, secret, "service.status", sequence=200, nonce="taze")
    assert fresh.status_code == 200  # 10 geçici hata sonrası 429 yok


async def test_sahte_imza_kilide_sayilir(rig: Rig) -> None:
    device_id, secret = rig.pair()
    for index in range(5):
        bad = await rig.rpc(device_id, secret, "service.status", signature="00", nonce=f"b{index}")
        assert bad.status_code == 401 and bad.json()["reason"] == "imza_gecersiz"
    locked = await rig.rpc(device_id, secret, "service.status", nonce="z")
    assert locked.status_code == 429
