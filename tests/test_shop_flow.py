"""Önizlemede gerçek alışveriş denemesi: ürünü sepete ekle, sepette gör (`shop_flow`).

Ölçüldü (3 Ekim 2026, 17. kabul koşusu): ürün sayfasındaki "SEPETE EKLE" düğmesi bir
`<form>` içinde değildi; tıklayınca hiçbir şey olmuyordu ve hiçbir ölçüm bunu söylemedi.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import pytest

from fusion_cli.tools.shop_flow import cart_flow_problem

_OLU_DUGME = (
    "<h1>Ayakkabı</h1><span class='price'>₺100</span>"
    "<button type='submit' name='add-to-cart' value='7'>SEPETE EKLE</button>"
)
_FORMLU_DUGME = (
    "<h1>Ayakkabı</h1><form method='post'><select name='beden'><option value=''>Seç</option>"
    "<option>42</option></select>"
    "<button type='submit' name='add-to-cart' value='7'>Sepete Ekle</button></form>"
)


class _Magaza(BaseHTTPRequestHandler):
    urun_govdesi = _OLU_DUGME
    sepette: ClassVar[list[str]] = []

    def log_message(self, *args: object) -> None:  # sessiz
        del args

    def _yaz(self, govde: str) -> None:
        veri = (
            f"<!doctype html><html><head><meta charset='utf-8'></head><body>{govde}</body></html>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(veri.encode())

    def do_GET(self) -> None:
        if self.path.startswith("/urun/"):
            self._yaz(self.urun_govdesi)
        elif self.path.startswith("/sepet/"):
            if self.sepette:
                self._yaz("<table><tr class='cart_item'><td>Ayakkabı</td></tr></table>")
            else:
                self._yaz("<p class='cart-empty'>Sepetiniz şu anda boş.</p>")
        else:
            self._yaz("<p>ana</p>")

    def do_POST(self) -> None:
        uzunluk = int(self.headers.get("Content-Length", 0))
        govde = self.rfile.read(uzunluk).decode()
        if "add-to-cart=7" in govde:
            self.sepette.append(govde)
        self._yaz(self.urun_govdesi)


@pytest.fixture
def magaza() -> Iterator[str]:
    _Magaza.sepette = []
    sunucu = ThreadingHTTPServer(("127.0.0.1", 0), _Magaza)
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{sunucu.server_address[1]}"
    finally:
        sunucu.shutdown()


async def _dene(adres: str) -> str | None:
    try:
        return await cart_flow_problem(f"{adres}/urun/a/", f"{adres}/sepet/")
    except RuntimeError as exc:  # pragma: no cover - tarayıcı ikilisi yoksa
        pytest.skip(str(exc))


async def test_form_disindaki_dugme_sepete_eklemez_ve_soylenir(magaza):
    _Magaza.urun_govdesi = _OLU_DUGME

    sorun = await _dene(magaza)

    assert sorun is not None
    assert "SEPETE EKLEME ÇALIŞMIYOR" in sorun
    assert "form içinde değil" in sorun


async def test_secenek_secilip_sepete_eklenen_urun_sepette_gorulur(magaza):
    _Magaza.urun_govdesi = _FORMLU_DUGME

    assert await _dene(magaza) is None
    assert _Magaza.sepette and "beden=42" in _Magaza.sepette[0]


async def test_urun_sayfasinda_sepete_ekle_dugmesi_yoksa_soylenir(magaza):
    _Magaza.urun_govdesi = "<h1>Ayakkabı</h1><p>Yalnız açıklama.</p>"

    sorun = await _dene(magaza)

    assert sorun is not None and "düğmesi yok" in sorun


async def test_css_ile_gizlenen_dugme_soylenir(magaza):
    """Ölçüldü (dalga20): ızgara için yazılan `.woocommerce .product .button {visibility:
    hidden}` ürün sayfasındaki asıl Sepete Ekle düğmesini de gizledi; kimse basamadı."""
    _Magaza.urun_govdesi = _FORMLU_DUGME.replace(
        "<button ", "<button style='visibility:hidden;opacity:0' "
    )

    sorun = await _dene(magaza)

    assert sorun is not None and "görünmüyor" in sorun
