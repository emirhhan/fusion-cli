"""Tarayıcı komutunun ağ ve insan bekleme süreleri ayrı sahiplik taşır."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CommandLease:
    device_id: str
    network_deadline: float
    permission_id: str = ""
    human_started: float = 0.0
    last_progress: float = 0.0

    def remaining(self, now: float, *, human_timeout: float, heartbeat_timeout: float) -> float:
        if not self.permission_id:
            return self.network_deadline - now
        if now - self.human_started >= human_timeout:
            raise TimeoutError("İzin bekleme süresi doldu; kullanıcı reddetmiş sayılmadı.")
        if now - self.last_progress >= heartbeat_timeout:
            raise TimeoutError("İzin beklerken tarayıcı bağlantısı koptu; komut iptal edildi.")
        return min(
            human_timeout - (now - self.human_started),
            heartbeat_timeout - (now - self.last_progress),
        )
