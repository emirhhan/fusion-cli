"""`/loop` aralığını Claude Code kurallarıyla ayrıştır (#345).

Claude (scheduled-tasks): aralık başta bir belirteç (`30m`) ya da sonda bir ifade
(`every 2 hours`) olabilir. Saniye en yakın üst dakikaya yuvarlanır; temiz bir cron adımına
denk gelmeyen değer (7m, 90m) en yakın adıma yuvarlanır ve kullanıcıya söylenir.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from ...core.session_cron import looks_like_interval, parse_interval

#: Saatin ya da günün tam böldüğü dakika adımları (cron `*/n` ile ifade edilebilenler).
_CLEAN_MINUTES = (1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60, 120, 180, 240, 360, 480, 720, 1440)
_UNITS = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1, "sn": 1, "saniye": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60, "dk": 60, "dakika": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600, "sa": 3600, "saat": 3600,
    "d": 86400, "day": 86400, "days": 86400, "gün": 86400, "gun": 86400,
}  # fmt: skip
_TRAILING = re.compile(
    r"\s+(?:every|her)\s+(\d+)?\s*([a-zçğıöşü]+?)(?:da|de|ta|te)?\s*$", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class LoopInterval:
    """Ayrıştırılmış aralık: dakika (None = aralık yok), görev metni, yuvarlama notu."""

    minutes: int | None
    prompt: str
    rounded_from: str = ""


def _round_to_step(seconds: int) -> int:
    """Saniyeyi üst dakikaya, sonra en yakın temiz cron adımına (eşitlikte küçüğe) yuvarla."""
    minutes = max(1, math.ceil(seconds / 60))
    if minutes > 1440:
        return round(minutes / 1440) * 1440
    return min(_CLEAN_MINUTES, key=lambda step: (abs(step - minutes), step))


def _from_seconds(seconds: int, raw: str, prompt: str) -> LoopInterval:
    minutes = _round_to_step(seconds)
    exact = seconds == minutes * 60
    return LoopInterval(minutes, prompt, "" if exact else raw)


def split_loop_interval(argument: str) -> LoopInterval:
    """Baştaki belirteci ya da sondaki `every …` ifadesini ayır; ikisi de yoksa aralık yok."""
    text = argument.strip()
    head, _, rest = text.partition(" ")
    if head and looks_like_interval(head):
        seconds = _token_seconds(head)
        return _from_seconds(seconds, head, rest.strip())
    match = _TRAILING.search(text)
    if match is not None:
        unit = _UNITS.get(match.group(2).casefold())
        if unit is not None:
            count = int(match.group(1) or 1)
            return _from_seconds(count * unit, match.group(0).strip(), text[: match.start()])
    return LoopInterval(None, text)


def _token_seconds(token: str) -> int:
    """`30s`/`5m`/`2h`/`1d` → saniye; 1 dakikadan kısası hata değil, yuvarlanır."""
    match = re.match(r"^\s*(\d+)\s*([smhd]?)\s*$", token, re.IGNORECASE)
    if match is not None and match.group(2).lower() == "s":
        return int(match.group(1))
    return parse_interval(token)
