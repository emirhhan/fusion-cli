"""Modelin hazır ret cevabını tanır.

Ölçüldü (27 Eylül): tarayıcı görevinde Nemotron "Ben sadece bir dil modeliyim ve bu
isteğinize yardımcı olamıyorum.", Gemini web "İsteğinizi gerçekleştirebilecek şekilde
programlanmadım." dedi — ikisi de elinde tarayıcı araçları varken, hiçbirini
denemeden. Fusion bu kalıp cevabı başarılı sonuç sayıp kullanıcıya gösteriyordu.

Yalnız KISA cevaplar ret sayılır: uzun bir rapor içinde geçen "yardımcı olamıyorum"
ifadesi gerçek bir cevabın parçasıdır ve dokunulmaz.
"""

from __future__ import annotations

import re

#: Bundan uzun cevap kalıp ret değildir; gerçek bir açıklamadır.
MAX_REFUSAL_CHARS = 400

_REFUSAL = re.compile(
    r"dil modeliyim|yapay zek[aâ](?: dil)? modeliyim|yardımcı olam(?:ıyorum|am)|"
    r"programlanmadım|bunu yapamam|"
    r"i'?m (?:just |only )?an? (?:ai |large )?language model|"
    r"i can(?:not|'t) (?:help|assist) with|i'?m (?:not able|unable) to help",
    re.IGNORECASE,
)


def looks_like_refusal(text: str) -> bool:
    """Metin, araç denemeden verilmiş kısa bir kalıp ret mi?"""
    stripped = text.strip()
    return bool(stripped) and len(stripped) <= MAX_REFUSAL_CHARS and bool(_REFUSAL.search(stripped))
