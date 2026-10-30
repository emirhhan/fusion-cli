"""Gömme sağlayıcısı seçimi.

Varsayılan YERELDİR: ChromaDB'nin gömülü ONNX modeli. Hızlı, çevrimdışı, anahtarsız.
Türkçe kalitesi orta düzeydedir.

Seçenek olarak NVIDIA NIM'in ücretsiz çok-dilli gömme modeli kullanılabilir; Türkçe
anlamsal kalite artar ama her sorguya ağ gecikmesi ekler. Bu yüzden varsayılan değildir.

Başlangıçta BİR KEZ yoklanır: NIM erişilemezse sessizce yerele düşülür ve uygulama
çalışmaya devam eder.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx

from ..core.atomic_file import atomic_replace_text
from ..core.clock import SystemClock
from ..core.constants import NIM_PROBE_CACHE_TTL_S, WEB_TIMEOUT_S
from ..core.protocols import Clock

_LOG = logging.getLogger(__name__)
#: Yoklama sonucunun önbellek dosyası (bellek dizininde).
NIM_PROBE_CACHE_NAME = "nim-embedding-probe.json"

NIM_EMBEDDINGS_URL = "https://integrate.api.nvidia.com/v1/embeddings"
#: NIM istek başına makul yığın boyutu.
NIM_BATCH = 50

LOCAL_PROVIDER = "local"
NIM_PROVIDER = "nim"
#: Eki model adı olmadan kurulan koleksiyonların modeli; bu modelin eki DEĞİŞMEZ ki
#: mevcut dersler ve kod indeksi görünmez olmasın.
LEGACY_NIM_MODEL = "nvidia/nv-embedqa-e5-v5"


class NimEmbeddingFunction:
    """ChromaDB gömme fonksiyonu — NVIDIA NIM /v1/embeddings çağırır.

    Doküman ve sorgu FARKLI `input_type` ile gömülür; e5 ailesi retrieval kalitesi
    buna bağlıdır.
    """

    def __init__(self, model: str, api_key: str) -> None:
        self._model = model
        self._key = api_key

    def name(self) -> str:
        """ChromaDB kalıcılık için gömme fonksiyonunun adını ister."""
        return f"nim:{self._model}"

    def __call__(self, input: list[str]) -> list[list[float]]:
        return self._embed(list(input), "passage")

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        return self._embed(list(input), "passage")

    def embed_query(self, input: list[str]) -> list[list[float]]:
        return self._embed(list(input), "query")

    def _embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        vectors: list[list[float]] = []
        with httpx.Client(timeout=WEB_TIMEOUT_S * 2) as client:
            for start in range(0, len(texts), NIM_BATCH):
                batch = texts[start : start + NIM_BATCH]
                response = client.post(
                    NIM_EMBEDDINGS_URL,
                    headers={"Authorization": f"Bearer {self._key}"},
                    json={
                        "model": self._model,
                        "input": batch,
                        "input_type": input_type,
                        "encoding_format": "float",
                        "truncate": "END",
                    },
                )
                response.raise_for_status()
                vectors.extend(item["embedding"] for item in response.json()["data"])
        return vectors


def build_embedding_function(
    provider: str,
    model: str,
    *,
    cache_dir: Path | None = None,
    clock: Clock | None = None,
) -> tuple[Any, str]:
    """(gömme fonksiyonu, koleksiyon eki) döndür.

    Yerel sağlayıcıda None döner: ChromaDB kendi varsayılanını kullanır. NIM istendi
    ama erişilemiyorsa SESSİZCE yerele düşülür — bellek çalışmaya devam etmelidir.

    Yoklama sonucu `cache_dir` verilmişse 10 dakika diskte önbelleklenir (M1-55): ölçüldü
    (30 Ekim) her süreç açılışı NIM'e ağ isteği atıyordu (kota + ağ gecikmesi). Yoklama
    ilk gömme çağrısına ERTELENEMEZ: koleksiyon eki ("nim…" mi yerel mi) yoklama sonucuna
    bağlıdır ve koleksiyon açılırken bilinmelidir; bu yüzden sonuç önbelleklenir.
    """
    if provider != NIM_PROVIDER:
        return None, ""

    api_key = os.getenv("NVIDIA_NIM_API_KEY")
    if not api_key:
        return None, ""

    now = (clock or SystemClock()).now()
    cached = _read_probe_cache(cache_dir, model, api_key, now)
    function = NimEmbeddingFunction(model, api_key)
    if cached is None:
        try:
            function(["yoklama"])
            cached = True
        except Exception:
            # NIM erişilemedi (ağ, kota, model adı). Yerele düşmek doğru davranıştır:
            # bellek kullanılabilir kalır, yalnızca Türkçe kalitesi biraz düşer.
            cached = False
        _write_probe_cache(cache_dir, model, api_key, ok=cached, now=now)
    if not cached:
        return None, ""
    return function, collection_suffix(model)


def _key_digest(api_key: str) -> str:
    """Anahtar değişince önbellek geçersiz olsun; anahtarın kendisi diske YAZILMAZ."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]


def _read_probe_cache(cache_dir: Path | None, model: str, api_key: str, now: float) -> bool | None:
    """Taze ve aynı model/anahtara ait yoklama sonucu; yoksa/bozuksa/eskiyse `None`."""
    if cache_dir is None:
        return None
    try:
        raw = json.loads((cache_dir / NIM_PROBE_CACHE_NAME).read_text(encoding="utf-8"))
        fresh = 0 <= now - float(raw["at"]) < NIM_PROBE_CACHE_TTL_S
        same = raw["model"] == model and raw["key"] == _key_digest(api_key)
        return bool(raw["ok"]) if fresh and same else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write_probe_cache(
    cache_dir: Path | None, model: str, api_key: str, *, ok: bool, now: float
) -> None:
    if cache_dir is None:
        return
    record = {"model": model, "key": _key_digest(api_key), "ok": ok, "at": now}
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        atomic_replace_text(cache_dir / NIM_PROBE_CACHE_NAME, json.dumps(record))
    except OSError as error:
        _LOG.warning("NIM yoklama önbelleği yazılamadı: %s", type(error).__name__)


def collection_suffix(model: str) -> str:
    """NIM koleksiyon eki: her gömme modeli kendi koleksiyonunu kullanır.

    Ölçüldü (29 Ekim): ek yalnız sağlayıcı adıydı; model değişince yeni vektörler
    eski modelin koleksiyonuna gidiyordu (boyut farklıysa ChromaDB hata verir, aynıysa
    arama sessizce anlamsız sonuç döner). Eski koleksiyon silinmez; model geri
    alınınca yeniden kullanılır.
    """
    if model == LEGACY_NIM_MODEL:
        return NIM_PROVIDER
    digest = hashlib.sha1(model.encode("utf-8"), usedforsecurity=False).hexdigest()[:10]
    return f"{NIM_PROVIDER}_{digest}"
