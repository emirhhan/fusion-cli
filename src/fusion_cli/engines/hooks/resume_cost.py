"""SessionStart `resume`/`fork` maliyet alanları (#111) — Claude Code ile aynı adlar.

Döküm (`transcript_path`) en az bir model cevabı içeriyorsa SessionStart girdisine dört
alan eklenir: `seconds_since_last_response`, `context_tokens` (sürdürülen oturumun ilk
isteğinin yeniden göndereceği tahmini belirteç), `prompt_cache_likely_expired` (son cevap
istem önbelleği ömründen eski mi) ve `estimated_cache_write_usd` (bu belirteçleri
önbelleğe yazmanın tahmini dolar maliyeti, cevap hariç).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

#: İstem önbelleği ömrü (Claude varsayılanı 5 dk).
CACHE_LIFETIME_S = 300
#: Önbelleğe yazma = girdi fiyatı × 1,25 (fiyat tablosunda ayrı değer yoksa).
CACHE_WRITE_MULTIPLIER = 1.25
#: Karakter → belirteç tahmini (`context_budget.CHARS_PER_TOKEN_ESTIMATE` ile aynı).
CHARS_PER_TOKEN = 3


def last_response_at(path: Path) -> float | None:
    """Dökümdeki son model cevabının zamanı; cevap yoksa `None`."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        stamp = row.get("timestamp") if isinstance(row, dict) else None
        if row.get("type") == "assistant" and isinstance(stamp, int | float):
            return float(stamp)
    return None


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
    last = last_response_at(transcript)
    if last is None:
        return {}
    elapsed = max(0, int((now if now is not None else time.time()) - last))
    tokens = max(0, context_chars // CHARS_PER_TOKEN)
    return {
        "seconds_since_last_response": elapsed,
        "context_tokens": tokens,
        "prompt_cache_likely_expired": elapsed > CACHE_LIFETIME_S,
        "estimated_cache_write_usd": cache_write_usd(model, tokens) if model else 0.0,
    }
