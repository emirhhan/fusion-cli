"""Değerlendirme setini bir yürütücü üzerinden koşturan ince orkestra.

Runner motoru tanımaz: her görevi bir `TaskExecutor` protokolüne verir, dönen
gözlemi puanlar ve rapor toplar. Bu ayrım sayesinde toplama/karşılaştırma mantığı
ağ olmadan, sahte yürütücüyle test edilebilir. Gerçek yürütücü (agent/fusion
motorunu çağıran) ayrı bir sağlayıcıda tanımlanır.
"""

from __future__ import annotations

from typing import Protocol

from evals.execution import TaskExecution
from evals.metrics import RunReport, merge_runs, score_task
from evals.tasks import EvalTask
from fusion_cli.core.errors import EvalError


class TaskExecutor(Protocol):
    """Bir görevi çalıştırıp ölçülebilir gözlem döndüren yürütücü."""

    async def run(self, task: EvalTask) -> TaskExecution: ...


async def run_suite(
    tasks: tuple[EvalTask, ...], executor: TaskExecutor, *, repeat: int = 1
) -> RunReport:
    """Görev setini sırayla çalıştırır ve raporu döndürür.

    Görevler sırayla koşturulur: ücretsiz modellerin oran sınırı paralel yükü
    kaldırmaz ve ölçümün kendisi yan etkisiz olmalıdır.

    `repeat` her görevi N kez koşturur ve geçme ORANI raporlanır. Tek koşu karar
    desteklemez: ölçüldü ki aynı görev aynı ayarla bir koşuda kalıp ötekinde
    geçebiliyor. Bir ayarın (workflow_mode, kademe, verified_synthesis) işe
    yarayıp yaramadığı ancak oranla söylenebilir.
    """
    if repeat < 1:
        raise EvalError(f"repeat en az 1 olmalı: {repeat}")

    results = []
    for task in tasks:
        kosular = [score_task(task, await executor.run(task)) for _ in range(repeat)]
        results.append(kosular[0] if repeat == 1 else merge_runs(kosular))
    return RunReport(results=tuple(results))
