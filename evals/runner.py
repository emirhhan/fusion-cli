"""Değerlendirme setini bir yürütücü üzerinden koşturan ince orkestra.

Runner motoru tanımaz: her görevi bir `TaskExecutor` protokolüne verir, dönen
gözlemi puanlar ve rapor toplar. Bu ayrım sayesinde toplama/karşılaştırma mantığı
ağ olmadan, sahte yürütücüyle test edilebilir. Gerçek yürütücü (agent/fusion
motorunu çağıran) ayrı bir sağlayıcıda tanımlanır.
"""

from __future__ import annotations

from typing import Protocol

from evals.execution import TaskExecution
from evals.metrics import RunReport, score_task
from evals.tasks import EvalTask


class TaskExecutor(Protocol):
    """Bir görevi çalıştırıp ölçülebilir gözlem döndüren yürütücü."""

    async def run(self, task: EvalTask) -> TaskExecution: ...


async def run_suite(tasks: tuple[EvalTask, ...], executor: TaskExecutor) -> RunReport:
    """Görev setini sırayla çalıştırır ve raporu döndürür.

    Görevler sırayla koşturulur: ücretsiz modellerin oran sınırı paralel yükü
    kaldırmaz ve ölçümün kendisi yan etkisiz olmalıdır.
    """

    results = []
    for task in tasks:
        execution = await executor.run(task)
        results.append(score_task(task, execution))
    return RunReport(results=tuple(results))
