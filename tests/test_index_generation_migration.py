"""Gömme modeli değişince vektörler eski modelin koleksiyonuna eklenmez (WP12).

Ölçüldü (29 Ekim): koleksiyon eki yalnız sağlayıcı adıydı (`nvidia_nim`). NIM gömme
modeli değiştirilince yeni vektörler aynı koleksiyona gidiyordu: boyut farklıysa
ChromaDB ekleme/sorguda hata verir, aynıysa arama sessizce anlamsız sonuç döner.
Varsayılan modelin eki DEĞİŞMEZ: mevcut dersler ve kod indeksi kaybolmaz.
"""

from __future__ import annotations

import pytest

from fusion_cli.memory import embeddings
from fusion_cli.memory.embeddings import NIM_PROVIDER, build_embedding_function

_VARSAYILAN = "nvidia/nv-embedqa-e5-v5"


@pytest.fixture(autouse=True)
def _nim_erisilebilir(monkeypatch):
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "test-anahtari")
    monkeypatch.setattr(embeddings.NimEmbeddingFunction, "__call__", lambda self, _texts: [[0.0]])


def test_varsayilan_model_eski_koleksiyon_ekini_korur():
    _function, suffix = build_embedding_function(NIM_PROVIDER, _VARSAYILAN)

    assert suffix == NIM_PROVIDER


def test_farkli_model_ayri_koleksiyon_kullanir():
    _f, varsayilan = build_embedding_function(NIM_PROVIDER, _VARSAYILAN)
    _f, diger = build_embedding_function(NIM_PROVIDER, "nvidia/llama-3.2-nv-embedqa-1b-v2")
    _f, ucuncu = build_embedding_function(NIM_PROVIDER, "baidu/bge-m3")

    assert len({varsayilan, diger, ucuncu}) == 3


def test_ek_chromadb_koleksiyon_adi_kurallarina_uyar():
    import re

    _f, suffix = build_embedding_function(NIM_PROVIDER, "nvidia/llama-3.2-nv-embedqa-1b-v2")
    name = f"lessons_{suffix}"

    assert re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{1,510}[a-zA-Z0-9]", name)
