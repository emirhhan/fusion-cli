"""`--permission-prompt-tool mcp__<sunucu>__<araç>` — onay isteğini MCP aracına sor (#293).

Claude Code'da `-p` koşusunda onay gereken çağrı bu MCP aracına `{tool_name, input,
tool_use_id}` ile sorulur; araç metin içeriğinde `{"behavior": "allow", "updatedInput":
{...}}` ya da `{"behavior": "deny", "message": "..."}` döndürür. Araç bulunamazsa, hata
verirse ya da cevap çözülemezse istek reddedilmiş sayılır (tur sürer, model başka yol
dener; neden stderr'e yazılır). `updatedInput` çağrının argümanının tamamı olur (`file_path`
Fusion'ın `path`'ine çevrilir; yeni argüman izin kurallarından yeniden geçer). `deny`'in
`message`'ı modele araç sonucu olarak gider ve tur sürer; `interrupt: true` turu durdurur.
`tool_use_id` modelin araç çağrısı kimliğidir.
"""

from __future__ import annotations

import inspect
import json
import sys
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

from ..config.models import Config
from ..core.tools import Tool, ToolContext, ToolResult
from ..engines.agent.approval import ApprovalAnswer, ApprovalReply, ApprovalRequest
from ..engines.agent.hook_bridge import tool_hook_fields
from ..ui import print_messages as texts
from .print_runtime import PrintPrompter
from .sdk_messages import claude_tool_name

ToolLoader = Callable[[str], Awaitable[Tool | None]]
_MCP_PREFIX = "mcp__"
_FUSION_PATH, _CLAUDE_PATH = "path", "file_path"


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


Answer = ApprovalAnswer | ApprovalReply


def claude_request(request: ApprovalRequest) -> tuple[str, dict[str, object], str]:
    """Onay sorusunun Claude alanları: (`tool_name`, `input` Claude adlarıyla, `tool_use_id`)."""
    tool_input = tool_hook_fields(request.tool.name, dict(request.args))["tool_input"]
    return (
        claude_tool_name(request.tool.name),
        dict(tool_input) if isinstance(tool_input, Mapping) else {},
        str(getattr(request, "call_id", "") or ""),
    )


def answer_from(payload: object, request: ApprovalRequest) -> Answer:
    """Claude izin cevabını (`allow`+`updatedInput` / `deny`+`message`) karara çevir."""
    if not isinstance(payload, Mapping):
        return ApprovalAnswer.UNAVAILABLE
    behavior = str(payload.get("behavior", "")).strip().lower()
    if behavior == "allow":
        updated = payload.get("updatedInput")
        if not isinstance(updated, Mapping):
            return ApprovalAnswer.ONCE
        return ApprovalReply(ApprovalAnswer.ONCE, updated_input=fusion_input(request, updated))
    if behavior != "deny":
        return ApprovalAnswer.UNAVAILABLE
    if payload.get("interrupt") is True:
        return ApprovalAnswer.DENY
    message = str(payload.get("message", "") or "").strip()
    if not message:
        return ApprovalAnswer.UNAVAILABLE
    return ApprovalReply(ApprovalAnswer.DENY, note=message)


def fusion_input(request: ApprovalRequest, updated: Mapping[str, object]) -> dict[str, object]:
    """`updatedInput` Claude'daki gibi argümanın TAMAMI olur; `file_path` → Fusion `path`."""
    arguments = dict(updated)
    if _FUSION_PATH not in request.args:
        return arguments
    # Soruda `path` ile birlikte `file_path` takma adı da gider; değişen ad kazanır.
    claude_path = arguments.pop(_CLAUDE_PATH, None)
    if claude_path is not None and arguments.get(_FUSION_PATH) in (
        None,
        request.args[_FUSION_PATH],
    ):
        arguments[_FUSION_PATH] = claude_path
    return arguments


def decision_from(result: ToolResult, request: ApprovalRequest) -> Answer:
    """Aracın cevabını karara çevir: yalnız açık `allow` onaydır."""
    payload: object = result.structured
    if not isinstance(payload, Mapping):
        try:
            payload = json.loads(result.output)
        except (TypeError, ValueError):
            return ApprovalAnswer.UNAVAILABLE
    if not result.ok:
        return ApprovalAnswer.UNAVAILABLE
    return answer_from(payload, request)


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

    async def confirm(self, request: ApprovalRequest) -> bool | Answer:
        self.requests.append(request)
        tool = await self._resolve()
        if tool is None:
            return ApprovalAnswer.UNAVAILABLE
        try:
            name, tool_input, call_id = claude_request(request)
            args = {"tool_name": name, "input": tool_input, "tool_use_id": call_id}
            outcome = tool.run(args, ToolContext(root=self._root))
            result = await outcome if inspect.isawaitable(outcome) else outcome
        except Exception as error:  # araç hatası onay değildir; reddedilmiş sayılır
            self._error(str(error))
            return ApprovalAnswer.UNAVAILABLE
        if not result.ok:
            self._error(result.output)
        return decision_from(result, request)

    def _error(self, text: str) -> None:
        self.errors.append(text)
        sys.stderr.write(texts.PRINT_PROMPT_TOOL_ERROR.format(tool=self._name, error=text) + "\n")

    async def _resolve(self) -> Tool | None:
        if not self._loaded:
            self._loaded = True
            try:
                self._tool = await self._loader(self._name)
            except Exception as error:  # bağlanamayan sunucu: istekler reddedilir
                self._error(str(error))
            if self._tool is None:
                self._error(texts.PRINT_PROMPT_TOOL_MISSING)
        return self._tool
