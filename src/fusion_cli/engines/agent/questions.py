"""İsteğe bağlı soruların tura ait görev ve sonuç sahipliği."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from enum import StrEnum
from itertools import count


class QuestionState(StrEnum):
    """Bekleme hiçbir zaman kullanıcı cevabı veya izin sayılmaz."""

    PENDING = "pending"
    ANSWERED = "answered"
    SKIPPED = "skipped"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class QuestionResult:
    """Modelin görebileceği açık soru sonucu."""

    question_id: str
    state: QuestionState
    text: str = ""


class PendingUserQuestions:
    """Görevler turdan uzun yaşayamaz; yalnız açık cevap sonuç olur."""

    def __init__(self) -> None:
        self._ids = count(1)
        self._tasks: dict[str, asyncio.Task[QuestionResult]] = {}
        self._answers: dict[str, asyncio.Future[str]] = {}

    def start(self, answer: Awaitable[str]) -> QuestionResult:
        """Cevabı sahipli görevde beklet; çağırana pending makbuzu ver."""
        identifier = f"optional:{next(self._ids)}"
        owned = asyncio.ensure_future(answer)
        self._answers[identifier] = owned
        self._tasks[identifier] = asyncio.create_task(self._wait(identifier, owned))
        return QuestionResult(identifier, QuestionState.PENDING)

    async def _wait(self, identifier: str, answer: Awaitable[str]) -> QuestionResult:
        try:
            text = await answer
        except asyncio.CancelledError:
            # Kanalın kendi Future'ı kapanırsa bağımsız tur iptal edilmez.
            # Sahipli görevin doğrudan iptali (stop/close) ise gerçek iptaldir.
            task = asyncio.current_task()
            if task is not None and task.cancelling():
                raise
            return QuestionResult(identifier, QuestionState.UNAVAILABLE)
        except Exception:
            logging.getLogger(__name__).error("İsteğe bağlı sorunun cevabı alınamadı.")
            return QuestionResult(identifier, QuestionState.UNAVAILABLE)
        return QuestionResult(
            identifier, QuestionState.ANSWERED if text else QuestionState.SKIPPED, text
        )

    @property
    def pending(self) -> bool:
        """Henüz cevaplanmamış soru var mı?"""
        return any(not task.done() for task in self._tasks.values())

    @property
    def ready(self) -> bool:
        """Modele henüz iletilmemiş sonuç var mı?"""
        return any(task.done() for task in self._tasks.values())

    def drain(self) -> tuple[QuestionResult, ...]:
        """Tamamlanan sonuçları bir kez tüket."""
        ready = tuple(identifier for identifier, task in self._tasks.items() if task.done())
        for identifier in ready:
            self._answers.pop(identifier)
        return tuple(self._tasks.pop(identifier).result() for identifier in ready)

    async def close(self) -> None:
        """Tur sonunda tüm bekleyen görevleri iptal et ve bekle."""
        tasks = tuple(self._tasks.values())
        answers = tuple(self._answers.values())
        self._tasks.clear()
        self._answers.clear()
        for answer in answers:
            if not answer.done():
                answer.cancel()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, *answers, return_exceptions=True)
