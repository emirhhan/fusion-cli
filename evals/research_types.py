"""Araştırma uyaranı dosyasını değişmez ve tipli bağımlılık girdisine dönüştürür."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from fusion_cli.core.execution_plan import VerificationCheck, VerificationCheckKind


@dataclass(frozen=True, slots=True)
class ExternalChange:
    path: str
    content: str


@dataclass(frozen=True, slots=True)
class LessonSeed:
    identity: str
    text: str
    version: str
    split: str
    supersedes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReproductionSpec:
    input_path: str
    before_command: str
    after_command: str
    before_success: bool = False


@dataclass(frozen=True, slots=True)
class ResearchScenario:
    kind: str
    split: str
    checks: tuple[VerificationCheck, ...]
    lessons: tuple[LessonSeed, ...]
    rule: str
    diagnostic: str
    after_read: ExternalChange | None
    reproduction: ReproductionSpec | None = None


def load_scenario(path: Path) -> ResearchScenario:
    """Yalnız harness manifestinin seçtiği yerel dosyayı çözümler."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    stimulus = raw.get("after_read")
    change = ExternalChange(stimulus["path"], stimulus["content"]) if stimulus else None
    if change and (Path(change.path).is_absolute() or ".." in Path(change.path).parts):
        raise ValueError("Uyaran yolu çalışma alanı içinde olmalı")
    return ResearchScenario(
        kind=raw["kind"],
        split=raw["split"],
        checks=tuple(
            VerificationCheck(
                item["id"], VerificationCheckKind.FILE_CONTAINS, item["path"], item["text"]
            )
            for item in raw.get("checks", [])
        ),
        lessons=tuple(
            LessonSeed(
                item["id"],
                item["text"],
                item.get("version", "2"),
                item.get("split", raw["split"]),
                tuple(item.get("supersedes", [])),
            )
            for item in raw.get("lessons", [])
        ),
        rule=raw.get("rule", "Açık koşulların hepsini tamamla."),
        diagnostic=raw.get("diagnostic", "İnceleme sürüyor."),
        after_read=change,
        reproduction=ReproductionSpec(**raw["reproduction"]) if raw.get("reproduction") else None,
    )
