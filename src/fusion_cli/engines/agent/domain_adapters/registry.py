"""Alan kayıt defteri — kayıtlı adaptörlerin kanıt sözleşmelerini birleştirir.

Kayıt defteri DEĞİŞMEZ bir değer nesnesidir ve modül seviyesinde tutulmaz; çağıran
onu kurucu/parametre yoluyla verir (RULES.md "Bağımlılık ve Soyutlama").

Çok alanlı projede eşleşen TÜM adaptörler uygulanır. Ölçüt: Meshy → Blender → Godot
zinciri aynı dizinde `.blend` ve `project.godot` taşır; "ilk eşleşen kazanır" ikinci
alanın kapısını sessizce düşürürdü.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from ....core.errors import FusionError
from ..plan_coverage import Deliverable
from .contract import DomainAdapter, ToolFailureMarkers


@dataclass(frozen=True, slots=True)
class DomainRegistry:
    """Kayıtlı alan adaptörleri, kayıt sırasıyla."""

    adapters: tuple[DomainAdapter, ...]

    def __post_init__(self) -> None:
        names = [adapter.name for adapter in self.adapters]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise FusionError(
                "Alan adaptörü adları tekil olmalı; tekrar eden: "
                + ", ".join(duplicates)
                + ". Her alanı kayıt defterine bir kez ekleyin."
            )

    def matching(self, root: Path) -> tuple[DomainAdapter, ...]:
        """Kökte işareti bulunan adaptörler, kayıt sırasıyla."""
        return tuple(adapter for adapter in self.adapters if adapter.matches(root))

    def first_match(self, root: Path) -> DomainAdapter | None:
        """Kökte eşleşen ilk adaptör; yoksa `None` (geriye uyumlu tekil sorgu)."""
        return next((adapter for adapter in self.adapters if adapter.matches(root)), None)

    def relevant(self, root: Path, task: str) -> tuple[DomainAdapter, ...]:
        """Kökte eşleşen ya da görevde adıyla anılan adaptörler."""
        return tuple(
            adapter
            for adapter in self.adapters
            if adapter.matches(root) or adapter.is_named_in(task)
        )

    def gate_commands(self, root: Path) -> tuple[str, ...]:
        """Eşleşen tüm alanların kapı komutları; sıra korunur, tekrar atılır."""
        return _unique(
            command for adapter in self.matching(root) for command in adapter.gate_commands(root)
        )

    def output_failure_markers(self) -> tuple[ToolFailureMarkers, ...]:
        """Kayıttaki TÜM alanların sıfır-çıkış işaretleri, araç adına göre.

        Eşleşmeye bağlı değildir: işaret, projenin değil çalışan aracın özelliğidir.
        """
        return tuple(
            ToolFailureMarkers(adapter.executable, adapter.output_failure_markers)
            for adapter in self.adapters
            if adapter.executable and adapter.output_failure_markers
        )

    def artifact_findings(self, root: Path) -> tuple[str, ...]:
        """Uygulanan alanların artifact bulguları; sıra korunur, tekrar atılır."""
        return _unique(
            finding for adapter in self.adapters for finding in adapter.artifact_findings(root)
        )

    def acceptance_criteria(self, root: Path, task: str) -> tuple[str, ...]:
        """Plan istemine girecek, ilgili alanların kabul koşulları."""
        return _unique(
            criterion
            for adapter in self.relevant(root, task)
            for criterion in adapter.acceptance_criteria()
        )

    def deliverables(self) -> tuple[Deliverable, ...]:
        """Kayıttaki tüm alanların teslimatları; aynı ad bir kez.

        Eşleşmeye bağlanmaz: teslimatın `request_markers` alanı zaten "görevde açıkça
        istendi mi" kapısıdır. Boş dizindeki bir oyun isteğinde kök işareti henüz
        yoktur ve eşleşmeye bağlamak istenen teslimatı sessizce düşürürdü.
        """
        seen: set[str] = set()
        collected: list[Deliverable] = []
        for adapter in self.adapters:
            for deliverable in adapter.deliverables:
                if deliverable.name not in seen:
                    seen.add(deliverable.name)
                    collected.append(deliverable)
        return tuple(collected)


def _unique(items: Iterable[str]) -> tuple[str, ...]:
    """Metinleri ilk görülme sırasıyla tekrarsız demete çevir."""
    return tuple(dict.fromkeys(items))
