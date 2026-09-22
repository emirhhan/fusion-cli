"""Kabul eşikleri — bir koşunun "yeterli" sayılıp sayılmadığı.

Eşikler 17 Eylül Claude paritesi yol haritasının Faz 7 maddesinden gelir ve
uydurulmamıştır: *"doğru tur oranı %70 üstü, yalan başarı 0, uzun oturumda 21/21
tamamlanma, ortalama tur 90 saniyenin altı."*

Neden makine-okunur: eşik yalnız bir raporun dipnotunda yazdığı sürece koşu
"yeşil" görünüp eşiğin altında kalabiliyordu. `evaluate` bir hüküm döndürür ve
`python -m evals run` bunu çıkış koduna çevirir.

Saf modüldür: ağ, dosya ve saat yoktur; doğrudan test edilir.
"""

from __future__ import annotations

from dataclasses import dataclass

from evals.metrics import RunReport

#: Doğru biten görevlerin en az oranı.
MIN_TASK_SUCCESS_RATE = 0.70
#: İzin verilen yalan başarı sayısı. SIFIR: bkz. `TaskResult.false_success`.
MAX_FALSE_SUCCESS = 0
#: Ölçülebilen görev oranı ("21/21 tamamlanma"). Kotaya takılan tur oturumu böler.
MIN_COMPLETION_RATE = 1.0
#: Ortalama görev süresi tavanı (saniye).
MAX_MEAN_DURATION_SECONDS = 90.0


@dataclass(frozen=True, slots=True)
class AcceptanceCheck:
    """Tek bir eşiğin sonucu."""

    name: str
    passed: bool
    #: Ölçülen değer ve eşik, kullanıcıya gösterilecek biçimde.
    detail: str


@dataclass(frozen=True, slots=True)
class AcceptanceVerdict:
    """Koşunun bütün eşiklere göre hükmü."""

    checks: tuple[AcceptanceCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failures(self) -> tuple[AcceptanceCheck, ...]:
        return tuple(check for check in self.checks if not check.passed)


def evaluate(report: RunReport) -> AcceptanceVerdict:
    """Raporu kabul eşiklerine vur ve hükmü döndür."""
    oran = report.task_success_rate
    yalan = report.false_success_count
    tamamlanma = report.completion_rate
    sure = report.mean_duration_seconds
    return AcceptanceVerdict(
        checks=(
            AcceptanceCheck(
                name="doğru tur oranı",
                passed=oran > MIN_TASK_SUCCESS_RATE,
                detail=f"%{oran * 100:.1f} (eşik: %{MIN_TASK_SUCCESS_RATE * 100:.0f} üstü)",
            ),
            AcceptanceCheck(
                name="yalan başarı",
                passed=yalan <= MAX_FALSE_SUCCESS,
                detail=(
                    f"{yalan} (eşik: {MAX_FALSE_SUCCESS})"
                    + (f" — {', '.join(report.false_success_tasks)}" if yalan else "")
                ),
            ),
            AcceptanceCheck(
                name="oturum tamamlanması",
                passed=tamamlanma >= MIN_COMPLETION_RATE,
                detail=(
                    f"{report.measured_task_count}/{report.task_count} ölçüldü "
                    f"(eşik: tamamı)"
                ),
            ),
            AcceptanceCheck(
                name="ortalama tur süresi",
                passed=sure < MAX_MEAN_DURATION_SECONDS,
                detail=f"{sure:.1f} sn (eşik: {MAX_MEAN_DURATION_SECONDS:.0f} sn altı)",
            ),
        )
    )
