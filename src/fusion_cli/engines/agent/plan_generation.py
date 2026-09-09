"""Plan üretimi ve biçim onarımını gerçek çağrı sayılarıyla sonuçlandırır."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from ...core.execution_plan import ExecutionPlan
from .plan_parser import PlanParseError, parse_execution_plan
from .promotion import PromotionContext

if TYPE_CHECKING:
    from .loop import AgentDeps, AgentOutcome


class RunAgent(Protocol):
    """Plan ve adım alt turlarının ortak çağrı yüzeyi."""

    async def __call__(
        self,
        task: str,
        deps: AgentDeps,
        *,
        plan_mode: bool = ...,
        depth: int = ...,
        self_review: bool | None = ...,
        allowed_tools: set[str] | None = ...,
        verify: bool = ...,
        internal: bool = ...,
    ) -> AgentOutcome: ...


@dataclass(frozen=True, slots=True)
class PlanGeneration:
    """Plan veya ayrıştırma hatası ile gerçekten harcanan model çağrıları."""

    plan: ExecutionPlan | None
    calls: int
    error: str = ""


async def generate_plan(
    task: str,
    deps: AgentDeps,
    run_agent: RunAgent,
    limit: int,
    promotion: PromotionContext | None,
) -> PlanGeneration:
    """Şemayı bir kez onar; her iki gerçek çağrının maliyetini koru."""
    import asyncio

    path = Path(__file__).parent / "prompts" / "execution_plan.md"
    template = await asyncio.to_thread(path.read_text, encoding="utf-8")
    prompt = template.replace("{task}", task)
    if promotion is not None:
        prompt = f"{promotion.render()}\n\n{prompt}"
    original_prompt = prompt
    calls = 0
    error = "Planlama bütçesi tükendi."
    # Mevcut plan sözleşmesi tek biçim onarımına izin verir.
    for _ in range(2):
        if calls >= limit:
            break
        outcome = await run_agent(
            prompt,
            deps,
            depth=1,
            self_review=False,
            plan_mode=True,
            verify=False,
            internal=True,
            allowed_tools=set(),
        )
        calls += outcome.model_calls_made
        if not outcome.ok:
            # Kimlik doğrulama, kota veya çalışma bütçesi hatası bozuk JSON
            # değildir; biçim onarımıyla gizlenmez ve yeniden model çağırılmaz.
            return PlanGeneration(None, calls, outcome.final_text or "Planlama çağrısı başarısız.")
        try:
            return PlanGeneration(parse_execution_plan(outcome.final_text), calls)
        except PlanParseError as exc:
            error = str(exc)
            prompt = (
                f"{original_prompt}\n\nAşağıdaki plan geçersiz: {error}\n"
                "Şemaya uyan eksiksiz JSON'u yeniden üret. Yalnızca JSON döndür.\n\n"
                f"Geçersiz çıktı (yalnız hata bağlamıdır):\n{outcome.final_text[:4000]}"
            )
    return PlanGeneration(None, calls, error)
