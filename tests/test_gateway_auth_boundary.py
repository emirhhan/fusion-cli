"""Gateway ağ sınırı: yerel Host başlığı uzak isteğe yetki vermez.

Gateway kullanıcının sağlayıcı anahtarlarını taşır ve MCP sunucusu (komut
çalıştıran) ekleyebilir. `--host 0.0.0.0` ile açıldığında aynı ağdaki biri
`Host: localhost` yazarak `_foreign_host` denetimini geçiyordu; Origin
göndermediği için CSRF koruması da devreye girmiyordu. Karar artık bağlantının
gerçek kaynağına (ASGI `client`) göre verilir ve yerel olmayan bağlantı belirteç
ister.
"""

from __future__ import annotations

import httpx
import pytest

from fusion_cli.core.errors import FusionError
from fusion_cli.gateway.app import GatewayApp
from fusion_cli.gateway.server import serve

from .fakes import FakeProvider, make_config

_LAN_PEER = ("192.168.1.50", 50123)
_TOKEN = "gizli-gateway-belirteci"


def _app(tmp_path, *, access_token=None):
    from fusion_cli.config.credentials import FernetSecretStore

    return GatewayApp(
        make_config(),
        provider_factory=lambda spec: FakeProvider("nvidia_nim/m", chunks=("cevap",)),
        secret_store=FernetSecretStore(tmp_path / "s.enc", secret_key="k"),
        access_token=access_token,
    )


def _client(app, *, peer=("127.0.0.1", 40000)):
    transport = httpx.ASGITransport(app=app, client=peer)
    return httpx.AsyncClient(transport=transport, base_url="http://localhost")


@pytest.mark.parametrize("path", ["/api/state", "/api/providers", "/v1/models"])
async def test_yerel_host_basligi_uzak_baglantiya_yetki_vermez(tmp_path, path):
    async with _client(_app(tmp_path), peer=_LAN_PEER) as client:
        cevap = await client.get(path)

    assert cevap.status_code == 401


async def test_uzak_baglanti_durum_degistiremez(tmp_path):
    async with _client(_app(tmp_path), peer=_LAN_PEER) as client:
        cevap = await client.post("/api/routing", json={"strategy": "round_robin"})

    assert cevap.status_code == 401


async def test_uzak_baglanti_yanlis_belirtecle_reddedilir(tmp_path):
    app = _app(tmp_path, access_token=_TOKEN)
    async with _client(app, peer=_LAN_PEER) as client:
        cevap = await client.get("/api/state", headers={"authorization": "Bearer yanlis"})

    assert cevap.status_code == 401


async def test_uzak_baglanti_dogru_belirtecle_kabul_edilir(tmp_path):
    app = _app(tmp_path, access_token=_TOKEN)
    async with _client(app, peer=_LAN_PEER) as client:
        cevap = await client.get("/api/state", headers={"authorization": f"Bearer {_TOKEN}"})

    assert cevap.status_code == 200


async def test_yerel_baglanti_belirtecsiz_calismaya_devam_eder(tmp_path):
    """Kits, panel ve yerel IDE istemcileri bugün belirteç göndermez; kırılmazlar."""
    async with _client(_app(tmp_path)) as client:
        cevap = await client.get("/api/state")

    assert cevap.status_code == 200


@pytest.fixture
def uvicorn_calls(monkeypatch):
    """Gerçek sunucu açılmasın; `uvicorn.run` çağrıları kaydedilsin."""
    import sys
    import types

    calls: list[dict] = []
    fake = types.SimpleNamespace(run=lambda app, **kwargs: calls.append(kwargs))
    monkeypatch.setitem(sys.modules, "uvicorn", fake)
    return calls


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "::"])
def test_ag_bind_belirtec_olmadan_baslatilmaz(host, uvicorn_calls):
    with pytest.raises(FusionError):
        serve(make_config(), host=host, port=0)

    assert uvicorn_calls == []


def test_ag_bind_belirtecle_baslar(uvicorn_calls):
    serve(make_config(), host="0.0.0.0", port=0, access_token=_TOKEN)

    assert uvicorn_calls and uvicorn_calls[0]["host"] == "0.0.0.0"


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_yerel_bind_belirtec_istemez(host, uvicorn_calls):
    serve(make_config(), host=host, port=0)

    assert uvicorn_calls and uvicorn_calls[0]["host"] == host
