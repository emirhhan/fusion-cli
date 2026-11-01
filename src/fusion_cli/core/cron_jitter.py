"""Zamanlanmış görev gecikmesi (jitter) — Claude Code tablosu (#363).

Claude Code (scheduled-tasks, Jitter): bütün oturumların görevleri aynı anda API'ye gitmesin
diye çalışma saati kaydırılır.

- Yineleyen görev, sıradaki çalışmaya kalan aralığın en çok YARISI kadar ve en çok 30 dk
  geç başlar; eşit aralıklı görev her seferinde aynı dakika kadar geç kalır (oran göreve
  sabittir).
- Her 5 dakikada bir (`*/5 * * * *`, `/loop 5m`) geciktirilmez; her çalışma bir öncekinden
  4 dk 45 sn sonra başlar (15 sn erken), beş dakikalık istem önbelleği dolmadan.
- :00 ya da :30'a kurulmuş tek seferlik görev en çok 90 sn ERKEN çalışır; başka dakikadaki
  tek seferlik görev kaydırılmaz.
"""

from __future__ import annotations

from datetime import datetime

__all__ = [
    "FIVE_MINUTES_S",
    "FIVE_MINUTE_EARLY_S",
    "MAX_DELAY_S",
    "ONCE_EARLY_MAX_S",
    "is_five_minute",
    "once_offset",
    "recurring_offset",
    "task_fraction",
]

FIVE_MINUTES_S = 300
FIVE_MINUTE_EARLY_S = 15.0
MAX_DELAY_S = 1800.0
ONCE_EARLY_MAX_S = 90.0
_FIVE_MINUTE_CRON = "*/5 * * * *"


def task_fraction(task_id: str) -> float:
    """Göreve sabit [0, 1) oranı (kimlikten; aynı görev her seferinde aynı gecikmeyi alır)."""
    try:
        return int(task_id[:8], 16) / 16**8
    except ValueError:
        return (sum(task_id.encode()) % 997) / 997


def is_five_minute(*, every_s: int = 0, cron: str = "") -> bool:
    return every_s == FIVE_MINUTES_S or " ".join(cron.split()) == _FIVE_MINUTE_CRON


def recurring_offset(task_id: str, gap_s: float, *, five_minute: bool) -> float:
    """Yineleyen görevin bu çalışmasına eklenecek saniye (5 dakikalıkta −15)."""
    if five_minute:
        return -FIVE_MINUTE_EARLY_S
    return task_fraction(task_id) * min(max(gap_s, 0.0) / 2, MAX_DELAY_S)


def once_offset(task_id: str, due: float) -> float:
    """Tek seferlik görev :00/:30'a denk geliyorsa en çok 90 sn erken (negatif saniye)."""
    moment = datetime.fromtimestamp(due)
    if moment.minute not in (0, 30) or moment.second != 0:
        return 0.0
    return -task_fraction(task_id) * ONCE_EARLY_MAX_S
