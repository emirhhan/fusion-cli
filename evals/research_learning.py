"""Araştırma derslerini gerçek Chroma deposu ve ürün recall yoluyla sunar."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, replace
from pathlib import Path
from typing import TYPE_CHECKING

from evals.research_types import ResearchScenario
from fusion_cli.core.lesson_runtime import LessonRuntimeContext
from fusion_cli.core.memory import Lesson, LessonKind, LessonRecallPolicy
from fusion_cli.memory.lessons import ChromaLessonMemory

if TYPE_CHECKING:
    from fusion_cli.engines.agent.loop import AgentDeps


class LocalFixtureEmbedding:
    """Model indirmeyen sabit uyaran; seçim gerçek lexical/ranking katmanındadır."""

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] if "python" in text.lower() else [0.0, 1.0] for text in input]

    def embed_query(self, input: list[str]) -> list[list[float]]:
        return self(input)

    def supported_spaces(self) -> list[str]:
        return ["cosine"]

    def default_space(self) -> str:
        return "cosine"

    def get_config(self) -> dict[str, object]:
        return {}

    @classmethod
    def build_from_config(cls, config: dict[str, object]) -> LocalFixtureEmbedding:
        return cls()

    def is_legacy(self) -> bool:
        return False

    @staticmethod
    def name() -> str:
        return "research-local-fixture"


async def prepare_lessons(deps: AgentDeps, directory: Path, spec: ResearchScenario) -> None:
    """Sabit kimlik/sürüm/bölüm uyaranı aynı gerçek öğrenme otoritesine gider."""
    memory = await asyncio.to_thread(
        ChromaLessonMemory, directory / "lessons", embedding_function=LocalFixtureEmbedding()
    )
    for item in spec.lessons:
        lesson = Lesson(
            text=item.text,
            kind=LessonKind.SUCCESS,
            id=item.identity,
            confidence=0.5,
            subject_key=(
                "garden"
                if item.identity == "irrelevant" and spec.kind != "lesson_relevance"
                else "python"
            ),
            version=item.version,
            source_split=item.split,
            supersedes=item.supersedes,
        )
        await asyncio.to_thread(memory.add, lesson)
    deps.lessons = memory
    deps.lesson_context = LessonRuntimeContext(
        LessonRecallPolicy(subject_key="python", version="2", source_split=spec.split)
    )
    deps.config = replace(
        deps.config,
        runtime=replace(
            deps.config.runtime,
            lessons=True,
            lesson_recall_hints=True,
            lesson_attributed_feedback=True,
            lesson_conflict_quarantine=spec.kind != "lesson_relevance",
        ),
    )


async def collect_lessons(deps: AgentDeps) -> dict[str, object]:
    """Kayıt kimliği ve güven sonucu gerçek depodan okunur."""
    if not isinstance(deps.lessons, ChromaLessonMemory):
        return {}
    lessons = await asyncio.to_thread(deps.lessons.all)
    records = []
    for lesson in lessons:
        record = asdict(lesson)
        record["subject"] = record.pop("subject_key")
        records.append(record)
    return {"lessons": records}
