"""Eval kümesine bağlı değerlendirici — `PromptEvaluator`ın gerçek uygulaması.

Aday istemi `evals` görev kümesinde koşturup `RunReport` döndürür. Hangi yürütücünün
(gerçek agent ya da test sahtesi) kullanılacağı bir fabrika ile dışarıdan verilir; bu
modül model çağrısı bilmez.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Protocol, runtime_checkable

from evals.execution import ModelCallIdentity, TaskExecution
from evals.executor import AgentRunner, AgentRunObservation, AgentTaskExecutor
from evals.metrics import RunReport
from evals.profiles import RunMetadata
from evals.runner import Sleeper, TaskExecutor, run_suite
from evals.tasks import EvalTask

from fusion_cli.core.protocols import Clock

from .targets import PromptTarget, override

#: İstem metninden o istemle çalışan görev yürütücüsünü üreten fabrika.
ExecutorFactory = Callable[[str], TaskExecutor]
MetadataFactory = Callable[[tuple[ModelCallIdentity, ...]], RunMetadata]


@runtime_checkable
class SampleExecutor(Protocol):
    """Tekrar kimliğini destekleyen mevcut yürütücü yeteneği."""

    async def run_sample(self, task: EvalTask, *, sample_index: int | None) -> TaskExecution: ...


class _ObservedExecutor:
    """Mevcut yürütücünün çağrı kökenini rapora kayıpsız aktar."""

    def __init__(self, inner: TaskExecutor) -> None:
        self.inner = inner
        self.calls: list[ModelCallIdentity] = []
        self.model_calls_total = 0

    async def run(self, task: EvalTask) -> TaskExecution:
        return await self.run_sample(task, sample_index=None)

    async def run_sample(self, task: EvalTask, *, sample_index: int | None) -> TaskExecution:
        if sample_index is not None and isinstance(self.inner, SampleExecutor):
            result = await self.inner.run_sample(task, sample_index=sample_index)
        else:
            result = await self.inner.run(task)
        self.calls.extend(result.calls)
        self.model_calls_total += result.model_calls
        return result


class SuiteEvaluator:
    """Bir istem metnini sabit görev kümesinde ölçer."""

    def __init__(
        self,
        tasks: tuple[EvalTask, ...],
        executor_factory: ExecutorFactory,
        *,
        repeat: int = 1,
        sleep: Sleeper | None = None,
        metadata_factory: MetadataFactory | None = None,
    ) -> None:
        self._tasks = tasks
        self._executor_factory = executor_factory
        self._repeat = repeat
        self._sleep = sleep
        self._metadata_factory = metadata_factory

    async def evaluate(self, prompt_text: str) -> RunReport:
        executor = _ObservedExecutor(self._executor_factory(prompt_text))
        if self._sleep is None:
            report = await run_suite(self._tasks, executor, repeat=self._repeat)
        else:
            report = await run_suite(self._tasks, executor, repeat=self._repeat, sleep=self._sleep)
        metadata = (
            self._metadata_factory(tuple(executor.calls))
            if self._metadata_factory
            else RunMetadata(
                calls=tuple(executor.calls),
                repeat=self._repeat,
                unknowns=("model", "flags", "source", "split", "budget"),
            )
        )
        from .proposals import text_digest

        return replace(
            report,
            metadata=replace(
                metadata,
                prompt_digest=text_digest(prompt_text),
                model_calls_total=executor.model_calls_total,
            ),
        )


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
    inner: AgentRunner,
    target: PromptTarget,
    *,
    workspace_root: Path,
    clock: Clock,
    runner_factory: Callable[[EvalTask, int], AgentRunner] | None = None,
) -> ExecutorFactory:
    """Gerçek agent koşucusunu aday istemle çalıştıran yürütücü fabrikası."""

    def make(text: str) -> TaskExecutor:
        return AgentTaskExecutor(
            PromptOverrideRunner(inner, target, text),
            workspace_root=workspace_root,
            clock=clock,
            runner_factory=(
                (
                    lambda task, repeat: PromptOverrideRunner(
                        runner_factory(task, repeat), target, text
                    )
                )
                if runner_factory is not None
                else None
            ),
        )

    return make
