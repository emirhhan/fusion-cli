"""Telefona canlı ekran: onaylı, süreli, hız sınırlı JPEG kare akışı.

Bu WebRTC DEĞİLDİR: saniyede ~2 kareye kadar imzalı RPC ile JPEG gönderir. Sebep: ek sunucu/TURN
altyapısı gerektirmez ve her kare aynı kimlik/yetki katmanından geçer. Her oturum masaüstünde
açıkça onaylanır; kare çekilmedikçe (boşta) kendiliğinden biter, kare çekilse bile üst sınırı
aşamaz ve masaüstü her an kesebilir.
"""

from __future__ import annotations

import asyncio
import io
import platform
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..core.protocols import Clock
from .constants import (
    SCREEN_IDLE_TTL_SECONDS,
    SCREEN_JPEG_QUALITY,
    SCREEN_MAX_SESSION_SECONDS,
    SCREEN_MAX_WIDTH,
    SCREEN_MIN_FRAME_INTERVAL_SECONDS,
    SCREEN_REQUEST_TTL_SECONDS,
)

STATE_NONE = "none"
STATE_PENDING = "pending"
STATE_ACTIVE = "active"


class ScreenUnavailableError(RuntimeError):
    """Ekran alınamadı; mesaj kullanıcıya gösterilebilir."""


class ScreenCapture(Protocol):
    """Ekranın tek karesi (JPEG baytları)."""

    async def frame(self) -> bytes: ...


class MacScreenCapture:
    """`screencapture` + Pillow ile küçültülmüş JPEG. Başka platformda dürüstçe reddeder."""

    async def frame(self) -> bytes:
        if platform.system() != "Darwin":
            raise ScreenUnavailableError("Canlı ekran şu an yalnız macOS'ta destekleniyor.")
        with tempfile.TemporaryDirectory(prefix="fusion-screen-") as directory:
            target = Path(directory) / "frame.png"
            process = await asyncio.create_subprocess_exec(
                "screencapture",
                "-x",
                "-t",
                "png",
                str(target),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(process.wait(), timeout=10)
            if process.returncode != 0 or not target.is_file():
                raise ScreenUnavailableError(
                    "Ekran alınamadı. Sistem Ayarları → Gizlilik → Ekran Kaydı izni gerekebilir."
                )
            return await asyncio.to_thread(_to_jpeg, target)


def _to_jpeg(path: Path) -> bytes:
    from PIL import Image

    with Image.open(path) as image:
        rgb = image.convert("RGB")
        if rgb.width > SCREEN_MAX_WIDTH:
            height = round(rgb.height * SCREEN_MAX_WIDTH / rgb.width)
            rgb = rgb.resize((SCREEN_MAX_WIDTH, height))
        buffer = io.BytesIO()
        rgb.save(buffer, format="JPEG", quality=SCREEN_JPEG_QUALITY, optimize=True)
        return buffer.getvalue()


@dataclass(slots=True)
class _Session:
    device_id: str
    state: str
    requested_at: float
    expires_at: float = 0.0
    hard_deadline: float = 0.0
    last_frame_at: float = 0.0
    sequence: int = 0


class ScreenShareGate:
    """Cihaz başına en fazla bir istek/oturum; onay masaüstündendir."""

    def __init__(
        self,
        clock: Clock,
        *,
        idle_ttl: float = SCREEN_IDLE_TTL_SECONDS,
        max_session: float = SCREEN_MAX_SESSION_SECONDS,
        request_ttl: float = SCREEN_REQUEST_TTL_SECONDS,
    ) -> None:
        self._clock = clock
        self._idle_ttl = idle_ttl
        self._max_session = max_session
        self._request_ttl = request_ttl
        self._sessions: dict[str, _Session] = {}

    def request(self, device_id: str) -> str:
        """Yeni istek; mevcut etkin oturum varsa korunur."""
        current = self._live(device_id)
        if current is not None:
            return current.state
        self._sessions[device_id] = _Session(device_id, STATE_PENDING, self._clock.now())
        return STATE_PENDING

    def approve(self, device_id: str) -> bool:
        session = self._live(device_id)
        if session is None or session.state != STATE_PENDING:
            return False
        now = self._clock.now()
        session.state = STATE_ACTIVE
        session.hard_deadline = now + self._max_session
        session.expires_at = min(now + self._idle_ttl, session.hard_deadline)
        return True

    def stop(self, device_id: str) -> bool:
        return self._sessions.pop(device_id, None) is not None

    def status(self, device_id: str) -> tuple[str, int]:
        """(durum, mutlak üst sınıra kalan saniye)."""
        session = self._live(device_id)
        if session is None:
            return STATE_NONE, 0
        if session.state != STATE_ACTIVE:
            return session.state, 0
        return session.state, max(0, round(session.hard_deadline - self._clock.now()))

    def next_sequence(self, device_id: str) -> int | str:
        """Kare izni: sıra numarası ya da red nedeni (`onay_yok`, `cok_sik`)."""
        session = self._live(device_id)
        if session is None or session.state != STATE_ACTIVE:
            return "onay_yok"
        now = self._clock.now()
        if now - session.last_frame_at < SCREEN_MIN_FRAME_INTERVAL_SECONDS:
            return "cok_sik"
        session.last_frame_at = now
        session.expires_at = min(now + self._idle_ttl, session.hard_deadline)
        session.sequence += 1
        return session.sequence

    def pending(self) -> list[str]:
        return [d for d, s in self._sessions.items() if self._live(d) and s.state == STATE_PENDING]

    def active(self) -> list[str]:
        return [d for d, s in self._sessions.items() if self._live(d) and s.state == STATE_ACTIVE]

    def _live(self, device_id: str) -> _Session | None:
        session = self._sessions.get(device_id)
        if session is None:
            return None
        now = self._clock.now()
        expired = session.state == STATE_ACTIVE and now > session.expires_at
        stale_request = (
            session.state == STATE_PENDING and now - session.requested_at > self._request_ttl
        )
        if expired or stale_request:
            self._sessions.pop(device_id, None)
            return None
        return session
