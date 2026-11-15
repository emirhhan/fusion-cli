"""`UserPromptExpansion` kancası (#90): kullanıcının yazdığı `/komut` isteme açılırken.

Claude: beceri ve özel komut (`slash_command`) ya da MCP istemi (`mcp_prompt`) açılmadan
önce çalışır; eşleştirici `command_name`'dir. Çıkış 2 ya da `decision: "block"` komutun
açılmasını engeller (gerekçe kullanıcıya); `additionalContext` ve düz stdout açılan istemin
yanına bağlam olarak eklenir. Modelin `Skill` aracı bu olayı tetiklemez (o `PreToolUse`).

Komut işleyicileri eşzamanlıdır: açılım `queue_expansion` ile oturuma yazılır, kanca sıradaki
kök turun başında (`UserPromptSubmit`'ten önce) çalışır.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...core.hooks.events import HookEvent, HookVerdict
from ..hooks.session import HookSession

SLASH_COMMAND = "slash_command"
MCP_PROMPT = "mcp_prompt"

#: Fusion beceri kaynağı → Claude `command_source`.
_SOURCES = {"claude-plugin": "plugin", "plugin": "plugin", "proje": "projectSettings"}


def command_source(source: str) -> str:
    """`claude-plugin` → `plugin`, `proje` → `projectSettings`, öteki → `userSettings`."""
    for part in source.split("+"):
        if part in _SOURCES:
            return _SOURCES[part]
    return "userSettings"


def state_hooks(state: object) -> HookSession | None:
    """Yüzey durumunun kanca oturumu (`ReplState.hooks`); yoksa `None`."""
    hooks = getattr(state, "hooks", None)
    session = hooks() if callable(hooks) else None
    return session if isinstance(session, HookSession) else None


def queue_expansion(
    session: HookSession | None,
    *,
    name: str,
    args: str,
    source: str,
    expansion_type: str = SLASH_COMMAND,
) -> None:
    """Açılan komutu sıradaki tur için kaydet (önceki bekleyenin yerine geçer)."""
    if session is None:
        return
    prompt = f"/{name} {args}".strip()
    session.pending_expansion = {
        "expansion_type": expansion_type,
        "command_name": name,
        "command_args": args,
        "command_source": source,
        "prompt": prompt,
    }


@dataclass(frozen=True, slots=True)
class ExpansionGate:
    """Kancanın sonucu: engel metni (kullanıcıya) ya da istemin yanına eklenecek bağlam."""

    blocked: str | None = None
    context: str = ""
    verdict: HookVerdict | None = None


def blocked_text(reason: str) -> str:
    return f"UserPromptExpansion operation blocked by hook:\n{reason}"


async def prompt_expansion(session: HookSession) -> ExpansionGate:
    """Bekleyen açılım varsa kancayı çalıştır; yoksa boş kapı."""
    fields, session.pending_expansion = session.pending_expansion, None
    if not fields:
        return ExpansionGate()
    name = str(fields.get("command_name", ""))
    verdict = await session.emit(HookEvent.USER_PROMPT_EXPANSION, subjects=(name,), fields=fields)
    if verdict.blocked or verdict.halt:
        reason = verdict.reason or verdict.stop_reason or "komut kancayla engellendi"
        return ExpansionGate(blocked=blocked_text(reason), verdict=verdict)
    return ExpansionGate(context=verdict.context_text, verdict=verdict)
