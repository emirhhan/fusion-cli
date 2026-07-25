"""Görev sınıflandırıcı — istek metninden görev türünü çıkarır.

Ucuz ve deterministik: model çağrısı YOK, yalnızca anahtar kelime kuralları. Sonuç
bağlam kurucuya girer — geri çağırmada yalnızca ilgili kapsamdaki (ya da kapsamsız/
genel) dersler enjekte edilir, öğrenilen ders de bu kapsamla etiketlenir.

Saftır ve doğrudan test edilir. Belirsizlikte `GENERAL` döner: bu durumda kapsam
filtresi uygulanmaz (yanlış daraltmaktansa filtrelememek yeğdir).
"""

from __future__ import annotations

import re
from enum import Enum


class TaskKind(Enum):
    """Bir isteğin kaba görev türü. Ders kapsamı (scope) olarak kullanılır."""

    BUGFIX = "bugfix"
    REFACTOR = "refactor"
    TEST = "test"
    WEBSITE = "website"
    DOCS = "docs"
    FEATURE = "feature"
    EXPLORE = "explore"
    GENERAL = "general"


#: Tür → anahtar kelimeler. Sıra ÖNCELİKTİR: ilk eşleşen tür kazanır. Daha özgül
#: türler (bugfix/test) genel olanlardan (feature) önce gelir.
_RULES: tuple[tuple[TaskKind, tuple[str, ...]], ...] = (
    (
        TaskKind.BUGFIX,
        (
            "hata",
            "bug",
            "düzelt",
            "duzelt",
            "çöz",
            "coz",
            "fix",
            "patch",
            "kırıl",
            "kiril",
            "çalışmıyor",
            "calismiyor",
        ),
    ),
    (TaskKind.TEST, ("test", "pytest", "unittest", "kapsam", "coverage", "assert")),
    (
        TaskKind.REFACTOR,
        (
            "refactor",
            "yeniden düzenle",
            "yeniden duzenle",
            "temizle",
            "sadeleştir",
            "sadelestir",
            "böl",
            "bol",
            "taşı",
            "tasi",
        ),
    ),
    (
        TaskKind.WEBSITE,
        (
            "web sitesi",
            "website",
            "sayfa",
            "html",
            "css",
            "landing",
            "arayüz",
            "arayuz",
            "frontend",
            "buton",
            "stil",
        ),
    ),
    (
        TaskKind.DOCS,
        (
            "doküman",
            "dokuman",
            "readme",
            "docs",
            "belge",
            "açıklama yaz",
            "aciklama yaz",
            "yorum ekle",
        ),
    ),
    (
        TaskKind.FEATURE,
        (
            "ekle",
            "oluştur",
            "olustur",
            "yeni özellik",
            "yeni ozellik",
            "implement",
            "yaz",
            "geliştir",
            "gelistir",
        ),
    ),
    (
        TaskKind.EXPLORE,
        (
            "nerede",
            "nasıl çalışıyor",
            "nasil calisiyor",
            "açıkla",
            "acikla",
            "incele",
            "bul",
            "araştır",
            "arastir",
        ),
    ),
)


def classify_task(request: str) -> TaskKind:
    """İstek metnini kaba bir görev türüne eşle. Belirsizse `GENERAL`."""

    tokens = set(re.split(r"[^0-9a-zçğıöşü]+", request.lower()))
    lowered = request.lower()

    # EŞLEŞME SAYISI kazanır, sıra değil. Eskiden "ilk eşleşen tür kazanır" idi ve
    # uzun isteklerde tesadüfi tek bir kelime konuyu kaçırtıyordu: bir e-ticaret
    # sayfası isteği, kampanya metnindeki "evine taşı" yüzünden REFACTOR sanılıyor,
    # WEBSITE'ın dört isabetli eşleşmesi (sayfa, html, css, arayüz) görmezden
    # geliniyordu. Beraberlikte kural sırası (özgülden genele) hâlâ belirleyicidir.
    best_kind = TaskKind.GENERAL
    best_score = 0
    for kind, keywords in _RULES:
        score = sum(1 for keyword in keywords if _matches(keyword, tokens, lowered))
        if score > best_score:
            best_kind, best_score = kind, score
    return best_kind


def scope_of(kind: TaskKind) -> str:
    """Kapsam etiketi: `GENERAL` için boş (her göreve uyan genel ders)."""

    return "" if kind is TaskKind.GENERAL else kind.value


def recall_scope(kind: TaskKind) -> str | None:
    """Geri çağırma filtresi: `GENERAL`'da filtre yok (None), aksi halde tür değeri."""

    return None if kind is TaskKind.GENERAL else kind.value


def _matches(keyword: str, tokens: set[str], lowered: str) -> bool:
    # Tek sözcüklü anahtar tam token eşleşmesiyle (yanlış-pozitif azalır); çok
    # sözcüklü anahtar alt-dize aramasıyla eşleşir.
    if " " in keyword:
        return keyword in lowered
    return keyword in tokens
