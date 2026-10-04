"""Web çıktısında hareket kusurları: layout özelliği canlandırma."""

from __future__ import annotations

import re

#: Canlandırılınca sayfayı yeniden dizen (reflow) özellikler.
_LAYOUT_PROPERTIES = frozenset(
    {
        "width", "height", "top", "left", "right", "bottom", "margin", "margin-top",
        "margin-left", "margin-right", "margin-bottom", "padding", "padding-top",
        "padding-left", "padding-right", "padding-bottom", "min-width", "max-width",
        "min-height", "max-height",
    }
)  # fmt: skip
_TRANSITION_DECL = re.compile(r"transition(?:-property)?\s*:\s*([^;}]+)", re.IGNORECASE)
_KEYFRAMES = re.compile(r"@keyframes\s+([\w-]+)\s*\{((?:[^{}]*\{[^{}]*\})*)[^{}]*\}", re.IGNORECASE)
_KEYFRAME_PROP = re.compile(r"([\w-]+)\s*:", re.IGNORECASE)


def layout_animations(css: str) -> list[str]:
    """`transition`/`@keyframes` ile canlandırılan layout özellikleri (blocking).

    Ölçüldü (4 Ekim, iki animasyon koşusu): model beceri notuna rağmen alt çizgi
    efektini `transition: width`, menüyü `transition: left` ile yaptı. Bu özellikler
    her karede sayfayı yeniden dizer ve takılma yapar; `transform`/`opacity` ile
    aynı görünüm akıcı elde edilir. Kural istemde değil burada verilir: model araç
    sonucuna uyuyor.
    """
    bulunan: list[str] = []
    for eslesme in _TRANSITION_DECL.finditer(css):
        for parca in eslesme.group(1).split(","):
            ad = parca.strip().split(" ", 1)[0].lower()
            if ad in _LAYOUT_PROPERTIES:
                bulunan.append(f"transition: {ad}")
    for eslesme in _KEYFRAMES.finditer(css):
        for ad in _KEYFRAME_PROP.findall(eslesme.group(2)):
            if ad.lower() in _LAYOUT_PROPERTIES:
                bulunan.append(f"@keyframes {eslesme.group(1)}: {ad.lower()}")
    if not bulunan:
        return []
    ozet = ", ".join(dict.fromkeys(bulunan))
    return [
        f"Layout özelliği canlandırılıyor ({ozet}): her karede sayfa yeniden dizilir ve "
        "hareket takılır. Aynı etkiyi transform (scaleX/translate) ve opacity ile yap; "
        "ör. alt çizgi için `transform: scaleX(0→1)` + `transform-origin: left`."
    ]
