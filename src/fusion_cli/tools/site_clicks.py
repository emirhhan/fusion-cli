"""Tıklamayla içerik değiştiren sekmeleri betiksiz kopyaya donmuş haller olarak taşı.

Ölçüldü (10 Ekim 2026, sneaksup.com): ana sayfadaki ürün şeritlerinin üstünde
"Kadın / Erkek / Çocuk" sekmeleri var; düz `<span>`lar, React tıklamayla şeridin
ürünlerini değiştiriyor. Kopya yalnız ilk hali taşıyordu, sekmeler ölüydü.

Yakalamada her sekmeye bir kez tıklanır, değişen öğelerin ortak atası (bölüm) bulunur
ve her hal o bölümün gizli bir kopyası olarak sayfaya eklenir. Kopyalar yerleşimi
korunmuş biçimde (ekran dışında) durur ki kopyalama betiği slayt genişliklerini onlarda
da dondurabilsin. Kopyada küçük yerel betik (`clone_interactions.js`) tıklanan sekmenin
halini gösterir; aynı betik kaydırıcı oklarını da yerel olarak kaydırır.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.async_api import Page

_LOG = logging.getLogger(__name__)

CLICK_SCRIPT = Path(__file__).with_name("assets") / "click_states.js"
#: Kopyada sekme/ok davranışını kuran yerel betik.
INTERACTIONS_RUNTIME = Path(__file__).with_name("assets") / "clone_interactions.js"
#: Sekmeye tıklayınca içeriğin (ve görsellerin) değişmesi için bekleme. sneaksup'ta
#: ürün görselleri 1,5 sn içinde yerine oturdu.
CLICK_WAIT_MS = 1_500
#: Kapalı haller görünmez; açılan kopya yerleşimini `data-kopya-stil`den geri alır.
CLICK_STATE_CSS = "[data-kopya-durum]:not([data-kopya-acik]){display:none!important}"


async def _click(page: Page, tab_id: str) -> None:
    await page.locator(f'[data-kopya-sekme="{tab_id}"]').first.click(timeout=5_000)
    await page.wait_for_timeout(CLICK_WAIT_MS)


async def _call(page: Page, script: str, *args: object) -> list[dict[str, Any]] | int | None:
    sonuc = await page.evaluate(script, list(args))
    return sonuc if isinstance(sonuc, (list, int)) or sonuc is None else None


async def capture_click_states(page: Page) -> tuple[str, ...]:
    """Sekme gruplarının hallerini dondur; yakalanan grupların etiketlerini döndür.

    Tıklama başarısız olursa (öğe örtülü, sayfa yönlendi) o grup atlanır; sayfa ilk
    sekmenin halinde bırakılır.
    """
    script = CLICK_SCRIPT.read_text(encoding="utf-8")
    yakalanan: list[str] = []
    gruplar = await _call(page, script, "groups", "", 0)
    for grup in gruplar if isinstance(gruplar, list) else []:
        kimlik, etiketler = str(grup["id"]), list(grup["labels"])
        try:
            if not await _freeze_group(page, script, kimlik, len(etiketler)):
                continue
        except Exception:  # sınır: kaynak sayfa tıklamada hata verdi ya da yönlendi
            _LOG.warning("Sekme grubu yakalanamadı: %s", etiketler, exc_info=True)
            continue
        yakalanan.append(" / ".join(etiketler))
    return tuple(yakalanan)


async def _freeze_group(page: Page, script: str, group: str, count: int) -> bool:
    # Önce bütün sekmeleri gez: bölüm kökü her halin değişen öğelerini kapsamalı.
    degisti = False
    for sira in range(1, count):
        await _call(page, script, "snapshot", group, sira)
        await _click(page, f"{group}-{sira}")
        degisti = bool(await _call(page, script, "diff", group, sira)) or degisti
    if not degisti:
        await _click(page, f"{group}-0")
        return False
    for sira in range(1, count):
        await _click(page, f"{group}-{sira}")
        await _call(page, script, "freeze", group, sira)
    await _click(page, f"{group}-0")
    await _call(page, script, "finish", group, 0)
    # Başlık ofseti sayfanın tepesinde ölçülür; tıklama sayfayı kaydırmış olabilir.
    await page.evaluate("window.scrollTo(0, 0)")
    return True
