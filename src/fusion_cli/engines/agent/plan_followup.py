"""Yeni kullanıcı mesajı, duraklamış bir planın DEVAMI mı yoksa yeni bir iş mi?

`store.find_resumable` aynı kök ve konuşmadaki duraklamış planı bulur; ama bulunan
planın yeni mesajla ilgisi sınanmazdı. Ölçüldü (29 Ekim, A3-03): alakasız bir istek,
eski planın "KULLANICININ SON YÖNLENDİRMESİ"ne dönüşüp eski plan canlandırılıyordu.

Karar bilinçli olarak kabadır ve model çağrısı harcamaz; yanlış tarafa düşmenin
bedeli asimetriktir: devam sanılan yeni iş yanlış işi yapar, yeni sanılan devam ise
yalnızca planı baştan üretir (tamamlanan adımlar diskte durur).
"""

from __future__ import annotations

import re

#: Tek başına "kaldığın yerden sürdür" anlamına gelen sözcükler.
_CONTINUATION_WORDS = frozenset(
    {
        "devam",
        "et",
        "edelim",
        "sürdür",
        "surdur",
        "tamam",
        "tamamdır",
        "evet",
        "lütfen",
        "kaldığın",
        "kaldigin",
        "yerden",
        "başla",
        "basla",
        "çalışmaya",
        "calismaya",
        "işe",
        "ise",
        "continue",
        "resume",
        "please",
        "ok",
        "okay",
        "yes",
        "go",
        "on",
        "where",
        "you",
        "left",
        "off",
        "start",
        "working",
    }
)
#: Bu kadar sözcüğe kadar olan mesaj yönlendirme sayılır ("mavi olsun", "bir daha dene").
_SHORT_GUIDANCE_WORDS = 3
#: Sözcük karşılaştırmasında kullanılan kök uzunluğu (Türkçe ekleri tolere eder).
_STEM = 4
#: Yeni mesajın kök kümesinin en az bu kadarı eski görevle ortak olmalı.
_MIN_OVERLAP = 0.25


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


def _stems(words: list[str]) -> set[str]:
    return {word[:_STEM] for word in words if len(word) >= 4}


def is_followup(task: str, previous_task: str) -> bool:
    """`task`, duraklamış `previous_task` planının devamı/yönlendirmesi mi?"""
    words = _words(task)
    if len(words) <= _SHORT_GUIDANCE_WORDS or all(word in _CONTINUATION_WORDS for word in words):
        return True
    mine, theirs = _stems(words), _stems(_words(previous_task))
    if not mine or not theirs:
        return False
    return len(mine & theirs) / len(mine) >= _MIN_OVERLAP
