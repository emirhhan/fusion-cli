"""Önizlemedeki mağazada gerçek alışveriş denemesi: ürünü sepete ekle, sepette gör.

Ölçüldü (3 Ekim 2026, 17. kabul koşusu): model ürün sayfasına kendi "SEPETE EKLE"
düğmesini yazdı ama düğme bir `<form>` içinde değildi; tıklayınca hiçbir şey olmuyordu.
Sayfa ölçümü (başlık, fiyat, düğme var mı) bunu göremez; yalnız düğmeye BASIP sepete
bakmak görür. Kullanıcının istediği "gerçek çalışan e-ticaret sitesi" bu denemeyle ölçülür.
"""

from __future__ import annotations

import contextlib
from typing import Any

#: Bir adımın (sayfa açma, tıklama sonrası bekleme) azami süresi.
STEP_TIMEOUT_MS = 15_000
#: Tıklamadan sonra isteklerin bitmesi için azami bekleme.
SETTLE_TIMEOUT_MS = 5_000

_BUY_TEXT = r"sepete ekle|add to (cart|bag|basket)|satın al|buy now"
#: Dolu sepet işaretleri: klasik WooCommerce, blok sepeti, genel kalıplar.
_CART_ITEMS = (
    ".cart_item, .wc-block-cart-items__row, .woocommerce-cart-form__cart-item, [data-cart-item]"
)

#: Ürün sayfasında seçenek seç ve sepete ekle düğmesini bul; düğme hakkında ipucu döndür.
_PREPARE = """(pattern) => {
  const re = new RegExp(pattern, "i");
  const shown = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  for (const select of document.querySelectorAll("form select")) {
    const option = [...select.options].find((o) => o.value && !o.disabled);
    if (option) {
      select.value = option.value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }
  const visible = (el) => {
    const s = getComputedStyle(el);
    return s.visibility !== "hidden" && s.display !== "none" && parseFloat(s.opacity) > 0.05;
  };
  const label = (el) => (el.innerText || el.textContent || el.value || "").trim();
  const matches = [...document.querySelectorAll("button, input[type=submit], a, [role=button]")]
    .filter((el) => re.test(label(el)));
  const button = matches.filter(shown).find(visible);
  if (!button) {
    const hidden = matches.find((el) => el.closest("form"));
    return hidden ? { hidden: true, text: label(hidden).slice(0, 40) } : null;
  }
  button.setAttribute("data-fusion-buy", "1");
  return {
    text: (button.innerText || button.value || "").trim().slice(0, 40),
    inForm: !!button.closest("form") || !!button.getAttribute("form"),
    submit: button.tagName === "BUTTON" ? (button.type || "submit") === "submit" : false,
    href: button.tagName === "A" ? button.getAttribute("href") || "" : "",
  };
}"""


async def cart_flow_problem(product_url: str, cart_url: str) -> str | None:
    """Ürünü sepete eklemeyi dene; çalışmıyorsa nedeniyle birlikte sorun metni döndür.

    Tarayıcı açılamazsa `RuntimeError` yükselir (çağıran sessizce geçebilir).
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as driver:
        try:
            browser = await driver.chromium.launch()
        except Exception as exc:
            raise RuntimeError(f"tarayıcı açılamadı: {exc}") from exc
        try:
            page = await browser.new_page()
            requests: list[str] = []
            page.on("request", lambda r: requests.append(r.method) if r.method != "GET" else None)
            await page.goto(product_url, timeout=STEP_TIMEOUT_MS, wait_until="load")
            button = await page.evaluate(_PREPARE, _BUY_TEXT)
            if button is None:
                return (
                    f"SEPETE EKLEME: ürün sayfasında ({product_url}) 'sepete ekle' düğmesi yok. "
                    "Ürün şablonunda WooCommerce'in `woocommerce_template_single_add_to_cart()` "
                    "çıktısını (form + düğme) kullan."
                )
            if button.get("hidden"):
                return (
                    f"SEPETE EKLEME ÇALIŞMIYOR: ürün sayfasında ({product_url}) "
                    f"'{button.get('text', '')}' düğmesi var ama görünmüyor (visibility/opacity/"
                    "display ile gizli); müşteri basamaz. Bir CSS kuralı onu gizliyor — çoğu "
                    "zaman ürün ızgarası için yazılmış geniş bir seçici (ör. `.product .button`). "
                    "Seçiciyi ızgaraya daralt ve düğmeyi görünür yap."
                )
            await page.click("[data-fusion-buy]", timeout=STEP_TIMEOUT_MS)
            with contextlib.suppress(Exception):
                await page.wait_for_load_state("networkidle", timeout=SETTLE_TIMEOUT_MS)
            await page.goto(cart_url, timeout=STEP_TIMEOUT_MS, wait_until="load")
            with contextlib.suppress(Exception):
                await page.wait_for_load_state("networkidle", timeout=SETTLE_TIMEOUT_MS)
            if await page.locator(_CART_ITEMS).count():
                return None
            return _failure(product_url, cart_url, button, sent=bool(requests))
        finally:
            await browser.close()


def _failure(product_url: str, cart_url: str, button: dict[str, Any], *, sent: bool) -> str:
    reasons: list[str] = []
    if button.get("submit") and not button.get("inForm"):
        reasons.append(
            f"'{button.get('text')}' düğmesi type=submit ama bir form içinde değil; tıklamak "
            "hiçbir şey göndermiyor"
        )
    if not sent and not button.get("href"):
        reasons.append("tıklayınca sunucuya hiç istek gitmedi")
    neden = ("; ".join(reasons) + ". ") if reasons else ""
    return (
        f"SEPETE EKLEME ÇALIŞMIYOR: {product_url} sayfasında seçenek seçilip "
        f"'{button.get('text')}' tıklandı, ama sepet ({cart_url}) boş kaldı. {neden}"
        "Ürün şablonunda WooCommerce'in kendi formunu "
        "(`woocommerce_template_single_add_to_cart()`) kullan ya da düğmeyi "
        "`<form class='cart' method='post'>` içine al."
    )
