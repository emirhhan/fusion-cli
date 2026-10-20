"""Gömme sağlayıcısı seçimi.

Varsayılan YERELDİR: ChromaDB'nin gömülü ONNX modeli. Hızlı, çevrimdışı, anahtarsız.
Türkçe kalitesi orta düzeydedir.

Seçenek olarak NVIDIA NIM'in ücretsiz çok-dilli gömme modeli kullanılabilir; Türkçe
anlamsal kalite artar ama her sorguya ağ gecikmesi ekler. Bu yüzden varsayılan değildir.

Başlangıçta BİR KEZ yoklanır: NIM erişilemezse sessizce yerele düşülür ve uygulama
çalışmaya devam eder.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from ..core.constants import WEB_TIMEOUT_S

NIM_EMBEDDINGS_URL = "https://integrate.api.nvidia.com/v1/embeddings"
#: NIM istek başına makul yığın boyutu.
NIM_BATCH = 50

LOCAL_PROVIDER = "local"
NIM_PROVIDER = "nim"


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


def build_embedding_function(provider: str, model: str) -> tuple[Any, str]:
    """(gömme fonksiyonu, koleksiyon eki) döndür.

    Yerel sağlayıcıda None döner: ChromaDB kendi varsayılanını kullanır. NIM istendi
    ama erişilemiyorsa SESSİZCE yerele düşülür — bellek çalışmaya devam etmelidir.
    """
    if provider != NIM_PROVIDER:
        return None, ""

    api_key = os.getenv("NVIDIA_NIM_API_KEY")
    if not api_key:
        return None, ""

    function = NimEmbeddingFunction(model, api_key)
    try:
        function(["yoklama"])
    except Exception:
        # NIM erişilemedi (ağ, kota, model adı). Yerele düşmek doğru davranıştır:
        # bellek kullanılabilir kalır, yalnızca Türkçe kalitesi biraz düşer.
        return None, ""
    return function, NIM_PROVIDER
