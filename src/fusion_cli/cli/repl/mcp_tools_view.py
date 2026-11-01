"""`/mcp tools <ad>`: bağlı sunucunun araçları tam adları ve izin durumlarıyla (#250).

Claude Code `/mcp` panelinde sunucu seçilince araçları tam adlarıyla (`mcp__<sunucu>__<araç>`)
ve izin ayarıyla gösterir; Fusion aynı bilgiyi metin olarak verir. Durum izin kurallarından
(`permissions.allow|ask|deny`) hesaplanır; kural yoksa çağrı oturumun izin kipine göre sorulur.
"""

from __future__ import annotations

from ...ui import mcp_messages

_MCP_PREFIX = "mcp__"
_DECISION_LABELS = {"allow": "izinli", "ask": "her çağrıda sorar", "deny": "reddedildi"}


def full_name(fusion_name: str) -> str:
    """Fusion kayıt adı (`sunucu__araç`) → Claude tam adı (`mcp__sunucu__araç`)."""
    return fusion_name if fusion_name.startswith(_MCP_PREFIX) else f"{_MCP_PREFIX}{fusion_name}"


def _decision(state: object, fusion_name: str) -> str:
    from ...tools.permission_match import evaluate

    rules_of = getattr(state, "permission_rules", None)
    if not callable(rules_of):
        return mcp_messages.TOOL_NO_RULE
    match = evaluate(rules_of(), fusion_name, {}, getattr(state, "root", None))
    if match is None:
        return mcp_messages.TOOL_NO_RULE
    return _DECISION_LABELS.get(match.decision.value, match.decision.value)


def tools_view(state: object, name: str) -> str:
    """Sunucunun araç listesi; bağlı değilse ne yapılacağını söyleyen tek satır."""
    from ...mcp_bridge.pool import connected_mcp_client

    if not name:
        return mcp_messages.TOOLS_USAGE
    client = connected_mcp_client(name)
    names_of = getattr(client, "registered_tool_names", None)
    if client is None or not callable(names_of):
        return mcp_messages.TOOLS_NOT_CONNECTED.format(name=name)
    names = tuple(names_of(name))
    if not names:
        return mcp_messages.TOOLS_NONE.format(name=name)
    rows = [f"· {full_name(tool)} — {_decision(state, tool)}" for tool in names]
    return "\n".join((mcp_messages.TOOLS_HEADER.format(name=name, count=len(names)), *rows))
