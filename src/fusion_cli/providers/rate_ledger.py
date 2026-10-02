"""Süreçler arası paylaşılan hız defteri — SQLite üstünde.

Neden SQLite: masaüstünde her sekme ayrı süreçtir ve paylaşılan durum için
çapraz platform (macOS, Windows) dosya kilidi gerekir. `fcntl` Windows'ta yok;
SQLite'ın kendi kilidi iki platformda da çalışır ve stdlib'dedir.

Defter KÜÇÜK ve kendini onarır: bozuk ya da kilitli bir dosya hız sınırını
yönetmeyi bırakır, turu ASLA düşürmez — her işlem başarısızlıkta "soğuma yok,
hak alındı" der ve olayı log'lar. Bu kasıtlıdır: defter bir iyileştirmedir,
model çağrısının ön şartı değil.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from pathlib import Path

from ..config.models import RuntimeConfig
from ..config.paths import user_data_dir
from ..core.clock import SystemClock
from ..core.constants import RATE_LEDGER_BUSY_TIMEOUT_S
from ..core.protocols import Clock
from ..core.rate_control import RateControl

_LOG = logging.getLogger(__name__)

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS cooldown (key TEXT PRIMARY KEY, until REAL NOT NULL)",
    "CREATE TABLE IF NOT EXISTS bucket (key TEXT PRIMARY KEY, tokens REAL NOT NULL, "
    "updated REAL NOT NULL)",
    "CREATE TABLE IF NOT EXISTS counter (key TEXT PRIMARY KEY, value INTEGER NOT NULL)",
)

#: Kova dakikalık sınırın TAMAMIYLA dolu başlar: normal kullanım hiç beklemez,
#: yalnız sınırı aşacak yoğunluk (paralel ajanlar, çok sekme) yavaşlar.
_SECONDS_PER_MINUTE = 60.0


class SqliteRateLedger:
    """`RateLedger` protokolünün SQLite uygulaması."""

    def __init__(self, path: Path, *, clock: Clock | None = None) -> None:
        self._path = path
        self._clock = clock or SystemClock()
        self._ready = False

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self._path, timeout=RATE_LEDGER_BUSY_TIMEOUT_S, isolation_level=None
        )
        if not self._ready:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            for statement in _SCHEMA:
                connection.execute(statement)
            self._ready = True
        return connection

    def cooled_until(self, key: str) -> float:
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    "SELECT until FROM cooldown WHERE key = ?", (key,)
                ).fetchone()
        except sqlite3.Error as error:
            _LOG.warning("hız defteri okunamadı", extra={"hata": str(error)})
            return 0.0
        if row is None:
            return 0.0
        until = float(row[0])
        return until if until > self._clock.now() else 0.0

    def cool(self, key: str, until: float) -> None:
        try:
            with closing(self._connect()) as connection:
                connection.execute(
                    "INSERT INTO cooldown (key, until) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET until = MAX(until, excluded.until)",
                    (key, until),
                )
        except sqlite3.Error as error:
            _LOG.warning("hız defterine yazılamadı", extra={"hata": str(error)})

    def take_token(self, key: str, per_minute: float) -> float:
        if per_minute <= 0:
            return 0.0
        now = self._clock.now()
        refill_per_s = per_minute / _SECONDS_PER_MINUTE
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT tokens, updated FROM bucket WHERE key = ?", (key,)
                ).fetchone()
                tokens = per_minute if row is None else float(row[0])
                updated = now if row is None else float(row[1])
                tokens = min(per_minute, tokens + max(0.0, now - updated) * refill_per_s)
                wait_s = 0.0 if tokens >= 1.0 else (1.0 - tokens) / refill_per_s
                if wait_s == 0.0:
                    tokens -= 1.0
                connection.execute(
                    "INSERT INTO bucket (key, tokens, updated) VALUES (?, ?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET tokens = excluded.tokens, "
                    "updated = excluded.updated",
                    (key, tokens, now),
                )
                connection.execute("COMMIT")
        except sqlite3.Error as error:
            _LOG.warning("hız kovası okunamadı", extra={"hata": str(error)})
            return 0.0
        return wait_s

    def next_index(self, key: str) -> int:
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    "INSERT INTO counter (key, value) VALUES (?, 0) "
                    "ON CONFLICT(key) DO UPDATE SET value = value + 1 RETURNING value",
                    (key,),
                ).fetchone()
        except sqlite3.Error as error:
            _LOG.warning("hız defteri sayacı okunamadı", extra={"hata": str(error)})
            return 0
        return int(row[0]) if row else 0


#: Defter dosyasının kullanıcı veri dizinindeki adı. Hesaptan bağımsızdır:
#: sağlayıcının hız sınırı hesaba değil anahtara/modele bağlıdır.
LEDGER_FILE_NAME = "rate-ledger.sqlite3"


def shared_rate_control(runtime: RuntimeConfig) -> RateControl:
    """Bu makinedeki bütün Fusion süreçlerinin paylaştığı hız denetimi."""
    return RateControl(
        ledger=SqliteRateLedger(user_data_dir() / LEDGER_FILE_NAME),
        per_minute=dict(runtime.rate_limit_per_minute),
        pace_max_wait_s=runtime.rate_pace_max_wait_s,
        cooldown_s=runtime.circuit_cooldown_s,
    )
