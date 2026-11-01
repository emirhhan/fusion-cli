"""`DirectoryAdded` kancası (#90): `/add-dir` oturuma yeni çalışma klasörü ekleyince.

Claude: ekleme hemen tamamlanır, kanca beklenmez (arka planda, 600 sn varsayılan süre).
Eşleştirici `source`'tur (`slash_command`). Karar denetimi yoktur; `continue` atılır,
`systemMessage` kullanıcıya gösterilmez, sonraki turda modele bağlam olarak gider.
`--add-dir` açılış bayrağı ve zaten çalışma kökü içinde olan klasör tetiklemez.
"""

from __future__ import annotations

from pathlib import Path

from ...core.hooks.events import HookEvent
from ..hooks.session import HookSession

SLASH_COMMAND_SOURCE = "slash_command"


def directory_added(
    session: HookSession | None, directory: Path, source: str = SLASH_COMMAND_SOURCE
) -> None:
    """Kancayı arka planda başlat; `systemMessage` sonraki kök turun bağlamına."""
    if session is None or not session.has(HookEvent.DIRECTORY_ADDED):
        return
    fields: dict[str, object] = {"directory": str(directory), "source": source}

    async def _run() -> None:
        verdict = await session.emit(HookEvent.DIRECTORY_ADDED, subjects=(source,), fields=fields)
        for text in verdict.system_messages:
            session.rewake_notes.append(f"{HookEvent.DIRECTORY_ADDED.value} hook: {text}")

    session.spawn(_run)
