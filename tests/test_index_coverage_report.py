"""İndeks tavanına takılınca dışarıda kalan dosyalar bildirilir (WP12).

Ölçüldü (29 Ekim): `build_chunks` 4.000 parçada sessizce duruyordu; dolaşma
sırasında sonra gelen dosyalar indekse girmiyor, kullanıcıya söylenmiyor ve
anlamsal arama onları hiç bulamıyordu.
"""

from __future__ import annotations

from fusion_cli.core.memory import IndexStats
from fusion_cli.memory.code_index import ChromaCodeIndex
from fusion_cli.ui import messages

from .test_hybrid_retrieval import LocalRetrievalEmbedding


def _proje(tmp_path, adet: int):
    proje = tmp_path / "proje"
    proje.mkdir()
    for index in range(adet):
        (proje / f"m{index:02d}.py").write_text(f"x{index} = {index}\n", encoding="utf-8")
    return proje


def test_tavana_takilan_indeks_kismi_oldugunu_bildirir(tmp_path):
    indeks = ChromaCodeIndex(
        tmp_path / "bellek", _proje(tmp_path, 5), embedding_function=LocalRetrievalEmbedding()
    )

    stats = indeks.reindex(limit=3)

    assert stats.total == 3
    assert stats.truncated
    assert "kısmi" in messages.reindex_summary(stats)


def test_tavan_altindaki_indeks_tam_sayilir(tmp_path):
    indeks = ChromaCodeIndex(
        tmp_path / "bellek", _proje(tmp_path, 3), embedding_function=LocalRetrievalEmbedding()
    )

    stats = indeks.reindex(limit=3)

    assert stats.total == 3
    assert not stats.truncated
    assert "kısmi" not in messages.reindex_summary(stats)


def test_eski_kurucu_cagrilari_tam_indeks_varsayar():
    assert IndexStats(total=1, added=1, removed=0).truncated is False
