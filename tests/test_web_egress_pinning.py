"""Web araçları denetlediği adrese bağlanır; CGNAT/Tailscale ağı da iç ağdır (WP03).

Ölçüldü (29 Ekim):
- `url_block_reason` adı çözüp denetliyor, ardından httpx adı KENDİSİ yeniden
  çözüyordu. TTL'i 0 olan bir alan adı ilk sorguda genel, ikincide iç adres
  döndürerek denetimi atlatabilirdi (DNS rebinding). `web_fetch`, `site_crawl` ve
  `download_file` aynı kalıbı kullanıyordu.
- `100.64.0.0/10` (CGNAT; Tailscale cihazları burada) "genel" sayılıyordu: bir sayfa
  kullanıcının Tailscale ağındaki cihaza yönlendirebilirdi.
"""

from __future__ import annotations

import socket

import httpx
import pytest

from fusion_cli.core.network_address import is_public_ip
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import download, pinned_http, web


@pytest.mark.parametrize(
    ("adres", "genel"),
    [("93.184.216.34", True), ("2606:2800:220:1::1", True),
     ("100.64.0.1", False), ("100.100.100.100", False), ("10.0.0.1", False),
     ("169.254.169.254", False), ("::ffff:10.0.0.1", False), ("64:ff9b::a00:1", False),
     ("::7f00:1", False), ("0.0.0.0", False), ("gecersiz", False)],
)  # fmt: skip
def test_adres_politikasi(adres, genel):
    assert is_public_ip(adres) is genel


def test_tailscale_adresi_web_icin_engellidir():
    assert web.url_block_reason("http://100.101.102.103/") is not None


@pytest.fixture
def rebinding(monkeypatch):
    """İlk çözüm genel, sonrakiler iç adres; bağlantılar kaydedilir."""
    sorgular: list[str] = []
    baglanan: list[str] = []

    def getaddrinfo(host, port, *args, **kwargs):
        sorgular.append(host)
        address = "93.184.216.34" if len(sorgular) == 1 else "10.0.0.7"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port or 0))]

    def handler(request: httpx.Request) -> httpx.Response:
        baglanan.append(request.url.host)
        return httpx.Response(200, text="ic ag", headers={"content-type": "text/plain"})

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(pinned_http, "direct_transport", lambda _h: httpx.MockTransport(handler))
    monkeypatch.setattr(
        pinned_http, "direct_async_transport", lambda _h: httpx.MockTransport(handler)
    )
    return baglanan


def test_web_fetch_denetlenen_adresten_baska_yere_baglanmaz(rebinding, tmp_path):
    result = web.web_fetch({"url": "https://rebind.example/"}, ToolContext(root=tmp_path))

    assert not result.ok
    assert "10.0.0.7" not in rebinding
    assert rebinding == []


async def test_indirme_denetlenen_adresten_baska_yere_baglanmaz(rebinding, tmp_path):
    result = await download.download_file(
        {"url": "https://rebind.example/a.png", "path": "a.png"}, ToolContext(root=tmp_path)
    )

    assert not result.ok
    assert rebinding == []
    assert not (tmp_path / "a.png").exists()


def test_genel_adres_sabitlenir_host_ve_sni_korunur(monkeypatch):
    gorulen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        gorulen.append(request)
        return httpx.Response(200, text="tamam", headers={"content-type": "text/plain"})

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    )
    monkeypatch.setattr(pinned_http, "direct_transport", lambda _h: httpx.MockTransport(handler))

    _ctype, body, final_url = web.fetch_following_redirects("https://ornek.example/sayfa")

    (istek,) = gorulen
    assert istek.url.host == "93.184.216.34"
    assert istek.headers["host"] == "ornek.example"
    assert istek.extensions["sni_hostname"] == "ornek.example"
    assert body == "tamam"
    assert final_url == "https://ornek.example/sayfa", "kullanıcıya özgün adres gösterilir"


def test_site_tasarimi_ic_ag_varligini_indirmez(monkeypatch, tmp_path):
    """Ölçülen sayfadaki `<img src>` metadata adresine ya da oraya yönlenen adrese gidemez."""
    from fusion_cli.tools import site_design

    baglanan: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        baglanan.append(request.url.host)
        if request.url.path == "/yonlen":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/token"})
        return httpx.Response(200, content=b"\x89PNG", headers={"content-type": "image/png"})

    monkeypatch.setattr(pinned_http, "direct_transport", lambda _h: httpx.MockTransport(handler))

    assert site_design._fetch("http://169.254.169.254/latest/meta-data/", tmp_path, 1000) is None
    assert site_design._fetch("https://93.184.216.34/yonlen", tmp_path, 1000) is None
    assert baglanan == ["93.184.216.34"]
    assert site_design._fetch("https://93.184.216.34/logo.png", tmp_path, 1000) is not None
    assert list(tmp_path.iterdir())
