"""Plan alt turlarının bütçe, araç ve istem sınırlarını kurar."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.checkpoint import StepCheckpointEvidence
from ...core.execution_plan import PlanStep
from ...core.tools import ToolContext, ToolFamily, tool_family
from ...tools import build_registry
from ..workflow.model import WorkflowBudget
from .execution_policy import ExecutionPolicy
from .plan_checkpoint import dependency_text

if TYPE_CHECKING:
    from .loop import AgentDeps


def workflow_budget(deps: AgentDeps) -> WorkflowBudget:
    """Mevcut yapılandırılmış zarfları alt turun sınırıyla birleştir.

    Adım zarfı, bir adımın alt-turuna TANINAN haktan küçük olamaz: alt tur zaten
    kendi politika sınırıyla kısıtlıdır, zarf bundan küçükse fatura iş DOĞRU
    giderken kesilir. Ölçüldü (Godot koşusu): 19-22 başarılı araç çağrısıyla
    ilerleyen adım tek bir hata vermeden yalnız zarf yüzünden duraklatıldı.
    """
    runtime = getattr(getattr(deps, "config", None), "runtime", None)
    defaults = WorkflowBudget()
    step_calls = getattr(getattr(deps, "execution", None), "max_model_calls", None)
    per_step = getattr(runtime, "workflow_step_calls", defaults.per_step)
    if isinstance(step_calls, int):
        per_step = max(per_step, step_calls)
    return WorkflowBudget(
        planning=getattr(runtime, "workflow_planning_calls", defaults.planning),
        per_step=per_step,
        recovery=getattr(runtime, "workflow_recovery_calls", defaults.recovery),
        final=getattr(runtime, "workflow_final_verification_calls", defaults.final),
        attempts=getattr(runtime, "workflow_attempt_calls", defaults.attempts),
    )


#: Bildirilen beklenen etkinin ZORUNLU kıldığı araç aileleri.
#:
#: Plan ailesini yazmayı unutursa adım kendi etkisini üretemez hâle gelir. Ölçüldü
#: (canlı starter koşusu): `test-ciktisini-okuyup-duzelt` adımı dosyayı düzeltmesi
#: gerekirken yalnız `shell` ailesiyle açıldı; `replace_range` ve `edit_file`
#: kapalıydı ve görev yapılamadı. Adımın kendi sözleşmesi, kapsamının alt sınırıdır.
_ETKI_AILELERI: dict[str, str] = {
    "workspace_mutation": ToolFamily.FILES.value,
    "shell_action": ToolFamily.SHELL.value,
    "git_commit": ToolFamily.VCS.value,
    "git_push": ToolFamily.VCS.value,
}


def _effect_families(step: PlanStep) -> set[str]:
    """Adımın bildirdiği etkiyi üretebilmesi için gereken aileler."""
    families = set()
    for effect in step.expected_effects:
        if effect.startswith("file:"):
            families.add(ToolFamily.FILES.value)
            continue
        aile = _ETKI_AILELERI.get(effect)
        if aile is not None:
            families.add(aile)
    return families


def step_deps(deps: AgentDeps, step: PlanStep, remaining: int, *, observe: bool) -> AgentDeps:
    """Adım ailesini gerçek kayıt adlarına çevir; gözlem turunu salt-okunur kıl.

    Kapsam YAN ETKİYİ sınırlar, bakmayı değil: okuma araçları her adımda açıktır.
    Ölçüldü (canlı starter koşusu): yalnız `shell` ailesiyle açılan adımda model
    traceback'i okumak için `read_file` çağırdı ve "kapsam dışı" cevabını aldı;
    başka bir adımda `read_file`, `replace_range` ve `edit_file` birlikte kapalıydı
    ve görev yapılamaz hâle geldi. Gözlemin yan etkisi yoktur, planın niyetini de
    ihlal edemez; kapsamın işi bir adımın BAŞKA adımın işini yapmasını önlemektir.
    """
    policy = getattr(deps, "execution", None) or ExecutionPolicy(is_web=False)
    registry = getattr(deps, "base_registry", None) or build_registry()
    families = set(step.allowed_tool_families) | _effect_families(step)
    # Kabuk açıkken dosya düzenlemeyi kapatmak GERÇEK bir kısıt değildir: `sed` ile
    # aynı değişiklik zaten yapılabilir. Ölçüldü (6 Eylül): yalnız `shell` ailesiyle
    # açılan adımda `edit_file` ve `replace_range` engellendi; kısıt işi engellemedi,
    # modeli daha kötü ve denetlenmesi zor araca itti.
    if ToolFamily.SHELL.value in families:
        families.add(ToolFamily.FILES.value)
    known = ((name, registry.get(name)) for name in registry.names())
    allowed = frozenset(
        name
        for name, tool in known
        if tool is not None
        and (not tool.mutating or tool_family(name).value in families)
        and (not observe or not tool.mutating)
    )
    if policy.allowed_tool_names is not None:
        allowed &= policy.allowed_tool_names
    effect = step.expected_effects[0] if step.expected_effects and not observe else None
    # Yapı kapısı "bu biçimi üreten araç VAR" derken adımın ÇAĞIRABİLECEĞİ araca
    # bakmalı. Ölçüldü (canlı Godot koşusu): plan sahne adımını yalnız `files`
    # ailesiyle açtı, `godot__save_scene` bu adımda kapalıydı ama kapı hâlâ o
    # araca yönlendirdi; model aynı duvara üç kez çarptı ve oyun teslim edilemedi.
    # Kural depoda zaten yazılı: bir kapı, işi YAPAMAYAN bir yeteneğe yönlendiremez.
    context = replace(
        deps.tool_context, available_tools=set(deps.tool_context.available_tools) & allowed
    )
    return replace(
        deps,
        tool_context=context,
        execution=replace(
            policy,
            required_effect=effect,
            requires_tool_evidence=effect is not None,
            allow_mutation=policy.allow_mutation and not observe,
            mutation_block_reason="Kurtarma yalnız mevcut durumu gözlemleyebilir."
            if observe
            else policy.mutation_block_reason,
            observe_only=observe,
            # Adım kaçıncı kez deneniyorsa zincir o kadar yukarı kaydırılır: aynı
            # modelle aynı duvara çarpmak yerine bir üst modele yükselinir.
            escalation=step.attempts,
            complex_task=policy.complex_task and not observe,
            max_model_calls=min(policy.max_model_calls, remaining)
            if policy.max_model_calls is not None
            else remaining,
            allowed_tool_names=allowed,
        ),
    )


def step_prompt(
    task: str,
    step: PlanStep,
    evidence: dict[str, StepCheckpointEvidence],
    *,
    workspace: str = "",
) -> str:
    """Dar adım istemini yalnız gerçek bağımlılık kanıtlarıyla üret."""
    return (
        f"ANA GÖREV:\n{task}\n\nPLAN ADIMI [{step.step_id}]:\n{step.goal}\n\n"
        f"{workspace}"
        f"BAĞIMLILIK KANITLARI:\n{dependency_text(step, evidence)}\n\nBAŞARI KOŞULLARI:\n"
        + "\n".join(f"- {criterion}" for criterion in step.success_criteria)
        + f"\n\nDOĞRULAMA İPUCU:\n{step.verification_hint}\n\n"
        "Yalnızca bu adımı tamamla. Sonuçta yaptığını ve gözlediğin kanıtı açıkça yaz."
    )


#: Adım isteminde listelenecek en fazla dosya adı.
#
# Adım istemi DAR olmalı; amaç dosya sistemini kopyalamak değil, aynı keşfi
# ikinci kez yaptırmamak. Uzun liste bağlamı şişirir ve context rot üretir.
MAX_STEP_WORKSPACE_FILES = 12


def workspace_block(context: ToolContext) -> str:
    """Bu turda ZATEN okunan ve değiştirilen dosyaları adım istemine yaz.

    Ölçüldü (7 Eylül canlı koşusu, `surum-sabitini-tek-kaynaga-indir`): depo
    haritası yalnız üst turda (`depth == 0`) veriliyor; plan adımları alt turda
    koştuğu için hiçbir bağlam görmüyordu. Her adım `list_dir` ve `glob **/*` ile
    baştan başladı, aynı üç dosyayı üst üste okudu ve bütçe iş bitmeden tükendi.

    Adımın kendi keşfini yapması yanlış değildir; aynı keşfi ÜÇÜNCÜ kez yapması
    israftır. Blok yalnız ADLARI taşır, içerik taşımaz: yönlendirir, bağlamı
    şişirmez.
    """
    okunan = _relative_names(context, context.fully_read)
    degisen = _relative_names(context, context.touched)
    if not okunan and not degisen:
        return ""
    satirlar = ["ÇALIŞMA ALANI (bu turda):"]
    if okunan:
        satirlar.append(f"- okunan: {', '.join(okunan)}")
    if degisen:
        satirlar.append(f"- değiştirilen: {', '.join(degisen)}")
    satirlar.append("Bu dosyaları yeniden aramana gerek yok; içeriği gerekiyorsa doğrudan oku.")
    return "\n".join(satirlar) + "\n\n"


def _relative_names(context: ToolContext, paths: Iterable[Path]) -> list[str]:
    """Yolları proje köküne göre kısalt; kök dışındakiler olduğu gibi kalır."""
    adlar: list[str] = []
    for path in sorted(paths):
        try:
            adlar.append(path.relative_to(context.root).as_posix())
        except ValueError:
            adlar.append(path.name)
        if len(adlar) >= MAX_STEP_WORKSPACE_FILES:
            break
    return adlar
