"""MCP elicitation isteğini `Elicitation`/`ElicitationResult` kancalarından geçirme (#90, #125).

Claude Code: sunucu görev ortasında kullanıcıdan girdi isteyince önce `Elicitation` kancaları
çalışır; `hookSpecificOutput.action` (accept|decline|cancel, accept'te `content`) dönerse
soru kullanıcıya hiç gösterilmez, çıkış 2 isteği reddeder (`decline`). Kanca karar vermezse
soru sorulur; kullanıcı yanıtlayınca (reddetse ya da vazgeçse de) yanıt sunucuya gitmeden
önce `ElicitationResult` kancaları çalışır ve `action` yanıtı değiştirebilir.

Bu modül `mcp_bridge` katmanındadır: kanca oturumunu tanımaz, yalnız kayıtlı bir
`ElicitationHooks` nesnesine danışır (motor katmanı `engines/hooks/elicitation.py` kaydeder).
Kullanıcıya soran iç geri çağırım varsa (`mcp_bridge.elicitation.elicitation_callback`) o
kullanılır; yoksa kanca karar vermediğinde istek `cancel` ile döner (kullanıcı yerine hiçbir
şey uydurulmaz).

Yetenek: soran modül de bağlanan oturumda `Elicitation` kancası da yoksa geri çağırım hiç
verilmez (`elicitation_callback_for` → None); SDK elicitation yeteneğini sunucuya bildirmez
ve sunucu yeteneksiz yoluna düşer (sessiz `cancel` yok).

Oturum başına: danışman süreç geneli değil, oturum bağlamına (ContextVar) kaydedilir. MCP
bağlantısı oturumlar arasında paylaşılabildiği ve sunucu isteği bağlantının alım görevinden
geldiği için istek, o sunucuya o an çağrı yapan oturumun danışmanına gider
(`elicitation_scope`); çağrı bitince kayıt düşer, kapanmış oturuma referans kalmaz.
"""

from __future__ import annotations

import contextlib
import importlib
import logging
from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Protocol, cast

from mcp import types
from mcp.client.session import ElicitationFnT, MessageHandlerFnT

_LOG = logging.getLogger(__name__)

Callback = Callable[[object, object], Awaitable[types.ElicitResult | types.ErrorData]]


@dataclass(frozen=True, slots=True)
class ElicitationRequest:
    """Kancaya giden istek (Claude girdi alanları)."""

    server: str
    mode: str
    message: str
    requested_schema: Mapping[str, object] | None = None
    url: str = ""
    elicitation_id: str = ""


@dataclass(frozen=True, slots=True)
class ElicitationAnswer:
    action: str
    content: Mapping[str, object] | None = None


class ElicitationHooks(Protocol):
    def handles(self, server: str) -> bool:
        """Bu sunucunun isteğini yanıtlayabilecek bir `Elicitation` kancası var mı?"""

    async def before(self, request: ElicitationRequest) -> ElicitationAnswer | None: ...

    def dialog(self, request: ElicitationRequest) -> None:
        """Soru kullanıcıya gösterilmek üzere (`Notification(elicitation_dialog)`)."""

    def completed(self, server: str, elicitation_id: str) -> None:
        """Sunucu url kipindeki isteğin bittiğini bildirdi (`elicitation_complete`)."""

    async def after(
        self, request: ElicitationRequest, answer: ElicitationAnswer
    ) -> ElicitationAnswer: ...


_CURRENT: ContextVar[ElicitationHooks | None] = ContextVar("fusion_elicitation_hooks", default=None)
#: Sunucu adı → o sunucuya şu an çağrı yapan oturumların danışmanları (son giren önce).
_ACTIVE: dict[str, list[ElicitationHooks]] = {}
#: url kipinde tamamlandı bildirimi çağrı bittikten sonra gelebilir: kimlik → danışman.
_URL_OWNERS: dict[str, ElicitationHooks] = {}
_URL_OWNER_LIMIT = 32


def register_elicitation_hooks(hooks: ElicitationHooks | None) -> None:
    """Bu oturum bağlamının kanca danışmanını kaydet (None: kaldır).

    Kaldırılan (None) danışmanın bekleyen URL elicitation sahiplikleri de düşer: modül
    düzeyindeki `_URL_OWNERS` kapanmış oturumu tutarsa, aynı kimlikli sonraki
    `elicitation/complete` bildirimi o eski oturumun kancalarına (eski köke) gidiyordu.
    Yeni danışmanla değiştirmede sahiplik korunur (tur değişse de URL akışı sürebilir).
    """
    previous = _CURRENT.get()
    if hooks is None and previous is not None:
        for elicitation_id in [key for key, owner in _URL_OWNERS.items() if owner is previous]:
            _URL_OWNERS.pop(elicitation_id, None)
    _CURRENT.set(hooks)


def registered_elicitation_hooks() -> ElicitationHooks | None:
    return _CURRENT.get()


@contextlib.contextmanager
def elicitation_scope(server: str) -> Iterator[None]:
    """Çağrı süresince sunucudan gelen elicitation bu bağlamın danışmanına gider."""
    hooks = _CURRENT.get()
    if hooks is None:
        yield
        return
    stack = _ACTIVE.setdefault(server, [])
    stack.append(hooks)
    try:
        yield
    finally:
        stack.remove(hooks)
        if not stack:
            _ACTIVE.pop(server, None)


def _hooks_for(server: str) -> ElicitationHooks | None:
    stack = _ACTIVE.get(server)
    return stack[-1] if stack else None


def _remember_url_owner(elicitation_id: str, hooks: ElicitationHooks) -> None:
    if not elicitation_id:
        return
    _URL_OWNERS[elicitation_id] = hooks
    while len(_URL_OWNERS) > _URL_OWNER_LIMIT:
        _URL_OWNERS.pop(next(iter(_URL_OWNERS)))


def request_of(server: str, params: object) -> ElicitationRequest:
    if isinstance(params, types.ElicitRequestURLParams):
        return ElicitationRequest(
            server=server,
            mode="url",
            message=params.message,
            url=str(params.url),
            elicitation_id=str(params.elicitationId or ""),
        )
    schema = getattr(params, "requestedSchema", None)
    return ElicitationRequest(
        server=server,
        mode="form",
        message=str(getattr(params, "message", "") or ""),
        requested_schema=dict(schema) if isinstance(schema, Mapping) else None,
    )


async def _cancel(context: object, params: object) -> types.ElicitResult:
    del context, params
    return types.ElicitResult(action="cancel")


def _asking_callback(server: str) -> Callback:
    """Kullanıcıya soran iç geri çağırım (MCP elicitation modülü kuruluysa)."""
    try:
        module = importlib.import_module(f"{__package__}.elicitation")
    except ImportError:
        return _cancel
    factory = getattr(module, "elicitation_callback", None)
    return cast(Callback, factory(server)) if callable(factory) else _cancel


def _result(answer: ElicitationAnswer) -> types.ElicitResult:
    content = dict(answer.content) if answer.action == "accept" and answer.content else None
    return types.ElicitResult(action=answer.action, content=content)  # type: ignore[arg-type]


def elicitation_callback_for(server: str, inner: Callback | None = None) -> ElicitationFnT | None:
    """Bağlantının geri çağırımı; yanıtlayacak taraf yoksa None (yetenek bildirilmez)."""
    asking = inner if inner is not None else _asking_callback(server)
    if asking is _cancel:
        hooks = _CURRENT.get()
        handles = getattr(hooks, "handles", None)
        if not (callable(handles) and handles(server)):
            return None
    return with_elicitation_hooks(server, asking)


def with_elicitation_hooks(server: str, inner: Callback | None = None) -> ElicitationFnT:
    """`ClientSession(elicitation_callback=…)`: kancalar + (karar yoksa) kullanıcıya sorma."""
    asking = inner if inner is not None else _asking_callback(server)

    async def _callback(context: object, params: object) -> types.ElicitResult | types.ErrorData:
        hooks = _hooks_for(server)
        if hooks is None:
            return await asking(context, params)
        request = request_of(server, params)
        if request.mode == "url":
            _remember_url_owner(request.elicitation_id, hooks)
        try:
            decided = await hooks.before(request)
        except Exception as error:  # kanca katmanı düşerse soru normal akışla sorulur
            _LOG.warning("Elicitation kancası çalışmadı: %s", type(error).__name__)
            decided = None
        if decided is not None:
            return _result(decided)
        if asking is _cancel:
            return await _cancel(context, params)  # soracak taraf yok: kullanıcı yanıtlamadı
        hooks.dialog(request)
        result = await asking(context, params)
        if not isinstance(result, types.ElicitResult):
            return result  # protokol hatası olduğu gibi sunucuya
        answer = ElicitationAnswer(result.action, result.content)
        try:
            final = await hooks.after(request, answer)
        except Exception as error:
            _LOG.warning("ElicitationResult kancası çalışmadı: %s", type(error).__name__)
            return result
        return _result(final)

    return cast(ElicitationFnT, _callback)


def with_completion_notice(server: str, inner: MessageHandlerFnT) -> MessageHandlerFnT:
    """`ClientSession(message_handler=…)`: `notifications/elicitation/complete` kancaya da gider."""

    async def _handle(message: object) -> None:
        root = getattr(message, "root", None)
        if isinstance(root, types.ElicitCompleteNotification):
            elicitation_id = str(root.params.elicitationId)
            hooks = _URL_OWNERS.pop(elicitation_id, None) or _hooks_for(server)
            if hooks is not None:
                hooks.completed(server, elicitation_id)
        await inner(message)  # type: ignore[arg-type]

    return cast(MessageHandlerFnT, _handle)
