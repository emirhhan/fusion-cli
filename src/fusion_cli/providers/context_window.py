"""Kurulu model kataloğundaki doğrulanabilir girdi penceresini oku."""

from __future__ import annotations

from functools import lru_cache

#: Kataloğu LiteLLM'de bulunmayan ama aynı modeli OpenRouter'da da sunan sağlayıcılar.
#
# Ölçüldü (28 Eylül): LiteLLM `nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b` için
# pencere bilmiyor; aynı ağırlıkların OpenRouter kaydı 262.144 token bildiriyor.
# Bilinmeyen pencere en dar varsayılana düşüyor ve bağlam göstergesi büyük görevde
# birkaç dosya okuması sonra "Yakında özetlenecek" diyordu. Pencere UYDURULMAZ:
# yalnız aynı modelin katalogdaki kaydı okunur.
_OPENROUTER_MIRRORED_PREFIXES = ("nvidia_nim/",)


@lru_cache(maxsize=256)
def input_window_tokens(model: str) -> int | None:
    """LiteLLM metadatası yoksa sınır uydurmadan ``None`` döndür."""
    own = _catalog_window(model)
    if own is not None:
        return own
    return _mirrored_window(model)


def _catalog_window(model: str) -> int | None:
    try:
        import litellm

        value = litellm.get_model_info(model).get("max_input_tokens")
    except Exception:
        return None
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _mirrored_window(model: str) -> int | None:
    """Aynı modelin OpenRouter kayıtlarından EN DAR pencereyi döndür."""
    prefix = next((p for p in _OPENROUTER_MIRRORED_PREFIXES if model.startswith(p)), None)
    if prefix is None:
        return None
    tail = model.removeprefix(prefix)
    # Ücretli ve ücretsiz kayıt farklı pencere bildirebilir (ultra: 262.144 / 1.000.000);
    # dar olan esas alınır, çünkü hangisinin sunulduğu bilinmiyor.
    known = [
        window
        for window in (
            _catalog_window(f"openrouter/{tail}"),
            _catalog_window(f"openrouter/{tail}:free"),
        )
        if window is not None
    ]
    return min(known) if known else None
