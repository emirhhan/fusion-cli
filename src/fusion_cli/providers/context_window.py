"""Kurulu model kataloğundaki doğrulanabilir girdi penceresini oku."""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=256)
def input_window_tokens(model: str) -> int | None:
    """LiteLLM metadatası yoksa sınır uydurmadan ``None`` döndür."""
    try:
        import litellm

        value = litellm.get_model_info(model).get("max_input_tokens")
    except Exception:
        return None
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None
