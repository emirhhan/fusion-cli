"""Uzaklaşınca oturum özeti (#230, Claude Code "Session recap").

Claude Code kullanıcı terminalden uzaklaşınca (yaklaşık 3 dakika, en az 3 tur) arka planda
`/recap` ile aynı tek satırlık özeti hazırlar ve dönüşte gösterir; `/config` içindeki
"Session recap" ayarı ya da `CLAUDE_CODE_ENABLE_AWAY_SUMMARY=0` kapatır. Fusion'da uzaklık
son kullanıcı etkinliğinden (gönderim ya da tur sonu) bu yana boşta geçen süredir; terminal
odak olayları her terminalde gelmediği için ölçüt budur. Özet hazır olunca konuşma alanına
bir kez basılır; yeni etkinlik olmadan ikinci özet üretilmez.

Not: eşik ve tur sayısı resmî belgede doğrulanamadı (üçüncü taraf kaynaklar 3 dk / 3 tur).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable

from ...core.turn_checkpoints import count_user_messages
from .state import ReplState

_LOG = logging.getLogger(__name__)

AWAY_AFTER_S = 180.0
MIN_TURNS = 3
POLL_S = 5.0
ENV_FLAG = "CLAUDE_CODE_ENABLE_AWAY_SUMMARY"


def enabled(state: ReplState) -> bool:
    if os.environ.get(ENV_FLAG, "").strip() in {"0", "false", "no", "off"}:
        return False
    return bool(getattr(state.config.runtime, "session_recap", True))


class AwayRecap:
    """Boşta kalma gözcüsü; `touch` kullanıcı etkinliğini işaretler."""

    def __init__(
        self,
        state: ReplState,
        is_busy: Callable[[], bool],
        produce: Callable[[], Awaitable[str]],
        emit: Callable[[str], None],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._state, self._is_busy, self._produce, self._emit = state, is_busy, produce, emit
        self._clock = clock
        self._last = clock()
        self._done = False

    def touch(self) -> None:
        self._last = self._clock()
        self._done = False

    def due(self) -> bool:
        if self._done or self._is_busy() or not enabled(self._state):
            return False
        if count_user_messages(self._state.history) < MIN_TURNS:
            return False
        return self._clock() - self._last >= AWAY_AFTER_S

    async def tick(self) -> bool:
        if not self.due():
            return False
        self._done = True
        text = await self._produce()
        if text.strip():
            self._emit(text)
        return True

    async def run(self) -> None:
        while self._state.running:
            await asyncio.sleep(POLL_S)
            try:
                await self.tick()
            except Exception:  # özet bir kolaylıktır; oturumu düşürmez, neden günlükte
                _LOG.warning("uzaklık özeti üretilemedi", exc_info=True)
