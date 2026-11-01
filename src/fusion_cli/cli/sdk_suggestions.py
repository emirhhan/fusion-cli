"""`-p --prompt-suggestions` (#289): her turdan sonra `prompt_suggestion` mesajı.

Claude Code stream-json'da tur sonucundan sonra kullanıcının olası sıradaki istemini
`{"type": "prompt_suggestion", "suggestion": ...}` olarak yayımlar. Fusion'da öneri,
turun kendi kanıtından üretilen ilk takip önerisidir (`core/followups.py`,
`FollowupsSuggested` olayı); ek model çağrısı açılmaz. Kanıt yoksa mesaj da yoktur.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping

from ..core.events import Event, FollowupsSuggested


class PromptSuggestions:
    """Turdaki ilk takip önerisini tutar; sonuç yazıldıktan sonra mesaj olarak verir."""

    def __init__(self, write: Callable[[Mapping[str, object]], None]) -> None:
        self._write = write
        self._pending: str | None = None

    def observe(self, event: Event) -> None:
        if isinstance(event, FollowupsSuggested) and event.items:
            self._pending = event.items[0][1]

    def flush(self, session_id: str) -> None:
        """Bekleyen öneriyi yaz (turda bir kez); öneri yoksa hiçbir şey yazılmaz."""
        suggestion, self._pending = self._pending, None
        if not suggestion:
            return
        self._write(
            {
                "type": "prompt_suggestion",
                "suggestion": suggestion,
                "uuid": str(uuid.uuid4()),
                "session_id": session_id,
            }
        )
