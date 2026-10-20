"""Tarayıcı araçlarında hedef öğe: seçiciyi çöz, belirsizliği reddet, öğeyi tanımla.

Ölçüldü (4 Ekim 2026, tarayıcı kabul koşusu, 53 araç çağrısı):

- Model `a:contains("Ürün tablosu")` gibi jQuery yazımı kullandı; Playwright bunu
  tanımaz ve dokuz çağrı "öğe bulunamadı" ile düştü.
- `browser_type` seçim kutusuna (`<select>`) yazamadı; model yedi kez denedi, sonunda
  `input` seçicisine yazdı. Seçici sayfadaki iki kutuya uyuyordu, araç SESSİZCE ilkini
  seçti ve zaten doldurulmuş "Ad" alanının üzerine "Destek" yazdı. Form yanlış
  değerlerle gönderildi, model "gönderildi" dedi.

Buradaki kurallar siteden bağımsızdır: seçici birden çok görünür öğeye uyuyorsa işlem
yapılmaz, adaylar kesin seçicileriyle listelenir; seçim kutusuna yazmak seçenek seçer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

#: Belirsizlik bildiriminde listelenecek en fazla aday.
MAX_CANDIDATES = 6
#: Adayın görünür metninden alınacak en fazla karakter.
MAX_LABEL_CHARS = 40

#: jQuery `:contains(...)` → Playwright `:has-text(...)` (tırnaklı ya da tırnaksız).
_CONTAINS = re.compile(r""":contains\(\s*(?:"([^"]*)"|'([^']*)'|([^)]*?))\s*\)""")


class TargetError(Exception):
    """Hedef öğe çözülemedi; mesaj modele olduğu gibi gider."""


@dataclass(frozen=True, slots=True)
class Target:
    """Çözülmüş tek hedef: Playwright locator'ı ve insan-okunur tanımı."""

    locator: Any
    description: str
    tag: str


def normalize_selector(selector: str) -> str:
    """Modellerin sık kullandığı jQuery yazımını Playwright karşılığına çevir."""

    def degistir(match: re.Match[str]) -> str:
        metin = next(grup for grup in match.groups() if grup is not None).strip()
        return ':has-text("' + metin.replace('"', '\\"') + '")'

    return _CONTAINS.sub(degistir, selector)


#: Sayfada çalışır: öğeyi kısa ve TEKRAR KULLANILABİLİR bir seçiciyle tanımla.
_DESCRIBE_JS = """(e) => {
    const tag = e.tagName.toLowerCase();
    const attr = (name) => e.getAttribute(name);
    const quote = (v) => '"' + v.replace(/"/g, '\\\\"') + '"';
    let selector = tag;
    if (e.id) selector = tag + '#' + CSS.escape(e.id);
    else if (attr('name')) selector = tag + '[name=' + quote(attr('name')) + ']';
    else if (attr('aria-label'))
        selector = tag + '[aria-label=' + quote(attr('aria-label')) + ']';
    else if (attr('placeholder'))
        selector = tag + '[placeholder=' + quote(attr('placeholder')) + ']';
    else {
        const text = (e.innerText || e.value || '').trim().replace(/\\s+/g, ' ')
            .slice(0, MAX_LABEL);
        if (text) selector = tag + ':has-text(' + quote(text) + ')';
        else if (attr('href')) selector = tag + '[href=' + quote(attr('href')) + ']';
    }
    return {selector, tag};
}""".replace("MAX_LABEL", str(MAX_LABEL_CHARS))


async def _visible(locator: Any) -> list[Any]:  # noqa: ANN401 - Playwright tipi opsiyonel
    sayi = int(await locator.count())
    gorunur = []
    for sira in range(sayi):
        oge = locator.nth(sira)
        if await oge.is_visible():
            gorunur.append(oge)
    return gorunur


async def resolve(page: Any, selector: str, timeout_ms: int) -> Target:  # noqa: ANN401
    """Seçiciyi tek bir görünür öğeye çöz; yoksa ya da belirsizse `TargetError`."""
    cozulmus = normalize_selector(selector)
    locator = page.locator(cozulmus)
    try:
        await locator.first.wait_for(state="visible", timeout=timeout_ms)
    except Exception as exc:
        raise TargetError(
            f"Öğe bulunamadı: {selector} ({type(exc).__name__}). browser_read ile sayfanın "
            "güncel halini oku ve seçiciyi ORADAN doğrula; seçici uydurma."
        ) from exc
    adaylar = await _visible(locator)
    if not adaylar:
        raise TargetError(f"Öğe görünür değil: {selector}.")
    tanimlar = [await aday.evaluate(_DESCRIBE_JS) for aday in adaylar[:MAX_CANDIDATES]]
    if len(adaylar) > 1:
        liste = "; ".join(str(tanim["selector"]) for tanim in tanimlar)
        fazla = f" (+{len(adaylar) - MAX_CANDIDATES} daha)" if len(adaylar) > MAX_CANDIDATES else ""
        raise TargetError(
            f"Seçici '{selector}' {len(adaylar)} görünür öğeye uyuyor; hangisini kastettiğin "
            f"belirsiz, işlem YAPILMADI. Adaylar: {liste}{fazla}. Bunlardan birini seçici "
            "olarak kullan."
        )
    return Target(adaylar[0], str(tanimlar[0]["selector"]), str(tanimlar[0]["tag"]))


async def fill_or_select(target: Target, text: str) -> str:
    """Alana yaz; seçim kutusunda metne uyan seçeneği seç. Sonucu anlatan metni döndür."""
    if target.tag == "select":
        secenekler = await target.locator.evaluate(
            "(e) => [...e.options].map(o => ({value: o.value, label: o.text.trim()}))"
        )
        aranan = text.strip().casefold()
        uyan = next(
            (s for s in secenekler if aranan in (s["value"].casefold(), s["label"].casefold())),
            None,
        ) or next((s for s in secenekler if aranan and aranan in s["label"].casefold()), None)
        if uyan is None:
            mevcut = ", ".join(s["label"] for s in secenekler)
            raise TargetError(
                f"{target.description} içinde '{text}' seçeneği yok. Seçenekler: {mevcut}."
            )
        await target.locator.select_option(value=uyan["value"])
        return f"{target.description} → '{uyan['label']}' seçildi"
    onceki = ""
    try:
        onceki = str(await target.locator.input_value())
    except Exception:  # sınır: contenteditable gibi değeri olmayan alanlar
        onceki = ""
    await target.locator.fill(text)
    if onceki and onceki != text:
        return f"{target.description} alanına yazıldı (önceki değer '{onceki[:60]}' silindi)"
    return f"{target.description} alanına yazıldı"
