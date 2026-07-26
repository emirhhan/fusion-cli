"""Değerlendirme setini bir yürütücü üzerinden koşturan ince orkestra.

Runner motoru tanımaz: her görevi bir `TaskExecutor` protokolüne verir, dönen
gözlemi puanlar ve rapor toplar. Bu ayrım sayesinde toplama/karşılaştırma mantığı
ağ olmadan, sahte yürütücüyle test edilebilir. Gerçek yürütücü (agent/fusion
motorunu çağıran) ayrı bir sağlayıcıda tanımlanır.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Protocol

from evals.execution import TaskExecution
from evals.metrics import RunReport, TaskResult, merge_runs, score_task
from evals.tasks import EvalTask
from fusion_cli.core.errors import EvalError
from fusion_cli.core.types import is_daily_quota_error


class RateLimitedError(EvalError):
    """Sağlayıcı kotası tükendi; ölçüm anlamını yitirdi."""


#: Geçici sınırda kaç kez daha denenir. Sınırsız denemek kotayı ve kullanıcının
#: zamanını tüketir; hiç denememek dakikalık bir sınır yüzünden koşuyu iptal eder.
MAX_RATE_LIMIT_RETRIES = 2

#: Yeniden denemeden önce beklenecek süre. Dakikalık sınırlar tipik olarak 60
#: saniyelik pencerelerde sıfırlanır.
RETRY_BACKOFF_S = 65.0


class Sleeper(Protocol):
    """Beklemeyi yapan taraf. Testte gerçek zaman harcanmasın diye enjekte edilir."""

    def __call__(self, seconds: float) -> Awaitable[None]: ...


async def _default_sleep(seconds: float) -> None:
    """Gerçek bekleme. `asyncio.sleep` doğrudan kullanılamıyor: aşırı yüklenmiş
    imzası `Sleeper` protokolüne uymuyor."""
    await asyncio.sleep(seconds)


async def _kosturs(task: EvalTask, executor: TaskExecutor, sleep: Sleeper) -> TaskResult:
    """Görevi çalıştır; geçici sınırda bekleyip tekrar dene.

    Günlük kota AYRIDIR: o gün için biter, beklemek kullanıcıyı boşuna oyalar ve
    koşu hemen durur. NVIDIA NIM çıplak 429 döndüğü için ayrımı yapamadığımız
    durumda GEÇİCİ varsayılır — yanlış tarafa düşmenin bedeli asimetriktir:
    boşuna bir bekleme, iptal edilmiş bir ölçümden ucuzdur.
    """
    for deneme in range(MAX_RATE_LIMIT_RETRIES + 1):
        sonuc = score_task(task, await executor.run(task))
        if not sonuc.rate_limited:
            return sonuc
        if is_daily_quota_error(sonuc.rate_limit_detail):
            raise RateLimitedError(
                f"sağlayıcının günlük kotası doldu ({task.id}); ölçüm durduruldu. "
                "Yarın tekrar dene ya da hesabına kredi yükle."
            )
        if deneme < MAX_RATE_LIMIT_RETRIES:
            await sleep(RETRY_BACKOFF_S)
    raise RateLimitedError(
        f"sağlayıcı hız sınırı {MAX_RATE_LIMIT_RETRIES} denemede aşılamadı ({task.id}); "
        "ölçüm durduruldu. Sonuçlar agent'ın yeteneği hakkında bilgi vermez."
    )


class TaskExecutor(Protocol):
    """Bir görevi çalıştırıp ölçülebilir gözlem döndüren yürütücü."""

    async def run(self, task: EvalTask) -> TaskExecution: ...


async def run_suite(
    tasks: tuple[EvalTask, ...],
    executor: TaskExecutor,
    *,
    repeat: int = 1,
    sleep: Sleeper = _default_sleep,
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
        kosular = []
        for _ in range(repeat):
            kosular.append(await _kosturs(task, executor, sleep))
        results.append(kosular[0] if repeat == 1 else merge_runs(kosular))
    return RunReport(results=tuple(results))
