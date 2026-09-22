"""Öğretmen → ders belleği köprüsü, çakışma kontrolüyle (Faz 4, Görev 3)."""

from __future__ import annotations

from fusion_cli.core.memory import Lesson, LessonKind, LessonSource
from fusion_cli.engines.agent.teacher_lessons import sync_teacher_lesson


class _SahteDersBellegi:
    def __init__(self, *, recall_sonucu=()):
        self._recall_sonucu = recall_sonucu
        self.eklenenler: list[Lesson] = []
        self._var_olanlar: set[str] = set()

    def add(self, lesson: Lesson) -> bool:
        if lesson.text.strip().lower() in self._var_olanlar:
            return False
        self._var_olanlar.add(lesson.text.strip().lower())
        self.eklenenler.append(lesson)
        return True

    def recall(self, task, limit=4, *, scope=None, workspace=None, tags=()):
        return self._recall_sonucu

    def reinforce(self, texts, *, success):
        raise AssertionError("reinforce çağrılmamalı")


def test_bos_cevap_yazilmaz():
    bellek = _SahteDersBellegi()

    yazildi, gerekce = sync_teacher_lesson(bellek, question="soru", answer="   ")

    assert yazildi is False
    assert "boş" in gerekce
    assert bellek.eklenenler == []


def test_catisma_yoksa_yazilir():
    bellek = _SahteDersBellegi(recall_sonucu=())

    yazildi, gerekce = sync_teacher_lesson(
        bellek, question="wc -l nasıl kullanılır", answer="wc -l dosya ile satır say"
    )

    assert yazildi is True
    assert gerekce == ""
    assert len(bellek.eklenenler) == 1
    ders = bellek.eklenenler[0]
    assert ders.source is LessonSource.TEACHER
    assert ders.kind is LessonKind.SUCCESS
    assert ders.task == "wc -l nasıl kullanılır"


def test_ayni_ders_zaten_kayitliysa_atlanir():
    bellek = _SahteDersBellegi()
    sync_teacher_lesson(bellek, question="s", answer="AYNI DERS")

    yazildi, gerekce = sync_teacher_lesson(bellek, question="s2", answer="AYNI DERS")

    assert yazildi is False
    assert "zaten kayıtlı" in gerekce


def test_olumsuzlama_asimetrisi_catisma_sayilir():
    mevcut = Lesson(text="run_shell kullan", kind=LessonKind.SUCCESS, source=LessonSource.LEARNED)
    bellek = _SahteDersBellegi(recall_sonucu=(mevcut,))

    yazildi, gerekce = sync_teacher_lesson(bellek, question="s", answer="run_shell KULLANMA")

    assert yazildi is False
    assert "çelişebilir" in gerekce
    assert bellek.eklenenler == []


def test_ikisi_de_olumsuzsa_catisma_sayilmaz():
    """İkisi de aynı yönde (ikisi de yasaklıyor) — çelişki YOK, gerçek bir uyum."""
    mevcut = Lesson(
        text="asla run_shell kullanma", kind=LessonKind.MISTAKE, source=LessonSource.LEARNED
    )
    bellek = _SahteDersBellegi(recall_sonucu=(mevcut,))

    yazildi, gerekce = sync_teacher_lesson(
        bellek, question="s", answer="run_shell kullanma, riskli"
    )

    assert yazildi is True
    assert gerekce == ""


def test_uzun_cevap_kirpilir():
    bellek = _SahteDersBellegi()
    uzun = "x" * 5_000

    sync_teacher_lesson(bellek, question="s", answer=uzun)

    assert len(bellek.eklenenler[0].text) <= 2_000
