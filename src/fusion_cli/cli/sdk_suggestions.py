"""`-p --prompt-suggestions` (#289): her turdan sonra `prompt_suggestion` mesajı.

Claude Code stream-json'da tur sonucundan sonra kullanıcının olası sıradaki istemini
`{"type": "prompt_suggestion", "suggestion": ...}` olarak yayımlar; öneri modelin
tahminidir. Fusion'da da tahmini hakem rolünün modeli yapar (`engines/agent/next_prompt`);
model ulaşılamaz ya da tahmin vermezse turun kanıtından üretilen ilk takip önerisi
(`core/followups.py`, `FollowupsSuggested`) kullanılır. Claude'daki gibi hatayla biten turda
ve plan kipinde öneri yoktur; ikisi de yoksa mesaj yazılmaz.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Mapping, Sequence

from ..config.models import Config
from ..core.events import Event, FollowupsSuggested
from ..core.types import Message
from ..engines.agent.next_prompt import predict_next_prompt

Predict = Callable[[], "str | None"]


def model_suggestion(history: Sequence[Message], config: Config) -> str | None:
    """Turdan sonra modelin tahmini (eşzamanlı çağıran için); olmazsa `None`."""
    return asyncio.run(predict_next_prompt(list(history), config))


class PromptSuggestions:
    """Turdaki ilk takip önerisini tutar; sonuç yazıldıktan sonra mesaj olarak verir."""

    def __init__(self, write: Callable[[Mapping[str, object]], None]) -> None:
        self._write = write
        self._pending: str | None = None

    def observe(self, event: Event) -> None:
        if isinstance(event, FollowupsSuggested) and event.items:
            self._pending = event.items[0][1]

    def flush(self, session_id: str, predict: Predict | None = None, *, skip: bool = False) -> None:
        """Öneriyi yaz (turda bir kez): önce model tahmini, yoksa kanıt önerisi."""
        fallback, self._pending = self._pending, None
        if skip:
            return
        suggestion = (predict() if predict is not None else None) or fallback
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
