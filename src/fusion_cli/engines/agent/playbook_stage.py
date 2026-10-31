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
from ...core.events import StatusChanged
from ...core.types import Message
from ...tools.safety import danger_reason
from ..playbook import Playbook, run_playbook
from ..playbook.library import ShellStepRunner, build_playbooks
from ..playbook.matching import find_match
from ..workflow import Budget, Stage, StageOutcome, run_workflow
from .approval import Decision, resolve_request

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

    Opt-in (varsayılan kapalı). Yalnızca tüm komutları güvenli olan ve kullanıcının
    onay kipinden geçen bir playbook çalıştırılır; akış başarısız olur (checks
    kırılır → geri alınır) ise kullanıcıya bildirilir, None dönülür ve normal agent
    akışına düşülür — model devralır.
    """
    from .loop import AgentOutcome  # runtime import: tip değil, gerçek sınıf gerekli.

    if not deps.config.runtime.playbooks:
        return None
    # Kütüphane PROJEDEN üretilir: sabit `ruff`/`pytest` bir Node projesinde
    # yanlış komuttur ve tur boşa gider.
    playbook = find_match(build_playbooks(deps.tool_context.root), task)
    if playbook is None or not all_commands_safe(playbook):
        return None
    if not await _commands_approved(playbook, deps):
        deps.publisher.publish(
            StatusChanged(
                f"Playbook '{playbook.id}' atlandı: komutları bu onay kipinde otomatik "
                "çalışamaz; normal akışa geçiliyor"
            )
        )
        return None

    runner = ShellStepRunner(cwd=str(deps.tool_context.root), timeout_s=SHELL_TIMEOUT_S)
    result = await run_playbook(playbook, runner)
    if not result.ok:
        # Sessiz geri düşme yok (A3-27): akış yarıda kesildiyse ve yan etkisi
        # geri alındıysa kullanıcı bunu görmeli; model normal akışta devralır.
        geri_alma = (
            "yapılan değişiklikler geri alındı"
            if result.rolled_back
            else "geri alınacak adım yoktu"
        )
        deps.publisher.publish(
            StatusChanged(
                f"Playbook '{playbook.id}' başarısız ({result.summary}); {geri_alma}. "
                "Normal akışa geçiliyor"
            )
        )
        return None
    return AgentOutcome(
        final_text=result.summary,
        messages=[Message("assistant", result.summary)],
        tool_calls_made=len(result.ran_steps),
    )


async def _commands_approved(playbook: Playbook, deps: AgentDeps) -> bool:
    """Playbook'un HER komutu, kullanıcının onay kipinden normal `run_shell` gibi geçmeli.

    Ölçüldü (30 Ekim, A3-27): playbook komutları `ShellStepRunner` ile doğrudan
    koşuyor, kip ve onay kapısına hiç uğramıyordu (manuel/plan kipinde bile). Aynı
    karar yolu (`resolve_request` + politika) kullanılır; komutlardan biri onaylanmaz
    ya da reddedilirse playbook hiç başlamaz.
    """
    tool = deps.base_registry.get("run_shell")
    if tool is None:
        return False
    policy = deps.policy_factory() if deps.policy_factory else deps.policy
    commands = [step.command for step in playbook.steps]
    commands += [step.rollback for step in playbook.steps if step.rollback]
    commands += list(playbook.checks)
    for command in dict.fromkeys(commands):
        request = await resolve_request(
            tool,
            {"command": command},
            deps.allowed_commands,
            root=deps.tool_context.root,
            context=deps.tool_context,
            rules=getattr(deps, "permission_rules", None),
        )
        if await policy.decide(request) is not Decision.ALLOW:
            return False
    return True


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


#: Aşama notunun sonraki aşamaya taşınan en çok uzunluğu. 500 karakter uzun planı PATCH
#: aşamasına kesik taşıyordu (A3-28).
_STAGE_NOTE_CHARS = 2_000


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
        # Bütçe kapısı GERÇEK model çağrısıyla beslenir; sayaç yoksa (0) araç turu + son
        # cevap turu tahmini kullanılır (A3-28: tahmin bütçeyi yanlış ölçüyordu).
        calls = outcome.model_calls_made or outcome.tool_calls_made + 1
        return StageOutcome(
            ok=ok, model_calls=calls, note=outcome.final_text.strip()[:_STAGE_NOTE_CHARS]
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
