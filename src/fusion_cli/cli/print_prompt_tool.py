"""`--permission-prompt-tool mcp__<sunucu>__<araç>` — onay isteğini MCP aracına sor (#293).

Claude Code'da `-p` koşusunda onay gereken çağrı bu MCP aracına `{tool_name, input,
tool_use_id}` ile sorulur; araç metin içeriğinde `{"behavior": "allow", "updatedInput":
{...}}` ya da `{"behavior": "deny", "message": "..."}` döndürür. Araç bulunamazsa, hata
verirse ya da cevap çözülemezse istek reddedilmiş sayılır (tur sürer, model başka yol
dener). `updatedInput` Fusion'da çağrının argümanını değiştiremez; yok sayılır.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

from ..config.models import Config
from ..core.tools import Tool, ToolContext, ToolResult
from ..engines.agent.approval import ApprovalAnswer, ApprovalRequest
from .print_runtime import PrintPrompter
from .sdk_messages import claude_tool_name

ToolLoader = Callable[[str], Awaitable[Tool | None]]
_MCP_PREFIX = "mcp__"


def fusion_tool_name(name: str) -> str:
    """`mcp__sunucu__araç` → Fusion kayıt adı `sunucu__araç`."""
    cleaned = name.strip()
    return cleaned[len(_MCP_PREFIX) :] if cleaned.startswith(_MCP_PREFIX) else cleaned


def mcp_tool_loader(config: Config) -> ToolLoader:
    """Yapılandırmadaki MCP sunucularına bağlanıp adı verilen aracı döndüren yükleyici."""

    async def _load(name: str) -> Tool | None:
        from ..mcp_bridge.pool import ensure_mcp_tools
        from ..tools.registry import ToolRegistry

        registry = ToolRegistry()
        await ensure_mcp_tools(config.mcp_servers, registry)
        return registry.get(name)

    return _load


def decision_from(result: ToolResult) -> ApprovalAnswer:
    """Aracın cevabını karara çevir: yalnız açık `allow` onaydır."""
    payload: object = result.structured
    if not isinstance(payload, Mapping):
        try:
            payload = json.loads(result.output)
        except (TypeError, ValueError):
            return ApprovalAnswer.UNAVAILABLE
    if not isinstance(payload, Mapping) or not result.ok:
        return ApprovalAnswer.UNAVAILABLE
    behavior = str(payload.get("behavior", "")).strip().lower()
    return ApprovalAnswer.ONCE if behavior == "allow" else ApprovalAnswer.UNAVAILABLE


class PromptToolPrompter(PrintPrompter):
    """Onayları MCP aracına soran `-p` arayüzü."""

    def __init__(self, tool_name: str, loader: ToolLoader, *, root: Path) -> None:
        super().__init__()
        self._name = fusion_tool_name(tool_name)
        self._loader = loader
        self._root = root
        self._tool: Tool | None = None
        self._loaded = False
        self.errors: list[str] = []

    async def confirm(self, request: ApprovalRequest) -> bool | ApprovalAnswer:
        self.requests.append(request)
        tool = await self._resolve()
        if tool is None:
            return ApprovalAnswer.UNAVAILABLE
        args = {
            "tool_name": claude_tool_name(request.tool.name),
            "input": dict(request.args),
            "tool_use_id": str(getattr(request, "call_id", "") or ""),
        }
        try:
            outcome = tool.run(args, ToolContext(root=self._root))
            result = await outcome if inspect.isawaitable(outcome) else outcome
        except Exception as error:  # araç hatası onay değildir; reddedilmiş sayılır
            self.errors.append(str(error))
            return ApprovalAnswer.UNAVAILABLE
        return decision_from(result)

    async def _resolve(self) -> Tool | None:
        if not self._loaded:
            self._loaded = True
            try:
                self._tool = await self._loader(self._name)
            except Exception as error:  # bağlanamayan sunucu: istekler reddedilir
                self.errors.append(str(error))
            if self._tool is None:
                self.errors.append(f"onay aracı bulunamadı: {self._name}")
        return self._tool
