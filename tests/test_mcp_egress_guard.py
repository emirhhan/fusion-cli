"""Uzak MCP'nin yönlendirdiği adresler iç ağa istek attıramaz (WP11, SSRF).

OAuth keşfinde sunucunun döndürdüğü metadata (yetkilendirme sunucusu, token uç
noktası) herhangi bir adresi gösterebilir ve SDK oraya aynı istemciyle gider. Kötü
niyetli bir MCP sunucusu Fusion'ı `169.254.169.254` (bulut metadata) ya da yerel ağ
cihazlarına istek atmaya yönlendirebilirdi. Kullanıcının bilerek yapılandırdığı
sunucunun kendi adresi serbesttir; başka her hedef genel bir HTTPS adresi olmalıdır.
"""

from __future__ import annotations

import httpx
import pytest

from fusion_cli.mcp_bridge.egress import EgressBlockedError, guarded_client_factory


def _istemci(configured: str, resolved: dict[str, str]):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"ok": True})

    async def resolve(host: str) -> list[str]:
        return [resolved.get(host, "93.184.216.34")]

    factory = guarded_client_factory(
        configured, transport_for=lambda _h: httpx.MockTransport(handler), resolver=resolve
    )
    return factory(), seen


@pytest.mark.parametrize(
    "hedef",
    [
        "http://169.254.169.254/latest/meta-data/",
        "https://169.254.169.254/token",
        "https://10.0.0.5/.well-known/oauth-authorization-server",
        "https://192.168.1.1/token",
        "https://[::1]/token",
        "https://127.0.0.1:9999/token",
        "https://ic-ag.example/token",
        "http://auth.example.com/token",
    ],
)
async def test_ic_ag_ve_duz_http_hedefi_engellenir(hedef):
    client, seen = _istemci("https://mcp.example.com/mcp", {"ic-ag.example": "10.1.2.3"})

    async with client:
        with pytest.raises(EgressBlockedError):
            await client.get(hedef)

    assert seen == []


async def test_yapilandirilan_sunucu_ve_genel_https_hedefi_serbesttir():
    client, seen = _istemci("https://mcp.example.com/mcp", {})

    async with client:
        await client.get("https://mcp.example.com/.well-known/oauth-protected-resource")
        await client.get("https://auth.example.com/token")

    assert len(seen) == 2


async def test_kullanicinin_ic_ag_sunucusu_kendi_adresiyle_calisir():
    client, seen = _istemci("https://10.0.0.5:8443/mcp", {})

    async with client:
        await client.get("https://10.0.0.5:8443/mcp")
        with pytest.raises(EgressBlockedError):
            await client.get("https://10.0.0.6/token")

    assert seen == ["https://10.0.0.5:8443/mcp"]


async def test_yerel_gelistirme_sunucusu_loopback_ile_calisir():
    client, seen = _istemci("http://127.0.0.1:3001/mcp", {})

    async with client:
        await client.get("http://127.0.0.1:3001/mcp")

    assert seen == ["http://127.0.0.1:3001/mcp"]


@pytest.mark.parametrize(
    ("cozulen", "beklenen_url"),
    [("93.184.216.34", "https://93.184.216.34/token"),
     ("2606:2800:220:1::1", "https://[2606:2800:220:1::1]/token")],
)  # fmt: skip
async def test_istek_denetlenen_ipye_sabitlenir_host_ve_sni_ozgun_adi_tasir(cozulen, beklenen_url):
    """DNS rebinding: denetimden sonra ad başka IP'ye çözülse de istek denetlenen IP'ye gider."""
    gorulen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        gorulen.append(request)
        return httpx.Response(200)

    async def resolve(host: str) -> list[str]:
        return [cozulen]

    factory = guarded_client_factory(
        "https://mcp.example.com/mcp",
        transport_for=lambda _h: httpx.MockTransport(handler),
        resolver=resolve,
    )
    async with factory() as client:
        await client.get("https://auth.example.com/token")

    (istek,) = gorulen
    assert str(istek.url) == beklenen_url
    assert istek.headers["host"] == "auth.example.com"
    assert istek.extensions["sni_hostname"] == "auth.example.com"


async def test_bir_adresi_ic_aga_cozulen_ad_engellenir():
    async def resolve(host: str) -> list[str]:
        return ["93.184.216.34", "10.0.0.1"]

    factory = guarded_client_factory(
        "https://mcp.example.com/mcp",
        transport_for=lambda _h: httpx.MockTransport(lambda r: httpx.Response(200)),
        resolver=resolve,
    )
    async with factory() as client:
        with pytest.raises(EgressBlockedError):
            await client.get("https://auth.example.com/token")


async def test_uzak_akis_korumali_istemciyle_acilir(monkeypatch):
    """Korumanın bağlantı yoluna takılı olduğu: SDK'ya kendi istemci üreticimiz gider."""
    from contextlib import asynccontextmanager

    from fusion_cli.config.models import McpServerConfig, McpTransport
    from fusion_cli.mcp_bridge import transport as transport_module

    kaydedilen: dict[str, object] = {}

    @asynccontextmanager
    async def fake_http(url, **kwargs):
        kaydedilen.update(kwargs)
        yield None, None, None

    monkeypatch.setattr(transport_module, "streamablehttp_client", fake_http)
    config = McpServerConfig(
        name="uzak", transport=McpTransport.STREAMABLE_HTTP, url="https://mcp.example.com/mcp"
    )

    async with transport_module.open_mcp_stream(config):
        pass

    client = kaydedilen["httpx_client_factory"]()
    async with client:
        with pytest.raises(EgressBlockedError):
            await client.get("http://169.254.169.254/latest/meta-data/")


def test_engel_kalici_ve_anlasilir_basarisizlik_olarak_siniflanir():
    from fusion_cli.config.models import McpServerConfig, McpTransport
    from fusion_cli.mcp_bridge.failures import McpFailureKind, classify_failure

    config = McpServerConfig(
        name="uzak", transport=McpTransport.STREAMABLE_HTTP, url="https://mcp.example.com/mcp"
    )
    failure = classify_failure(
        EgressBlockedError("MCP sunucusu Fusion'ı iç ağdaki bir adrese (10.0.0.1) yönlendirdi"),
        config,
    )

    assert failure.kind is McpFailureKind.EGRESS_BLOCKED
    assert failure.is_permanent
    assert "10.0.0.1" in failure.message


@pytest.mark.parametrize(
    "hedef",
    ["https://[64:ff9b::a00:1]/token",       # NAT64 → 10.0.0.1
     "https://[::ffff:a9fe:a9fe]/token",     # IPv4-mapped → 169.254.169.254
     "https://[::7f00:1]/token"],            # eski IPv4-uyumlu → 127.0.0.1
)  # fmt: skip
async def test_ipv6ya_gomulu_ic_ag_adresi_engellenir(hedef):
    client, seen = _istemci("https://mcp.example.com/mcp", {})

    async with client:
        with pytest.raises(EgressBlockedError):
            await client.get(hedef)

    assert seen == []


async def test_ipv4_once_denenir_baglanamayan_adres_atlanir():
    denenen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        denenen.append(request.url.host)
        if request.url.host == "93.184.216.34":
            raise httpx.ConnectError("ulaşılamadı", request=request)
        return httpx.Response(200)

    async def resolve(host: str) -> list[str]:
        return ["2606:2800:220:1::1", "93.184.216.34"]

    factory = guarded_client_factory(
        "https://mcp.example.com/mcp",
        transport_for=lambda _h: httpx.MockTransport(handler),
        resolver=resolve,
    )
    async with factory() as client:
        response = await client.get("https://auth.example.com/token")

    assert response.status_code == 200
    assert denenen == ["93.184.216.34", "2606:2800:220:1::1"]


async def test_her_ana_makine_kendi_baglanti_havuzunu_kullanir():
    """Aynı IP'deki iki ad, birinin sertifikasıyla doğrulanmış bağlantıyı paylaşamaz."""
    havuzlar: dict[str, httpx.MockTransport] = {}

    def transport_for(host: str) -> httpx.MockTransport:
        havuzlar[host] = httpx.MockTransport(lambda r: httpx.Response(200))
        return havuzlar[host]

    async def resolve(host: str) -> list[str]:
        return ["93.184.216.34"]

    factory = guarded_client_factory(
        "https://mcp.example.com/mcp", transport_for=transport_for, resolver=resolve
    )
    async with factory() as client:
        await client.get("https://a.example.com/x")
        await client.get("https://b.example.com/x")
        await client.get("https://a.example.com/y")

    assert sorted(havuzlar) == ["a.example.com", "b.example.com"]
