"""Düz metin otomatik bellek araçları: `remember` ve `memory_read` (P-036).

`AgentDeps.plain_memory` doluysa kaydedilir; bellek kapalıyken (`runtime.auto_memory:
false`) ya da bu ajana bellek verilmemişse araçlar HİÇ sunulmaz. `remember` dosya
sistemine yazar ama proje kökü dışındaki Fusion veri dizinine yazdığı ve kullanıcının
kendi notu olduğu için değiştirici (onaylı) araç sayılmaz; `memory_read` salt okur.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...core.tools import Tool, ToolArgs, ToolContext, ToolResult
from ...memory.plain_memory import PlainMemory, PlainMemoryError
from ...ui import messages

if TYPE_CHECKING:
    from .loop import AgentDeps

_STRING = {"type": "string"}


def memory_prompt_block(deps: AgentDeps) -> str:
    """Bu ajanın bellek bloğu (indeksin başı); bellek yoksa boş."""
    memory: PlainMemory | None = getattr(deps, "plain_memory", None)
    return memory.prompt_block() if memory is not None else ""


def remember_tool(memory: PlainMemory) -> Tool:
    def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        topic = str(args.get("konu", "")).strip()
        text = str(args.get("metin", "")).strip()
        if not topic or not text:
            return ToolResult.failure(messages.MEMORY_TOOL_EMPTY)
        try:
            written = memory.remember(topic, text)
        except PlainMemoryError as error:
            return ToolResult.failure(str(error))
        return ToolResult(
            messages.MEMORY_TOOL_SAVED.format(path=written.path.name, lines=written.lines)
        )

    return Tool(
        name="remember",
        description=(
            "Gelecek oturumlarda da geçerli, projeye ya da kullanıcıya dair KALICI bir bilgiyi "
            "düz metin belleğe yaz (ör. 'kullanıcı Türkçe ve kısa yanıt ister', 'ödeme akışı "
            "sandbox'ta'). Konu başlığı + tek cümle. Geçici görev notu ya da sır yazma; "
            "dersler için bu değil recall_lessons/learn kullanılır."
        ),
        parameters={
            "type": "object",
            "properties": {
                "konu": {**_STRING, "description": "kısa konu adı (ör. odeme-akisi, kullanici)"},
                "metin": {**_STRING, "description": "hatırlanacak tek cümle"},
            },
            "required": ["konu", "metin"],
        },
        run=_run,
    )


def memory_read_tool(memory: PlainMemory) -> Tool:
    def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        topic = str(args.get("konu", "")).strip()
        try:
            text = memory.read(topic)
        except PlainMemoryError as error:
            return ToolResult.failure(str(error))
        if not text.strip():
            topics = ", ".join(memory.topics())
            return ToolResult(
                messages.MEMORY_TOOL_NONE.format(topics=topics or "-")
                if topic
                else messages.MEMORY_TOOL_EMPTY_INDEX
            )
        return ToolResult(text)

    return Tool(
        name="memory_read",
        description=(
            "Düz metin belleği oku: konu verilmezse BELLEK.md indeksinin tamamı, verilirse o "
            "konu dosyası. Bağlamdaki bellek bloğu kırpılmışsa ya da bir konunun ayrıntısı "
            "gerekiyorsa çağır."
        ),
        parameters={
            "type": "object",
            "properties": {"konu": {**_STRING, "description": "konu adı; boş = indeks"}},
        },
        run=_run,
    )
