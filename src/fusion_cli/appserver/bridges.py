"""Motorun olay ve soru dikişlerini uygulama teline bağlar.

Motor terminali tanımaz; olayları bir ``EventSink``'e yayar ve kullanıcı
kararlarını bir ``Prompter`` ile ``UserAsker``'dan ister. Bu modül, bu
sözleşmeleri uygulama protokolüne taşır.
"""

from __future__ import annotations

import asyncio
import json
from collections import OrderedDict
from collections.abc import Callable, Iterator
from hashlib import sha256
from itertools import count
from pathlib import Path
from uuid import uuid4

from ..core.constants import QUESTION_RECEIPT_HISTORY_LIMIT
from ..core.events import Event
from ..core.submission import SubmissionReceipt
from ..engines.agent.approval import ApprovalAnswer, ApprovalRequest
from ..engines.agent.engine_tools import QuestionOption
from ..ui import messages
from .approval_preview import onizleme_diffi
from .approval_summary import approval_summary
from .protocol import encode_error, encode_event, encode_question
from .serialize import event_to_dict

#: Tek satır yazan taraf. Testte listeye, üretimde stdout'a yazar.
Writer = Callable[[str], None]


class ProtocolSink:
    """Olayları tel üzerine yazan ``EventSink``."""

    def __init__(
        self,
        writer: Writer,
        *,
        receipt: SubmissionReceipt | None = None,
        sequence: Iterator[int] | None = None,
    ) -> None:
        self._writer = writer
        self._receipt = receipt
        self._sequence = sequence if sequence is not None else count(1)

    def handle(self, event: Event) -> None:
        """Olayı tek bir protokol satırı olarak ilet.

        `event_to_dict` desteklenmeyen bir alan tipinde `TypeError` fırlatabilir
        (bkz. `serialize.py::_plain`). `EventBus._dispatch` bu istisnayı yakalayıp
        kimsenin okumadığı `failures` listesine yazar — olay sessizce kaybolurdu.
        Burada yakalanıp `ProtocolError` olayına çevrilir: uygulama en azından
        BİR olayın iletilemediğini görür.
        """
        try:
            payload = event_to_dict(event)
            if self._receipt is not None:
                payload.update(
                    event_id=f"{self._receipt.attempt_id}:{next(self._sequence)}",
                    session_id=self._receipt.key.conversation_id,
                    turn_id=self._receipt.attempt_id,
                    schema_version=1,
                )
            self._writer(encode_event(payload))
        except TypeError:
            self._writer(
                encode_error(messages.APP_EVENT_SERIALIZE_FAILED.format(olay=type(event).__name__))
            )


class PendingQuestions:
    """Cevap bekleyen soruların kimlikten geleceğe eşlemesi."""

    def __init__(self, *, receipt_history_limit: int = QUESTION_RECEIPT_HISTORY_LIMIT) -> None:
        if receipt_history_limit < 1:
            raise ValueError("Cevap makbuzu penceresi pozitif olmalı.")
        self._receipt_history_limit = receipt_history_limit
        self._pending: dict[str, asyncio.Future[dict[str, object]]] = {}
        self._ids = count(1)
        self._epoch = uuid4().hex
        self._answered: OrderedDict[str, str] = OrderedDict()

    def new_question(self, namespace: str = "") -> tuple[str, asyncio.Future[dict[str, object]]]:
        """Yeni soru kimliğini ve cevabını taşıyacak geleceği üret."""
        sequence = f"{self._epoch}:{next(self._ids)}"
        identifier = f"{namespace}:question:{sequence}" if namespace else sequence
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

    def answer(self, question_id: str, data: dict[str, object]) -> bool:
        """Makbuzlu cevabı tek kez uygula; yakın cevapların güvenli tekrarına izin ver."""
        decision = data.get("decisionId")
        if not isinstance(decision, str) or not decision:
            return False
        digest = sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if question_id in self._answered:
            return self._answered[question_id] == digest
        if not self.resolve(question_id, data):
            return False
        self._answered[question_id] = digest
        if len(self._answered) > self._receipt_history_limit:
            self._answered.popitem(last=False)
        return True

    def discard(self, question_id: str, future: asyncio.Future[dict[str, object]]) -> None:
        """Yalnız bu gelecek hâlâ kimliğe bağlıysa bekleyen kaydı kaldır."""
        if self._pending.get(question_id) is future:
            self._pending.pop(question_id)

    def cancel_all(self) -> tuple[str, ...]:
        """Bekleyen soruları boş cevapla kapat; uygulama kapanmış olabilir."""
        identifiers = tuple(self._pending)
        for future in self._pending.values():
            if not future.done():
                future.set_result({})
        self._pending.clear()
        self._answered.clear()
        return identifiers


class ProtocolPrompter:
    """Onay ve soruları tel üzerinden soran ``Prompter`` ve ``UserAsker``."""

    def __init__(
        self,
        writer: Writer,
        pending: PendingQuestions,
        root: Path | None = None,
        element_name: Callable[[object], str | None] | None = None,
        namespace: str = "",
        on_closed: Callable[[str], None] | None = None,
    ) -> None:
        self._writer = writer
        self._pending = pending
        self._namespace = namespace
        self._on_closed = on_closed
        #: Tarayıcıda tıklanacak öğenin adı (ref → ad); kart "e52" yerine adı gösterir.
        self._element_name = element_name
        #: Önizleme diffi için proje kökü. Verilmezse önizleme üretilmez;
        #: onay akışı bundan bağımsız çalışır.
        self._root = root

    async def confirm(self, request: ApprovalRequest) -> ApprovalAnswer:
        """Onay isteğini ilet ve güvenli varsayılanla kullanıcı kararını döndür."""
        element = (
            self._element_name(request.args.get("ref")) if self._element_name is not None else None
        )
        baslik, hedef = approval_summary(request.tool.name, request.args, element=element or "")
        data = await self._ask_wire(
            {
                "tur": "onay",
                "arac": request.tool.name,
                "baslik": baslik,
                "hedef": hedef,
                "argumanlar": _preview_args(request),
                "tehlike": request.danger,
                # Neden soruluyor / silme hedefi (tehlike değil, bilgi).
                "neden": None if request.danger else request.note,
                # Kullanıcı "ne değişecek" sorusunu argümanlardan değil diff'ten
                # okumalı (bkz. `approval_preview`).
                "diff": self._onizleme(request),
                "secenekler": _approval_options(request),
            }
        )
        choice = data.get("secim")
        if choice == "once":
            return ApprovalAnswer.ONCE
        if choice == "session" and request.can_remember:
            return ApprovalAnswer.SESSION
        return ApprovalAnswer.DENY

    def _onizleme(self, request: ApprovalRequest) -> str:
        """Düzenleme onaylarında değişiklik önizlemesi; üretilemezse boş metin."""
        if self._root is None:
            return ""
        try:
            return onizleme_diffi(request.tool.name, dict(request.args), self._root)
        except Exception:  # pragma: no cover - önizleme onayı ASLA engellemez
            return ""

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
        identifier, future = self._pending.new_question(self._namespace)
        try:
            self._writer(encode_question(identifier, payload))
            return await future
        finally:
            self._pending.discard(identifier, future)
            if not future.done():
                future.cancel()
            if self._on_closed is not None:
                self._on_closed(identifier)


def _preview_args(request: ApprovalRequest) -> list[str]:
    """Onay için `ad=değer` çiftleri; terminal önizlemesiyle (`tui_loop._preview`)
    AYNI bilgiyi taşır.

    Önceki sürüm yalnız argüman ADLARINI gönderiyordu — kullanıcı `run_shell(command)`
    görüp hangi komutun çalışacağını bilmeden onaylıyordu. Bu redaksiyon zaten
    anlamsızdı: aynı değerler `ToolExecuted.args` olayıyla tam hâlde tele akıyordu
    (bkz. `core/events.py`); burada gizlemek yalnız onay kararını körleştiriyordu.
    Değerler terminaldeki gibi `repr()` ile taşınır — JSON'a çevrilemeyen bir tip
    (Path, dataclass, …) gelse bile tel bozulmaz.
    """
    return [f"{name}={value!r}" for name, value in sorted(request.args.items())]


def _approval_options(request: ApprovalRequest) -> list[dict[str, str]]:
    """Yıkıcı istekte oturum izni olmadan onay seçeneklerini üret."""
    options = [{"deger": "once", "etiket": messages.TUI_APPROVAL_ONCE}]
    if request.can_remember:
        session = {"deger": "session", "etiket": messages.TUI_APPROVAL_SESSION}
        description = request.remembered_scope_description
        if description:
            session["aciklama"] = description
        options.append(session)
    options.append({"deger": "deny", "etiket": messages.TUI_APPROVAL_DENY})
    return options
