"""Ödeme sayfasında kapıda ödemeyle test siparişi verme denemesi.

Klasik (`form.checkout`, `#billing_*`) ve blok tabanlı (`.wc-block-checkout`)
ödeme sayfalarını tanır. Siparişin gerçekten oluşup oluşmadığına bu modül değil,
denetçi WP-CLI ile sipariş sayısına bakarak karar verir; burada yalnız formun
varlığı ölçülür ve deneme notu döner.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from evals.kabul.model import Check

if TYPE_CHECKING:
    from playwright.sync_api import Page

#: Test siparişinin alanları; gerçek kişi verisi değildir.
BILLING = {
    "first_name": "Deneme",
    "last_name": "Kullanıcı",
    "address_1": "Deneme Sokak 1",
    "city": "İstanbul",
    "postcode": "34000",
    "phone": "05550000000",
    "email": "deneme@ornek.test",
}
CLASSIC_FORM = "form.checkout"
BLOCK_FORM = ".wc-block-checkout"
COD_INPUTS = "#payment_method_cod, input[value=cod]"
PLACE_ORDER = "#place_order, .wc-block-components-checkout-place-order-button"
ORDER_SETTLE_MS = 8_000


def _fill_classic(sayfa: Page) -> None:
    for alan, deger in BILLING.items():
        kutu = sayfa.locator(f"#billing_{alan}")
        if kutu.count() and kutu.first.is_visible():
            kutu.first.fill(deger)


def _fill_block(sayfa: Page) -> None:
    for alan, deger in BILLING.items():
        kutu = sayfa.locator(f"#billing-{alan}, #shipping-{alan}, #{alan}")
        if kutu.count() and kutu.first.is_visible():
            kutu.first.fill(deger)


def place_order(sayfa: Page, checkout_url: str, timeout_ms: int) -> tuple[Check, str]:
    """Formu doldur, kapıda ödemeyi seç, siparişi ver. (madde, deneme notu) döner."""
    from playwright.sync_api import Error as PlaywrightError

    if not checkout_url:
        return Check("odeme_formu_var", False, "ödeme sayfası tanımlı değil"), "deneme yok"
    try:
        sayfa.goto(checkout_url, timeout=timeout_ms)
        klasik = sayfa.locator(CLASSIC_FORM).count() > 0
        blok = sayfa.locator(BLOCK_FORM).count() > 0
        madde = Check(
            "odeme_formu_var",
            klasik or blok,
            "klasik form" if klasik else ("blok form" if blok else "form yok"),
        )
        if not (klasik or blok):
            return madde, "form olmadığı için sipariş denenmedi"
        _fill_classic(sayfa) if klasik else _fill_block(sayfa)
        kapida = sayfa.locator(COD_INPUTS)
        if kapida.count():
            kapida.first.check(force=True)
        sayfa.locator(PLACE_ORDER).first.click()
        sayfa.wait_for_timeout(ORDER_SETTLE_MS)
        return madde, f"sipariş düğmesine basıldı, son adres {sayfa.url}"
    except PlaywrightError as hata:
        return Check("odeme_formu_var", False, f"akış kırıldı: {str(hata)[:160]}"), "hata"
