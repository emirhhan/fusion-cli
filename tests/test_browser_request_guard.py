"""Tarayıcı araçlarında yönlendirme ve alt kaynak istekleri de adres kapısından geçer (T1-07).

Gerçek Chromium kullanılır: sahte sayfa `route` davranışını ölçemez. İzinli bir
yerel sunucu (A) izinsiz bir yerel sunucuya (B) yönlendirir ya da B'den alt kaynak
ister; B'ye hiçbir istek ulaşmamalıdır.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import browser

pytest.importorskip("playwright.async_api")


class _Sunucu:
    def __init__(self, yanitlar: dict[str, tuple[int, dict[str, str], bytes]]) -> None:
        self.istekler: list[str] = []
        sunucu = self

        class _Isleyici(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                sunucu.istekler.append(self.path)
                kod, basliklar, govde = yanitlar.get(self.path, (404, {}, b""))
                self.send_response(kod)
                for ad, deger in basliklar.items():
                    self.send_header(ad, deger)
                self.send_header("Content-Length", str(len(govde)))
                self.end_headers()
                self.wfile.write(govde)

            def log_message(self, *_: object) -> None:
                return None

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Isleyici)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @property
    def origin(self) -> str:
        return f"127.0.0.1:{self.port}"

    def kapat(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


@contextmanager
def _sunucular(
    hedef_yaniti: dict[str, tuple[int, dict[str, str], bytes]],
    kaynak_yaniti: Callable[[int], dict[str, tuple[int, dict[str, str], bytes]]],
) -> Iterator[tuple[_Sunucu, _Sunucu]]:
    hedef = _Sunucu(hedef_yaniti)
    kaynak = _Sunucu(kaynak_yaniti(hedef.port))
    try:
        yield hedef, kaynak
    finally:
        hedef.kapat()
        kaynak.kapat()


_GIZLI = (200, {"Content-Type": "text/html"}, b"<html><body>IC-AG-SIRRI</body></html>")


async def test_yonlendirme_izinsiz_yerel_adrese_gidemez(tmp_path):
    with _sunucular(
        {"/gizli": _GIZLI},
        lambda port: {"/": (302, {"Location": f"http://127.0.0.1:{port}/gizli"}, b"")},
    ) as (hedef, kaynak):
        context = ToolContext(root=tmp_path)
        context.local_origins.add(kaynak.origin)
        try:
            sonuc = await browser.browser_open({"url": f"http://{kaynak.origin}/"}, context)
        finally:
            await context.browser.close()

    assert hedef.istekler == [], "yönlendirme izinsiz yerel sunucuya ulaştı"
    assert "IC-AG-SIRRI" not in sonuc.output
    assert not sonuc.ok


async def test_alt_kaynak_izinsiz_yerel_adresten_yuklenmez(tmp_path):
    sayfa = b"""<html><body>ANA<script>
      fetch('http://127.0.0.1:%PORT%/gizli').then(r => r.text())
        .then(t => { document.body.append('SIZDI:' + t); }).catch(() => {});
      </script><img src="http://127.0.0.1:%PORT%/gizli.png"></body></html>"""
    with _sunucular(
        {"/gizli": _GIZLI, "/gizli.png": _GIZLI},
        lambda port: {
            "/": (200, {"Content-Type": "text/html"}, sayfa.replace(b"%PORT%", str(port).encode()))
        },
    ) as (hedef, kaynak):
        context = ToolContext(root=tmp_path)
        context.local_origins.add(kaynak.origin)
        try:
            sonuc = await browser.browser_open({"url": f"http://{kaynak.origin}/"}, context)
            await context.browser.page.wait_for_timeout(500)
        finally:
            await context.browser.close()

    assert sonuc.ok and "ANA" in sonuc.output
    assert hedef.istekler == [], "alt kaynak izinsiz yerel sunucuya ulaştı"


async def test_izinli_yerel_alt_kaynak_hala_yuklenir(tmp_path):
    with _sunucular(
        {},
        lambda _port: {
            "/": (200, {"Content-Type": "text/html"}, b"<html><body>TAMAM</body></html>")
        },
    ) as (_hedef, kaynak):
        context = ToolContext(root=tmp_path)
        context.local_origins.add(kaynak.origin)
        try:
            sonuc = await browser.browser_open({"url": f"http://{kaynak.origin}/"}, context)
        finally:
            await context.browser.close()

    assert sonuc.ok and "TAMAM" in sonuc.output
    assert kaynak.istekler == ["/"]


async def test_cok_adimli_zincirin_ikinci_halkasi_izinsizse_engellenir(tmp_path):
    with _sunucular(
        {"/gizli": _GIZLI},
        lambda port: {
            "/": (302, {"Location": "/ara"}, b""),
            "/ara": (302, {"Location": f"http://127.0.0.1:{port}/gizli"}, b""),
        },
    ) as (hedef, kaynak):
        context = ToolContext(root=tmp_path)
        context.local_origins.add(kaynak.origin)
        try:
            sonuc = await browser.browser_open({"url": f"http://{kaynak.origin}/"}, context)
        finally:
            await context.browser.close()

    assert hedef.istekler == []
    assert not sonuc.ok and "IC-AG-SIRRI" not in sonuc.output


async def test_izinli_yonlendirme_sayfaya_ulasir(tmp_path):
    with _sunucular(
        {},
        lambda _port: {
            "/": (302, {"Location": "/hedef"}, b""),
            "/hedef": (200, {"Content-Type": "text/html"}, b"<html><body>VARDI</body></html>"),
        },
    ) as (_hedef, kaynak):
        context = ToolContext(root=tmp_path)
        context.local_origins.add(kaynak.origin)
        try:
            sonuc = await browser.browser_open({"url": f"http://{kaynak.origin}/"}, context)
        finally:
            await context.browser.close()

    assert sonuc.ok and "VARDI" in sonuc.output and "/hedef" in sonuc.output
