"""Başarısız kimlik doğrulama sınırı: kaba kuvvet ve kod tahminine karşı kilit."""

from __future__ import annotations

from ..core.protocols import Clock
from .constants import AUTH_FAILURE_LIMIT, AUTH_FAILURE_WINDOW_SECONDS, AUTH_LOCKOUT_SECONDS


class FailureLimiter:
    """Anahtar başına kayan pencerede hata sayar; eşikte kilitler."""

    def __init__(
        self,
        clock: Clock,
        *,
        limit: int = AUTH_FAILURE_LIMIT,
        window_seconds: float = AUTH_FAILURE_WINDOW_SECONDS,
        lockout_seconds: float = AUTH_LOCKOUT_SECONDS,
    ) -> None:
        self._clock = clock
        self._limit = limit
        self._window = window_seconds
        self._lockout = lockout_seconds
        self._failures: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}

    def is_locked(self, key: str) -> bool:
        until = self._locked_until.get(key)
        if until is None:
            return False
        if self._clock.now() >= until:
            self._locked_until.pop(key, None)
            self._failures.pop(key, None)
            return False
        return True

    def record_failure(self, key: str) -> None:
        now = self._clock.now()
        recent = [t for t in self._failures.get(key, []) if now - t <= self._window]
        recent.append(now)
        self._failures[key] = recent
        if len(recent) >= self._limit:
            self._locked_until[key] = now + self._lockout

    def record_success(self, key: str) -> None:
        self._failures.pop(key, None)
