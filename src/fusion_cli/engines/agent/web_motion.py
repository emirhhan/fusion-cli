"""Web çıktısında hareket kusurları: layout özelliği canlandırma."""

from __future__ import annotations

import re

#: Canlandırılınca sayfayı yeniden dizen (reflow) ve KONUM kaydıran özellikler: menü
#: `left`, kayan blok `margin-left` gibi. Bunlar nesnel olarak takılır → BLOCKING.
_POSITION_PROPERTIES = frozenset(
    {
        "top", "left", "right", "bottom", "margin", "margin-top", "margin-left",
        "margin-right", "margin-bottom",
    }
)  # fmt: skip
#: Boyut/dolgu geçişleri (akordeon `max-height`, ilerleme çubuğu `width`, `padding`):
#: yaygın ve çoğu kez BİLİNÇLİ. Takılabilir ama sayfayı bozmaz → yalnız UYARI (A4-43).
_SIZE_PROPERTIES = frozenset(
    {
        "width", "height", "min-width", "max-width", "min-height", "max-height", "padding",
        "padding-top", "padding-left", "padding-right", "padding-bottom",
    }
)  # fmt: skip
_TRANSITION_DECL = re.compile(r"transition(?:-property)?\s*:\s*([^;}]+)", re.IGNORECASE)
_KEYFRAMES = re.compile(
    r"@(?:-webkit-)?keyframes\s+([\w-]+)\s*\{((?:[^{}]*\{[^{}]*\})*)[^{}]*\}", re.IGNORECASE
)
_KEYFRAME_PROP = re.compile(r"([\w-]+)\s*:", re.IGNORECASE)


def _animated(css: str, properties: frozenset[str]) -> list[str]:
    bulunan: list[str] = []
    for eslesme in _TRANSITION_DECL.finditer(css):
        for parca in eslesme.group(1).split(","):
            # Sekme/satır sonu ayracı da olabilir: `split(" ")` kırılgandı (A4-43).
            ad = (parca.split() or [""])[0].lower()
            if ad in properties:
                bulunan.append(f"transition: {ad}")
    for eslesme in _KEYFRAMES.finditer(css):
        for ad in _KEYFRAME_PROP.findall(eslesme.group(2)):
            if ad.lower() in properties:
                bulunan.append(f"@keyframes {eslesme.group(1)}: {ad.lower()}")
    return list(dict.fromkeys(bulunan))


def layout_animations(css: str) -> list[str]:
    """`transition`/`@keyframes` ile canlandırılan KONUM özellikleri (blocking).

    Ölçüldü (4 Ekim, iki animasyon koşusu): model beceri notuna rağmen alt çizgi
    efektini `transition: width`, menüyü `transition: left` ile yaptı. Bu özellikler
    her karede sayfayı yeniden dizer ve takılma yapar; `transform`/`opacity` ile
    aynı görünüm akıcı elde edilir. Kural istemde değil burada verilir: model araç
    sonucuna uyuyor.

    30 Ekim (A4-43): yalnız konum kaydıranlar (`top/left/right/bottom/margin*`) engeldir.
    Akordeon `max-height`, ilerleme çubuğu `width` gibi boyut geçişleri bilinçli bir
    tasarım olabilir; onlar `size_animations` ile UYARI olur.
    """
    bulunan = _animated(css, _POSITION_PROPERTIES)
    if not bulunan:
        return []
    ozet = ", ".join(bulunan)
    return [
        f"Layout özelliği canlandırılıyor ({ozet}): her karede sayfa yeniden dizilir ve "
        "hareket takılır. Aynı etkiyi transform (scaleX/translate) ve opacity ile yap; "
        "ör. alt çizgi için `transform: scaleX(0→1)` + `transform-origin: left`."
    ]


def size_animations(css: str) -> list[str]:
    """`width`/`height`/`max-height`/`padding` geçişleri: engel değil, UYARI."""
    bulunan = _animated(css, _SIZE_PROPERTIES)
    if not bulunan:
        return []
    ozet = ", ".join(bulunan)
    return [
        f"Boyut özelliği canlandırılıyor ({ozet}): düşük başlı cihazda takılabilir. "
        "Akordeon/ilerleme çubuğu bilinçliyse bırak; değilse transform (scale) ve "
        "opacity ile yap."
    ]
