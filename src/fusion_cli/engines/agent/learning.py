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
import re
from pathlib import Path

from ...config.models import Config
from ...core.memory import Lesson, LessonKind, LessonMemory, LessonSource
from ...core.types import CompletionRequest, Message
from ...providers.factory import build_provider
from . import history

_PROMPT = (Path(__file__).parent / "prompts" / "lessons.txt").read_text(encoding="utf-8")
_JSON_ARRAY = re.compile(r"\[.*\]", re.DOTALL)

#: Ders çıkarımı için token bütçesi. Kısa dersler istiyoruz.
EXTRACT_MAX_TOKENS = 400
#: Bir turdan alınacak en fazla ders. Model coşarsa bellek çöple dolmasın.
MAX_LESSONS_PER_TURN = 3


def parse_lessons(text: str, task: str) -> tuple[Lesson, ...]:
    """Model çıktısındaki JSON diziyi derslere çevir. Bozuksa boş döner."""
    match = _JSON_ARRAY.search(text or "")
    if match is None:
        return ()
    try:
        items = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return ()
    if not isinstance(items, list):
        return ()

    lessons: list[Lesson] = []
    for item in items:
        lesson = _to_lesson(item, task)
        if lesson is not None:
            lessons.append(lesson)
    return tuple(lessons[:MAX_LESSONS_PER_TURN])


async def extract_lessons(
    task: str, messages: list[Message], *, config: Config
) -> tuple[Lesson, ...]:
    """Oturumdan ders çıkar. Model erişilemezse ya da çıktı bozuksa boş döner."""
    trace = history.transcript(messages)
    if not trace.strip():
        return ()

    request = CompletionRequest(
        messages=(Message("user", _PROMPT.replace("{task}", task).replace("{trace}", trace)),),
        temperature=0.1,
        max_tokens=EXTRACT_MAX_TOKENS,
        timeout_s=config.runtime.request_timeout_s,
        max_retries=config.runtime.max_retries,
    )
    # Sessiz sağlayıcı: ders çıkarımı arka plan işidir, kullanıcı ilerlemesini kirletmez.
    result = await build_provider(config.judge, publisher=None).complete(request)
    return parse_lessons(result.text, task) if result.ok else ()


def store_lessons(lessons: tuple[Lesson, ...], memory: LessonMemory) -> int:
    """Dersleri belleğe yaz; YENİ eklenen sayısını döndür (tekilleştirme belleğin işi)."""
    return sum(1 for lesson in lessons if memory.add(lesson))


def _to_lesson(item: object, task: str) -> Lesson | None:
    if not isinstance(item, dict):
        return None
    text = str(item.get("lesson", "")).strip()
    if not text:
        return None
    try:
        kind = LessonKind(str(item.get("kind", "")).strip().lower())
    except ValueError:
        return None
    return Lesson(text=text, kind=kind, task=task, source=LessonSource.LEARNED)
