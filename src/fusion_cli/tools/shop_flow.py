"""Önizlemedeki mağazada gerçek alışveriş denemesi: ürünü sepete ekle, sepette gör.

Ölçüldü (3 Ekim 2026, 17. kabul koşusu): model ürün sayfasına kendi "SEPETE EKLE"
düğmesini yazdı ama düğme bir `<form>` içinde değildi; tıklayınca hiçbir şey olmuyordu.
Sayfa ölçümü (başlık, fiyat, düğme var mı) bunu göremez; yalnız düğmeye BASIP sepete
bakmak görür. Kullanıcının istediği "gerçek çalışan e-ticaret sitesi" bu denemeyle ölçülür.
"""

from __future__ import annotations

import contextlib
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.async_api import Page

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
                return await _checkout_problem(page, cart_url)
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


#: Sepetten ödemeye geçiş: WooCommerce düğmesi ya da ödeme sayfasına giden bağlantı.
_CHECKOUT_LINK = """() => {
  const re = /ödeme|odeme|checkout|siparişi tamamla|satın al/i;
  const link = [...document.querySelectorAll("a[href]")].find(
    (a) => a.classList.contains("checkout-button") || /\\/(checkout|odeme)\\/?$/.test(
      new URL(a.href, location.href).pathname) || (re.test(a.innerText || "") &&
      !/sepet|cart/i.test(a.innerText || ""))
  );
  return link ? link.href : null;
}"""
#: Ödeme sayfasındaki etkin ödeme yöntemleri (klasik ve blok ödeme).
_PAYMENT_METHODS = (
    "input[name=payment_method], input[name^=radio-control-wc-payment-method], "
    ".wc-block-components-radio-control__input, "
    ".wc-block-checkout__payment-method input[type=radio]"
)
#: Ödeme formunu test bilgileriyle doldurur: görünür ve boş alanlar türlerine göre.
_FILL_CHECKOUT = """() => {
  const shown = (el) => {
    const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden";
  };
  const set = (el, value) => {
    const proto = Object.getPrototypeOf(el);
    const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
    setter ? setter.call(el, value) : (el.value = value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  };
  for (const el of document.querySelectorAll("form input, form select, form textarea")) {
    if (el.type === "hidden" || el.disabled) continue;
    if (el.type === "checkbox") {
      if (el.required || /terms|kosul|sozlesme/i.test(el.name || el.id)) el.checked = true;
      continue;
    }
    if (el.type === "radio") continue;
    if (el.value || !shown(el)) continue;
    if (el.tagName === "SELECT") {
      const o = [...el.options].find((o) => o.value && !o.disabled);
      if (o) set(el, o.value);
      continue;
    }
    const key = `${el.type} ${el.name} ${el.id} ${el.autocomplete}`.toLowerCase();
    const value = /email/.test(key) ? "test@example.com"
      : /tel|phone/.test(key) ? "5550000000"
      : /post|zip/.test(key) ? "34000"
      : "Test";
    set(el, value);
  }
  const methods = "input[name=payment_method], input[name^=radio-control-wc-payment-method]";
  const radio = document.querySelector(methods);
  if (radio && ![...document.querySelectorAll(methods)].some((r) => r.checked)) radio.click();
}"""
_PLACE_ORDER = (
    "#place_order, .wc-block-components-checkout-place-order-button, "
    "form.checkout button[type=submit]"
)
_ORDER_DONE = re.compile(r"order-received|siparis-alindi|sipariş(iniz)? alındı|thank you", re.I)
_ERRORS = (
    ".woocommerce-error, .woocommerce-NoticeGroup-checkout, "
    ".wc-block-components-notice-banner.is-error"
)


async def _checkout_problem(page: Page, cart_url: str) -> str | None:
    """Sepetten ödemeye geç, ödeme yöntemine bak, test siparişi ver.

    Ölçüldü (5-6 Ekim, dalga20-21): sepet çalıştığında bile ödeme yöntemi yoktu ya da
    sipariş düğmesine basılamıyordu; deneme sepette durduğu için model bunu hiç görmedi.
    Yerel önizleme veritabanına bir test siparişi yazılır (gerçek ödeme yok).
    """
    checkout = await page.evaluate(_CHECKOUT_LINK)
    if checkout is None:
        return (
            f"ÖDEMEYE GEÇİŞ YOK: sepette ({cart_url}) ödeme sayfasına giden düğme/bağlantı yok. "
            "Sepet şablonunda WooCommerce'in `woocommerce_proceed_to_checkout()` çıktısını kullan."
        )
    await page.goto(checkout, timeout=STEP_TIMEOUT_MS, wait_until="load")
    with contextlib.suppress(Exception):
        await page.wait_for_load_state("networkidle", timeout=SETTLE_TIMEOUT_MS)
    # Blok ödeme sayfası yöntemleri JavaScript'le sonradan çizer (ölçüldü: networkidle
    # sonrası bile yoktu); kısa süre beklenir.
    with contextlib.suppress(Exception):
        await page.wait_for_selector(_PAYMENT_METHODS, state="attached", timeout=SETTLE_TIMEOUT_MS)
    if not await page.locator(_PAYMENT_METHODS).count():
        return (
            f"ÖDEME YÖNTEMİ YOK: ödeme sayfasında ({checkout}) seçilebilir ödeme yöntemi yok; "
            "müşteri sipariş veremez. En az bir yöntemi etkinleştir, ör. kapıda ödeme: "
            '`wp option update woocommerce_cod_settings \'{"enabled":"yes","title":'
            '"Kapıda ödeme"}\' --format=json`.'
        )
    await page.evaluate(_FILL_CHECKOUT)
    button = page.locator(_PLACE_ORDER).first
    if not await button.count():
        return f"SİPARİŞ OLUŞMADI: ödeme sayfasında ({checkout}) sipariş düğmesi yok."
    if not await button.is_visible():
        return (
            f"SİPARİŞ OLUŞMADI: ödeme sayfasında ({checkout}) sipariş düğmesi var ama "
            "görünmüyor (CSS ile gizli); müşteri basamaz."
        )
    try:
        await button.click(timeout=STEP_TIMEOUT_MS)
        with contextlib.suppress(Exception):
            await page.wait_for_url(_ORDER_DONE, timeout=STEP_TIMEOUT_MS)
    except Exception as exc:
        return f"SİPARİŞ OLUŞMADI: sipariş düğmesine basılamadı ({str(exc).splitlines()[0]})."
    if _ORDER_DONE.search(page.url) or _ORDER_DONE.search(await page.inner_text("body")):
        return None
    hatalar = " ".join((await page.locator(_ERRORS).all_inner_texts()) or [])
    hata = " ".join(hatalar.split())[:300] or "sayfada hata mesajı yok"
    return (
        f"SİPARİŞ OLUŞMADI: test bilgileriyle {checkout} formu gönderildi ama sipariş "
        f"onay sayfasına gidilmedi (son adres {page.url}). Sayfanın dediği: {hata}"
    )
