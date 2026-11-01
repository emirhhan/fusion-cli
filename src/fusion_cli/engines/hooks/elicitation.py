"""`Elicitation`/`ElicitationResult` kancalarının oturum tarafı (#90, #125) — Claude Code.

Eşleştirici MCP sunucusunun adıdır. Girdi: `mcp_server_name`, `message`, `mode`
(form|url), formda `requested_schema`, url kipinde `url` ve `elicitation_id`;
ElicitationResult'ta ek olarak kullanıcının `action`'ı ve `content`'i. Çıktı:
`hookSpecificOutput.action` (+ `content`); `action`'sız çıktı yok sayılır, çıkış 2 isteği
(ya da yanıtı) `decline` yapar. Soru kullanıcıya açılırken `Notification(elicitation_dialog)`,
kullanıcı yanıtlayınca `Notification(elicitation_response)`, sunucu url kipindeki isteğin
bittiğini bildirince `Notification(elicitation_complete)` arka planda çalışır.
"""

from __future__ import annotations

from ...core.hooks.events import HookEvent, HookVerdict
from ...mcp_bridge.elicitation_hooks import ElicitationAnswer, ElicitationRequest
from ...ui import messages
from .notify import NOTIFICATION_TITLE
from .session import HookSession

#: Claude bildirim türleri.
ELICITATION_DIALOG = "elicitation_dialog"
ELICITATION_RESPONSE = "elicitation_response"
ELICITATION_COMPLETE = "elicitation_complete"
_DECLINE = ElicitationAnswer("decline")


def _fields(request: ElicitationRequest) -> dict[str, object]:
    fields: dict[str, object] = {
        "mcp_server_name": request.server,
        "message": request.message,
        "mode": request.mode,
    }
    if request.mode == "url":
        fields["url"] = request.url
        if request.elicitation_id:
            fields["elicitation_id"] = request.elicitation_id
    elif request.requested_schema is not None:
        fields["requested_schema"] = dict(request.requested_schema)
    return fields


def _answer(verdict: HookVerdict) -> ElicitationAnswer | None:
    if verdict.blocked:
        return _DECLINE
    if not verdict.elicitation_action:
        return None
    return ElicitationAnswer(verdict.elicitation_action, verdict.elicitation_content)


class SessionElicitationHooks:
    """`mcp_bridge.elicitation_hooks.ElicitationHooks`: kancaları bu oturumda çalıştırır."""

    def __init__(self, session: HookSession) -> None:
        self._session = session

    async def before(self, request: ElicitationRequest) -> ElicitationAnswer | None:
        if not self._session.has(HookEvent.ELICITATION):
            return None
        verdict = await self._session.emit(
            HookEvent.ELICITATION, subjects=(request.server,), fields=_fields(request)
        )
        return _answer(verdict)

    def dialog(self, request: ElicitationRequest) -> None:
        self._notify(ELICITATION_DIALOG, messages.HOOKS_ELICITATION_NOTICE, request.server)

    def completed(self, server: str, elicitation_id: str) -> None:
        del elicitation_id  # bildirim girdisinde yeri yok (notification_type/message/title)
        self._notify(ELICITATION_COMPLETE, messages.HOOKS_ELICITATION_COMPLETE_NOTICE, server)

    async def after(
        self, request: ElicitationRequest, answer: ElicitationAnswer
    ) -> ElicitationAnswer:
        self._notify(
            ELICITATION_RESPONSE, messages.HOOKS_ELICITATION_RESPONSE_NOTICE, request.server
        )
        if not self._session.has(HookEvent.ELICITATION_RESULT):
            return answer
        fields = {**_fields(request), "action": answer.action}
        if answer.content is not None:
            fields["content"] = dict(answer.content)
        verdict = await self._session.emit(
            HookEvent.ELICITATION_RESULT, subjects=(request.server,), fields=fields
        )
        return _answer(verdict) or answer

    def _notify(self, kind: str, template: str, server: str) -> None:
        session = self._session
        if not session.has(HookEvent.NOTIFICATION):
            return
        message = template.format(server=server)
        session.spawn(lambda: session.notify(kind, message, title=NOTIFICATION_TITLE))
