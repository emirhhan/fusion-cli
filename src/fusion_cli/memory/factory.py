"""Yapılandırmadan bellek kurma — tüm parçaların birleştiği tek yer.

Bellek AÇILAMAZSA uygulama çökmez: boş (null) belleğe düşülür ve neden düşüldüğü
çağırana bildirilir. Bellek bir iyileştirmedir; onsuz da çalışılmalıdır.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config.models import Config
from ..core.memory import CodeIndex, LessonMemory, PerformanceMemory
from .code_index import ChromaCodeIndex
from .embeddings import build_embedding_function
from .lessons import ChromaLessonMemory
from .null import NullCodeIndex, NullLessonMemory, NullPerformanceMemory
from .performance import ChromaPerformanceMemory
from .store import MemoryUnavailableError


@dataclass(frozen=True, slots=True)
class Memory:
    """Uygulamanın kullandığı bellek üçlüsü."""

    performance: PerformanceMemory
    lessons: LessonMemory
    code_index: CodeIndex
    #: Bellek açılamadıysa nedeni; açıldıysa None.
    unavailable_reason: str | None = None

    @property
    def enabled(self) -> bool:
        return self.unavailable_reason is None


def null_memory(reason: str | None = None) -> Memory:
    """Hiçbir şey saklamayan bellek (`--no-memory` ya da erişilemeyen depo)."""
    return Memory(
        performance=NullPerformanceMemory(),
        lessons=NullLessonMemory(),
        code_index=NullCodeIndex(),
        unavailable_reason=reason,
    )


def build_memory(config: Config, *, root: Path) -> Memory:
    """Yapılandırmaya göre belleği kur; açılamazsa boş belleğe düş."""
    try:
        embedding_function, suffix = build_embedding_function(
            config.embedding.provider, config.embedding.model
        )
        directory = config.memory_dir
        return Memory(
            performance=ChromaPerformanceMemory(directory),
            lessons=ChromaLessonMemory(
                directory, embedding_function=embedding_function, suffix=suffix
            ),
            code_index=ChromaCodeIndex(
                directory, root, embedding_function=embedding_function, suffix=suffix
            ),
        )
    except MemoryUnavailableError as exc:
        return null_memory(str(exc))


def build_performance_memory(config: Config) -> Memory:
    """Yalnız performans tablosunu açan ucuz bellek (`fusion stats` / `memory stats`).

    Model performans tablosu gömme kullanmaz. Buna rağmen tam kurulumdan geçmek,
    NIM sağlayıcısında `build_embedding_function` içindeki yoklama isteği yüzünden
    kullanıcıyı ağa ve kotaya bağımlı kılıyordu: tabloyu görmek için ödenmemesi
    gereken bir bedel. Ders ve kod dizini bu yolda hiç açılmaz; null kalır.
    """
    try:
        return Memory(
            performance=ChromaPerformanceMemory(config.memory_dir),
            lessons=NullLessonMemory(),
            code_index=NullCodeIndex(),
        )
    except MemoryUnavailableError as exc:
        return null_memory(str(exc))
