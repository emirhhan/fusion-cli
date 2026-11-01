"""Kancanın modele giden metinleri — Claude Code biçimi (ek yönerge eklenmez).

engel     `PreToolUse:Bash hook error: [komut]: <gerekçe>` (aracın hatası olarak)
bağlam    `<system-reminder>` içinde, kanca adıyla başlar; metindeki
          `<system-reminder>` / `</system-reminder>` etiketinin `<`'i `&lt;` olur
Stop      `reason` olduğu gibi; `additionalContext` "Stop hook feedback" etiketiyle
istem     engel mesajı `Original prompt:` + metinle biter (`suppressOriginalPrompt` hariç)
"""

from __future__ import annotations

import re

from ...core.hooks.decision import hook_label
from ...core.hooks.events import HookEvent, HookVerdict

_REMINDER_TAG = re.compile(r"<(?=\\?/?system-reminder>)")
STOP_FEEDBACK_LABEL = "Stop hook feedback"


def escape_reminder(text: str) -> str:
    """`<system-reminder>`, `</system-reminder>` (ve `<\\/…>`) etiketlerinin `<`'ini kaçır."""
    return _REMINDER_TAG.sub("&lt;", text)


def system_reminder(body: str) -> str:
    return f"<system-reminder>\n{escape_reminder(body)}\n</system-reminder>"


def context_reminder(event: HookEvent, context: str) -> str:
    """Kancanın ek bağlamı: sistem hatırlatması, kanca adıyla."""
    return system_reminder(f"{event.value} hook additional context: {context}") if context else ""


def block_error(event: HookEvent, subject: str, verdict: HookVerdict) -> str:
    """Engellenen çağrının modele giden hata metni (Claude ile aynı önek)."""
    source = f"[{verdict.block_source}]: " if verdict.block_source else ""
    return f"{hook_label(event, subject)} hook error: {source}{verdict.reason}"


def stop_feedback(context: str) -> str:
    return system_reminder(f"{STOP_FEEDBACK_LABEL}:\n{context}")


def prompt_blocked(reason: str, prompt: str, *, suppress: bool) -> str:
    """UserPromptSubmit engel mesajı (kullanıcıya ve dökümde)."""
    text = f"UserPromptSubmit operation blocked by hook:\n{reason}"
    return text if suppress else f"{text}\n\nOriginal prompt: {prompt}"
