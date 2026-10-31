"""`/v1/embeddings` köprüsü — OpenAI gömme isteğini Fusion'ın gömme sağlayıcısına çevir (P-074).

Gömme fonksiyonu bellek katmanındaki yapılandırmadan gelir (`embedding.provider`: `nim`
ya da `local`). Yerel sağlayıcı ChromaDB'nin gömülü ONNX modelidir; kurulu değilse 501
döner, gateway çökmez. Vektörler iş parçacığında hesaplanır (bloklayan HTTP/ONNX çağrısı
olay döngüsünü tutmaz).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping
from typing import Any

from ..config.models import Config
from .translate import GatewayError

_LOG = logging.getLogger(__name__)

#: Metin listesi → vektör listesi.
EmbedFunction = Callable[[list[str]], list[list[float]]]


class EmbeddingUnavailableError(Exception):
    """Yapılandırılmış gömme sağlayıcısı bu süreçte kullanılamıyor (501)."""


def parse_inputs(payload: Mapping[str, object]) -> tuple[list[str], str]:
    """`input` (metin ya da metin listesi) ve istenen model adını çıkar."""
    raw = payload.get("input")
    if isinstance(raw, str):
        texts = [raw]
    elif isinstance(raw, list) and raw and all(isinstance(item, str) for item in raw):
        texts = list(raw)
    else:
        raise GatewayError("'input' bir metin ya da boş olmayan metin listesi olmalı.")
    if not any(text.strip() for text in texts):
        raise GatewayError("'input' boş metin içeremez.")
    return texts, str(payload.get("model", "") or "")


def build_embedder(config: Config) -> tuple[EmbedFunction, str]:
    """(gömme fonksiyonu, model adı). Sağlayıcı kurulamazsa `EmbeddingUnavailable`."""
    from ..memory.embeddings import build_embedding_function

    function, _suffix = build_embedding_function(config.embedding.provider, config.embedding.model)
    if function is not None:
        return function, config.embedding.model
    try:
        # Tembel: chromadb ağırdır, yalnız gömme istendiğinde yüklenir.
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
    except ImportError as error:
        raise EmbeddingUnavailableError(
            "Yerel gömme modeli için chromadb kurulu değil (pip install 'fusion-cli[memory]')."
        ) from error
    try:
        default = DefaultEmbeddingFunction()
    except Exception as error:  # ONNX modeli indirilemedi vb.; sınır katmanı, log'lanır
        _LOG.warning("Yerel gömme modeli kurulamadı", extra={"hata": type(error).__name__})
        raise EmbeddingUnavailableError(f"Yerel gömme modeli kurulamadı: {error}") from error

    def _embed(texts: list[str]) -> list[list[float]]:
        return [list(map(float, vector)) for vector in default(texts)]

    return _embed, "chromadb/all-MiniLM-L6-v2"


async def embed(texts: list[str], function: EmbedFunction) -> list[list[float]]:
    return await asyncio.to_thread(function, texts)


def to_openai_embeddings(
    vectors: list[list[float]], model: str, texts: list[str]
) -> dict[str, Any]:
    """OpenAI `list` zarfı; token sayısı bilinmediği için kaba karakter/4 tahmini yazılır."""
    approx_tokens = sum(max(1, len(text) // 4) for text in texts)
    return {
        "object": "list",
        "data": [
            {"object": "embedding", "index": index, "embedding": vector}
            for index, vector in enumerate(vectors)
        ],
        "model": model,
        "usage": {"prompt_tokens": approx_tokens, "total_tokens": approx_tokens},
    }
