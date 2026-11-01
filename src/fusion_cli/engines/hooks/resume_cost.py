"""SessionStart `resume`/`fork` maliyet alanları (#111) — Claude Code ile aynı adlar.

Döküm (`transcript_path`) en az bir model cevabı içeriyorsa SessionStart girdisine dört
alan eklenir: `seconds_since_last_response`, `context_tokens` (sürdürülen oturumun ilk
isteğinin yeniden göndereceği tahmini belirteç), `prompt_cache_likely_expired` (son cevap
istem önbelleği ömründen eski mi ya da ondan sonra özetleme oldu mu) ve
`estimated_cache_write_usd` (bu belirteçleri önbelleğe yazmanın tahmini dolar maliyeti,
cevap hariç).
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from pathlib import Path

#: İstem önbelleği ömrü (Claude varsayılanı 5 dk).
CACHE_LIFETIME_S = 300
#: Önbelleğe yazma = girdi fiyatı × 1,25 (fiyat tablosunda ayrı değer yoksa).
CACHE_WRITE_MULTIPLIER = 1.25
#: Karakter → belirteç tahmini (`context_budget.CHARS_PER_TOKEN_ESTIMATE` ile aynı).
CHARS_PER_TOKEN = 3


#: Döküm sondan bu boyda parçalarla okunur (büyük dökümde tamamı belleğe alınmaz).
TAIL_CHUNK_BYTES = 64 * 1024
COMPACT_BOUNDARY = "compact_boundary"


def _lines_from_end(path: Path) -> Iterator[str]:
    """Dosyanın satırları sondan başa (parça parça okunur)."""
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        rest = b""
        while position > 0:
            size = min(TAIL_CHUNK_BYTES, position)
            position -= size
            handle.seek(position)
            parts = (handle.read(size) + rest).split(b"\n")
            rest = parts[0]
            for raw in reversed(parts[1:]):
                yield raw.decode("utf-8", errors="replace")
        yield rest.decode("utf-8", errors="replace")


def last_response(path: Path) -> tuple[float, bool] | None:
    """(son model cevabının zamanı, ondan sonra özetleme oldu mu); cevap yoksa `None`."""
    compacted = False
    try:
        for line in _lines_from_end(path):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict):
                continue
            if row.get("type") == "system" and row.get("subtype") == COMPACT_BOUNDARY:
                compacted = True
            stamp = row.get("timestamp")
            if row.get("type") == "assistant" and isinstance(stamp, int | float):
                return float(stamp), compacted
    except OSError:
        return None
    return None


def last_response_at(path: Path) -> float | None:
    """Dökümdeki son model cevabının zamanı; cevap yoksa `None`."""
    found = last_response(path)
    return found[0] if found is not None else None


def cache_write_usd(model: str, tokens: int) -> float:
    """Fiyat tablosundan (litellm) önbellek yazma maliyeti; model bilinmiyorsa 0."""
    try:
        import litellm
    except ImportError:
        return 0.0
    entry = litellm.model_cost.get(model) or litellm.model_cost.get(model.split("/", 1)[-1])
    if not isinstance(entry, dict):
        return 0.0
    price = entry.get("cache_creation_input_token_cost")
    if not isinstance(price, int | float):
        base = entry.get("input_cost_per_token")
        price = base * CACHE_WRITE_MULTIPLIER if isinstance(base, int | float) else 0.0
    return round(float(price) * tokens, 4)


def resume_fields(
    transcript: Path | None, context_chars: int, model: str, now: float | None = None
) -> dict[str, object]:
    """Dört alan; döküm yoksa ya da cevap içermiyorsa boş."""
    if transcript is None:
        return {}
    found = last_response(transcript)
    if found is None:
        return {}
    last, compacted = found
    elapsed = max(0, int((now if now is not None else time.time()) - last))
    tokens = max(0, context_chars // CHARS_PER_TOKEN)
    return {
        "seconds_since_last_response": elapsed,
        "context_tokens": tokens,
        "prompt_cache_likely_expired": elapsed > CACHE_LIFETIME_S or compacted,
        "estimated_cache_write_usd": cache_write_usd(model, tokens) if model else 0.0,
    }
