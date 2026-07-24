"""Ders belleği — agent'ın öz-gelişimi.

Agent her görevden somut dersler çıkarır; benzer bir görev geldiğinde bunlar sistem
promptuna geri enjekte edilir. Zamanla aynı hataları tekrarlamaz.

İki koruma kritiktir:

- **Alaka eşiği** — kosinüs mesafesi eşiği aşan dersler ENJEKTE EDİLMEZ. Aksi halde
  basit bir göreve alakasız ders gürültüsü sızar ve prompt zehirlenir.
- **Yazma kilidi** — ders çıkarımı arka planda çalışabilir; aynı SQLite dosyasına
  eşzamanlı yazma bozulmaya yol açar. Tüm yazmalar süreç genelinde serileştirilir.
"""

from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path
from typing import Any

from ..core.memory import DEFAULT_LESSON_CONFIDENCE, Lesson, LessonKind, LessonSource
from .lesson_ranking import Candidate, select_lessons
from .lesson_scoring import reinforced
from .store import get_collection

COLLECTION = "agent_lessons"

#: Süreç geneli yazma kilidi. Farklı örnekler olsa bile aynı dosyaya yazılır.
_write_lock = threading.Lock()


class ChromaLessonMemory:
    """ChromaDB destekli ders belleği."""

    def __init__(
        self, directory: Path, *, embedding_function: Any = None, suffix: str = ""
    ) -> None:
        # Gömme sağlayıcısı değişirse vektör boyutu da değişir; koleksiyon adına ek
        # koyulur ki farklı boyutlu kayıtlar aynı koleksiyonda karışmasın.
        name = f"{COLLECTION}_{suffix}" if suffix else COLLECTION
        self._collection = get_collection(directory, name, embedding_function=embedding_function)

    def add(self, lesson: Lesson) -> bool:
        text = lesson.text.strip()
        if not text:
            return False
        with _write_lock:
            if self._exists(text):
                return False
            self._collection.add(
                ids=[uuid.uuid4().hex],
                documents=[text],
                metadatas=[_to_metadata(lesson)],
            )
            return True

    def recall(self, task: str, limit: int = 4) -> tuple[Lesson, ...]:
        total = self.count()
        if not total or not task.strip():
            return ()

        # Geniş çek, sonra saf sıralayıcıyla ele: alaka VE güven eşiğini geçen `limit`
        # dersi yakalamak için aday havuzunu bilerek geniş tutuyoruz.
        result = self._collection.query(query_texts=[task], n_results=min(limit * 3, total))
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0] or [0.0] * len(documents)

        candidates = tuple(
            Candidate(lesson=_to_lesson(document, metadata), distance=float(distance))
            for document, metadata, distance in zip(documents, metadatas, distances, strict=False)
        )
        return select_lessons(candidates, limit=limit)

    def reinforce(self, texts: tuple[str, ...], *, success: bool) -> int:
        """Metni eşleşen derslerin güvenini tur sonucuna göre günceller."""
        wanted = {text.strip().lower() for text in texts if text.strip()}
        if not wanted:
            return 0
        with _write_lock:
            rows = self._collection.get()
            ids = rows.get("ids") or []
            documents = rows.get("documents") or []
            metadatas = rows.get("metadatas") or []
            updated = 0
            for row_id, document, metadata in zip(ids, documents, metadatas, strict=False):
                if document.strip().lower() not in wanted:
                    continue
                lesson = reinforced(_to_lesson(document, metadata), success=success)
                self._collection.update(
                    ids=[row_id], documents=[document], metadatas=[_to_metadata(lesson)]
                )
                updated += 1
            return updated

    def all(self) -> tuple[Lesson, ...]:
        rows = self._collection.get()
        documents = rows.get("documents") or []
        metadatas = rows.get("metadatas") or []
        lessons = [
            _to_lesson(document, metadata)
            for document, metadata in zip(documents, metadatas, strict=False)
        ]
        lessons.sort(key=lambda lesson: 0 if lesson.kind is LessonKind.MISTAKE else 1)
        return tuple(lessons)

    def count(self) -> int:
        return int(self._collection.count())

    def _exists(self, text: str) -> bool:
        """Kaba tekilleştirme: aynı ders defalarca birikmesin."""
        normalized = text.lower()
        existing = self._collection.get().get("documents") or []
        return any(document.strip().lower() == normalized for document in existing)


def _to_metadata(lesson: Lesson) -> dict[str, Any]:
    """Dersi ChromaDB metadata'sına çevir. Güven/sayaç alanları burada kalıcılaşır."""
    return {
        "task": lesson.task[:500],
        "kind": lesson.kind.value,
        "source": lesson.source.value,
        "confidence": float(lesson.confidence),
        "success_count": int(lesson.success_count),
        "failure_count": int(lesson.failure_count),
        "scope": lesson.scope[:100],
        "trigger": lesson.trigger[:200],
        "timestamp": time.time(),
    }


def _to_lesson(document: str, metadata: dict[str, Any]) -> Lesson:
    # Geriye dönük uyumluluk: güven/sayaç alanları taşınmadan önce yazılmış eski
    # kayıtlar bu alanları içermez; makul varsayılanlarla okunur.
    return Lesson(
        text=document,
        kind=_enum(LessonKind, metadata.get("kind"), LessonKind.SUCCESS),
        task=str(metadata.get("task", "")),
        source=_enum(LessonSource, metadata.get("source"), LessonSource.LEARNED),
        confidence=float(metadata.get("confidence", DEFAULT_LESSON_CONFIDENCE)),
        success_count=int(metadata.get("success_count", 0)),
        failure_count=int(metadata.get("failure_count", 0)),
        scope=str(metadata.get("scope", "")),
        trigger=str(metadata.get("trigger", "")),
    )


def _enum(enum_type: Any, raw: object, fallback: Any) -> Any:
    """Bilinmeyen değer kaydı bozmaz; makul bir varsayılana düşülür."""
    try:
        return enum_type(str(raw))
    except ValueError:
        return fallback


def as_prompt_block(lessons: tuple[Lesson, ...]) -> str:
    """Geri çağrılan dersleri sistem promptuna eklenecek metne çevir."""
    if not lessons:
        return ""
    lines = [
        f"- [{'KAÇIN' if lesson.kind is LessonKind.MISTAKE else 'UYGULA'}] {lesson.text}"
        for lesson in lessons
    ]
    return (
        "<dersler>\nGeçmiş görevlerden çıkardığın dersler — bunlara uy:\n"
        + "\n".join(lines)
        + "\n</dersler>"
    )
