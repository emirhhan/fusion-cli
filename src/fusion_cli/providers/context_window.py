"""Kurulu model kataloğundaki doğrulanabilir girdi penceresini oku."""

from __future__ import annotations

import os
from functools import lru_cache

import httpx

from ..config.keys import environ_snapshot

#: Kataloğu LiteLLM'de bulunmayan ama aynı modeli OpenRouter'da da sunan sağlayıcılar.
#
# Ölçüldü (28 Eylül): LiteLLM `nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b` için
# pencere bilmiyor; aynı ağırlıkların OpenRouter kaydı 262.144 token bildiriyor.
# Bilinmeyen pencere en dar varsayılana düşüyor ve bağlam göstergesi büyük görevde
# birkaç dosya okuması sonra "Yakında özetlenecek" diyordu. Pencere UYDURULMAZ:
# yalnız aynı modelin katalogdaki kaydı okunur.
_OPENROUTER_MIRRORED_PREFIXES = ("nvidia_nim/",)


#: Ollama bağlamının BİLİNMEYEN durumdaki (RAM ya da model ölçülemedi) varsayılanı (token).
#: Ollama varsayılanı 4096'dır ve Fusion'ın istemi + araç şemaları (~10 bin token) bunu aşar.
#: 18 Ekim 2026'da qwen3.5 9B Q4 ile 16 GB makinede ölçüldü: 32k → 6,1 GB, 64k → 6,95 GB,
#: 128k → 8,3 GB bellek. 64k, uzun kod görevine yer bırakır ve makinede Chrome
#: oturumlarıyla rahat sığar; 128k bellek baskısı yaratır.
OLLAMA_NUM_CTX = 65536
_OLLAMA_PREFIXES = ("ollama/", "ollama_chat/")
OLLAMA_DEFAULT_API_BASE = "http://localhost:11434"
#: Yerel `/api/show` yoklamasının üst süresi (sn); Ollama kapalıysa istek anında reddedilir.
_OLLAMA_SHOW_TIMEOUT_S = 1.0
_GIB = 1024**3
#: (toplam RAM üst sınırı GiB, bağlam tavanı): küçük makinede bağlam daraltılır ama Fusion'ın
#: sistem istemi + araç şemaları (~16k) sığsın diye 32k'nın altına inilmez.
_OLLAMA_RAM_TIERS = ((12, 32_768), (32, 65_536))
_OLLAMA_RAM_TIER_MAX = 131_072


@lru_cache(maxsize=64)
def ollama_num_ctx(model: str) -> int:
    """Ollama isteğinde verilecek `num_ctx`: min(modelin gerçek penceresi, RAM'e göre tavan).

    Ölçüldü (30 Ekim): sabit 64k, 8 GB makinede bellek baskısı yaratıyor, bağlamı 8k olan
    modelde ise gerçek pencereyi aşıp göstergeyi yanıltıyordu. Pencere yerel `/api/show`'dan
    okunur (kapalıysa yok sayılır); RAM bilinmiyorsa ölçülmüş 64k varsayılanı kullanılır.
    """
    ram = _total_ram_bytes()
    cap = OLLAMA_NUM_CTX if ram is None else _ram_cap(ram)
    api_base = environ_snapshot().get("OLLAMA_API_BASE") or OLLAMA_DEFAULT_API_BASE
    model_max = _ollama_context_length(model, api_base)
    return min(cap, model_max) if model_max else cap


def _ram_cap(ram_bytes: int) -> int:
    for limit_gib, cap in _OLLAMA_RAM_TIERS:
        if ram_bytes < limit_gib * _GIB:
            return cap
    return _OLLAMA_RAM_TIER_MAX


def _total_ram_bytes() -> int | None:
    """Toplam fiziksel bellek; platform desteklemiyorsa `None`."""
    try:
        return int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))
    except (AttributeError, ValueError, OSError):
        return None


def _ollama_context_length(model: str, api_base: str) -> int | None:
    """Modelin gerçek bağlam uzunluğu (`/api/show`); ulaşılamazsa ya da okunamazsa `None`."""
    name = model.split("/", 1)[1] if model.startswith(_OLLAMA_PREFIXES) else model
    try:
        response = httpx.post(
            f"{api_base.rstrip('/')}/api/show", json={"model": name}, timeout=_OLLAMA_SHOW_TIMEOUT_S
        )
        response.raise_for_status()
        return _context_length_from_show(response.json())
    except (httpx.HTTPError, ValueError):
        return None


def _context_length_from_show(payload: object) -> int | None:
    """`model_info` içindeki `<mimari>.context_length` değerini oku."""
    info = payload.get("model_info") if isinstance(payload, dict) else None
    if not isinstance(info, dict):
        return None
    for key, value in info.items():
        if (
            isinstance(key, str)
            and key.endswith(".context_length")
            and isinstance(value, int)
            and not isinstance(value, bool)
            and value > 0
        ):
            return value
    return None


@lru_cache(maxsize=256)
def input_window_tokens(model: str) -> int | None:
    """LiteLLM metadatası yoksa sınır uydurmadan ``None`` döndür.

    Yerel Ollama modelinde pencere kataloğun söylediği DEĞİL, istekte bizim verdiğimiz
    `num_ctx`tir; özetleme eşiği buna göre kurulur.
    """
    if model.startswith(_OLLAMA_PREFIXES):
        return ollama_num_ctx(model)
    own = _catalog_window(model)
    if own is not None:
        return own
    return _mirrored_window(model)


def output_limit_tokens(model: str) -> int | None:
    """LiteLLM kataloğundaki en çok çıktı token'ı; bilinmiyorsa `None`."""
    try:
        import litellm

        value = litellm.get_model_info(model).get("max_output_tokens")
    except Exception:
        return None
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


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
