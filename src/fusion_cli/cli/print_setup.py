"""`--init`, `--init-only`, `-p --maintenance` → `Setup` kanca olayı (#301).

Claude Code (Hooks reference, "Setup"): olay yalnız `--init-only` ya da `-p --init` /
`-p --maintenance` ile tetiklenir; olağan açılışta çalışmaz. Eşleştirici değeri bayrağı
söyler (`init` | `maintenance`), girdi ortak alanlara ek olarak `trigger` taşır. Setup
engelleyemez: JSON çıktısı ve çıkış kodu yok sayılır. `--init-only` Setup ile
`SessionStart(startup)` kancalarını koşar ve konuşma açmadan, başarıda çıktısız çıkar.

Kancalar oturumun kanca ayarlarına uyar (`--bare`, `disableAllHooks`, `--setting-sources`).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from ..config.models import Config
from ..core.hooks.events import HookEvent
from ..engines.hooks.session import open_hook_session

TRIGGER_INIT = "init"
TRIGGER_MAINTENANCE = "maintenance"

_LOG = logging.getLogger(__name__)


def setup_triggers(*, init: bool, init_only: bool, maintenance: bool) -> tuple[str, ...]:
    """Bayraklardan Setup tetikleri (sırayla `init`, `maintenance`)."""
    triggers: list[str] = []
    if init or init_only:
        triggers.append(TRIGGER_INIT)
    if maintenance:
        triggers.append(TRIGGER_MAINTENANCE)
    return tuple(triggers)


async def _emit(
    config: Config, root: Path, triggers: tuple[str, ...], session_id: str, *, session_start: bool
) -> None:
    session = open_hook_session(root, config, session_id=session_id or uuid.uuid4().hex)
    for trigger in triggers:
        verdict = await session.emit(
            HookEvent.SETUP, subjects=(trigger,), fields={"trigger": trigger}
        )
        # Engelleyemez: karar, JSON ve çıkış kodu yok sayılır; yalnız hata ayıklama günlüğü.
        _LOG.debug("Setup:%s kancaları çalıştı (%d komut)", trigger, verdict.ran)
    if session_start:
        verdict = await session.start("startup")
        _LOG.debug("SessionStart:startup kancaları çalıştı (%d komut)", verdict.ran)


def run_setup_hooks(
    config: Config,
    root: Path,
    triggers: tuple[str, ...],
    *,
    session_id: str = "",
    session_start: bool = False,
) -> None:
    """Setup kancalarını (ve `--init-only`'de SessionStart'ı) eşzamanlı koş."""
    if not triggers and not session_start:
        return
    asyncio.run(_emit(config, root, triggers, session_id, session_start=session_start))


def run_init_only(
    config: Config, root: Path, triggers: tuple[str, ...], session_id: str | None
) -> int:
    """Claude `--init-only`: Setup + SessionStart(startup); konuşma ve çıktı yok, çıkış 0."""
    run_setup_hooks(config, root, triggers, session_id=session_id or "", session_start=True)
    return 0
