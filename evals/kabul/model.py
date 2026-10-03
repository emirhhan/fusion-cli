"""Kabul koşusunun veri tipleri ve sonuç sınıflandırması.

Bir koşunun sonucu dört sınıftan biridir; istatistiğe yalnız ilk ikisi girer:

- `gecti`: bütün kabul maddeleri geçti ve iş Fusion'ın ana (API) modeliyle bitti.
- `kaldi`: en az bir kabul maddesi düştü.
- `gecersiz`: ölçüm yapılamadı (ortam ön-kontrolü, sürücü hatası, Chrome eşleşmesi,
  denetçinin kendisi çalışamadı). Bu bir başarısızlık DEĞİLDİR; koşu yinelenir.
- `ogretmen_destekli`: maddeler geçti ama ana döngünün model çağrılarının bir kısmını
  web öğretmeni karşıladı (devralma ya da web yedeğine düşüş). Ayrı raporlanır ki
  "Nemotron yaptı" ile "sistem yaptı" karışmasın.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class Outcome(StrEnum):
    """Bir kabul koşusunun sonuç sınıfı."""

    PASSED = "gecti"
    FAILED = "kaldi"
    INVALID = "gecersiz"
    TEACHER_ASSISTED = "ogretmen_destekli"


@dataclass(frozen=True, slots=True)
class Check:
    """Tek bir kabul maddesi: ne ölçüldü, geçti mi, neden."""

    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class Inspection:
    """Denetçinin çıktısı. `invalid_reason` doluysa maddeler yok sayılır."""

    checks: tuple[Check, ...] = ()
    invalid_reason: str = ""

    @property
    def passed_count(self) -> int:
        return sum(1 for check in self.checks if check.passed)

    @property
    def all_passed(self) -> bool:
        return bool(self.checks) and all(check.passed for check in self.checks)


#: Denetçi imzası: çalışma klasörü ve hazırlık adımının verdiği değerler
#: (ör. yerel fikstür adresi) alır, maddeleri döner.
Inspector = Callable[[Path, Mapping[str, str]], Inspection]
#: Hazırlık imzası: koşu boyunca açık kalan kaynak (fikstür sunucusu, worktree);
#: görev metnindeki `{anahtar}` yer tutucularını dolduracak değerleri verir.
Preparer = Callable[[Path], AbstractContextManager[Mapping[str, str]]]


@dataclass(frozen=True, slots=True)
class Area:
    """Bir kabul alanının tanımı: ajana verilen görev ve onu ölçen denetçi."""

    name: str
    task: str
    timeout_s: float
    inspect: Inspector
    prepare: Preparer | None = None
    #: Görev Fusion Browser eklentisi bağlıyken koşulur; eşleşme olmazsa koşu geçersiz.
    needs_chrome: bool = False
    #: Ön-kontrolün PATH'te arayacağı çalıştırılabilirler (ör. php, ffprobe).
    required_executables: tuple[str, ...] = ()
    #: Doluysa ajan çalışma klasöründe değil, hazırlığın bu anahtarla verdiği
    #: klasörde koşar (ör. Fusion deposunun worktree kopyası).
    root_key: str = ""


@dataclass(frozen=True, slots=True)
class RunMetrics:
    """Sürücünün sayaçlarından derlenen koşu ölçüleri."""

    elapsed_s: float = 0.0
    model_calls: int = 0
    web_model_calls: int = 0
    teacher_calls: int = 0
    tool_calls: int = 0
    tool_errors: int = 0
    fallbacks: int = 0
    prompt_tokens: int = 0
    max_prompt_tokens: int = 0


@dataclass(frozen=True, slots=True)
class RunRecord:
    """Tek koşunun tam kaydı; rapor JSON'una aynen yazılır."""

    area: str
    attempt: int
    workdir: str
    outcome: Outcome
    inspection: Inspection
    metrics: RunMetrics
    agent_ok: bool | None = None
    agent_text: str = ""
    driver_error: str = ""
    tools: tuple[str, ...] = field(default_factory=tuple)

    @property
    def false_success(self) -> bool:
        """Ajan 'bitti' dedi ama maddeler düştü."""
        return bool(self.agent_ok) and self.outcome is Outcome.FAILED


def classify(inspection: Inspection, metrics: RunMetrics, driver_error: str) -> Outcome:
    """Denetim ve sürücü durumundan sonuç sınıfını çıkar."""
    if driver_error or inspection.invalid_reason or not inspection.checks:
        return Outcome.INVALID
    if not inspection.all_passed:
        return Outcome.FAILED
    if metrics.web_model_calls > 0:
        return Outcome.TEACHER_ASSISTED
    return Outcome.PASSED
