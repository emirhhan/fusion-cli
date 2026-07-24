"""Faz 2 — hibrit retrieval: BM25 lexical skor, RRF füzyonu ve kapsam filtresi.

Hepsi saf fonksiyon olarak, ağ/ChromaDB olmadan test edilir. "Bilinen sorgu →
beklenen ders" senaryosu lexical katmanın embedding'i nasıl kurtardığını gösterir.
"""

from __future__ import annotations

from fusion_cli.core.memory import Lesson, LessonKind
from fusion_cli.memory.hybrid import (
    bm25_scores,
    reciprocal_rank_fusion,
    tokenize,
)
from fusion_cli.memory.lesson_ranking import Candidate, select_lessons


def _lesson(text: str, *, scope: str = "", confidence: float = 1.0) -> Lesson:
    return Lesson(text=text, kind=LessonKind.SUCCESS, scope=scope, confidence=confidence)


# --------------------------------------------------------------------------- #
# Tokenizasyon
# --------------------------------------------------------------------------- #


def test_tokenize_turkce_ve_alt_cizgiyi_ayirir():
    tokens = tokenize("multi_edit aracını KULLAN")
    assert "multi" in tokens
    assert "edit" in tokens
    assert "kullan" in tokens


def test_tokenize_kisa_tokenlari_eler():
    assert "a" not in tokenize("a bc def")


# --------------------------------------------------------------------------- #
# BM25 lexical skor
# --------------------------------------------------------------------------- #


def test_bm25_birebir_terim_iceren_belgeyi_one_cikarir():
    documents = [
        "multi_edit ile tek seferde birden çok değişiklik yap",
        "kedi beslemek için günde iki öğün yeterlidir",
    ]
    scores = bm25_scores("multi_edit nasıl kullanılır", documents)
    assert scores[0] > scores[1]


def test_bm25_bos_sorgu_sifir_doner():
    assert bm25_scores("", ["herhangi bir belge"]) == [0.0]


def test_bm25_bos_havuz_bos_liste():
    assert bm25_scores("sorgu", []) == []


def test_bm25_nadir_terim_yaygindan_daha_agirlikli():
    documents = [
        "run_shell komutunu dikkatli kullan",
        "komutu dikkatli kullan",
        "komutu dikkatli çalıştır",
    ]
    # 'run_shell' yalnızca ilk belgede geçer (nadir) → yüksek idf.
    scores = bm25_scores("run_shell", documents)
    assert scores[0] > scores[1]
    assert scores[0] > scores[2]


# --------------------------------------------------------------------------- #
# RRF füzyonu
# --------------------------------------------------------------------------- #


def test_rrf_her_iki_sirada_iyi_olan_kazanir():
    # 0. aday hem en yakın hem lexical olarak en güçlü.
    distances = [0.1, 0.5, 0.9]
    lexical = [3.0, 1.0, 0.0]
    fused = reciprocal_rank_fusion(distances, lexical)
    assert fused[0] == max(fused)


def test_rrf_lexical_sinyal_yoksa_embedding_sirasini_korur():
    distances = [0.1, 0.4, 0.8]
    lexical = [0.0, 0.0, 0.0]
    fused = reciprocal_rank_fusion(distances, lexical)
    # Tüm lexical eşit → sıralama tümüyle mesafeye iner: en yakın en yüksek füzyon.
    assert fused[0] > fused[1] > fused[2]


def test_rrf_lexical_kurtarir():
    """Lexical birebir eşleşen uzak aday, eşleşmeyen daha yakın adayı geçebilmeli."""
    # 2. aday embedding'de en uzak ama tek lexical eşleşen; 1. aday ondan yakın ama eşleşmesiz.
    distances = [0.2, 0.3, 0.65]
    lexical = [0.0, 0.0, 5.0]
    fused = reciprocal_rank_fusion(distances, lexical)
    assert fused[2] > fused[1]


def test_rrf_uyusmayan_uzunluk_guvenli():
    assert reciprocal_rank_fusion([0.1, 0.2], [1.0]) == [0.0, 0.0]


# --------------------------------------------------------------------------- #
# Kapsam (scope) filtresi + lexical kurtarma — select_lessons
# --------------------------------------------------------------------------- #


def test_kapsam_disindaki_ders_elenir():
    bugfix = Candidate(_lesson("hata ayıkla", scope="bugfix"), distance=0.2)
    website = Candidate(_lesson("stil ekle", scope="website"), distance=0.2)
    secilen = select_lessons((bugfix, website), limit=4, scope="bugfix")
    assert [ders.text for ders in secilen] == ["hata ayıkla"]


def test_kapsamsiz_ders_her_kapsama_uyar():
    genel = Candidate(_lesson("genel kural", scope=""), distance=0.2)
    secilen = select_lessons((genel,), limit=4, scope="refactor")
    assert len(secilen) == 1


def test_lexical_eslesme_uzak_dersi_kurtarir():
    """Embedding eşiğini aşan ama lexical skoru olan aday elenmemeli."""
    uzak_ama_lexical = Candidate(
        _lesson("run_shell çıkış kodunu kontrol et"), distance=0.9, lexical=4.0, fused=0.03
    )
    secilen = select_lessons((uzak_ama_lexical,), limit=4)
    assert len(secilen) == 1


def test_yuksek_fuzyon_skoru_one_siralanir():
    dusuk = Candidate(_lesson("düşük"), distance=0.2, fused=0.01)
    yuksek = Candidate(_lesson("yüksek"), distance=0.2, fused=0.05)
    secilen = select_lessons((dusuk, yuksek), limit=4)
    assert secilen[0].text == "yüksek"
