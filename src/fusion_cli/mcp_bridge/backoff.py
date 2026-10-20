"""Geçici MCP bağlantı arızalarında yapılandırılmış, sonlu bekleme aralıkları."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from ..config.models import McpServerConfig
from .types import McpConnectionStatus


@dataclass(frozen=True, slots=True)
class _Retry:
    config: McpServerConfig
    status: McpConnectionStatus
    attempt: int
    next_retry_at: float


class McpBackoff:
    """Saat ve kayıtların sahibi mevcut sunucu havuzudur."""

    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._records: dict[str, _Retry] = {}

    @property
    def statuses(self) -> dict[str, McpConnectionStatus]:
        return {
            name: replace(
                retry.status,
                state="backoff",
                retry_after_s=max(0.0, retry.next_retry_at - self._clock()),
            )
            for name, retry in self._records.items()
        }

    def is_waiting(self, config: McpServerConfig) -> bool:
        retry = self._records.get(config.name)
        if retry is not None and retry.config != config:
            self.forget(config.name)
            return False
        return retry is not None and self._clock() < retry.next_retry_at

    def record(self, config: McpServerConfig, status: McpConnectionStatus) -> None:
        delays = config.retry_delays_s or ()
        if not delays:
            return
        previous = self._records.get(config.name)
        attempt = previous.attempt + 1 if previous and previous.config == config else 0
        delay = delays[min(attempt, len(delays) - 1)]
        self._records[config.name] = _Retry(config, status, attempt, self._clock() + delay)

    def forget(self, name: str) -> None:
        self._records.pop(name, None)

    def clear(self) -> None:
        self._records.clear()
