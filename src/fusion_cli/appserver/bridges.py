"""Motorun olay ve soru dikişlerini uygulama teline bağlar.

Motor terminali tanımaz; olayları bir ``EventSink``'e yayar ve kullanıcı
kararlarını bir ``Prompter`` ile ``UserAsker``'dan ister. Bu modül, bu
sözleşmeleri uygulama protokolüne taşır.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from itertools import count

from ..core.events import Event
from ..engines.agent.approval import ApprovalAnswer, ApprovalRequest
from ..engines.agent.engine_tools import QuestionOption
from ..ui import messages
from .protocol import encode_event, encode_question
from .serialize import event_to_dict

#: Tek satır yazan taraf. Testte listeye, üretimde stdout'a yazar.
Writer = Callable[[str], None]


class ProtocolSink:
    """Olayları tel üzerine yazan ``EventSink``."""

    def __init__(self, writer: Writer) -> None:
        self._writer = writer

    def handle(self, event: Event) -> None:
        """Olayı tek bir protokol satırı olarak ilet."""
        self._writer(encode_event(event_to_dict(event)))


class PendingQuestions:
    """Cevap bekleyen soruların kimlikten geleceğe eşlemesi."""

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[dict[str, object]]] = {}
        self._ids = count(1)

    def new_question(self) -> tuple[str, asyncio.Future[dict[str, object]]]:
        """Yeni soru kimliğini ve cevabını taşıyacak geleceği üret."""
        identifier = str(next(self._ids))
        future = asyncio.get_running_loop().create_future()
        self._pending[identifier] = future
        return identifier, future

    def resolve(self, question_id: str, data: dict[str, object]) -> bool:
        """Cevabı ilgili soruya bağla; eşleşme yoksa ``False`` döndür."""
        future = self._pending.pop(question_id, None)
        if future is None or future.done():
            return False
        future.set_result(data)
        return True

    def discard(self, question_id: str, future: asyncio.Future[dict[str, object]]) -> None:
        """Yalnız bu gelecek hâlâ kimliğe bağlıysa bekleyen kaydı kaldır."""
        if self._pending.get(question_id) is future:
            self._pending.pop(question_id)

    def cancel_all(self) -> None:
        """Bekleyen soruları boş cevapla kapat; uygulama kapanmış olabilir."""
        for future in self._pending.values():
            if not future.done():
                future.set_result({})
        self._pending.clear()


class ProtocolPrompter:
    """Onay ve soruları tel üzerinden soran ``Prompter`` ve ``UserAsker``."""

    def __init__(self, writer: Writer, pending: PendingQuestions) -> None:
        self._writer = writer
        self._pending = pending

    async def confirm(self, request: ApprovalRequest) -> ApprovalAnswer:
        """Onay isteğini ilet ve güvenli varsayılanla kullanıcı kararını döndür."""
        data = await self._ask_wire(
            {
                "tur": "onay",
                "arac": request.tool.name,
                "argumanlar": sorted(str(name) for name in request.args),
                "tehlike": request.danger,
                "secenekler": _approval_options(request),
            }
        )
        choice = data.get("secim")
        if choice == "once":
            return ApprovalAnswer.ONCE
        if choice == "session" and request.danger is None:
            return ApprovalAnswer.SESSION
        return ApprovalAnswer.DENY

    async def ask(
        self,
        question: str,
        options: tuple[QuestionOption, ...] = (),
        recommended: str | None = None,
    ) -> str:
        """Serbest metin sorusunu ilet ve geçerli metin cevabını döndür."""
        data = await self._ask_wire(
            {
                "tur": "soru",
                "soru": question,
                "secenekler": [
                    {"etiket": option.label, "aciklama": option.description} for option in options
                ],
                "onerilen": recommended,
            }
        )
        answer = data.get("metin")
        return answer if isinstance(answer, str) else ""

    async def _ask_wire(self, payload: dict[str, object]) -> dict[str, object]:
        """Soruyu ilet, eş kimlikli cevabı bekle; kapanışta boş cevap döndür."""
        identifier, future = self._pending.new_question()
        self._writer(encode_question(identifier, payload))
        try:
            return await future
        finally:
            self._pending.discard(identifier, future)


def _approval_options(request: ApprovalRequest) -> list[dict[str, str]]:
    """Yıkıcı istekte oturum izni olmadan onay seçeneklerini üret."""
    options = [{"deger": "once", "etiket": messages.TUI_APPROVAL_ONCE}]
    if request.danger is None:
        options.append({"deger": "session", "etiket": messages.TUI_APPROVAL_SESSION})
    options.append({"deger": "deny", "etiket": messages.TUI_APPROVAL_DENY})
    return options
