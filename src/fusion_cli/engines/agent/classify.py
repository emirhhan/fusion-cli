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


_OPERATION_RE = re.compile(
    r"\b(?:push(?:la|le)?[a-zçğıöşü]*|commit(?:le)?[a-zçğıöşü]*|deploy(?:\s+et)?|"
    r"restart|yeniden\s+başlat|yeniden\s+baslat)\b",
    re.IGNORECASE,
)
#: "Çalışır hale getir" ailesi — var olanı işler duruma sokma emri.
#
# Ölçüldü (gerçek koşu): "dashboard'ı tüm fonksiyonlarıyla çalışır bir hale
# getirmesini istiyorum" GENERAL'e düşüyordu. GENERAL demek `complex_task=False`
# demek; ne kanıt kapısı ne de "iş yapmadan durdu" kapısı kuruluyor ve model
# hiçbir dosyaya dokunmadan "yaptım" diyebiliyordu.
#
# Bu kalıp tam-token listesine sığmaz: araya sıfat girer ("çalışır BİR hale
# getir") ve fiil ek alır ("getirmesini"). Bu yüzden anahtar kelime değil regex.
_MAKE_OPERATIONAL_RE = re.compile(
    r"\b(?:"
    r"(?:çalışır|calisir|düzgün|duzgun|aktif|işler|isler)\s+(?:\w+\s+)?hale\s+getir|"
    r"hale\s+getir|"
    r"ayağa\s+kaldır|ayaga\s+kaldir|"
    r"devreye\s+al|"
    r"hayata\s+geçir|hayata\s+gecir|"
    r"entegre\s+et"
    r")[a-zçğıöşü]*",
    re.IGNORECASE,
)
_EXPLANATION_RE = re.compile(
    r"\b(?:nedir|ne\s+demek|nasıl\s+yapılır|nasil\s+yapilir|açıkla|acikla)\b",
    re.IGNORECASE,
)

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
            "pushla",
            "push et",
            "commit et",
            "commitle",
            "deploy et",
            "çalıştır",
            "calistir",
            "başlat",
            "baslat",
            "yeniden başlat",
            "yeniden baslat",
            "güncelle",
            "guncelle",
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
            "kontrol et",
            "doğrula",
            "dogrula",
            "listele",
            "oku",
            "göster",
            "goster",
        ),
    ),
)


def classify_task(request: str) -> TaskKind:
    """İstek metnini kaba bir görev türüne eşle. Belirsizse `GENERAL`."""

    tokens = set(re.split(r"[^0-9a-zçğıöşü]+", request.lower()))
    lowered = request.lower()

    # Git/deploy gibi gerçek operasyon fiillerinin Türkçe ekli biçimleri tam-token
    # anahtar listesine sığmaz (pushlayabilir, commitleyelim…). Açıklama sorusu
    # değilse bunları doğrudan FEATURE bütçesine al.
    if _OPERATION_RE.search(lowered) and not _EXPLANATION_RE.search(lowered):
        return TaskKind.FEATURE

    # "Çalışır hale getir" de aynı bütçeye girer: var olanı işler duruma sokmak
    # kod değiştirmeyi gerektirir. Açıklama sorusu ("nasıl çalışır hale getirilir")
    # dışarıda kalır — orada istenen bilgi, değişiklik değil.
    if _MAKE_OPERATIONAL_RE.search(lowered) and not _EXPLANATION_RE.search(lowered):
        return TaskKind.FEATURE

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


#: Ek almış biçimlerin de sayılması için gereken en az anahtar uzunluğu.
#
# Türkçe eklemeli bir dildir ve tam-token eşleşme ekli biçimleri kaçırıyordu:
# "hataları" ≠ "hata", "testleri" ≠ "test". Ölçüldü — üç hatayı düzeltmek isteyen
# bir istek ("hataları oku, sonra düzelt, sonra doğrula") EXPLORE sanılıyordu:
# EXPLORE'un iki eşleşmesine (oku, doğrula) karşı BUGFIX yalnızca bir tane
# bulabiliyordu. Sonuç, göreve olması gerekenden dar bir bütçe verilmesiydi.
#
# Önek eşleşmesi yalnızca UZUN anahtarlarda açılır: kısa anahtarlarda yanlış-pozitif
# riski yüksektir ("bul" → "bulut", "yaz" → "yazılım" gibi).
_PREFIX_MATCH_MIN = 4


def _matches(keyword: str, tokens: set[str], lowered: str) -> bool:
    # Çok sözcüklü anahtar alt-dize aramasıyla eşleşir.
    if " " in keyword:
        return keyword in lowered
    if keyword in tokens:
        return True
    if len(keyword) < _PREFIX_MATCH_MIN:
        return False
    return any(token.startswith(keyword) for token in tokens)
