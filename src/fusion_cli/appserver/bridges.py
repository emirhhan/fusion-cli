"""Motorun olay ve soru dikişlerini uygulama teline bağlar.

Motor terminali tanımaz; olayları bir ``EventSink``'e yayar ve kullanıcı
kararlarını bir ``Prompter`` ile ``UserAsker``'dan ister. Bu modül, bu
sözleşmeleri uygulama protokolüne taşır.
"""

from __future__ import annotations

import asyncio
import json
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import replace
from hashlib import sha256
from itertools import count
from pathlib import Path
from uuid import uuid4

from ..core.constants import APPROVAL_UNANSWERED_TIMEOUT_S, QUESTION_RECEIPT_HISTORY_LIMIT
from ..core.events import Event, ToolCallRepaired, ToolExecuted, ToolStarted
from ..core.redaction import redact
from ..core.submission import SubmissionReceipt
from ..engines.agent.approval import ApprovalAnswer, ApprovalReply, ApprovalRequest
from ..engines.agent.engine_tools import QuestionOption
from ..engines.agent.permission_persist import always_description
from ..ui import messages
from ..ui.chrome_site_labels import site_options
from .approval_preview import onizleme_diffi
from .approval_summary import approval_summary
from .protocol import encode_error, encode_event, encode_question
from .serialize import event_to_dict

#: Onay kartında tek argüman değerinin en çok karakteri; kalanı "… N karakter daha".
APPROVAL_ARG_PREVIEW_MAX_CHARS = 2_000
#: Kullanıcının onay cevabına eklediği notun en çok karakteri (P-013).
APPROVAL_NOTE_MAX_CHARS = 1_000

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

    def correlate(self, event: Event) -> Event:
        """Makbuzun tek sıra otoritesini fanout öncesinde ve legacy çağrıda kullan."""
        if self._receipt is None:
            return event
        attempt_id = self._receipt.attempt_id
        session_id = self._receipt.key.conversation_id
        prefix = f"{attempt_id}:"
        has_receipt_id = (
            event.event_id is not None
            and event.event_id.startswith(prefix)
            and event.event_id[len(prefix) :].isdecimal()
            and event.session_id == session_id
            and event.turn_id == attempt_id
        )
        event = replace(
            event,
            event_id=event.event_id if has_receipt_id else f"{prefix}{next(self._sequence)}",
            session_id=session_id,
            turn_id=attempt_id,
            schema_version=1,
        )
        if isinstance(event, (ToolStarted, ToolExecuted, ToolCallRepaired)):
            event = replace(event, attempt_id=attempt_id)
        return event

    def handle(self, event: Event) -> None:
        """Olayı tek bir protokol satırı olarak ilet.

        `event_to_dict` desteklenmeyen bir alan tipinde `TypeError`, `encode_event`
        dairesel yapıda `ValueError` fırlatabilir (bkz. `serialize.py::_plain`).
        `EventBus._dispatch` bu istisnayı yakalayıp kimsenin okumadığı
        `failures` listesine yazar — olay sessizce kaybolurdu.
        Burada yakalanıp `ProtocolError` olayına çevrilir: uygulama en azından
        BİR olayın iletilemediğini görür.
        """
        try:
            correlated = self.correlate(event)
            payload = event_to_dict(correlated)
            if self._receipt is not None:
                # FusionCompleted özet serileştiricisi üst alanları düşürür; kimlik
                # yeniden üretilmez, ortak sınırın verdiği alanlar aynen taşınır.
                payload.update(
                    event_id=correlated.event_id,
                    session_id=correlated.session_id,
                    turn_id=correlated.turn_id,
                    schema_version=correlated.schema_version,
                )
            self._writer(encode_event(payload))
        except (TypeError, ValueError):
            # `ValueError`: dairesel yapı / kodlanamayan değer (`json.dumps`). Yazar tarafı
            # kopmuşsa (`BrokenPipeError`) `server._stdout_writer` süreci zaten sonlandırır.
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
        approval_timeout_s: float = APPROVAL_UNANSWERED_TIMEOUT_S,
        edit_fuzzy_match: bool = True,
        on_app_denied: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self._edit_fuzzy_match = edit_fuzzy_match
        #: Masaüstü kartında "Her zaman reddet" (P-007): uygulamayı `desktop.denied_apps`'e yazar.
        self._on_app_denied = on_app_denied
        #: Bu turda "Her zaman reddet" denen uygulamalar (hedef anahtarı). Turun ayarı tur başında
        #: alınmış bir kopyadır; gerekçeli ret turu sürdürdüğü için aynı uygulamanın sonraki
        #: çağrısı kart açmadan reddedilir (ölçüldü, 31 Ekim: kart yeniden açılıyordu).
        self._denied_apps: set[str] = set()
        self._writer = writer
        self._approval_timeout_s = approval_timeout_s
        self._pending = pending
        self._namespace = namespace
        self._on_closed = on_closed
        #: Tarayıcıda tıklanacak öğenin adı (ref → ad); kart "e52" yerine adı gösterir.
        self._element_name = element_name
        #: Önizleme diffi için proje kökü. Verilmezse önizleme üretilmez;
        #: onay akışı bundan bağımsız çalışır.
        self._root = root

    async def confirm(self, request: ApprovalRequest) -> ApprovalAnswer | ApprovalReply:
        """Onay isteğini ilet ve güvenli varsayılanla kullanıcı kararını döndür.

        Cevaptaki `not` alanı (P-013) kararla birlikte taşınır: ret gerekçesi modele gider.
        """
        target = request.desktop_target
        if target is not None and target.key in self._denied_apps:
            return ApprovalReply(
                ApprovalAnswer.DENY, messages.BILGISAYAR_DENIED_IN_TURN.format(app=target.app)
            )
        element = (
            self._element_name(request.args.get("ref")) if self._element_name is not None else None
        )
        baslik, hedef = approval_summary(request.tool.name, request.args, element=element or "")
        payload: dict[str, object] = {
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
            "secenekler": _approval_options(request, self._root),
            # İsteyen alt ajan (P-034): kart "Alt ajan X izin istiyor" der; ana ajanda None.
            "ajan": request.agent_label or None,
            # Eşleşen izin kuralı ve "not ekle" desteği (P-001, P-013).
            "kural": request.rule,
            "not_alinir": True,
            # Masaüstü hedefi (P-007): uygulama adı, kademe, kategori uyarısı, tıklanan öğe.
            "masaustu": _desktop_payload(request),
        }
        data = await self._ask_approval(payload, request)
        choice = data.get("secim")
        raw_note = data.get("not")
        note = raw_note.strip()[:APPROVAL_NOTE_MAX_CHARS] if isinstance(raw_note, str) else ""
        if choice == "once":
            answer: ApprovalAnswer = ApprovalAnswer.ONCE
        elif choice == "session" and request.can_remember:
            answer = ApprovalAnswer.SESSION
        elif choice == "always" and request.can_persist:
            answer = ApprovalAnswer.ALWAYS
        else:
            answer = ApprovalAnswer.DENY
            if choice == "never":
                await self._deny_app(request)
        return ApprovalReply(answer, note) if note else answer

    async def _deny_app(self, request: ApprovalRequest) -> None:
        """Uygulamayı kalıcı ret listesine yaz (sahip oturum yazar ve canlı ayarı günceller)."""
        target = request.desktop_target
        if target is None:
            return
        self._denied_apps.add(target.key)
        if self._on_app_denied is not None:
            await self._on_app_denied(target.app)

    def _onizleme(self, request: ApprovalRequest) -> str:
        """Düzenleme onaylarında değişiklik önizlemesi; üretilemezse boş metin."""
        if self._root is None:
            return ""
        try:
            return onizleme_diffi(
                request.tool.name,
                dict(request.args),
                self._root,
                edit_fuzzy_match=self._edit_fuzzy_match,
            )
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

    async def _ask_approval(
        self, payload: dict[str, object], request: ApprovalRequest
    ) -> dict[str, object]:
        """Onayı sor; süre dolana dek cevap gelmezse boş cevap (= RED) döndür ve olay yay.

        Ölçüldü (30 Ekim): zaman aşımı yoktu; kullanıcı yokken tur ve turu tutan kilit sonsuza
        dek açık kalıyordu. İptal `_ask_wire`'ın `finally`'sine ulaşır: bekleyen kayıt
        silinir, `SoruKapandi` yayılır, geç gelen cevap hiçbir soruyla eşleşmez.
        """
        asked: list[str] = []
        try:
            # `asyncio.timeout` aynı görevde çalışır (`wait_for` gibi ikinci görev açmaz): soru
            # tele, çağıran ilk `await`te yazılmış olur.
            async with asyncio.timeout(self._approval_timeout_s):
                return await self._ask_wire(payload, on_asked=asked.append)
        except TimeoutError:
            self._writer(
                encode_event(
                    {
                        "olay": "OnayZamanAsimi",
                        "id": asked[0] if asked else "",
                        "arac": request.tool.name,
                        "sure_s": self._approval_timeout_s,
                        "mesaj": messages.APPROVAL_TIMED_OUT.format(
                            arac=request.tool.name, dakika=round(self._approval_timeout_s / 60)
                        ),
                    }
                )
            )
            return {}

    async def _ask_wire(
        self, payload: dict[str, object], on_asked: Callable[[str], None] | None = None
    ) -> dict[str, object]:
        """Soruyu ilet, eş kimlikli cevabı bekle; kapanışta boş cevap döndür."""
        identifier, future = self._pending.new_question(self._namespace)
        if on_asked is not None:
            on_asked(identifier)
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
    return [f"{name}={_preview_value(value)}" for name, value in sorted(request.args.items())]


def _preview_value(value: object) -> str:
    """Tek argüman değerinin onay kartı gösterimi: sırlar maskeli, uzunluk sınırlı.

    Ölçüldü (30 Ekim): `write_file(content=<2 MB>)` tüm içeriği onay isteğine ve
    Chrome akışına basıyordu; `history_view` aynı değeri `redact` ediyordu, burası etmiyordu.
    """
    raw = repr(value)
    # Önce kes, sonra maskele: `redact` çok uzun, boşluksuz bir gövdede (base64) çok yavaşlıyor.
    if len(raw) <= APPROVAL_ARG_PREVIEW_MAX_CHARS:
        return redact(raw)
    hidden = len(raw) - APPROVAL_ARG_PREVIEW_MAX_CHARS
    return f"{redact(raw[:APPROVAL_ARG_PREVIEW_MAX_CHARS])}… {hidden} karakter daha"


def _approval_options(request: ApprovalRequest, root: Path | None = None) -> list[dict[str, str]]:
    """Yıkıcı istekte oturum izni olmadan onay seçeneklerini üret.

    `can_persist` istekte "bir daha sorma" (kalıcı kural, P-003) de sunulur; açıklama
    yazılacak kuralı gösterir ki kullanıcı neye izin verdiğini görsün.
    """
    target = request.desktop_target
    if target is not None and request.consent_key is not None:
        # Uygulama onayı (#426): Claude'daki gibi yalnız "Allow for this session / Deny";
        # tek çağrılık "Evet" ve "Her zaman reddet" yok (ret listesi Ayarlar'dan yönetilir).
        session = {
            "deger": "session",
            "etiket": messages.BILGISAYAR_APPROVAL_SESSION.format(app=target.app),
        }
        if request.remembered_scope_description:
            session["aciklama"] = request.remembered_scope_description
        return [session, {"deger": "deny", "etiket": messages.TUI_APPROVAL_DENY}]
    site = site_options(request)
    if site is not None:
        # Chrome site izni (#435): Allow this action / Always allow… / Decline.
        return site
    options = [{"deger": "once", "etiket": messages.TUI_APPROVAL_ONCE}]
    if request.can_remember:
        label = (
            messages.BILGISAYAR_APPROVAL_SESSION.format(app=target.app)
            if target is not None and request.consent_key is not None
            else messages.TUI_APPROVAL_SESSION
        )
        session = {"deger": "session", "etiket": label}
        description = request.remembered_scope_description
        if description:
            session["aciklama"] = description
        options.append(session)
    if request.can_persist:
        options.append(
            {
                "deger": "always",
                "etiket": messages.TUI_APPROVAL_ALWAYS,
                # Kapsamı da söyler: kullanıcı dosyasına düşüyorsa "TÜM PROJELER" (P-003).
                "aciklama": always_description(request, root),
            }
        )
    options.append({"deger": "deny", "etiket": messages.TUI_APPROVAL_DENY})
    return options


def _desktop_payload(request: ApprovalRequest) -> dict[str, object] | None:
    target = request.desktop_target
    return target.payload() if target is not None else None
