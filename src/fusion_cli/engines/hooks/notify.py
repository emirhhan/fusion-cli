"""`PermissionRequest` ve `Notification` kancaları: kullanıcıdan izin istenirken.

Soru açılmadan önce `PermissionRequest` kancaları çalışır; karar verirlerse soru hiç
gösterilmez (bkz. `engines/agent/hook_permission.py`).

Claude Code gibi: onay sorusu açılır, kullanıcı ~6 sn yanıt vermezse kanca arka planda
tetiklenir; yanıt daha önce gelirse bildirim iptal edilir. Kanca soruyu ASLA bekletmez ve
kararı (hatalar dahil) yok sayılır.
"""

from __future__ import annotations

import asyncio
import contextlib

from ...ui import messages
from ..agent.approval import ApprovalAnswer, ApprovalReply, ApprovalRequest, Prompter
from .session import HookSession

#: Claude Code'un izin istemi bildirim türü.
PERMISSION_PROMPT = "permission_prompt"
#: Yanıtsız istemden sonra bildirim gecikmesi (Claude: yaklaşık 6 sn).
PERMISSION_NOTIFY_DELAY_S = 6.0
#: Bildirim başlığı (`title`).
NOTIFICATION_TITLE = "Fusion"


class NotifyingPrompter:
    """`confirm` öncesinde `Notification` kancalarını çalıştıran `Prompter`."""

    def __init__(self, inner: Prompter, session: HookSession, delay_s: float | None = None) -> None:
        self._inner = inner
        self._session = session
        self._delay_s = delay_s

    async def confirm(self, request: ApprovalRequest) -> bool | ApprovalAnswer | ApprovalReply:
        from ..agent.hook_permission import permission_request

        decided = await permission_request(self._session, request)
        if decided is not None:
            return decided
        message = messages.HOOKS_PERMISSION_NOTICE.format(tool=request.tool.name)
        notice = asyncio.get_running_loop().create_task(self._notify_later(message))
        try:
            return await self._inner.confirm(request)
        finally:
            if not notice.done():
                notice.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await notice

    async def _notify_later(self, message: str) -> None:
        await asyncio.sleep(PERMISSION_NOTIFY_DELAY_S if self._delay_s is None else self._delay_s)
        await self._session.notify(PERMISSION_PROMPT, message, title=NOTIFICATION_TITLE)


def notifying(prompter: Prompter, session: HookSession | None) -> Prompter:
    """Kanca oturumu varsa sarmala; tanım soru anında aranır (eşleşme yoksa süreç açılmaz).

    Ölçüldü (31 Ekim): sarmalama kararı tur başında, tanımlar tazelenmeden ÖNCE veriliyordu;
    yeni eklenen Notification kancası bir tur geç devreye giriyordu.
    """
    if session is None:
        return prompter
    return NotifyingPrompter(prompter, session)
