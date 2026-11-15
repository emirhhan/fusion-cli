"""Gömme modeli değişince vektörler eski modelin koleksiyonuna eklenmez (WP12).

Ölçüldü (29 Ekim): koleksiyon eki yalnız sağlayıcı adıydı (`nvidia_nim`). NIM gömme
modeli değiştirilince yeni vektörler aynı koleksiyona gidiyordu: boyut farklıysa
ChromaDB ekleme/sorguda hata verir, aynıysa arama sessizce anlamsız sonuç döner.
Varsayılan modelin eki DEĞİŞMEZ: mevcut dersler ve kod indeksi kaybolmaz.
"""

from __future__ import annotations

from pathlib import Path

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


def test_symbol_stratejisi_eski_embeddingi_kullanmaz_ve_reindex_artimlidir(tmp_path):
    from fusion_cli.memory.code_index import ChromaCodeIndex

    from .test_hybrid_retrieval import LocalRetrievalEmbedding

    root = tmp_path / "project"
    root.mkdir()
    (root / "a.py").write_text("def exactSymbol():\n    return 1\n", encoding="utf-8")
    lines = ChromaCodeIndex(tmp_path / "memory", root, embedding_function=LocalRetrievalEmbedding())
    lines.reindex()
    symbols = ChromaCodeIndex(
        tmp_path / "memory",
        root,
        embedding_function=LocalRetrievalEmbedding(),
        chunk_strategy="symbols",
        lexical_candidates=4,
    )
    assert symbols.search("exactSymbol") == ()
    assert symbols.reindex().added == 1
    assert symbols.search("exactSymbol")[0].path == "a.py"
    assert symbols.reindex().added == 0
    assert lines.search("exactSymbol") == ()


def test_reindex_silinen_ve_degisen_chunk_lexicalden_donmez(tmp_path):
    from fusion_cli.memory.code_index import ChromaCodeIndex

    from .test_hybrid_retrieval import LocalRetrievalEmbedding

    root = tmp_path / "project"
    root.mkdir()
    path = root / "a.py"
    path.write_text("def oldIdentifier():\n    return 1\n", encoding="utf-8")
    index = ChromaCodeIndex(
        tmp_path / "memory",
        root,
        embedding_function=LocalRetrievalEmbedding(),
        lexical_candidates=5,
    )
    index.reindex()
    assert "oldIdentifier" in index.search("oldIdentifier")[0].snippet
    path.write_text("def newIdentifier():\n    return 2\n", encoding="utf-8")
    stats = index.reindex()
    assert stats.added == stats.removed == 1
    assert all("oldIdentifier" not in match.snippet for match in index.search("oldIdentifier"))
    path.unlink()
    index.reindex()
    assert index.search("newIdentifier") == ()


def test_ayni_indeksi_kullanan_diger_nesne_guncel_nesli_gorur(tmp_path):
    from fusion_cli.memory.code_index import ChromaCodeIndex

    from .test_hybrid_retrieval import LocalRetrievalEmbedding

    root = tmp_path / "project"
    root.mkdir()
    path = root / "a.py"
    path.write_text("def beforeGeneration():\n    return 1\n", encoding="utf-8")
    first = ChromaCodeIndex(
        tmp_path / "memory",
        root,
        embedding_function=LocalRetrievalEmbedding(),
        lexical_candidates=4,
    )
    first.reindex()
    second = ChromaCodeIndex(
        tmp_path / "memory",
        root,
        embedding_function=LocalRetrievalEmbedding(),
        lexical_candidates=4,
    )
    path.write_text("def afterGeneration():\n    return 2\n", encoding="utf-8")
    second.reindex()
    matches = first.search("afterGeneration")
    assert matches and "afterGeneration" in matches[0].snippet
    assert all(
        "beforeGeneration" not in match.snippet for match in first.search("beforeGeneration")
    )


@pytest.mark.parametrize("lexical_candidates", [0, 4])
@pytest.mark.parametrize("is_existing_reader", [False, True])
@pytest.mark.parametrize("mutation", ["delete", "change", "failed_add"])
def test_basarisiz_fiziksel_silme_diger_nesnede_eski_chunk_dondurmez(
    tmp_path, monkeypatch, lexical_candidates, is_existing_reader, mutation
):
    from fusion_cli.memory.code_index import ChromaCodeIndex

    from .test_hybrid_retrieval import LocalRetrievalEmbedding

    root = tmp_path / "project"
    root.mkdir()
    path = root / "a.py"
    path.write_text("def obsoleteIdentifier():\n    return 1\n", encoding="utf-8")
    writer = ChromaCodeIndex(
        tmp_path / "memory",
        root,
        embedding_function=LocalRetrievalEmbedding(),
        lexical_candidates=lexical_candidates,
    )
    writer.reindex()
    reader = (
        ChromaCodeIndex(
            tmp_path / "memory",
            root,
            embedding_function=LocalRetrievalEmbedding(),
            lexical_candidates=lexical_candidates,
        )
        if is_existing_reader
        else None
    )
    monkeypatch.setattr(writer._collection, "delete", lambda **kwargs: False)
    if mutation == "delete":
        path.unlink()
    else:
        path.write_text("def currentIdentifier():\n    return 2\n", encoding="utf-8")
    if mutation == "failed_add":
        monkeypatch.setattr(writer._collection, "add", lambda **kwargs: False)
    stats = writer.reindex()
    assert stats.failed >= 1
    assert writer._collection.count() >= 1
    if reader is None:
        reader = ChromaCodeIndex(
            tmp_path / "memory",
            root,
            embedding_function=LocalRetrievalEmbedding(),
            lexical_candidates=lexical_candidates,
        )
    matches = reader.search("obsoleteIdentifier")
    assert all("obsoleteIdentifier" not in match.snippet for match in matches)
    if mutation == "change":
        assert "currentIdentifier" in reader.search("currentIdentifier")[0].snippet
    else:
        assert matches == ()


@pytest.mark.parametrize("unsafe_path", ["outside", "symlink", "environment", "excluded"])
def test_guvensiz_indeks_yolu_kaynak_okumadan_elenir(tmp_path, monkeypatch, unsafe_path):
    from fusion_cli.memory import code_index

    from .test_hybrid_retrieval import LocalRetrievalEmbedding

    root = tmp_path / "project"
    root.mkdir()
    source = root / "a.py"
    source.write_text("def indexedIdentifier():\n    return 1\n", encoding="utf-8")
    index = code_index.ChromaCodeIndex(
        tmp_path / "memory",
        root,
        embedding_function=LocalRetrievalEmbedding(),
        lexical_candidates=4,
    )
    index.reindex()
    identifier = index._collection.get(include=[])["ids"][0]
    outside = tmp_path / "outside.py"
    outside.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    if unsafe_path == "outside":
        candidate_path = "../outside.py"
    elif unsafe_path == "symlink":
        (root / "alias.py").symlink_to(outside)
        candidate_path = "alias.py"
    elif unsafe_path == "environment":
        (root / ".env.py").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        candidate_path = ".env.py"
    else:
        (root / "node_modules").mkdir()
        (root / "node_modules" / "a.py").write_text(
            source.read_text(encoding="utf-8"), encoding="utf-8"
        )
        candidate_path = "node_modules/a.py"
    index._collection.update(ids=[identifier], metadatas=[{"path": candidate_path}])

    def forbidden_read(*args, **kwargs):
        raise AssertionError("Güvensiz aday için kaynak okunmamalı")

    monkeypatch.setattr("fusion_cli.core.source_read.os.read", forbidden_read)
    assert index.search("indexedIdentifier") == ()


def test_okunamayan_mevcut_kaynak_eski_chunk_dondurmez(tmp_path, monkeypatch):
    from fusion_cli.memory.code_index import ChromaCodeIndex

    from .test_hybrid_retrieval import LocalRetrievalEmbedding

    root = tmp_path / "project"
    root.mkdir()
    (root / "a.py").write_text("def currentIdentifier():\n    return 1\n", encoding="utf-8")
    index = ChromaCodeIndex(
        tmp_path / "memory",
        root,
        embedding_function=LocalRetrievalEmbedding(),
        lexical_candidates=4,
    )
    index.reindex()

    def unreadable(*args, **kwargs):
        raise PermissionError("Kaynak okunamıyor")

    monkeypatch.setattr("fusion_cli.core.source_read.os.open", unreadable)
    assert index.search("currentIdentifier") == ()


def test_bellek_ortak_descriptor_okumasini_kullanir_ve_utf8_hata_davranisini_korur(
    tmp_path, monkeypatch
):
    from fusion_cli.memory import code_index
    from fusion_cli.memory.chunking import MAX_FILE_BYTES

    from .test_hybrid_retrieval import LocalRetrievalEmbedding

    root = tmp_path / "project"
    root.mkdir()
    (root / "a.py").write_bytes(b"def currentIdentifier():\n    return 1\n# \xff\n")
    index = code_index.ChromaCodeIndex(
        tmp_path / "memory",
        root,
        embedding_function=LocalRetrievalEmbedding(),
        lexical_candidates=4,
    )
    index.reindex()
    read_scoped_source = code_index.read_scoped_source
    calls = []

    def record_read(source_root, relative, *, max_bytes):
        calls.append((source_root, relative, max_bytes))
        return read_scoped_source(source_root, relative, max_bytes=max_bytes)

    monkeypatch.setattr(code_index, "read_scoped_source", record_read)
    matches = index.search("currentIdentifier")
    assert matches and "currentIdentifier" in matches[0].snippet
    assert calls == [(root, Path("a.py"), MAX_FILE_BYTES)]


@pytest.mark.parametrize("lexical_candidates", [0, 4])
def test_bellek_guvenli_okuma_destegi_yoksa_eski_kaynak_dondurmez(
    tmp_path, monkeypatch, lexical_candidates
):
    import os

    from fusion_cli.memory.code_index import ChromaCodeIndex

    from .test_hybrid_retrieval import LocalRetrievalEmbedding

    root = tmp_path / "project"
    root.mkdir()
    (root / "a.py").write_text("def currentIdentifier():\n    return 1\n", encoding="utf-8")
    index = ChromaCodeIndex(
        tmp_path / "memory",
        root,
        embedding_function=LocalRetrievalEmbedding(),
        lexical_candidates=lexical_candidates,
    )
    index.reindex()
    monkeypatch.setattr(os, "supports_dir_fd", set())
    assert index.search("currentIdentifier") == ()
