"""Ekrandaki skor/can yazısı oyun durumuyla uyuşuyor mu; oyun sonunda yeniden başlat çalışıyor mu?

Ölçüldü (10 Ekim 2026, dalga47 HTML oyun): oyuncu hiç oynamayınca oyun 8,2 sn'de bitti;
R'ye basınca `__GAME_STATE__` can=3'e döndü ama ekrandaki DOM yazısı "Can: 0" kaldı.
Sonda R'ye yalnız oyun ortasında basıyordu (orada R çalışmıyor, bu tasarım geçerli);
oyun sonu hiç denenmediği için kusur kapıdan geçti, kabulde yakalandı.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.async_api import Page

#: Görünür yaprak öğelerdeki "Can: 3", "Skor 120", "Lives: 2" gibi sayılı HUD yazıları.
_HUD_NUMBERS = """() => [...document.querySelectorAll('body *')].filter((el) => {
  if (el.children.length) return false; const r = el.getBoundingClientRect();
  const s = getComputedStyle(el); return r.width > 0 && r.height > 0 &&
    s.visibility !== 'hidden' && parseFloat(s.opacity) > 0.05; })
  .map((el) => (el.textContent || '').trim()).filter((t) => t.length <= 40)"""
_HUD_PATTERN = re.compile(
    r"\b(can|canlar|lives|life|hp|skor|score|puan)\b\s*[:=]?\s*(-?\d+)", re.IGNORECASE
)
#: HUD etiketi → `__GAME_STATE__` içinde aranacak anahtarlar.
_STATE_KEYS = {
    "can": ("can", "lives", "life", "hp"),
    "skor": ("skor", "score", "puan"),
}
_LABELS = {
    "can": "can",
    "canlar": "can",
    "lives": "can",
    "life": "can",
    "hp": "can",
    "skor": "skor",
    "score": "skor",
    "puan": "skor",
}
#: HUD bir kare geride kalabilir; uyuşmazlık iki okumada da sürerse kusurdur (ms).
HUD_RECHECK_MS = 300
#: Oyuncu hiç oynamazken oyunun kendiliğinden bitmesi için beklenen üst sınır (ms).
#: Ölçüldü: dalga47 8,2 sn'de bitti; kabul denetçisi 90 sn bekliyor. Kapanış kapısı
#: her turda koştuğu için daha kısa tutuldu; bitmeyen oyun kusur değil, "ölçülemedi"dir.
END_WAIT_MS = 45_000
END_POLL_MS = 500
RESTART_SETTLE_MS = 700
_END_STATE = re.compile(r"over|bitti|bit\b|son\b|dead|lost|kaybet", re.IGNORECASE)
_RESTART_BUTTON = re.compile(r"yeniden|restart|tekrar|again|replay|baştan|retry", re.IGNORECASE)


def hud_numbers(texts: list[str]) -> dict[str, int]:
    """HUD yazılarından etiket → sayı (aynı etiketin ilk görüneni)."""
    sayilar: dict[str, int] = {}
    for yazi in texts:
        for eslesme in _HUD_PATTERN.finditer(yazi):
            sayilar.setdefault(_LABELS[eslesme.group(1).lower()], int(eslesme.group(2)))
    return sayilar


def _state_number(state: dict[str, Any], label: str) -> int | None:
    for anahtar in _STATE_KEYS[label]:
        deger = state.get(anahtar)
        if isinstance(deger, bool):
            continue
        if isinstance(deger, (int, float)):
            return int(deger)
    return None


#: Oyun sürerken yalnız can karşılaştırılır: skor yazısı çoğu oyunda sayarak artar
#: (animasyon), anlık fark kusur değildir. Yeniden başlatmada ikisi de sıfırlanmalı.
PLAYING_LABELS = ("can",)
ALL_LABELS = ("can", "skor")


def hud_mismatches(
    texts: list[str], state_json: str | None, labels: tuple[str, ...] = ALL_LABELS
) -> tuple[str, ...]:
    """Ekrandaki sayı ile durumdaki sayı farklıysa kusur cümleleri."""
    if not state_json:
        return ()
    try:
        durum = json.loads(state_json)
    except ValueError:
        return ()
    if not isinstance(durum, dict):
        return ()
    sorunlar = []
    for etiket, ekranda in hud_numbers(texts).items():
        if etiket not in labels:
            continue
        gercek = _state_number(durum, etiket)
        if gercek is not None and gercek != ekranda:
            sorunlar.append(
                f"ekranda '{etiket}: {ekranda}' yazıyor ama oyun durumunda {etiket}={gercek} "
                "(HUD yazısı durumla birlikte güncellenmiyor)"
            )
    return tuple(sorunlar)


async def read_hud_mismatches(
    page: Page, state_script: str, labels: tuple[str, ...] = ALL_LABELS
) -> tuple[str, ...]:
    """İki okumada da süren uyuşmazlık (tek kare gecikme kusur sayılmaz)."""
    for deneme in range(2):
        if deneme:
            await page.wait_for_timeout(HUD_RECHECK_MS)
        yazilar = await page.evaluate(_HUD_NUMBERS)
        sorunlar = hud_mismatches(yazilar, await page.evaluate(state_script), labels)
        if not sorunlar:
            return ()
    return sorunlar


def _ended(state_json: str | None) -> bool:
    if not state_json:
        return False
    try:
        durum = json.loads(state_json)
    except ValueError:
        return False
    if not isinstance(durum, dict):
        return False
    deger = durum.get("durum", durum.get("state", durum.get("mode")))
    return isinstance(deger, str) and bool(_END_STATE.search(deger))


async def restart_after_end(page: Page, state_script: str) -> tuple[str, ...]:
    """Oyunu kendiliğinden bitmeye bırak, R / Yeniden Başla ile başlat, sonucu ölç.

    Durum kancası yoksa ya da oyun süre içinde bitmezse ölçülemedi: boş döner.
    """
    gecen = 0
    while not _ended(await page.evaluate(state_script)):
        if gecen >= END_WAIT_MS:
            return ()
        await page.wait_for_timeout(END_POLL_MS)
        gecen += END_POLL_MS
    await page.keyboard.press("r")
    await page.wait_for_timeout(RESTART_SETTLE_MS)
    if _ended(await page.evaluate(state_script)):
        dugme = page.get_by_role("button", name=_RESTART_BUTTON)
        if await dugme.count() and await dugme.first.is_visible():
            await dugme.first.click()
            await page.wait_for_timeout(RESTART_SETTLE_MS)
    if _ended(await page.evaluate(state_script)):
        return ("oyun bittikten sonra R tuşu ve 'Yeniden başla' düğmesi oyunu başlatmadı",)
    return tuple(
        f"yeniden başlattıktan sonra {sorun}"
        for sorun in await read_hud_mismatches(page, state_script)
    )
