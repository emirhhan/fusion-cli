"""`Notification` kancası: kullanıcıdan izin istenirken (P-009, `permission_prompt`).

Onay politikaları kullanıcıya yalnız `Prompter.confirm` üzerinden sorar; bu sarmalayıcı
sorudan HEMEN önce kancayı çalıştırır (ör. masaüstü bildirimi, telefon mesajı) ve cevabı
olduğu gibi döndürür. Kanca hatası soruyu engellemez.
"""

from __future__ import annotations

from ...ui import messages
from ..agent.approval import ApprovalAnswer, ApprovalReply, ApprovalRequest, Prompter
from .session import HookSession

#: Claude Code'un izin istemi bildirim türü.
PERMISSION_PROMPT = "permission_prompt"


class NotifyingPrompter:
    """`confirm` öncesinde `Notification` kancalarını çalıştıran `Prompter`."""

    def __init__(self, inner: Prompter, session: HookSession) -> None:
        self._inner = inner
        self._session = session

    async def confirm(self, request: ApprovalRequest) -> bool | ApprovalAnswer | ApprovalReply:
        await self._session.notify(
            PERMISSION_PROMPT, messages.HOOKS_PERMISSION_NOTICE.format(tool=request.tool.name)
        )
        return await self._inner.confirm(request)


def notifying(prompter: Prompter, session: HookSession | None) -> Prompter:
    """Oturumda `Notification` kancası varsa sarmala; yoksa aynı nesne (ek maliyet yok)."""
    from ...core.hooks.events import HookEvent

    if session is None or not session.has(HookEvent.NOTIFICATION):
        return prompter
    return NotifyingPrompter(prompter, session)
