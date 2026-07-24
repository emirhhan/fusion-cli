"""Faz 1 — yerel ders kalitesi: güven decay'i, sıralama, yazım kapısı, sır tespiti.

Hepsi saf fonksiyon olarak, ağ/ChromaDB olmadan test edilir. Depoya dokunan geriye
dönük uyumluluk ve reinforce testleri `slow` işaretiyle ayrıca çalışır.
"""

from __future__ import annotations

import pytest

from fusion_cli.core.memory import DEFAULT_LESSON_CONFIDENCE, Lesson, LessonKind, LessonSource
from fusion_cli.core.redaction import contains_sensitive
from fusion_cli.core.types import Message
from fusion_cli.engines.agent import learning
from fusion_cli.memory.lesson_ranking import Candidate, select_lessons
from fusion_cli.memory.lesson_scoring import (
    is_injectable,
    reinforced,
)


def _lesson(text: str, *, kind: LessonKind = LessonKind.SUCCESS, confidence: float = 1.0) -> Lesson:
    return Lesson(text=text, kind=kind, confidence=confidence)


# --------------------------------------------------------------------------- #
# Güven decay'i (reinforced) — saf
# --------------------------------------------------------------------------- #


def test_basari_guveni_artirir_ve_sayaci_yukseltir():
    lesson = _lesson("test calistir", confidence=0.5)
    updated = reinforced(lesson, success=True)
    assert updated.confidence > lesson.confidence
    assert updated.success_count == 1
    assert updated.failure_count == 0


def test_basarisizlik_guveni_dusurur_ve_sayaci_yukseltir():
    lesson = _lesson("test calistir", confidence=0.5)
    updated = reinforced(lesson, success=False)
    assert updated.confidence < lesson.confidence
    assert updated.failure_count == 1
    assert updated.success_count == 0


def test_basarisizlik_basaridan_daha_sert_dususur():
    base = _lesson("x", confidence=0.5)
    kazanc = reinforced(base, success=True).confidence - 0.5
    kayip = 0.5 - reinforced(base, success=False).confidence
    assert kayip > kazanc


def test_guven_sinirlar_icinde_kalir():
    assert reinforced(_lesson("x", confidence=1.0), success=True).confidence == 1.0
    assert reinforced(_lesson("x", confidence=0.0), success=False).confidence == 0.0


def test_reinforced_girdiyi_mutasyona_ugratmaz():
    lesson = _lesson("x", confidence=0.5)
    reinforced(lesson, success=False)
    assert lesson.confidence == 0.5
    assert lesson.failure_count == 0


def test_tekrarli_basarisizlik_dersi_esigin_altina_indirir():
    lesson = _lesson("kotu ders", confidence=1.0)
    for _ in range(10):
        lesson = reinforced(lesson, success=False)
    assert not is_injectable(lesson)


# --------------------------------------------------------------------------- #
# Sıralama ve eşikler (select_lessons) — saf
# --------------------------------------------------------------------------- #


def test_alakasiz_ders_elenir():
    yakin = Candidate(_lesson("alakali"), distance=0.2)
    uzak = Candidate(_lesson("alakasiz"), distance=0.9)
    secilen = select_lessons((yakin, uzak), limit=4)
    assert [ders.text for ders in secilen] == ["alakali"]


def test_dusuk_guvenli_ders_enjekte_edilmez():
    guvenli = Candidate(_lesson("guvenli", confidence=0.9), distance=0.2)
    zehirli = Candidate(_lesson("zehirli", confidence=0.1), distance=0.2)
    secilen = select_lessons((guvenli, zehirli), limit=4)
    assert [ders.text for ders in secilen] == ["guvenli"]


def test_hatalar_basarilardan_once_siralanir():
    basari = Candidate(_lesson("basari", kind=LessonKind.SUCCESS), distance=0.1)
    hata = Candidate(_lesson("hata", kind=LessonKind.MISTAKE), distance=0.3)
    secilen = select_lessons((basari, hata), limit=4)
    assert secilen[0].kind is LessonKind.MISTAKE


def test_esit_turde_yuksek_guven_one_gelir():
    dusuk = Candidate(_lesson("dusuk", confidence=0.5), distance=0.2)
    yuksek = Candidate(_lesson("yuksek", confidence=0.95), distance=0.2)
    secilen = select_lessons((dusuk, yuksek), limit=4)
    assert secilen[0].text == "yuksek"


def test_limit_uygulanir():
    adaylar = tuple(Candidate(_lesson(f"ders{i}"), distance=0.1) for i in range(5))
    assert len(select_lessons(adaylar, limit=2)) == 2


# --------------------------------------------------------------------------- #
# Sır / kişisel veri tespiti
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "text",
    [
        "anahtar sk-ABCDEFGH1234567890abcd kullan",
        "token: ghp_ABCDEFGHIJKLMNOP1234567890",
        "AWS AKIAIOSFODNN7EXAMPLE anahtari",
        "-----BEGIN RSA PRIVATE KEY-----",
        "password=supersecret123",
        "iletisim: ali@example.com",
    ],
)
def test_sir_iceren_metin_yakalanir(text):
    assert contains_sensitive(text) is True


def test_temiz_metin_sir_sayilmaz():
    assert contains_sensitive("Dosyayi degistirmeden once oku.") is False


# --------------------------------------------------------------------------- #
# Yazım kapısı (screen_lesson / screen_lessons) — saf
# --------------------------------------------------------------------------- #


def test_kanitsiz_ders_reddedilir():
    result = learning.screen_lesson(_lesson("bir sey"), (), has_evidence=False)
    assert not result.accepted
    assert "kanıt" in result.reason


def test_sirli_ders_reddedilir():
    lesson = _lesson("anahtar sk-ABCDEFGH1234567890abcd kullanildi")
    result = learning.screen_lesson(lesson, (), has_evidence=True)
    assert not result.accepted


def test_cok_benzer_ders_dedup_ile_reddedilir():
    mevcut = (_lesson("dosyayi degistirmeden once mutlaka oku ve kontrol et"),)
    aday = _lesson("dosyayi degistirmeden once mutlaka oku ve kontrol et ayrica")
    result = learning.screen_lesson(aday, mevcut, has_evidence=True)
    assert not result.accepted


def test_farkli_ders_kabul_edilir():
    mevcut = (_lesson("dosyayi once oku"),)
    aday = _lesson("test kirilinca implementasyonu duzelt sakin testi silme")
    result = learning.screen_lesson(aday, mevcut, has_evidence=True)
    assert result.accepted


def test_celiskili_ders_isaretlenir_ama_kabul_edilir():
    mevcut = (_lesson("multi_edit araci kullan"),)
    aday = _lesson("multi_edit araci kullanma")
    result = learning.screen_lesson(aday, mevcut, has_evidence=True)
    assert result.accepted
    assert result.contradiction is True


def test_screen_lessons_kabul_edilenler_sonrakilere_dedup_uygular():
    aday = _lesson("test kirilinca implementasyonu duzelt sakin testi silme")
    ikiz = _lesson("test kirilinca implementasyonu duzelt sakin testi silme kesinlikle")
    kabul = learning.screen_lessons((aday, ikiz), (), has_evidence=True)
    assert len(kabul) == 1


def test_measurable_evidence_arac_mesajiyla_dogru():
    with_tool = [Message("assistant", "x"), Message("tool", "cikti", ok=True)]
    without_tool = [Message("assistant", "x"), Message("user", "y")]
    assert learning.has_measurable_evidence(with_tool) is True
    assert learning.has_measurable_evidence(without_tool) is False


# --------------------------------------------------------------------------- #
# Depo: geriye dönük uyumluluk ve reinforce (gerçek ChromaDB — yavaş)
# --------------------------------------------------------------------------- #


@pytest.mark.slow
def test_eski_kayit_varsayilan_guvenle_okunur(tmp_path):
    """Güven/sayaç alanları taşınmadan yazılmış eski kayıt varsayılanla okunmalı."""
    from fusion_cli.memory.lessons import ChromaLessonMemory, _to_lesson

    bellek = ChromaLessonMemory(tmp_path)
    bellek.add(Lesson(text="eski ders", kind=LessonKind.SUCCESS))
    # Eski metadata'yı taklit et: yeni alanlar hiç yok.
    eski = _to_lesson("eski ders", {"kind": "success", "source": "seed"})
    assert eski.confidence == DEFAULT_LESSON_CONFIDENCE
    assert eski.success_count == 0
    assert eski.source is LessonSource.SEED


@pytest.mark.slow
def test_reinforce_basarisizlikta_guveni_dusurur(tmp_path):
    from fusion_cli.memory.lessons import ChromaLessonMemory

    bellek = ChromaLessonMemory(tmp_path)
    bellek.add(Lesson(text="denenecek ders", kind=LessonKind.SUCCESS))

    updated = bellek.reinforce(("denenecek ders",), success=False)
    assert updated == 1
    kayit = bellek.all()[0]
    assert kayit.confidence < DEFAULT_LESSON_CONFIDENCE
    assert kayit.failure_count == 1


@pytest.mark.slow
def test_reinforce_eslesmeyen_metni_atlar(tmp_path):
    from fusion_cli.memory.lessons import ChromaLessonMemory

    bellek = ChromaLessonMemory(tmp_path)
    bellek.add(Lesson(text="var olan", kind=LessonKind.SUCCESS))
    assert bellek.reinforce(("olmayan ders",), success=True) == 0
