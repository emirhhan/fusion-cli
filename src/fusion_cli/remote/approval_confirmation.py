"""Tek soruya ve karara bağlı, kısa ömürlü telefon teyitleri."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from ..core.protocols import Clock
from .constants import PAIRING_CODE_TTL_SECONDS


@dataclass(frozen=True)
class _Confirmation:
    device_id: str
    run_id: str
    question_id: str
    choice: str
    digest: str
    expires_at: float


def _digest(question: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(question, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


class ApprovalConfirmations:
    """Eşleştirme teyidiyle aynı kısa ömürde, tek kullanımlık işlem izni."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._pending: dict[str, _Confirmation] = {}

    def issue(
        self, device: str, run: str, question: str, choice: str, payload: dict[str, Any]
    ) -> str:
        now = self._clock.now()
        self._pending = {key: item for key, item in self._pending.items() if item.expires_at > now}
        self._pending = {
            key: item
            for key, item in self._pending.items()
            if (item.device_id, item.question_id) != (device, question)
        }
        token = uuid.uuid4().hex
        self._pending[token] = _Confirmation(
            device, run, question, choice, _digest(payload), now + PAIRING_CODE_TTL_SECONDS
        )
        return token

    def consume(
        self,
        token: object,
        device: str,
        run: str,
        question: str,
        choice: str,
        payload: dict[str, Any],
    ) -> bool:
        if not isinstance(token, str):
            return False
        item = self._pending.get(token)
        if item is None:
            return False
        if (item.device_id, item.run_id, item.question_id, item.choice, item.digest) != (
            device,
            run,
            question,
            choice,
            _digest(payload),
        ) or item.expires_at <= self._clock.now():
            return False
        self._pending.pop(token)
        return True
