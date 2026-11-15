"""`PermissionRequest` kancası: Fusion kullanıcıya izin sormak üzereyken (Claude Code).

Eşleştirici araç adıdır (PreToolUse ile aynı değerler); girdi `tool_name`, `tool_input`
(MCP'de `mcp_server`), `tool_use_id` YOK. `decision.behavior: allow` soruyu sormadan
izin verir (deny/ask kuralları bu noktadan önce değerlendirilmiştir); `deny` reddeder,
`message` modele gerekçe olarak gider, `interrupt: true` turu durdurur. Kararsız kanca
akışı değiştirmez: soru kullanıcıya (etkileşimsiz oturumda "sorulamadı") gider.
"""

from __future__ import annotations

from pathlib import Path

from ...core.hooks.events import HookEvent
from ..hooks.session import HookSession
from .approval import ApprovalAnswer, ApprovalReply, ApprovalRequest
from .hook_bridge import tool_hook_fields

#: `message` boş ret için modele giden gerekçe.
DENIED_BY_HOOK = "PermissionRequest kancası izni reddetti"


async def permission_request(
    session: HookSession, request: ApprovalRequest
) -> ApprovalAnswer | ApprovalReply | None:
    """Kanca kararı; karar yoksa `None` (soru kullanıcıya gider)."""
    if not session.has(HookEvent.PERMISSION_REQUEST):
        return None
    root: Path = session.project_dir or session.root
    fields = tool_hook_fields(request.tool.name, request.args, root=root)
    verdict = await session.emit(
        HookEvent.PERMISSION_REQUEST,
        subjects=(str(fields["tool_name"]),),
        fields=fields,
        target=(request.tool.name, request.args),
    )
    if verdict.permission == "allow":
        return ApprovalAnswer.ONCE
    if verdict.permission != "deny":
        return None
    if verdict.halt:
        return ApprovalAnswer.DENY
    return ApprovalReply(ApprovalAnswer.DENY, verdict.reason or DENIED_BY_HOOK)
