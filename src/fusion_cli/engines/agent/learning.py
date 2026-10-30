"""Ders çıkarımı — agent'ın kendi deneyiminden öğrenmesi.

Tur bittikten sonra oturum izi hızlı bir modele verilir ve somut dersler istenir.
Çıkan dersler belleğe yazılır; benzer bir görev geldiğinde sistem promptuna geri
enjekte edilir.

Ders çıkarımı YALNIZCA gerçek iş yapıldığında (araç çağrısı olduğunda) çalışır:
sohbet turlarından ders çıkarmak hem boşuna model çağrısıdır hem de belleği
değersiz kayıtlarla doldurur.

Ayrıştırma saftır ve doğrudan test edilir; model bozuk JSON verirse ders çıkmaz,
tur etkilenmez.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from ...config.models import Config
from ...core.errors import ConfigError, ProviderError
from ...core.events import EventPublisher
from ...core.memory import Lesson, LessonKind, LessonMemory, LessonSource
from ...core.redaction import contains_sensitive, redact
from ...core.text_fold import fold_tr
from ...core.types import CompletionRequest, Message
from ...providers.factory import build_provider
from ...providers.web_browser import WebBrowserError
from ...providers.web_registry import web_registry_for
from . import history

_LOG = logging.getLogger(__name__)

_PROMPT = (Path(__file__).parent / "prompts" / "lessons.txt").read_text(encoding="utf-8")

#: Ders çıkarımı için token bütçesi. Kısa dersler istiyoruz.
EXTRACT_MAX_TOKENS = 400
#: Bir turdan alınacak en fazla ders. Model coşarsa bellek çöple dolmasın.
MAX_LESSONS_PER_TURN = 3
#: İki dersin "çok benzer" sayıldığı token örtüşmesi (Jaccard) eşiği.
DEDUP_JACCARD_THRESHOLD = 0.6
#: Çelişki adayı sayılmak için gereken asgari token örtüşmesi (aynı konu).
CONTRADICTION_OVERLAP_THRESHOLD = 0.4
#: Bir tokenın anlamlı sayılması için asgari uzunluk (kısa ekler gürültüdür).
_MIN_TOKEN_LENGTH = 3
#: Türkçe olumsuzluk işaretleri: iki ders aynı konuda ama zıt kutupsa çelişir.
_NEGATION_MARKERS = frozenset(
    {"yapma", "etme", "kullanma", "silme", "gomme", "gömme", "asla", "degil", "değil", "yok"}
)


def parse_lessons(
    text: str, task: str, workspace: str = "", tags: tuple[str, ...] = ()
) -> tuple[Lesson, ...]:
    """Model çıktısındaki JSON diziyi derslere çevir. Bozuksa boş döner."""
    items = _first_json_list(text or "")
    if items is None:
        return ()

    lessons: list[Lesson] = []
    for item in items:
        lesson = _to_lesson(item, task, workspace, tags)
        if lesson is not None:
            lessons.append(lesson)
    return tuple(lessons[:MAX_LESSONS_PER_TURN])


def _first_json_list(text: str) -> list[object] | None:
    """Metindeki İLK geçerli JSON dizisini (ya da tek nesneyi) bul.

    Ölçüldü (30 Ekim, A2-10): açgözlü `\\[.*\\]` ilk `[`'den SON `]`'e kadar alıyordu;
    "[Not] ... [{...}]" ya da dizi sonrası açıklama JSON'u bozup dersi sessizce
    düşürüyordu. Tek nesne (`{...}`) dizi olmadan dönerse de atılıyordu.
    """
    decoder = json.JSONDecoder()
    for konum, karakter in enumerate(text):
        if karakter not in "[{":
            continue
        try:
            deger, _ = decoder.raw_decode(text, konum)
        except ValueError:
            continue
        if isinstance(deger, list) and (not deger or isinstance(deger[0], dict)):
            return deger
        if isinstance(deger, dict) and "lesson" in deger:
            return [deger]
    return None


async def extract_lessons(
    task: str,
    messages: list[Message],
    *,
    config: Config,
    publisher: EventPublisher | None = None,
    workspace: str = "",
    tags: tuple[str, ...] = (),
) -> tuple[Lesson, ...]:
    """Oturumdan ders çıkar. Model erişilemezse ya da çıktı bozuksa boş döner."""
    # Üçüncü taraf/web judge'a giden iz maskelenir (A2-13): `contains_sensitive`
    # yalnız ÜRETİLEN dersi süzüyordu, gönderilen oturum izini değil.
    trace = redact(history.transcript(messages))
    if not trace.strip():
        return ()

    request = CompletionRequest(
        messages=(Message("user", _fill_prompt(redact(task), trace)),),
        temperature=config.runtime.utility_temperature,
        max_tokens=EXTRACT_MAX_TOKENS,
        timeout_s=config.runtime.request_timeout_s,
        max_retries=config.runtime.max_retries,
        # Düşünen modelde 400 token'lık bütçe akıl yürütmede biter, JSON kesilir (A2-10).
        disable_thinking=True,
    )
    # Arka plan işi: gösterilmez ama harcadığı token muhasebeye girer.
    # Ölçüldü (30 Ekim, A2-09): sağlayıcı kurulamaz/çağrı istisna fırlatırsa
    # (judge tanımsız, web oturumu kopuk) ön planda tur cevap basıldıktan sonra
    # hatayla bitiyordu; öğrenme bir iyileştirmedir.
    try:
        provider = build_provider(
            config.judge,
            publisher=publisher,
            retry_delays_s=config.runtime.retry_delays_s,
            background=True,
            web_sessions=web_registry_for(config),
        )
        result = await provider.complete(request)
    except (ConfigError, ProviderError, WebBrowserError, OSError) as error:
        _LOG.info("ders çıkarımı atlandı: %s", error)
        return ()
    if not result.ok:
        _LOG.info("ders çıkarımı model hatasıyla bitti: %s", result.error)
        return ()
    if result.truncated:
        _LOG.info("ders çıkarımı çıktısı kesildi; ders alınmadı")
    return parse_lessons(result.text, task, workspace, tags)


def _fill_prompt(task: str, trace: str) -> str:
    """`{task}`/`{trace}` yer tutucularını TEK geçişte doldur.

    Zincirleme `.replace` görev metnindeki "{trace}" yazısını oturum iziyle
    değiştirirdi (A2-41).
    """
    degerler = {"task": task, "trace": trace}
    return re.sub(r"\{(task|trace)\}", lambda eslesme: degerler[eslesme.group(1)], _PROMPT)


def store_lessons(lessons: tuple[Lesson, ...], memory: LessonMemory) -> int:
    """Dersleri belleğe yaz; YENİ eklenen sayısını döndür (tekilleştirme belleğin işi)."""
    return sum(1 for lesson in lessons if memory.add(lesson))


# --------------------------------------------------------------------------- #
# Yazım kapısı — bellek çöple/zehirle dolmasın
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ScreenResult:
    """Tek bir ders adayının kapıdan geçme kararı."""

    accepted: bool
    #: Reddedildiyse Türkçe gerekçe; kabul edildiyse boş.
    reason: str = ""
    #: Mevcut bir dersle çeliştiği işaretlendi mi (tek başına engellemez).
    contradiction: bool = False


def has_measurable_evidence(messages: list[Message]) -> bool:
    """Turda ölçülebilir kanıt (bir araç çıktısı) var mı.

    Kanıtsız — yalnızca modelin iddiasına dayanan — ders belleğe girmez: doğrulanmamış
    bir davranış kuralı gelecekteki turları yanlış yönlendirebilir.
    """

    return any(message.role == "tool" for message in messages)


def screen_lesson(
    lesson: Lesson, existing: tuple[Lesson, ...], *, has_evidence: bool
) -> ScreenResult:
    """Bir ders adayını dört kapıdan geçir: kanıt, sır, tekilleştirme, çelişki."""

    if not has_evidence:
        return ScreenResult(accepted=False, reason="ölçülebilir kanıt yok")
    if contains_sensitive(lesson.text):
        return ScreenResult(accepted=False, reason="sır/kişisel veri içeriyor")
    # Çelişki tekilleştirmeden ÖNCE bakılır: zıt kutuplu bir ders yüksek token
    # örtüşmesine rağmen kopya DEĞİLDİR — reddedilmez, işaretlenerek kabul edilir.
    contradiction = any(contradicts(lesson.text, item.text) for item in existing)
    if not contradiction and is_near_duplicate(lesson.text, tuple(item.text for item in existing)):
        return ScreenResult(accepted=False, reason="çok benzer ders zaten var")
    return ScreenResult(accepted=True, contradiction=contradiction)


def screen_lessons(
    candidates: tuple[Lesson, ...], existing: tuple[Lesson, ...], *, has_evidence: bool
) -> tuple[Lesson, ...]:
    """Adayları kapıdan geçir; kabul edilenler sonrakiler için de "mevcut" sayılır."""

    accepted: list[Lesson] = []
    known = existing
    for lesson in candidates:
        if screen_lesson(lesson, known, has_evidence=has_evidence).accepted:
            accepted.append(lesson)
            known = (*known, lesson)
    return tuple(accepted)


def contradicted_texts(
    accepted: tuple[Lesson, ...], existing: tuple[Lesson, ...]
) -> tuple[str, ...]:
    """Kabul edilen yeni derslerle ÇELİŞEN eski dersler (güveni düşürülecekler).

    Ölçüldü (30 Ekim, A2-11): `screen_lesson` çelişkiyi işaretliyor ama sonuç hiçbir
    yerde kullanılmıyordu; "X'i kullan" ile "X'i kullanma" yan yana saklanıp ikisi de
    geri çağrılıyordu. Yeni ders ölçülebilir kanıtla kapıdan geçtiği için eskisi silinmez,
    yalnız güveni düşer (`reinforce(success=False)`); gerçekten yanlışsa eşik altına
    iner, doğruysa sonraki başarılı turlarla toparlanır.
    """
    texts = [
        old.text for old in existing if any(contradicts(new.text, old.text) for new in accepted)
    ]
    return tuple(dict.fromkeys(texts))


def is_near_duplicate(
    text: str, existing_texts: tuple[str, ...], threshold: float = DEDUP_JACCARD_THRESHOLD
) -> bool:
    """Metin, mevcut derslerden birine token örtüşmesi olarak çok benziyor mu."""

    tokens = _tokens(text)
    if not tokens:
        return False
    return any(_jaccard(tokens, _tokens(other)) >= threshold for other in existing_texts)


def contradicts(text: str, other: str) -> bool:
    """İki ders aynı konuda (yüksek örtüşme) ama zıt kutupta mı (olumsuzluk farkı)."""

    overlap = _jaccard(_tokens(text), _tokens(other))
    if overlap < CONTRADICTION_OVERLAP_THRESHOLD:
        return False
    return _is_negative(text) != _is_negative(other)


def _tokens(text: str) -> frozenset[str]:
    words = re.split(r"[^0-9a-zçğıöşü]+", fold_tr(text))
    return frozenset(word for word in words if len(word) >= _MIN_TOKEN_LENGTH)


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _is_negative(text: str) -> bool:
    return bool(_tokens(text) & _NEGATION_MARKERS)


def _to_lesson(
    item: object, task: str, workspace: str = "", tags: tuple[str, ...] = ()
) -> Lesson | None:
    if not isinstance(item, dict):
        return None
    text = str(item.get("lesson", "")).strip()
    if not text:
        return None
    try:
        kind = LessonKind(str(item.get("kind", "")).strip().lower())
    except ValueError:
        return None
    # Ders ÖĞRENİLDİĞİ projeye etiketlenir: "auth src/auth altında" gibi bir gözlem
    # yalnızca orada doğrudur, başka projede modeli yanlış yere yönlendirir.
    #
    # `tags` ise dersin TEKNOLOJİSİDİR (godot, python, mcp:godot…) ve aynı
    # teknolojideki başka projelerde de geçerli olmasını sağlar.
    return Lesson(
        text=text,
        kind=kind,
        task=task,
        source=LessonSource.LEARNED,
        workspace=workspace,
        tags=tags,
    )
