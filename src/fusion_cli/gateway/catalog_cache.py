"""Panel için birleşik model kataloğu — TTL önbellekli.

Sağlayıcıların `/models` uçlarından (OpenRouter ücretsiz + ücretli, NVIDIA NIM)
gelen modelleri tek listede toplar; panelde otomatik-tamamlamalı bir açılır liste
olarak sunulur. Kullanıcı artık `openrouter/…:free` gibi kimliği ezberden yazmak
zorunda değil — listeden seçer.

Katalog sık değişmediği için kısa TTL ile önbelleklenir; her panel açılışı sağlayıcı
ucunu dövmesin. Ağ ya da ayrıştırma hatasında `catalog.py` boş liste döndürür; bu bir
iyileştirmedir, gateway'i çökertmez.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from ..core.constants import CATALOG_CACHE_TTL_S
from ..providers import catalog
from ..providers.catalog import CatalogEntry

#: Bir katalog kaynağı: modelleri getiren fonksiyon.
CatalogFetcher = Callable[[], tuple[CatalogEntry, ...]]
#: (ücretsiz-mi, fetcher) çiftlerinden oluşan kaynak listesi.
CatalogSources = Sequence[tuple[bool, CatalogFetcher]]
#: Birleşik katalog üreten fonksiyon (test için enjekte edilebilir).
Aggregator = Callable[[], tuple["CatalogModel", ...]]


@dataclass(frozen=True, slots=True)
class CatalogModel:
    """Panele sunulan tek bir model satırı."""

    id: str
    provider: str
    free: bool
    context_length: int


def _default_sources() -> CatalogSources:
    """Varsayılan kaynaklar: ücretsiz kaynak ücretliden önce (tekilleştirmede kazanır)."""
    return (
        (True, catalog.fetch_openrouter_free),
        (True, catalog.fetch_nim),  # NIM ücretsiz katman; anahtar yoksa boş döner
        (False, catalog.fetch_openrouter_paid),
    )


def aggregate(sources: CatalogSources | None = None) -> tuple[CatalogModel, ...]:
    """Tüm kaynakları topla, kimliğe göre tekilleştir, kimliğe göre sırala."""
    srcs = sources if sources is not None else _default_sources()
    by_id: dict[str, CatalogModel] = {}
    for free, fetch in srcs:
        for entry in fetch():
            # İlk gören kazanır: ücretsiz kaynaklar önce geldiği için ücretsiz işareti korunur.
            by_id.setdefault(
                entry.model_id,
                CatalogModel(entry.model_id, entry.provider, free, entry.context_length),
            )
    return tuple(sorted(by_id.values(), key=lambda model: model.id))


class CatalogCache:
    """TTL'li birleşik model kataloğu önbelleği (yalnız gateway).

    `get()` senkron (bloklayan httpx) olduğundan gateway'de bir iş parçacığında
    çağrılmalıdır; olay döngüsünü bloklamamak için.
    """

    def __init__(
        self,
        aggregator: Aggregator = aggregate,
        *,
        ttl_s: float = CATALOG_CACHE_TTL_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._aggregate = aggregator
        self._ttl = ttl_s
        self._clock = clock
        self._models: tuple[CatalogModel, ...] = ()
        self._fetched_at: float | None = None

    def get(self, *, refresh: bool = False) -> tuple[CatalogModel, ...]:
        """Önbellekten döndür; süresi dolduysa ya da `refresh` ise yeniden çek."""
        now = self._clock()
        expired = self._fetched_at is None or (now - self._fetched_at) > self._ttl
        if refresh or expired:
            self._models = self._aggregate()
            self._fetched_at = now
        return self._models
