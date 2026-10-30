"""Eval kümesine bağlı değerlendirici — `PromptEvaluator`ın gerçek uygulaması.

Aday istemi `evals` görev kümesinde koşturup `RunReport` döndürür. Hangi yürütücünün
(gerçek agent ya da test sahtesi) kullanılacağı bir fabrika ile dışarıdan verilir; bu
modül model çağrısı bilmez.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from evals.executor import AgentRunner, AgentRunObservation, AgentTaskExecutor
from evals.metrics import RunReport
from evals.runner import Sleeper, TaskExecutor, run_suite
from evals.tasks import EvalTask

from fusion_cli.core.protocols import Clock

from .targets import PromptTarget, override

#: İstem metninden o istemle çalışan görev yürütücüsünü üreten fabrika.
ExecutorFactory = Callable[[str], TaskExecutor]


class SuiteEvaluator:
    """Bir istem metnini sabit görev kümesinde ölçer."""

    def __init__(
        self,
        tasks: tuple[EvalTask, ...],
        executor_factory: ExecutorFactory,
        *,
        repeat: int = 1,
        sleep: Sleeper | None = None,
    ) -> None:
        self._tasks = tasks
        self._executor_factory = executor_factory
        self._repeat = repeat
        self._sleep = sleep

    async def evaluate(self, prompt_text: str) -> RunReport:
        executor = self._executor_factory(prompt_text)
        if self._sleep is None:
            return await run_suite(self._tasks, executor, repeat=self._repeat)
        return await run_suite(self._tasks, executor, repeat=self._repeat, sleep=self._sleep)


class PromptOverrideRunner:
    """Asıl koşucuyu, istemi geçici olarak `text` yaparak çalıştıran sarmalayıcı."""

    def __init__(self, inner: AgentRunner, target: PromptTarget, text: str) -> None:
        self._inner = inner
        self._target = target
        self._text = text

    async def run(
        self,
        request: str,
        *,
        root: Path,
        strict_approval: bool = False,
        transcript: Path | None = None,
    ) -> AgentRunObservation:
        with override(self._target, self._text):
            return await self._inner.run(
                request, root=root, strict_approval=strict_approval, transcript=transcript
            )


def agent_executor_factory(
    inner: AgentRunner, target: PromptTarget, *, workspace_root: Path, clock: Clock
) -> ExecutorFactory:
    """Gerçek agent koşucusunu aday istemle çalıştıran yürütücü fabrikası."""

    def make(text: str) -> TaskExecutor:
        return AgentTaskExecutor(
            PromptOverrideRunner(inner, target, text), workspace_root=workspace_root, clock=clock
        )

    return make
