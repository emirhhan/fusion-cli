"""Kimseye sormayan onaylayıcı: `fusion agent` varsayılanı (Claude -p Manual kipi; #353).

Claude Code (permission-modes): "`claude -p` and Agent SDK runs with no permission mode set
start in Manual mode … Calls needing approval are denied unless you approve them with an allow
rule, hook, `canUseTool` callback, or `--permission-prompt-tool`." Allow kuralı ve kanca onayı
politikadan önce uygulanır; buraya gelen istek sorulmadan reddedilir.
"""

from __future__ import annotations

from typing import Any

from ..engines.agent.approval import ApprovalAnswer, ApprovalRequest
from ..ui import messages


class UnpromptedPrompter:
    """Her onay isteğine "sorulamadı" der; tur sürer, model gerekçeyi görür.

    Onay sorusu değil olan `ask_user` soruları (varsa) asıl sorucuya iletilir.
    """

    def __init__(self, asker: Any | None = None) -> None:
        self._asker = asker

    async def confirm(self, request: ApprovalRequest) -> ApprovalAnswer:
        del request
        return ApprovalAnswer.UNAVAILABLE

    async def ask(self, question: str, options: Any = (), recommended: str | None = None) -> str:
        if self._asker is None:
            return messages.NO_ANSWER_AVAILABLE
        answer: str = await self._asker.ask(question, options, recommended)
        return answer
