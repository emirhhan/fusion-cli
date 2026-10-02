"""Modelin hazır ret cevabını tanır.

Ölçüldü (27 Eylül): tarayıcı görevinde Nemotron "Ben sadece bir dil modeliyim ve bu
isteğinize yardımcı olamıyorum.", Gemini web "İsteğinizi gerçekleştirebilecek şekilde
programlanmadım." dedi — ikisi de elinde tarayıcı araçları varken, hiçbirini
denemeden. Fusion bu kalıp cevabı başarılı sonuç sayıp kullanıcıya gösteriyordu.

Yalnız KISA cevaplar ret sayılır: uzun bir rapor içinde geçen "yardımcı olamıyorum"
ifadesi gerçek bir cevabın parçasıdır ve dokunulmaz.

`core`'dadır çünkü iki katman kullanır: agent döngüsü (modeli bir kez geri çevirir)
ve web taşıması (seçili model kalıp ret verirse komşu modele geçer).
"""

from __future__ import annotations

import re

#: Bundan uzun cevap kalıp ret değildir; gerçek bir açıklamadır.
MAX_REFUSAL_CHARS = 400

# Ölçüldü (2 Ekim 2026, Gemini web "3.1 Pro", 9 çağrı): kalıp ret her seferinde başka
# sözcüklerle geldi — "…dil modeli olduğum için…", "…metin tabanlı bir yapay zeka
# platformu olduğum için… kabiliyete sahip değilim", "Ben yalnızca metin oluşturuyorum".
_REFUSAL = re.compile(
    r"dil modeliyim|dil modeli olarak|dil modeli olduğum|yapay zek[aâ](?: dil)? modeliyim|"
    r"yapay zek[aâ] (?:platformu|asistanı|modeli) olduğum|kabiliyete sahip (?:değilim|olmadığım)|"
    r"ben yalnızca metin (?:oluşturuyorum|tabanlı)|"
    r"yardımcı olam(?:ıyorum|am)|programlanmadım|tasarlanmadım|bunu yapamam|"
    r"i'?m (?:just |only )?an? (?:ai |large )?language model|"
    r"i can(?:not|'t) (?:help|assist) with|i'?m (?:not able|unable) to help",
    re.IGNORECASE,
)


def looks_like_refusal(text: str) -> bool:
    """Metin, araç denemeden verilmiş kısa bir kalıp ret mi?"""
    stripped = text.strip()
    return bool(stripped) and len(stripped) <= MAX_REFUSAL_CHARS and bool(_REFUSAL.search(stripped))
