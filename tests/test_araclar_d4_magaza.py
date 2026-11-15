"""Mağaza akışı güvenliği (T2-13)."""

from __future__ import annotations

import pytest

from fusion_cli.tools import shop_flow


@pytest.mark.parametrize(
    "adres",
    [
        "https://motogate.com.tr/urun/kask/",
        "http://192.168.1.20/urun/x/",
        "https://localhost.evil.example/urun/x/",
        "http://10.0.0.5:8080/",
        "ftp://127.0.0.1/x",
    ],
)
async def test_yerel_olmayan_adreste_siparis_denenmez(adres):
    """Canlı mağazaya sahte sipariş/müşteri kaydı düşmesin; RuntimeError çağıranı sessiz geçirir."""
    with pytest.raises(RuntimeError, match="yerel"):
        await shop_flow.cart_flow_problem(adres, None)


@pytest.mark.parametrize(
    "adres",
    ["http://127.0.0.1:8123/urun/x/", "http://localhost:8123/", "http://[::1]:8080/urun/a/"],
)
def test_yerel_adresler_kabul_edilir(adres):
    assert shop_flow.is_local_store_url(adres)


def test_bulten_tesekkur_penceresi_siparis_tamam_sayilmaz():
    assert not shop_flow._ORDER_DONE.search("Thank you for subscribing to our newsletter!")
    assert shop_flow._ORDER_DONE.search("Thank you. Your order has been received.")
    assert shop_flow._ORDER_DONE.search("https://x/checkout/order-received/12/")


# --- T2-35: woo_theme PHP enjeksiyonu ----------------------------------------

from fusion_cli.tools.woo_theme import wire_store_links  # noqa: E402


def test_kotu_niyetli_kategori_slugi_php_enjekte_edemez():
    """`'` içeren slug PHP tek tırnaklı dizeyi kapatıp kod enjekte edebilirdi."""
    html = '<a href="/yeni-urunler">Yeni</a>'

    cikti = wire_store_links(html, ("x' ); system('id'); //", "motor-kasklari"))

    assert "system(" not in cikti
    assert "'id'" not in cikti


def test_gecerli_kategori_slugi_baglanir():
    cikti = wire_store_links('<a href="/kasklar">K</a>', ("kasklar",))

    assert "?product_cat=kasklar" in cikti
