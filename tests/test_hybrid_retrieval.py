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


def test_tokenize_turkce_buyuk_i_ve_noktasiz_i_ayni_terimdir():
    """Ölçüldü (30 Ekim): `"İstanbul".lower()` = 'i' + birleşik nokta (U+0307); regex sınıfı
    U+0307'yi ayırıcı sayıp "İstanbul" → ['stanbul'], "İNDİR" → ['ndir'] yapıyordu.
    `I`→`ı` yüzünden "ISPARTA" ≠ "ısparta"/"isparta" (M1-37)."""
    assert tokenize("İstanbul") == ["istanbul"]
    assert tokenize("İNDİR") == ["indir"]
    assert tokenize("ISPARTA") == tokenize("ısparta") == tokenize("isparta") == ["isparta"]


class LocalRetrievalEmbedding:
    """Sentetik fixture: hedefler uzak, diğer belgeler/sorgular yakın vektör alır."""

    def __call__(self, input):
        return [[0.0, 1.0] if "TARGET_FAR" in text else [1.0, 0.0] for text in input]

    @staticmethod
    def is_legacy():
        return True

    @staticmethod
    def name():
        return "task7a-local-synthetic-v1"

    @staticmethod
    def get_config():
        return {}

    @staticmethod
    def build_from_config(config):
        return LocalRetrievalEmbedding()

    def embed_query(self, input):
        return self(input)


def local_retrieval_project(root, *, targets=1):
    root.mkdir()
    for number in range(24):
        (root / f"noise{number:02}.py").write_text(
            f"def generic{number}():\n    return 'unrelated nearby code'\n", encoding="utf-8"
        )
    for number in range(targets):
        (root / f"target{number:02}.py").write_text(
            f"# TARGET_FAR\ndef UnicornDispatch{number:02}():\n    return 'unique handler'\n",
            encoding="utf-8",
        )
    return root


def test_bagimsiz_lexical_havuz_vector_adayinda_olmayan_tanimlayiciyi_bulur(tmp_path):
    from fusion_cli.memory.code_index import ChromaCodeIndex

    root = local_retrieval_project(tmp_path / "project")
    baseline = ChromaCodeIndex(
        tmp_path / "memory", root, embedding_function=LocalRetrievalEmbedding()
    )
    baseline.reindex()
    assert all(
        match.path != "target00.py" for match in baseline.search("UnicornDispatch00", limit=5)
    )

    enabled = ChromaCodeIndex(
        tmp_path / "memory",
        root,
        embedding_function=LocalRetrievalEmbedding(),
        lexical_candidates=4,
    )
    assert enabled.search("UnicornDispatch00", limit=5)[0].path == "target00.py"
    assert enabled.search("UnicornDispatch00", limit=0) == ()


def test_id_siralari_eksik_vector_icin_sahte_mesafe_uretmez():
    from fusion_cli.memory.hybrid import fuse_ranked_ids

    scores = fuse_ranked_ids(("vector", "both"), ("lexical", "both"))
    assert scores["both"] > scores["vector"] == scores["lexical"]
    assert scores["vector"] == 1 / 61
    assert fuse_ranked_ids(("vector",), ()) == {"vector": 1 / 61}


def test_lexical_yalniz_maskelenmis_mevcut_indeksi_okur(tmp_path):
    from fusion_cli.memory.code_index import ChromaCodeIndex

    root = tmp_path / "project"
    root.mkdir()
    secret = "sk-or-v1-" + "a" * 48
    (root / "secret.py").write_text(f"TOKEN = '{secret}'\n", encoding="utf-8")
    index = ChromaCodeIndex(
        tmp_path / "memory",
        root,
        embedding_function=LocalRetrievalEmbedding(),
        lexical_candidates=3,
    )
    index.reindex()
    matches = index.search("TOKEN")
    assert matches and secret not in matches[0].snippet


def test_lexical_havuz_tavani_ve_sinyalsiz_sorgu_vector_sirasini_korur(tmp_path):
    from fusion_cli.memory.code_index import ChromaCodeIndex

    root = local_retrieval_project(tmp_path / "project", targets=4)
    index = ChromaCodeIndex(
        tmp_path / "memory",
        root,
        embedding_function=LocalRetrievalEmbedding(),
        lexical_candidates=1,
    )
    index.reindex()
    matches = index.search("unique handler", limit=10)
    assert sum(match.path.startswith("target") for match in matches) == 1
    assert len(index.search("", limit=5)) == 0
    assert len(index.search("zzzznomatch", limit=5)) == 5


# Sürümlü yerel/sentetik etiketler: sekiz uzak vektörlü tanımlayıcı için dört sorgu
# biçimi, her sorguya tek ilgili yol. Model başarımı ölçülmez.
LOCAL_RETRIEVAL_VERSION = "task7a-synthetic-local-v1"
LOCAL_RETRIEVAL_LABELS = (
    ("exact-00", "exact_identifier", "UnicornDispatch00", "target00.py"),
    ("tr-00", "turkish_identifier", "UnicornDispatch00 nerede", "target00.py"),
    ("en-00", "english_identifier", "find UnicornDispatch00", "target00.py"),
    ("mixed-00", "mixed_identifier", "UnicornDispatch00 kodunu göster", "target00.py"),
    ("exact-01", "exact_identifier", "UnicornDispatch01", "target01.py"),
    ("tr-01", "turkish_identifier", "UnicornDispatch01 nerede", "target01.py"),
    ("en-01", "english_identifier", "find UnicornDispatch01", "target01.py"),
    ("mixed-01", "mixed_identifier", "UnicornDispatch01 kodunu göster", "target01.py"),
    ("exact-02", "exact_identifier", "UnicornDispatch02", "target02.py"),
    ("tr-02", "turkish_identifier", "UnicornDispatch02 nerede", "target02.py"),
    ("en-02", "english_identifier", "find UnicornDispatch02", "target02.py"),
    ("mixed-02", "mixed_identifier", "UnicornDispatch02 kodunu göster", "target02.py"),
    ("exact-03", "exact_identifier", "UnicornDispatch03", "target03.py"),
    ("tr-03", "turkish_identifier", "UnicornDispatch03 nerede", "target03.py"),
    ("en-03", "english_identifier", "find UnicornDispatch03", "target03.py"),
    ("mixed-03", "mixed_identifier", "UnicornDispatch03 kodunu göster", "target03.py"),
    ("exact-04", "exact_identifier", "UnicornDispatch04", "target04.py"),
    ("tr-04", "turkish_identifier", "UnicornDispatch04 nerede", "target04.py"),
    ("en-04", "english_identifier", "find UnicornDispatch04", "target04.py"),
    ("mixed-04", "mixed_identifier", "UnicornDispatch04 kodunu göster", "target04.py"),
    ("exact-05", "exact_identifier", "UnicornDispatch05", "target05.py"),
    ("tr-05", "turkish_identifier", "UnicornDispatch05 nerede", "target05.py"),
    ("en-05", "english_identifier", "find UnicornDispatch05", "target05.py"),
    ("mixed-05", "mixed_identifier", "UnicornDispatch05 kodunu göster", "target05.py"),
    ("exact-06", "exact_identifier", "UnicornDispatch06", "target06.py"),
    ("tr-06", "turkish_identifier", "UnicornDispatch06 nerede", "target06.py"),
    ("en-06", "english_identifier", "find UnicornDispatch06", "target06.py"),
    ("mixed-06", "mixed_identifier", "UnicornDispatch06 kodunu göster", "target06.py"),
    ("exact-07", "exact_identifier", "UnicornDispatch07", "target07.py"),
    ("tr-07", "turkish_identifier", "UnicornDispatch07 nerede", "target07.py"),
    ("en-07", "english_identifier", "find UnicornDispatch07", "target07.py"),
    ("mixed-07", "mixed_identifier", "UnicornDispatch07 kodunu göster", "target07.py"),
)


def test_32_etiketli_yerel_sentetik_retrieval_replay(tmp_path, record_property):
    import hashlib
    import json
    import platform
    from importlib.metadata import version

    from fusion_cli.memory.code_index import ChromaCodeIndex

    root = local_retrieval_project(tmp_path / "project", targets=8)
    index = ChromaCodeIndex(tmp_path / "memory", root, embedding_function=LocalRetrievalEmbedding())
    index.reindex()
    hybrid = ChromaCodeIndex(
        tmp_path / "memory",
        root,
        embedding_function=LocalRetrievalEmbedding(),
        lexical_candidates=4,
    )
    corpus = [(path.name, path.read_text(encoding="utf-8")) for path in sorted(root.iterdir())]
    provenance = json.dumps(
        [LOCAL_RETRIEVAL_VERSION, corpus, LOCAL_RETRIEVAL_LABELS], ensure_ascii=False
    )
    rows = _replay_rows(index, hybrid)
    summary = _replay_summary(rows)
    report = {
        "version": LOCAL_RETRIEVAL_VERSION,
        "provenance": "local/synthetic; real Chroma; fake 2D vectors",
        "fixture_sha256": hashlib.sha256(provenance.encode()).hexdigest(),
        "python": platform.python_version(),
        "chromadb": version("chromadb"),
        "query_count": len(rows),
        "corpus_chunks": 32,
        "limit": 5,
        "lexical_candidates": 4,
        "summary": summary,
        "queries": rows,
        "limits": (
            "32 ilişkili tanımlayıcı sorgusu; kasıtlı uzak vektörler; tek sıralı geçiş; "
            "gerçek LLM/depo başarısı iddiası yok"
        ),
    }
    record_property("task7a_retrieval_metrics", json.dumps(report, ensure_ascii=False))
    assert len(rows) == 32
    assert summary["baseline"]["recall_at_5"] == 0.0
    assert summary["hybrid"]["recall_at_5"] == 1.0
    assert summary["hybrid"]["mrr_at_5"] == 1.0


def _replay_rows(index, hybrid):
    """Gerçek yerel arama çağrılarını zamanla; bağımsız yol etiketine göre puanla."""
    import time

    rows = []
    for identifier, label, query, expected in LOCAL_RETRIEVAL_LABELS:
        row = {"id": identifier, "label": label, "query": query, "expected": expected}
        for name, retriever in (("baseline", index), ("hybrid", hybrid)):
            started = time.perf_counter()
            matches = retriever.search(query, limit=5)
            elapsed = (time.perf_counter() - started) * 1000
            paths = [match.path for match in matches]
            rank = paths.index(expected) + 1 if expected in paths else None
            row[name] = {
                "recall_at_5": float(rank is not None),
                "reciprocal_rank_at_5": 1 / rank if rank is not None else 0.0,
                "latency_ms": round(elapsed, 3),
                "paths": paths,
            }
        rows.append(row)
    return rows


def _replay_summary(rows):
    """Tek ilgili yol için recall@5 ve kesilmiş MRR@5; p95 en yakın üst yüzdelik."""
    import statistics

    summary = {}
    for name in ("baseline", "hybrid"):
        samples = [row[name] for row in rows]
        latencies = sorted(sample["latency_ms"] for sample in samples)
        summary[name] = {
            "recall_at_5": statistics.mean(sample["recall_at_5"] for sample in samples),
            "mrr_at_5": statistics.mean(sample["reciprocal_rank_at_5"] for sample in samples),
            "latency_p50_ms": statistics.median(latencies),
            "latency_p95_ms": latencies[30],
        }
    return summary
