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


# M1-55 — Ölçüldü (30 Ekim): her süreç açılışında NIM'e yoklama isteği gidiyordu (kota + gecikme).
class _Saat:
    def __init__(self) -> None:
        self.value = 1_000_000.0

    def now(self) -> float:
        return self.value

    def monotonic(self) -> float:
        return self.value


@pytest.fixture
def yoklama_sayaci(monkeypatch):
    sayac = {"cagri": 0, "basarili": True}

    def yokla(self, _texts):
        sayac["cagri"] += 1
        if not sayac["basarili"]:
            raise RuntimeError("erişilemedi")
        return [[0.0]]

    monkeypatch.setattr(embeddings.NimEmbeddingFunction, "__call__", yokla)
    return sayac


def test_yoklama_sonucu_10_dakika_diskte_onbelleklenir(tmp_path, yoklama_sayaci):
    saat = _Saat()
    for _ in range(3):
        function, suffix = build_embedding_function(
            NIM_PROVIDER, _VARSAYILAN, cache_dir=tmp_path, clock=saat
        )
        assert function is not None and suffix == NIM_PROVIDER

    assert yoklama_sayaci["cagri"] == 1
    saat.value += 601
    build_embedding_function(NIM_PROVIDER, _VARSAYILAN, cache_dir=tmp_path, clock=saat)
    assert yoklama_sayaci["cagri"] == 2


def test_basarisiz_yoklama_da_onbelleklenir_yerele_dusulur(tmp_path, yoklama_sayaci):
    yoklama_sayaci["basarili"] = False
    saat = _Saat()

    for _ in range(2):
        function, suffix = build_embedding_function(
            NIM_PROVIDER, _VARSAYILAN, cache_dir=tmp_path, clock=saat
        )
        assert function is None and suffix == ""

    assert yoklama_sayaci["cagri"] == 1


def test_model_ya_da_anahtar_degisince_onbellek_gecersizdir(tmp_path, monkeypatch, yoklama_sayaci):
    saat = _Saat()
    build_embedding_function(NIM_PROVIDER, _VARSAYILAN, cache_dir=tmp_path, clock=saat)
    build_embedding_function(NIM_PROVIDER, "baidu/bge-m3", cache_dir=tmp_path, clock=saat)
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "baska-anahtar")
    build_embedding_function(NIM_PROVIDER, "baidu/bge-m3", cache_dir=tmp_path, clock=saat)

    assert yoklama_sayaci["cagri"] == 3


def test_onbellek_dosyasi_anahtari_acik_yazmaz_bozuksa_yoklar(tmp_path, yoklama_sayaci):
    saat = _Saat()
    build_embedding_function(NIM_PROVIDER, _VARSAYILAN, cache_dir=tmp_path, clock=saat)
    dosya = tmp_path / embeddings.NIM_PROBE_CACHE_NAME
    assert "test-anahtari" not in dosya.read_text(encoding="utf-8")

    dosya.write_text("{bozuk", encoding="utf-8")
    build_embedding_function(NIM_PROVIDER, _VARSAYILAN, cache_dir=tmp_path, clock=saat)

    assert yoklama_sayaci["cagri"] == 2
