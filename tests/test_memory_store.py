"""ChromaDB destekli bellek — gerçek depoyla, geçici dizinde, ağsız."""

from __future__ import annotations

import pytest

from fusion_cli.core.memory import Feedback, Lesson, LessonKind, LessonSource, Outcome
from fusion_cli.memory.code_index import ChromaCodeIndex, format_matches
from fusion_cli.memory.lessons import ChromaLessonMemory
from fusion_cli.memory.performance import ChromaPerformanceMemory
from fusion_cli.memory.seed import SEED_LESSONS, seed
from fusion_cli.memory.store import reset_clients

pytestmark = pytest.mark.slow


@pytest.fixture(autouse=True)
def _izole_istemci():
    reset_clients()
    yield
    reset_clients()


def _sonuc(model, *, score=0.9, latency=1000, won=True, task_type="general"):
    return Outcome(
        task="ornek gorev",
        task_type=task_type,
        model_name=model,
        score=score,
        latency_ms=latency,
        tokens=100,
        won=won,
    )


# --- Performans belleği ------------------------------------------------------ #


def test_kayit_sonrasi_en_iyi_model_bulunur(tmp_path):
    bellek = ChromaPerformanceMemory(tmp_path)
    bellek.record(_sonuc("iyi", score=0.95))
    bellek.record(_sonuc("kotu", score=0.40))

    assert bellek.best_model("general") == "iyi"


def test_gorev_tipleri_birbirini_etkilemez(tmp_path):
    bellek = ChromaPerformanceMemory(tmp_path)
    bellek.record(_sonuc("kodcu", score=0.95, task_type="code"))
    bellek.record(_sonuc("genelci", score=0.95, task_type="general"))

    assert bellek.best_model("code") == "kodcu"
    assert bellek.best_model("general") == "genelci"


def test_kayit_yoksa_en_iyi_model_yok(tmp_path):
    assert ChromaPerformanceMemory(tmp_path).best_model("general") is None


def test_istatistikler_puana_gore_sirali(tmp_path):
    bellek = ChromaPerformanceMemory(tmp_path)
    bellek.record(_sonuc("dusuk", score=0.3, won=False))
    bellek.record(_sonuc("yuksek", score=0.9))

    satirlar = bellek.stats()

    assert [row.model for row in satirlar] == ["yuksek", "dusuk"]
    assert satirlar[0].wins == 1 and satirlar[1].wins == 0


def test_geri_bildirim_puani_dusurur(tmp_path):
    bellek = ChromaPerformanceMemory(tmp_path)
    bellek.record(_sonuc("model", score=0.9))

    assert bellek.apply_feedback("general", "model", Feedback.BAD) == 1
    assert bellek.stats()[0].avg_score == pytest.approx(0.8, abs=0.001)


def test_geri_bildirim_kayit_yoksa_sifir_doner(tmp_path):
    bellek = ChromaPerformanceMemory(tmp_path)

    assert bellek.apply_feedback("general", "yok", Feedback.GOOD) == 0


def test_puan_bir_ustune_cikamaz(tmp_path):
    bellek = ChromaPerformanceMemory(tmp_path)
    bellek.record(_sonuc("model", score=0.98))

    bellek.apply_feedback("general", "model", Feedback.GOOD)

    assert bellek.stats()[0].avg_score <= 1.0


# --- Ders belleği ------------------------------------------------------------ #


def test_ders_eklenir_ve_okunur(tmp_path):
    bellek = ChromaLessonMemory(tmp_path)

    assert bellek.add(Lesson(text="kor edit yapma", kind=LessonKind.MISTAKE))
    assert bellek.count() == 1
    assert bellek.all()[0].kind is LessonKind.MISTAKE


def test_ayni_ders_iki_kez_eklenmez(tmp_path):
    bellek = ChromaLessonMemory(tmp_path)
    ders = Lesson(text="tekrar eden ders", kind=LessonKind.SUCCESS)

    assert bellek.add(ders)
    assert not bellek.add(ders)
    assert bellek.count() == 1


def test_bos_ders_reddedilir(tmp_path):
    assert not ChromaLessonMemory(tmp_path).add(Lesson(text="  ", kind=LessonKind.SUCCESS))


def test_alakali_ders_hatirlanir_alakasiz_elenir(tmp_path):
    bellek = ChromaLessonMemory(tmp_path)
    bellek.add(
        Lesson(
            text="Dosya duzenlemeden once mutlaka oku, kor degisiklik yapma.",
            kind=LessonKind.SUCCESS,
        )
    )
    bellek.add(
        Lesson(text="Kedi beslemek icin gunde iki ogun yeterlidir.", kind=LessonKind.SUCCESS)
    )

    hatirlanan = bellek.recall("bir dosyayi degistirecegim, once ne yapmaliyim?")

    metinler = [ders.text for ders in hatirlanan]
    assert any("kor degisiklik" in metin for metin in metinler)
    assert not any("Kedi" in metin for metin in metinler)


def test_hatalar_basarilardan_once_gelir(tmp_path):
    bellek = ChromaLessonMemory(tmp_path)
    bellek.add(Lesson(text="testi degil implementasyonu duzelt", kind=LessonKind.SUCCESS))
    bellek.add(Lesson(text="test kirilinca testi silme", kind=LessonKind.MISTAKE))

    hatirlanan = bellek.recall("testler kirildi ne yapmaliyim")

    assert hatirlanan[0].kind is LessonKind.MISTAKE


def test_bos_bellekte_hatirlama_bos_doner(tmp_path):
    assert ChromaLessonMemory(tmp_path).recall("herhangi bir gorev") == ()


def test_seed_tekrar_calistirilabilir(tmp_path):
    bellek = ChromaLessonMemory(tmp_path)

    ilk = seed(bellek)
    ikinci = seed(bellek)

    assert ilk == len(SEED_LESSONS)
    assert ikinci == 0


def test_kaynak_bilgisi_korunur(tmp_path):
    bellek = ChromaLessonMemory(tmp_path)
    bellek.add(
        Lesson(text="elle ogretilen kural", kind=LessonKind.SUCCESS, source=LessonSource.MANUAL)
    )

    assert bellek.all()[0].source is LessonSource.MANUAL


# --- Kod indeksi ------------------------------------------------------------- #


def test_indeks_kurulur_ve_anlamsal_arama_yapar(tmp_path):
    proje = tmp_path / "proje"
    proje.mkdir()
    (proje / "auth.py").write_text(
        "def kullanici_dogrula(kullanici, parola):\n"
        "    '''Kullanici kimligini dogrular ve oturum acar.'''\n"
        "    return kullanici.parola == parola\n",
        encoding="utf-8",
    )
    (proje / "rapor.py").write_text(
        "def aylik_satis_raporu(kayitlar):\n    return sum(kayitlar)\n", encoding="utf-8"
    )

    indeks = ChromaCodeIndex(tmp_path / "bellek", proje)
    stats = indeks.reindex()

    assert stats.total == 2 and stats.added == 2
    eslesmeler = indeks.search("kimlik dogrulama nerede yapiliyor?", limit=1)
    assert eslesmeler and eslesmeler[0].path == "auth.py"


def test_degismemis_repoda_yeniden_gomme_olmaz(tmp_path):
    proje = tmp_path / "proje"
    proje.mkdir()
    (proje / "a.py").write_text("x = 1\n", encoding="utf-8")
    indeks = ChromaCodeIndex(tmp_path / "bellek", proje)
    indeks.reindex()

    ikinci = indeks.reindex()

    assert ikinci.added == 0 and ikinci.removed == 0
    assert ikinci.unchanged == ikinci.total


def test_silinen_dosya_indeksten_cikarilir(tmp_path):
    proje = tmp_path / "proje"
    proje.mkdir()
    (proje / "a.py").write_text("x = 1\n", encoding="utf-8")
    (proje / "b.py").write_text("y = 2\n", encoding="utf-8")
    indeks = ChromaCodeIndex(tmp_path / "bellek", proje)
    indeks.reindex()

    (proje / "b.py").unlink()
    stats = indeks.reindex()

    assert stats.removed == 1 and stats.total == 1


def test_bos_indekste_arama_bos_doner(tmp_path):
    proje = tmp_path / "proje"
    proje.mkdir()

    assert ChromaCodeIndex(tmp_path / "bellek", proje).search("herhangi bir sey") == ()


def test_eslesmeler_modele_okunur_metne_cevrilir():
    from fusion_cli.core.memory import CodeMatch

    metin = format_matches((CodeMatch(path="a.py", start_line=1, end_line=5, snippet="kod"),))

    assert "a.py:1-5" in metin and "kod" in metin


def test_eslesme_yoksa_bilgilendirici_metin():
    assert "eşleşme yok" in format_matches(())
