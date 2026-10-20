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


#: Yerel Ollama modellerine istekte verdiğimiz bağlam uzunluğu (token). Ollama
#: varsayılanı 4096'dır ve Fusion'ın istemi + araç şemaları (~10 bin token) bunu aşar.
#: 18 Ekim 2026'da qwen3.5 9B Q4 ile 16 GB makinede ölçüldü: 32k → 6,1 GB, 64k → 6,95 GB,
#: 128k → 8,3 GB bellek. 64k, uzun kod görevine yer bırakır ve makinede Chrome
#: oturumlarıyla rahat sığar; 128k bellek baskısı yaratır.
OLLAMA_NUM_CTX = 65536
_OLLAMA_PREFIXES = ("ollama/", "ollama_chat/")


@lru_cache(maxsize=256)
def input_window_tokens(model: str) -> int | None:
    """LiteLLM metadatası yoksa sınır uydurmadan ``None`` döndür.

    Yerel Ollama modelinde pencere kataloğun söylediği DEĞİL, istekte bizim verdiğimiz
    `num_ctx`tir; özetleme eşiği buna göre kurulur.
    """
    if model.startswith(_OLLAMA_PREFIXES):
        return OLLAMA_NUM_CTX
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
