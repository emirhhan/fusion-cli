"""Playbook ve aşamalı workflow yürütme — serbest agent döngüsüne alternatif yollar.

İki opt-in yol (varsayılan kapalı) buradadır:

- **Playbook** — istek bilinen deterministik bir akışı tetiklerse (ör. "commit yap"),
  serbest ReAct döngüsü yerine o akış çalışır: daha az model çağrısı, öngörülebilir
  sonuç. Tüm komutları güvenli olmayan ya da kapısı kırılan playbook reddedilir.
- **Workflow** — zor görevlerde aşamalı akış (localize→plan→patch→verify→review) tur
  başına SABİT model-çağrısı bütçesiyle çalışır; maliyet öngörülebilir olur.

Her ikisi de bir alt-turu `run_agent` ile çalıştırır. Döngüsel import'tan kaçınmak
için `run_agent` çağrı sırasında parametre olarak geçirilir; bu modül onu import etmez.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from ...core.constants import SHELL_TIMEOUT_S
from ...core.types import Message
from ...tools.safety import danger_reason
from ..playbook import Playbook, run_playbook
from ..playbook.library import ShellStepRunner, build_playbooks
from ..playbook.matching import find_match
from ..workflow import Budget, Stage, StageOutcome, run_workflow

if TYPE_CHECKING:
    from .loop import AgentDeps, AgentOutcome


class RunAgent(Protocol):
    """`run_agent`'ın bu modülün ihtiyaç duyduğu çağrı imzası."""

    async def __call__(
        self,
        task: str,
        deps: AgentDeps,
        *,
        depth: int = ...,
        self_review: bool | None = ...,
    ) -> AgentOutcome: ...


async def maybe_run_playbook(task: str, deps: AgentDeps) -> AgentOutcome | None:
    """İstek bir playbook'u tetikliyorsa deterministik akışı çalıştır.

    Opt-in (varsayılan kapalı). Yalnızca tüm komutları güvenli olan bir playbook
    çalıştırılır; akış başarısız olur (checks kırılır → geri alınır) ise None dönülür
    ve normal agent akışına düşülür — model devralır.
    """
    from .loop import AgentOutcome  # runtime import: tip değil, gerçek sınıf gerekli.

    if not deps.config.runtime.playbooks:
        return None
    # Kütüphane PROJEDEN üretilir: sabit `ruff`/`pytest` bir Node projesinde
    # yanlış komuttur ve tur boşa gider.
    playbook = find_match(build_playbooks(deps.tool_context.root), task)
    if playbook is None or not all_commands_safe(playbook):
        return None

    runner = ShellStepRunner(cwd=str(deps.tool_context.root), timeout_s=SHELL_TIMEOUT_S)
    result = await run_playbook(playbook, runner)
    if not result.ok:
        return None
    return AgentOutcome(
        final_text=result.summary,
        messages=[Message("assistant", result.summary)],
        tool_calls_made=len(result.ran_steps),
    )


#: Her aşamaya modele verilecek odaklı Türkçe yönerge. `{task}` görev, `{notes}`
#: önceki aşamaların birikmiş notlarıdır. Aşama dar tutulur: bütçe boşa gitmesin.
_STAGE_PROMPTS: dict[Stage, str] = {
    Stage.LOCALIZE: (
        "AŞAMA: Yer belirleme. Şu görev için değişikliğin yapılacağı yeri bul "
        "(dosya:satır). Henüz DEĞİŞİKLİK YAPMA, yalnızca yeri raporla.\n\nGörev: {task}"
    ),
    Stage.PLAN: (
        "AŞAMA: Plan. Aşağıdaki bulgulara dayanarak EN KÜÇÜK değişikliğin planını "
        "maddeler halinde çıkar. Kod yazma.\n\nGörev: {task}\n\nBulgular:\n{notes}"
    ),
    Stage.PATCH: (
        "AŞAMA: Yama. Planı uygula: yalnızca gerekli en küçük değişikliği yap. "
        "Kapsam dışına çıkma.\n\nGörev: {task}\n\nPlan:\n{notes}"
    ),
    Stage.VERIFY: (
        "AŞAMA: Doğrulama. Yaptığın değişikliği syntax/lint/test çalıştırarak doğrula. "
        "Kırılan varsa en dar düzeltmeyi uygula.\n\nGörev: {task}\n\nYapılan:\n{notes}"
    ),
    Stage.REVIEW: (
        "AŞAMA: Gözden geçirme. Değişikliğin diff'ini gözden geçir; kapsam dışı ya da "
        "gereksiz bir şey varsa geri al ve kısa bir özet ver.\n\nGörev: {task}\n\nÖzet:\n{notes}"
    ),
}


class _AgentStageExecutor:
    """Her workflow aşamasını, odaklı bir alt-turla (run_agent) çalıştıran köprü."""

    def __init__(self, task: str, deps: AgentDeps, run_agent: RunAgent) -> None:
        self._task = task
        self._deps = deps
        self._run_agent = run_agent

    async def run(self, stage: Stage, notes: dict[Stage, str]) -> StageOutcome:
        prompt = _STAGE_PROMPTS[stage].format(task=self._task, notes=_format_notes(notes))
        # depth=1: üstteki workflow/playbook/öz-denetim dalları yeniden tetiklenmesin.
        outcome = await self._run_agent(prompt, self._deps, depth=1, self_review=False)
        ok = outcome.ok and not outcome.hit_step_limit
        # Model çağrısı ~ araç turu + son cevap turu. Bütçe kapısını besleyen tahmin.
        return StageOutcome(
            ok=ok, model_calls=outcome.tool_calls_made + 1, note=outcome.final_text.strip()[:500]
        )


def _format_notes(notes: dict[Stage, str]) -> str:
    if not notes:
        return "(yok)"
    return "\n".join(f"[{stage.value}] {note}" for stage, note in notes.items())


async def run_workflow_stages(task: str, deps: AgentDeps, run_agent: RunAgent) -> AgentOutcome:
    """Aşamalı workflow'u bütçe kapısıyla çalıştır ve sonucu agent turu sonucuna çevir."""
    from .loop import AgentOutcome  # runtime import: tip değil, gerçek sınıf gerekli.

    executor = _AgentStageExecutor(task, deps, run_agent)
    budget = Budget(max_model_calls=deps.config.runtime.workflow_max_model_calls)
    result = await run_workflow(executor, budget=budget)
    text = result.final_note or result.summary
    return AgentOutcome(
        final_text=text,
        messages=[Message("assistant", text)],
        tool_calls_made=len(result.stages_run),
        hit_step_limit=result.budget_exhausted,
        ok=result.ok,
    )


def all_commands_safe(playbook: Playbook) -> bool:
    """Playbook'un tüm komutları (adım/geri-alma/doğrulama) yıkıcı desen içermiyor mu."""
    commands = [step.command for step in playbook.steps]
    commands += [step.rollback for step in playbook.steps if step.rollback]
    commands += list(playbook.checks)
    return all(danger_reason("run_shell", {"command": command}) is None for command in commands)
