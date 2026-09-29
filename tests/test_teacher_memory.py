"""Öğretmen planının ders belleğinden yeniden kullanılması (tekrar sormama)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from fusion_cli.core.events import TeacherLessonRecorded, TeacherMemoryUsed
from fusion_cli.core.memory import Lesson, LessonKind, LessonSource
from fusion_cli.engines.agent.teacher_memory import (
    MIN_TASK_SIMILARITY,
    TEACHER_PLAN_SCOPE,
    find_reusable_plan,
    plan_lesson_text,
    plan_steps_from_lesson,
    record_plan_outcome,
    task_similarity,
)
from fusion_cli.engines.agent.teacher_plan import parse_teacher_plan
from fusion_cli.memory.lesson_scoring import reinforced

from .fakes import model_result
from .test_teacher_first import _setup

_PLAN_JSON = (
    '{"adimlar":["Dosyayı oku","Hatayı düzelt","Testi çalıştır"],"dosyalar":["src/app.py"],'
    '"riskler":[],"yapilamayanlar":[],"dogrulama":["python -m unittest"]}'
)


_TASK = "src/app.py içindeki add hatasını düzelt; testi çalıştır"


class _FakeLessons:
    """Geri çağırmada eleme yapmayan bellek: benzerlik kararını modül verir."""

    def __init__(self, lessons: tuple[Lesson, ...] = ()) -> None:
        self.lessons = list(lessons)

    def add(self, lesson: Lesson) -> bool:
        if any(item.text == lesson.text for item in self.lessons):
            return False
        self.lessons.append(lesson)
        return True

    def recall(self, task, limit=4, *, scope=None, workspace=None, tags=()):
        return tuple(self.lessons[:limit])

    def all(self):
        return tuple(self.lessons)

    def reinforce(self, texts, *, success):
        updated = 0
        for index, lesson in enumerate(self.lessons):
            if lesson.text in texts:
                self.lessons[index] = reinforced(lesson, success=success)
                updated += 1
        return updated


def _plan_lesson(task: str, **changes) -> Lesson:
    lesson = Lesson(
        text=plan_lesson_text(parse_teacher_plan(_PLAN_JSON)),
        kind=LessonKind.SUCCESS,
        task=task,
        source=LessonSource.TEACHER,
        scope=TEACHER_PLAN_SCOPE,
        success_count=1,
    )
    return replace(lesson, **changes)


@pytest.mark.parametrize(
    ("first", "second", "similar"),
    [
        # Aynı işin farklı çekim ekleriyle yazılmışı benzer sayılmalı.
        (
            "src/app.py içindeki add hatasını düzelt; testi çalıştır",
            "src/app.py dosyasındaki add hatasını düzelt ve testleri çalıştır",
            True,
        ),
        # Aynı projede ama başka bir iş: öğretmen atlanmamalı.
        (
            "src/app.py içindeki add hatasını düzelt; testi çalıştır",
            "README dosyasına kurulum bölümü ekle",
            False,
        ),
        (
            "Shopify API ile ürün yayımlama akışını kur",
            "Instagram API ile story paylaşma akışını kur",
            False,
        ),
    ],
)
def test_gorev_benzerligi_esigi(first: str, second: str, similar: bool) -> None:
    """Eşik (MIN_TASK_SIMILARITY) bu üç örnekle sabitlenir; değişirse burası kırılır."""
    assert (task_similarity(first, second) >= MIN_TASK_SIMILARITY) is similar


def test_plan_ders_metninden_adimlar_geri_okunur() -> None:
    text = plan_lesson_text(parse_teacher_plan(_PLAN_JSON))

    assert plan_steps_from_lesson(text) == ("Dosyayı oku", "Hatayı düzelt", "Testi çalıştır")
    assert "python -m unittest" in text


def test_basarili_ve_benzer_plan_yeniden_kullanilir() -> None:
    memory = _FakeLessons((_plan_lesson(_TASK),))

    found = find_reusable_plan(
        memory, "src/app.py dosyasındaki add hatasını düzelt ve testleri çalıştır",
        workspace="", tags=(),
    )

    assert found is not None
    assert found[1] >= MIN_TASK_SIMILARITY


def test_basarisizligi_basarisindan_az_olmayan_plan_kullanilmaz() -> None:
    """Hafızadaki plan bir kez başarısız olunca öğretmene yeniden sorulmalı."""
    lesson = _plan_lesson(_TASK, failure_count=1)

    assert find_reusable_plan(_FakeLessons((lesson,)), lesson.task, workspace="", tags=()) is None


def test_ogretmen_kaynakli_olmayan_ders_plan_sayilmaz() -> None:
    lesson = _plan_lesson("src/app.py içindeki add hatasını düzelt", source=LessonSource.LEARNED)

    assert find_reusable_plan(_FakeLessons((lesson,)), lesson.task, workspace="", tags=()) is None


def test_basarisiz_turun_plani_belleğe_yazilmaz() -> None:
    memory = _FakeLessons()
    plan = parse_teacher_plan(_PLAN_JSON)

    written = record_plan_outcome(
        memory, task="src/app.py hatasını düzelt", plan=plan, success=False, workspace="", tags=()
    )

    assert written is False
    assert memory.lessons == []


def test_basarili_turun_plani_kanitla_yazilir_ve_tekrarinda_guclenir() -> None:
    memory = _FakeLessons()
    plan = parse_teacher_plan(_PLAN_JSON)

    assert record_plan_outcome(
        memory, task="src/app.py hatasını düzelt", plan=plan, success=True,
        workspace="/kok", tags=("python",),
    )
    lesson = memory.lessons[0]
    assert lesson.source is LessonSource.TEACHER
    assert lesson.scope == TEACHER_PLAN_SCOPE
    assert lesson.success_count == 1
    assert lesson.workspace == "/kok"

    record_plan_outcome(
        memory, task="src/app.py hatasını düzelt", plan=plan, success=True,
        workspace="/kok", tags=("python",),
    )
    assert len(memory.lessons) == 1
    assert memory.lessons[0].success_count == 2


async def test_hafizadaki_plan_varken_ogretmene_sorulmaz(monkeypatch, tmp_path) -> None:
    deps, sink, teacher, apprentice = _setup(monkeypatch, tmp_path)
    task = "src/app.py içindeki add hatasını düzelt; testi çalıştır"
    _enable_lessons(deps, _FakeLessons((_plan_lesson(task),)))

    await run_agent_for(task, deps)

    assert teacher.calls == 0
    assert apprentice.calls >= 1
    assert [item.content for item in deps.tool_context.todos.items] == [
        "Dosyayı oku",
        "Hatayı düzelt",
        "Testi çalıştır",
    ]
    assert any("Hafızadan" in message.content for message in apprentice.seen_messages[0])
    assert any(isinstance(event, TeacherMemoryUsed) for event in sink.events)


async def test_hafizadaki_plan_basarisiz_olunca_guveni_duser(monkeypatch, tmp_path) -> None:
    deps, _sink, _teacher, _apprentice = _setup(
        monkeypatch, tmp_path, apprentice_answers=[model_result("")]
    )
    task = "src/app.py içindeki add hatasını düzelt; testi çalıştır"
    memory = _FakeLessons((_plan_lesson(task),))
    _enable_lessons(deps, memory)

    result = await run_agent_for(task, deps)

    assert result.ok is False
    assert memory.lessons[0].failure_count == 1
    assert find_reusable_plan(memory, task, workspace="", tags=()) is None


async def test_otomatik_plan_cevabi_tur_bitmeden_ders_olarak_yazilmaz(
    monkeypatch, tmp_path
) -> None:
    """Eskiden her öğretmen cevabı anında SUCCESS dersi oluyordu; plan artık sonuca bağlı."""
    (tmp_path / "src").mkdir()
    deps, sink, _teacher, _apprentice = _setup(
        monkeypatch,
        tmp_path,
        teacher_answers=[model_result(_PLAN_JSON), model_result('{"bulgular": []}')],
        apprentice_answers=[
            model_result(tool_calls=(_write_call(),)),
            model_result("Dosya yazıldı."),
        ],
    )
    memory = _FakeLessons()
    _enable_lessons(deps, memory)

    result = await run_agent_for("src/app.py dosyasını oluştur", deps)

    plan_lessons = [lesson for lesson in memory.lessons if lesson.scope == TEACHER_PLAN_SCOPE]
    other_teacher = [
        lesson for lesson in memory.lessons
        if lesson.source is LessonSource.TEACHER and lesson.scope != TEACHER_PLAN_SCOPE
    ]
    assert result.ok is True
    assert other_teacher == []
    assert len(plan_lessons) == 1
    assert "1 dosya değişti" in plan_lessons[0].trigger
    assert any(isinstance(event, TeacherLessonRecorded) for event in sink.events)


def _enable_lessons(deps, memory) -> None:
    """Test ayarı dersleri kapalı kurar; bu testler ders belleğini sınar."""
    deps.lessons = memory
    deps.config = replace(deps.config, runtime=replace(deps.config.runtime, lessons=True))


def _write_call():
    from .fakes import tool_call

    return tool_call("write_file", path="src/app.py", content="x = 1\n")


async def run_agent_for(task, deps):
    from fusion_cli.engines.agent.loop import run_agent

    return await run_agent(task, deps)
