"""EffectContract'a karşılık gelen deterministik workflow runner.

Bu katman gerçek dünya etkilerini LLM ReAct döngüsünden ayırır. Model yalnızca
niyetin anlaşılmasında rol oynar; desteklenen bir effect için handler seçimi,
çalıştırma ve post-condition kararı Fusion koduna aittir.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Awaitable, Callable

from ...core.events import EffectWorkflowFinished, EffectWorkflowStarted
from .detect import detect_contract, explicitly_disallows_tools
from .git_push import GitPushWorkflow
from .model import EffectContract, EffectKind, EffectRunResult
from .store import WorkflowStore

if TYPE_CHECKING:  # pragma: no cover
    from ...tools import ToolRegistry
    from ..agent.loop import AgentDeps


Handler = Callable[[str, "AgentDeps", "ToolRegistry", WorkflowStore], Awaitable[EffectRunResult]]


class WorkflowRunner:
    """Deterministik effect handler'larını tek kapıdan çalıştırır.

    Bir handler kayıtlı değilse normal agent akışı devam eder; bu durum sözleşmeyi
    gevşetmez. Kayıtlı handler'larda ise LLM çağrısı yapılmaz ve başarı yalnızca
    handler'ın post-condition doğrulamasıyla üretilebilir.
    """

    def __init__(self, deps: "AgentDeps", registry: "ToolRegistry") -> None:
        self.deps = deps
        self.registry = registry
        self.store = WorkflowStore(deps.config.memory_dir / "effect-workflows")

    async def run(
        self,
        task: str,
        *,
        plan_mode: bool = False,
        depth: int = 0,
    ) -> EffectRunResult | None:
        if plan_mode or depth > 0:
            return None

        contract = detect_contract(task)
        if contract is None or contract.deterministic_handler is None:
            return None

        if explicitly_disallows_tools(task):
            return EffectRunResult(
                final_text=(
                    "İşlem tamamlanmadı: bu görev gerçek araç kullanımı gerektiriyor, "
                    "ancak kullanıcı araçları açıkça yasakladı. Herhangi bir değişiklik "
                    "veya push yapılmış kabul edilmemelidir."
                ),
                ok=False,
            )

        return await self._dispatch(task, contract)

    async def _dispatch(
        self, task: str, contract: EffectContract
    ) -> EffectRunResult | None:
        if contract.kind is EffectKind.GIT_PUSH:
            workflow = GitPushWorkflow(
                task,
                self.deps,
                self.registry,
                store=self.store,
                contract=contract,
            )
            self.deps.publisher.publish(
                EffectWorkflowStarted(
                    workflow_id=workflow.workflow_id,
                    kind=contract.kind.value,
                    title="Git push workflow başlatıldı",
                )
            )
            result = await workflow.run()
            self.deps.publisher.publish(
                EffectWorkflowFinished(
                    workflow_id=result.workflow_id or workflow.workflow_id,
                    kind=result.kind or contract.kind.value,
                    status=result.status or ("completed" if result.ok else "failed"),
                    ok=result.ok,
                    title=result.title,
                    details=result.details,
                    message=result.final_text,
                )
            )
            return result
        return None


async def maybe_run_effect_workflow(
    task: str,
    deps: "AgentDeps",
    registry: "ToolRegistry",
    *,
    plan_mode: bool = False,
    depth: int = 0,
) -> EffectRunResult | None:
    """Geriye uyumlu işlevsel giriş noktası."""

    return await WorkflowRunner(deps, registry).run(
        task, plan_mode=plan_mode, depth=depth
    )
