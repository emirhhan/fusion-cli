"""Plan üretimi ve biçim onarımını gerçek çağrı sayılarıyla sonuçlandırır."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from ...core.execution_plan import ExecutionPlan
from .plan_coverage import coverage_instruction, missing_deliverables
from .plan_parser import PlanParseError, parse_execution_plan
from .promotion import PromotionContext

if TYPE_CHECKING:
    from ...core.types import Message
    from .loop import AgentDeps, AgentOutcome


class RunAgent(Protocol):
    """Plan ve adım alt turlarının ortak çağrı yüzeyi."""

    async def __call__(
        self,
        task: str,
        deps: AgentDeps,
        *,
        history: list[Message] | None = ...,
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
    #: Görevde istenip planda karşılanamayan teslimatların adları.
    #:
    #: Plan yine çalıştırılır ama eksik SESSİZ kalmaz: kullanıcıya "tamamlandı"
    #: denirken istediği şeyin planlanmadığını bilmesi gerekir.
    missing: tuple[str, ...] = ()


async def generate_plan(
    task: str,
    deps: AgentDeps,
    run_agent: RunAgent,
    limit: int,
    promotion: PromotionContext | None,
    *,
    check_coverage: bool = False,
    history: list[Message] | None = None,
) -> PlanGeneration:
    """Şemayı bir kez onar; her iki gerçek çağrının maliyetini koru.

    `check_coverage` yalnız GÖREVİN TAMAMI için plan üretilirken açılır. Yeniden
    planlama tek bir başarısız adımın yerine küçük bir dal üretir; oradaki plan
    görevin bütün teslimatlarını kapsamak zorunda değildir ve kapsama kapısını
    orada çalıştırmak her yeniden planlamaya gereksiz bir onarım turu ekler.

    `history` verilirse plan üretimi de paylaşılan konuşmayı görür: kullanıcının
    kök turda söylediği bir kısıt ya da tercih, plan üretiminden hiç haberdar
    olmayan bir model için kaybolmaz.
    """
    import asyncio

    path = Path(__file__).parent / "prompts" / "execution_plan.md"
    template = await asyncio.to_thread(path.read_text, encoding="utf-8")
    prompt = template.replace("{task}", task)
    if promotion is not None:
        prompt = f"{promotion.render()}\n\n{prompt}"
    original_prompt = prompt
    calls = 0
    error = "Planlama bütçesi tükendi."
    son_plan: ExecutionPlan | None = None
    son_eksikler: tuple[str, ...] = ()
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
            history=history,
        )
        calls += outcome.model_calls_made
        if not outcome.ok:
            # Kimlik doğrulama, kota veya çalışma bütçesi hatası bozuk JSON
            # değildir; biçim onarımıyla gizlenmez ve yeniden model çağırılmaz.
            return PlanGeneration(None, calls, outcome.final_text or "Planlama çağrısı başarısız.")
        try:
            plan = parse_execution_plan(outcome.final_text)
        except PlanParseError as exc:
            error = str(exc)
            # Onarım isteği HATAYI ÖNE ALIR. Eskiden önce bütün şema, sonra
            # hata geliyordu ve model uzun şablonu yeniden okuyup aynı planı
            # üretiyordu (ölçüldü: Godot koşusunda iki deneme de aynı kaçışsız
            # tırnak hatasıyla düştü). Şimdi ilk gördüğü şey ne yaptığı.
            prompt = (
                f"ÖNCEKİ PLANIN GEÇERSİZ: {error}\n"
                "Bunu düzelt ve şemaya uyan eksiksiz JSON'u yeniden üret. "
                "Yalnızca JSON döndür.\n\n"
                f"{original_prompt}\n\n"
                f"Geçersiz çıktı (yalnız hata bağlamıdır):\n{outcome.final_text[:4000]}"
            )
            continue
        eksikler = missing_deliverables(task, plan) if check_coverage else ()
        if not eksikler:
            return PlanGeneration(plan, calls)
        # Kapsama eksiği bir BİÇİM hatası değildir; onarım hakkı bitmişse planı
        # reddetmek de doğru değil: elde çalışan bir plan var, onu çöpe atmak
        # kullanıcıya hiçbir şey teslim etmemektir. Eksik adlandırılarak kaydedilir
        # ve plan yine döner (bkz. `PlanGeneration.missing`).
        error = coverage_instruction(eksikler)
        prompt = f"{error}\n\n{original_prompt}"
        son_plan = plan
        son_eksikler = tuple(teslimat.name for teslimat in eksikler)
    if son_plan is not None:
        return PlanGeneration(son_plan, calls, missing=son_eksikler)
    return PlanGeneration(None, calls, error)
