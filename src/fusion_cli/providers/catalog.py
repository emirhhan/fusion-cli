"""Sağlayıcı model katalogları.

Varsayılan modeller sağlayıcı tarafında SESSİZCE kaybolabiliyor: taşıma sırasında
`z-ai/glm-5.2` NIM kataloğunda hiç yoktu ve `tencent/hy3:free` ücretsiz katmandan
çıkarılmıştı — ikisi de yapılandırmada duruyordu ve hiçbir model yanıt vermiyordu.

Bu modül canlı katalogdan gerçekten kullanılabilir modelleri listeler; bir daha
"neden hiçbir şey çalışmıyor?" sorusunu tahminle cevaplamak gerekmez.

Ağ ya da ayrıştırma hatasında istisna fırlatmaz; boş liste döner.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from ..core.constants import WEB_TIMEOUT_S

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
NIM_MODELS_URL = "https://integrate.api.nvidia.com/v1/models"

#: OpenRouter'da ücretsiz sayılan girdi fiyatları.
_FREE_PRICES = frozenset({"0", "0.0", "0.00"})


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """Katalogdan gelen bir model."""

    #: LiteLLM biçiminde kullanılabilir kimlik ("<sağlayıcı>/<model>").
    model_id: str
    provider: str
    context_length: int = 0


def fetch_openrouter_free(timeout_s: float = WEB_TIMEOUT_S) -> tuple[CatalogEntry, ...]:
    """OpenRouter'ın ÜCRETSİZ modelleri. Anahtar gerekmez (public uç)."""
    data = _get_json(OPENROUTER_MODELS_URL, timeout_s=timeout_s)
    entries = [
        CatalogEntry(
            model_id=f"openrouter/{item['id']}",
            provider="openrouter",
            context_length=_as_int(item.get("context_length")),
        )
        for item in data
        if _is_free(item) and item.get("id")
    ]
    return tuple(sorted(entries, key=lambda entry: entry.model_id))


def fetch_nim(timeout_s: float = WEB_TIMEOUT_S) -> tuple[CatalogEntry, ...]:
    """NVIDIA NIM kataloğu. Anahtar yoksa boş döner."""
    api_key = os.getenv("NVIDIA_NIM_API_KEY")
    if not api_key:
        return ()
    data = _get_json(
        NIM_MODELS_URL, timeout_s=timeout_s, headers={"Authorization": f"Bearer {api_key}"}
    )
    entries = [
        CatalogEntry(model_id=f"nvidia_nim/{item['id']}", provider="nvidia_nim")
        for item in data
        if item.get("id")
    ]
    return tuple(sorted(entries, key=lambda entry: entry.model_id))


def _as_int(value: object) -> int:
    """Katalog alanları tipsizdir; sayıya çevrilemeyen değer 0 sayılır."""
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _is_free(item: dict[str, object]) -> bool:
    pricing = item.get("pricing")
    if not isinstance(pricing, dict):
        return False
    return str(pricing.get("prompt", "")).strip() in _FREE_PRICES


def _get_json(
    url: str, *, timeout_s: float, headers: dict[str, str] | None = None
) -> list[dict[str, object]]:
    try:
        with httpx.Client(timeout=timeout_s) as client:
            response = client.get(url, headers=headers or {})
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        # Katalog alınamadı: bu bir iyileştirmedir, komutun çökmesine değmez.
        return []
    data = payload.get("data") if isinstance(payload, dict) else None
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
