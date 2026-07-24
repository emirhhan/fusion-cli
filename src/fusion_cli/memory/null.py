"""Hiçbir şey yapmayan bellek uygulamaları.

`--no-memory` seçeneği, bellek dizinine erişilememesi ya da test ortamı — hepsinde
bunlar kullanılır. Motor kodunda "bellek var mı?" dalı açılmaz: sözleşme her zaman
karşılanır, yalnızca içi boştur.
"""

from __future__ import annotations

from ..core.memory import CodeMatch, Feedback, IndexStats, Lesson, ModelStats, Outcome


class NullPerformanceMemory:
    """Kayıt tutmayan performans belleği."""

    def record(self, outcome: Outcome) -> None:
        return None

    def best_model(self, task_type: str) -> str | None:
        return None

    def apply_feedback(self, task_type: str, model_name: str, feedback: Feedback) -> int:
        return 0

    def stats(self) -> tuple[ModelStats, ...]:
        return ()


class NullLessonMemory:
    """Ders tutmayan bellek."""

    def add(self, lesson: Lesson) -> bool:
        return False

    def recall(self, task: str, limit: int = 4, *, scope: str | None = None) -> tuple[Lesson, ...]:
        return ()

    def reinforce(self, texts: tuple[str, ...], *, success: bool) -> int:
        return 0

    def all(self) -> tuple[Lesson, ...]:
        return ()

    def count(self) -> int:
        return 0


class NullCodeIndex:
    """İndeks kurmayan kod araması."""

    def search(self, query: str, limit: int = 6) -> tuple[CodeMatch, ...]:
        return ()

    def reindex(self) -> IndexStats:
        return IndexStats(total=0, added=0, removed=0)
