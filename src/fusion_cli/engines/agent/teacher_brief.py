"""Öğretmen brief derleyici (Faz 4, Görev 1).

`ask_teacher` aracının web öğretmene gönderdiği paketi kurar: durum özeti +
dokunulan dosyalar ("ilgili kod") + denenenler + modelin sorduğu TEK soru.
Saf ve test edilebilirdir: ağ, dosya, süreç bilmez.

`durum`/`denenenler`/`soru` MODELİN kendi metnidir (tıpkı `council` aracındaki
`question` gibi) — araç yalnızca biçimlendirir ve bütçeler, model çağrısı
yapmaz. Tek istisna "ilgili kod": bu, modelin BEYANI değil `ToolContext`'in
merkezi kaydından (`touched` ∪ `fully_read`) gelen GERÇEK dosya listesidir —
model unutabilir ya da yanlış hatırlayabilir, çalışma-anı kaydı unutmaz.

25.000 karakter sınırı uydurulmadı: Faz 4 planında (`docs/superpowers/plans/
2026-09-22-ogretmen-protokolu.md`, Görev 1) kullanıcıyla netleşen üst sınırdır
— öğretmen web oturumunun prompt kutusuna sığması ve dosya yükleme (Görev 2)
gerekmeden makul bir bağlam taşıması için seçildi.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

#: Brief'in sert üst sınırı. Aşan kısım KIRPILIR, sessizce değil — kırpma notu
#: eklenir (bkz. `compile_brief` docstring'i).
BRIEF_CHAR_BUDGET = 25_000

_KIRPMA_NOTU = "\n\n[…brief 25.000 karakter sınırına sığdırılırken kırpıldı…]"


@dataclass(frozen=True, slots=True)
class TeacherBrief:
    """Derlenmiş brief ve kırpılıp kırpılmadığı bilgisi."""

    text: str
    truncated: bool


def compile_brief(
    *,
    durum: str,
    denenenler: str,
    question: str,
    touched_paths: Iterable[str] = (),
    char_budget: int = BRIEF_CHAR_BUDGET,
) -> TeacherBrief:
    """Durum + ilgili kod + denenenler + soruyu tek bir brief'te birleştir.

    Sıra bilinçlidir: soru EN SONDA durur ki kırpma gerekirse önce durum/kod/
    denenenler kısalır, soru asla kaybolmaz (öğretmenin cevaplayacağı şey budur).
    """
    ilgili_kod = "\n".join(f"- {yol}" for yol in dict.fromkeys(touched_paths))
    bolumler = [
        ("## Durum", durum.strip()),
        ("## İlgili kod", ilgili_kod),
        ("## Denenenler", denenenler.strip()),
        ("## Soru", question.strip()),
    ]
    parcalar = [f"{baslik}\n{govde}" for baslik, govde in bolumler if govde]
    brief = "\n\n".join(parcalar)
    if len(brief) <= char_budget:
        return TeacherBrief(text=brief, truncated=False)
    return TeacherBrief(text=_kirp(brief, question, char_budget), truncated=True)


def _kirp(brief: str, question: str, char_budget: int) -> str:
    """Soru bölümünü KORUYARAK geri kalanı kırp.

    Soru genelde kısadır; onu payından düşürmek yerine geri kalan (durum + kod
    + denenenler) kırpılır. Soru TEK BAŞINA bütçeyi aşıyorsa (olağandışı) son
    çare olarak o da kırpılır.
    """
    soru_bolumu = f"## Soru\n{question.strip()}"
    ayrac = "\n\n"
    kalan_pay = char_budget - len(soru_bolumu) - len(_KIRPMA_NOTU) - len(ayrac)
    if kalan_pay <= 0:
        return (soru_bolumu[: char_budget - len(_KIRPMA_NOTU)]) + _KIRPMA_NOTU
    govde = brief[: brief.rfind(soru_bolumu)] if soru_bolumu in brief else brief
    return govde[:kalan_pay] + _KIRPMA_NOTU + ayrac + soru_bolumu
