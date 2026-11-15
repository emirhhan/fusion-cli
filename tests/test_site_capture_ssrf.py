"""Site yakalamada varlık indirmeleri iç ağ adreslerine gidemez (T2-12).

Ölçüldü (29 Ekim): `_download` ve `_blocked_css` Playwright `request.get` ile, adres
denetimi olmadan ve yönlendirme izleyerek indiriyordu; yerel sunucudaki bir "görsel"
proje klasörüne yazılıyordu (eski kodda yerel sunucu isteği aldı).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

from fusion_cli.tools import site_capture
from fusion_cli.tools.pinned_http import AsyncPinnedTransport


class _Yerel:
    """Dahili ağdaki hizmeti temsil eden yerel sunucu; gelen istekleri sayar."""

    def __init__(self) -> None:
        self.istekler: list[str] = []
        sahip = self

        class _Isleyici(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                sahip.istekler.append(self.path)
                govde = b"IC-AG-SIRRI" if self.path.endswith(".css") else b"\x89PNG-IC-AG"
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(govde)))
                self.end_headers()
                self.wfile.write(govde)

            def log_message(self, *_: object) -> None:
                return None

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Isleyici)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def kapat(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def yerel():
    sunucu = _Yerel()
    yield sunucu
    sunucu.kapat()


async def test_yerel_adresteki_gorsel_indirilmez(tmp_path, yerel):
    problemler: list[str] = []

    eslesme = await site_capture._download(
        [f"http://127.0.0.1:{yerel.port}/sizinti.png"], tmp_path, problemler
    )

    assert eslesme == {}
    assert yerel.istekler == []
    assert list(tmp_path.rglob("*.png")) == []
    assert any("iç ağ" in satir for satir in problemler)


async def test_yerel_adresteki_stil_dosyasi_indirilmez(yerel):
    problemler: list[str] = []

    css = await site_capture._blocked_css(
        [f"http://127.0.0.1:{yerel.port}/sizinti.css"], problemler
    )

    assert css == [] and yerel.istekler == []
    assert any("iç ağ" in satir for satir in problemler)


def _genel_istemci(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[[], httpx.AsyncClient]:
    """Genel IP'ye çözülen sahte alan adı + sahte taşıma (ağa çıkmaz)."""

    async def cozucu(_host: str) -> list[str]:
        return ["93.184.216.34"]

    def istemci() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            follow_redirects=True,
            transport=AsyncPinnedTransport(
                resolver=cozucu, transport_for=lambda _host: httpx.MockTransport(handler)
            ),
        )

    return istemci


async def test_genel_adresteki_gorsel_indirilir(tmp_path: Path, monkeypatch):
    govde = b"\x89PNG-GERCEK"
    monkeypatch.setattr(
        site_capture,
        "_public_client",
        _genel_istemci(
            lambda _istek: httpx.Response(200, content=govde, headers={"content-type": "image/png"})
        ),
    )
    problemler: list[str] = []

    eslesme = await site_capture._download(["https://cdn.ornek.test/a.png"], tmp_path, problemler)

    assert list(eslesme) == ["https://cdn.ornek.test/a.png"]
    assert (tmp_path / next(iter(eslesme.values()))).read_bytes() == govde
    assert problemler == []


async def test_genel_adresten_ic_agda_yonlendirme_engellenir(tmp_path: Path, monkeypatch, yerel):
    hedef = f"http://127.0.0.1:{yerel.port}/gizli.png"
    monkeypatch.setattr(
        site_capture,
        "_public_client",
        _genel_istemci(lambda _istek: httpx.Response(302, headers={"location": hedef})),
    )
    problemler: list[str] = []

    eslesme = await site_capture._download(["https://cdn.ornek.test/a.png"], tmp_path, problemler)

    assert eslesme == {} and yerel.istekler == []
    assert any("iç ağ" in satir for satir in problemler)


# --- Dalga 4 (T2-34) --------------------------------------------------------------------


async def test_yerel_yazma_hatasi_tum_yakalamayi_dusurmez(tmp_path, monkeypatch):
    """Çok uzun dosya adı `OSError` verip `gather` ile bütün varlık indirmesini düşürüyordu."""
    from fusion_cli.tools import site_capture as sc

    class _Yanit:
        ok = True
        body = b"x"
        content_type = "image/png"

    async def _fetch(client, url, limit):
        return _Yanit()

    monkeypatch.setattr(sc, "_fetch_public", _fetch)
    cagri = {"n": 0}
    gercek = sc.asset_local_path

    def _yol(url):
        cagri["n"] += 1
        return "a" * 400 + ".png" if cagri["n"] == 1 else gercek(url)

    monkeypatch.setattr(sc, "asset_local_path", _yol)
    problems: list[str] = []

    eslesme = await sc._download(
        ["https://x.test/bir.png", "https://x.test/iki.png"], tmp_path, problems
    )

    assert len(eslesme) == 1
    assert any("yazılamadı" in p for p in problems)
