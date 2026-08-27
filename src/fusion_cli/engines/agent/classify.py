"""Görev sınıflandırıcı — istek metninden görev türünü çıkarır.

Ucuz ve deterministik: model çağrısı YOK, yalnızca anahtar kelime kuralları. Sonuç
bağlam kurucuya girer — geri çağırmada yalnızca ilgili kapsamdaki (ya da kapsamsız/
genel) dersler enjekte edilir, öğrenilen ders de bu kapsamla etiketlenir.

Saftır ve doğrudan test edilir. Belirsizlikte `GENERAL` döner: bu durumda kapsam
filtresi uygulanmaz (yanlış daraltmaktansa filtrelememek yeğdir).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
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
            "yap",
            "kur",
            "inşa et",
            "insa et",
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


@dataclass(frozen=True, slots=True)
class TaskClassification:
    """Görevin ana niyeti ve yardımcı niyetleri.

    `primary` execution policy / ana scope için kullanılır.
    `secondary` kullanıcı isteğinde gerçekten bulunan ama ana hedef olmayan
    davranışları taşır. Böylece "özellik yap, sonra test et" TEST'e dönüşmez.

    `confidence` [0, 1] aralığında yalnız deterministik sınıflandırma güvenidir;
    model güveni değildir.
    """

    primary: TaskKind
    secondary: tuple[TaskKind, ...] = ()
    confidence: float = 0.0
    scores: tuple[tuple[TaskKind, int], ...] = ()

    def score_for(self, kind: TaskKind) -> int:
        return next((score for item, score in self.scores if item is kind), 0)


#: İlk bölüm kullanıcının ASIL emrini taşıma eğilimindedir. Uzun acceptance/test
#: listelerinin sonradan ana görevi ele geçirmesini engellemek için burada görülen
#: sinyaller daha ağırdır. 320 karakter, gerçek benchmark promptunda ilk ana emri ve
#: kısa açıklamasını kapsarken uzun test/checklist bölümünü dışarıda bırakır.
_PRIMARY_HEAD_CHARS = 320
_HEAD_MATCH_BONUS = 2

#: Ana niyet sinyalleri yalnız promptun baş bölümünde bonus alır.
#:
#: Bunlar _RULES'un yerine geçmez; yalnız "asıl emir" ile sonraki doğrulama
#: talimatlarını ayırır. Spesifik türler FEATURE'dan daha yüksek bonus alır:
#: "pytest testi yaz" TEST, "README belgesi ekle" DOCS kalmalıdır.
_HEAD_INTENT_RULES: dict[TaskKind, tuple[re.Pattern[str], int]] = {
    TaskKind.BUGFIX: (
        re.compile(
            r"\b(?:düzelt|duzelt|fix|çöz|coz|onar)[a-zçğıöşü]*\b",
            re.IGNORECASE,
        ),
        4,
    ),
    TaskKind.TEST: (
        re.compile(
            r"\b(?:pytest|unittest|test(?:i|leri)?\s+"
            r"(?:yaz|ekle|oluştur|olustur|çalıştır|calistir))[a-zçğıöşü]*\b",
            re.IGNORECASE,
        ),
        3,
    ),
    TaskKind.REFACTOR: (
        re.compile(
            r"\b(?:refactor|yeniden\s+düzenle|yeniden\s+duzenle|"
            r"sadeleştir|sadelestir)[a-zçğıöşü]*\b",
            re.IGNORECASE,
        ),
        4,
    ),
    TaskKind.WEBSITE: (
        re.compile(
            r"\b(?:web\s+sitesi|website|landing|html|css|frontend|"
            r"arayüz|arayuz)\b",
            re.IGNORECASE,
        ),
        3,
    ),
    TaskKind.DOCS: (
        re.compile(
            r"\b(?:readme|docs|doküman|dokuman|belge)\b",
            re.IGNORECASE,
        ),
        3,
    ),
    TaskKind.FEATURE: (
        re.compile(
            r"\b(?:yap|oluştur|olustur|ekle|implement|geliştir|gelistir|"
            r"kur|inşa\s+et|insa\s+et)[a-zçğıöşü]*\b",
            re.IGNORECASE,
        ),
        2,
    ),
    TaskKind.EXPLORE: (
        re.compile(
            r"\b(?:incele|araştır|arastir|listele|oku|göster|goster|"
            r"kontrol\s+et)\b",
            re.IGNORECASE,
        ),
        2,
    ),
}


def _classification_scores(request: str) -> tuple[tuple[TaskKind, int], ...]:
    """Bütün prompt + ağırlaştırılmış ilk bölüm için deterministik skorlar."""

    lowered = request.lower()
    tokens = set(re.split(r"[^0-9a-zçğıöşü]+", lowered))

    head = request[:_PRIMARY_HEAD_CHARS].lower()
    head_tokens = set(re.split(r"[^0-9a-zçğıöşü]+", head))

    scores: list[tuple[TaskKind, int]] = []

    for kind, keywords in _RULES:
        full_hits = sum(
            1
            for keyword in keywords
            if _matches(keyword, tokens, lowered)
        )
        head_hits = sum(
            1
            for keyword in keywords
            if _matches(keyword, head_tokens, head)
        )

        score = full_hits + (_HEAD_MATCH_BONUS * head_hits)

        intent = _HEAD_INTENT_RULES.get(kind)
        if intent is not None:
            pattern, bonus = intent
            if pattern.search(head):
                score += bonus

        scores.append((kind, score))

    return tuple(scores)


def classify_task_details(request: str) -> TaskClassification:
    """Primary ve secondary görev niyetlerini çıkar.

    Özel operasyon regex'leri önceki davranışı korur. Normal görevlerde uzun promptun
    ilk bölümü daha ağırdır; sonraki test/doğrulama checklist'i yine secondary olarak
    görünür ama primary'yi kolayca ele geçiremez.
    """

    lowered = request.lower()

    # "yap" tek başına mutation niyetini kanıtlamaz. Kullanıcının ne yapılacağını
    # belirtmediği bu tip kısa emirlerde FEATURE seçmek ask_user akışını gereksiz
    # workspace-mutation zorlamasına sokar.
    normalized = re.sub(r"[^0-9a-zçğıöşü]+", " ", lowered).strip()
    if normalized == "yap":
        return TaskClassification(
            primary=TaskKind.GENERAL,
            confidence=0.0,
        )

    # Git/deploy ve "çalışır hale getir" sözleşmeleri gerçek mutation emirleridir.
    forced_feature = (
        (
            _OPERATION_RE.search(lowered)
            and not _EXPLANATION_RE.search(lowered)
        )
        or (
            _MAKE_OPERATIONAL_RE.search(lowered)
            and not _EXPLANATION_RE.search(lowered)
        )
    )

    scores = _classification_scores(request)

    if forced_feature:
        primary = TaskKind.FEATURE
    else:
        # _RULES sırası tie-breaker olarak korunur: sorted stable'dır.
        ranked = sorted(scores, key=lambda item: item[1], reverse=True)
        primary = (
            ranked[0][0]
            if ranked and ranked[0][1] > 0
            else TaskKind.GENERAL
        )

    positive = sorted(
        (
            (kind, score)
            for kind, score in scores
            if score > 0 and kind is not primary
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    secondary = tuple(kind for kind, _score in positive)

    primary_score = next(
        (score for kind, score in scores if kind is primary),
        0,
    )
    second_score = positive[0][1] if positive else 0

    if forced_feature:
        confidence = 1.0
    elif primary_score <= 0:
        confidence = 0.0
    else:
        confidence = max(
            0.0,
            min(1.0, (primary_score - second_score) / primary_score),
        )

    return TaskClassification(
        primary=primary,
        secondary=secondary,
        confidence=confidence,
        scores=scores,
    )


def classify_task(request: str) -> TaskKind:
    """Geriye uyumlu API: yalnız primary görev türünü döndür."""
    return classify_task_details(request).primary


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
