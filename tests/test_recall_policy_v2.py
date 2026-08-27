from __future__ import annotations

from types import SimpleNamespace

from fusion_cli.engines.agent.classify import TaskClassification, TaskKind
from fusion_cli.engines.agent.learning_steps import AUTO_RECALL_LIMIT, recall_lessons
from fusion_cli.engines.agent.skill_recall import (
    AUTO_REFERENCE_BUDGET,
    AUTO_SKILL_BUDGET,
    auto_expertise_block,
    should_auto_context,
    should_auto_reference,
    should_auto_skill,
)


def classification(
    primary: TaskKind,
    *,
    confidence: float,
    primary_score: int,
    secondary: TaskKind | None = None,
    secondary_score: int = 0,
) -> TaskClassification:
    scores = [(primary, primary_score)]
    secondary_items: tuple[TaskKind, ...] = ()

    if secondary is not None:
        scores.append((secondary, secondary_score))
        secondary_items = (secondary,)

    return TaskClassification(
        primary=primary,
        secondary=secondary_items,
        confidence=confidence,
        scores=tuple(scores),
    )


def test_belirsiz_tie_uzmanlik_contexti_enjekte_etmez():
    result = classification(
        TaskKind.WEBSITE,
        confidence=0.0,
        primary_score=5,
        secondary=TaskKind.FEATURE,
        secondary_score=5,
    )

    assert not should_auto_context(result)
    assert not should_auto_reference(result)
    assert auto_expertise_block(result) == ""


def test_guclu_primary_dusuk_margin_olsa_da_context_alabilir():
    result = classification(
        TaskKind.WEBSITE,
        confidence=0.10,
        primary_score=7,
        secondary=TaskKind.FEATURE,
        secondary_score=6,
    )

    assert should_auto_context(result)
    assert should_auto_reference(result)


def test_general_ve_explore_asla_otomatik_context_almaz():
    general = classification(
        TaskKind.GENERAL,
        confidence=1.0,
        primary_score=10,
    )
    explore = classification(
        TaskKind.EXPLORE,
        confidence=1.0,
        primary_score=10,
    )

    assert not should_auto_context(general)
    assert not should_auto_context(explore)


def test_feature_icin_genel_frontend_skill_zorlanmaz():
    result = classification(
        TaskKind.FEATURE,
        confidence=0.9,
        primary_score=10,
    )

    assert should_auto_context(result)
    assert not should_auto_skill(result)
    assert not should_auto_reference(result)


def test_website_skill_ve_reference_ancak_guvenli_classificationda_acilir():
    result = classification(
        TaskKind.WEBSITE,
        confidence=0.5,
        primary_score=5,
    )

    assert should_auto_skill(result)
    assert should_auto_reference(result)


def test_otomatik_expertise_butcesi_eski_maksimumdan_daha_kucuk():
    assert AUTO_SKILL_BUDGET < 2_500
    assert AUTO_REFERENCE_BUDGET < 6_000
    assert AUTO_SKILL_BUDGET + AUTO_REFERENCE_BUDGET <= 5_000


class FakeLessons:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def recall(self, task, limit=4, *, scope=None, workspace=None):
        self.calls.append(
            {
                "task": task,
                "limit": limit,
                "scope": scope,
                "workspace": workspace,
            }
        )
        return ()


class FakePublisher:
    def publish(self, event) -> None:
        pass


def deps(tmp_path):
    lessons = FakeLessons()
    value = SimpleNamespace(
        lessons=lessons,
        config=SimpleNamespace(
            runtime=SimpleNamespace(lessons=True),
        ),
        tool_context=SimpleNamespace(root=tmp_path),
        publisher=FakePublisher(),
    )
    return value, lessons


def test_auto_lesson_recall_en_faz_iki_ders_ister(tmp_path):
    value, lessons = deps(tmp_path)

    recall_lessons(
        "bir özellik ekle",
        value,
        scope="feature",
    )

    assert len(lessons.calls) == 1
    assert lessons.calls[0]["limit"] == AUTO_RECALL_LIMIT == 2


def test_disabled_lesson_recall_memorye_hic_dokunmaz(tmp_path):
    value, lessons = deps(tmp_path)

    result = recall_lessons(
        "belirsiz görev",
        value,
        scope=None,
        enabled=False,
    )

    assert result == ()
    assert lessons.calls == []
