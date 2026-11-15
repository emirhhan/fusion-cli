"""`Setup` kancası (#90): depo kurulumu/bakımı için yalnız açıkça istenince çalışır.

Claude Code: `--init` ve `--init-only` `trigger: "init"`, `--maintenance` `trigger:
"maintenance"` ile tetikler (eşleştirici bu değere bakar). Yalnız `command` ve `mcp_tool`
türleri; SessionStart gibi `CLAUDE_ENV_FILE` verilir, `additionalContext` (ve düz stdout)
konuşmanın başına, ilk istemden önce eklenir. Engelleme kararı yoktur.

Bayrak bağlantısı başsız (`-p`) giriş noktasındadır; bu modül yalnız olayı tetikler.
"""

from __future__ import annotations

from ...core.errors import FusionError
from ...core.hooks.events import HookEvent, HookVerdict
from .session import HookSession

#: Claude'un `Setup` tetikleri.
SETUP_TRIGGERS = ("init", "maintenance")


async def run_setup(session: HookSession, trigger: str) -> HookVerdict:
    """`Setup` kancalarını çalıştır; bağlamı açılış bağlamına ekle."""
    if trigger not in SETUP_TRIGGERS:
        raise FusionError(f"Setup tetiği init ya da maintenance olmalı: {trigger!r}")
    from ..agent.hook_text import context_reminder

    verdict = await session.emit(HookEvent.SETUP, subjects=(trigger,), fields={"trigger": trigger})
    if verdict.context_text:
        session.add_start_context(context_reminder(HookEvent.SETUP, verdict.context_text))
    return verdict
