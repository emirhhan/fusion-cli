"""Plan adımının model çağrısı hakkı, görev düzeyi kademesine hapsolmaz.

Ölçülmüş hata (Dead Cells koşusu, `assets/ASSETS.json` adımı): adım hiçbir hata
vermeden "agent adım bütçesi doldu" ile düştü. Zincir şuydu —

1. Görev metni karmaşıklık anahtar kelimelerine çarpmadı, beklenen etki `file:...`
   ise `_MUTATING_EFFECTS` içinde DEĞİLDİ; `policy_for` sohbet kademesini verdi:
   `max_model_calls=8`.
2. `workflow_budget()` adım zarfını 40'a yükseltti (doğru davranış).
3. `step_deps` ise `min(policy.max_model_calls, remaining)` = `min(8, 40)` = 8
   uyguladı. Zarf hiç bağlamadı; adım 8 çağrıda kesildi.

Plan adımının harcama yetkisi ZARFTIR: çok adımlı plan çalıştırma kararı zaten
işin karmaşık olduğunun kanıtıdır.
"""

from __future__ import annotations

from fusion_cli.core.execution_plan import PlanPhase, PlanStep, RetrySafety
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.classify import TaskKind
from fusion_cli.engines.agent.execution_policy import policy_for
from fusion_cli.engines.agent.plan_context import step_deps

from .fakes import AlwaysApprove, make_config


class _Publisher:
    def publish(self, event: object) -> None:
        return None


def _deps(config, policy, tmp_path):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.loop import AgentDeps

    return AgentDeps(
        config=config,
        publisher=_Publisher(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        execution=policy,
    )


def _step(**extra: object) -> PlanStep:
    return PlanStep(
        step_id="varliklari-uret",
        goal="assets/ASSETS.json dosyasını üret",
        depends_on=(),
        expected_effects=("file:assets/ASSETS.json",),
        allowed_tool_families=("files",),
        success_criteria=("dosya var",),
        verification_hint="dosyayı oku",
        retry_safety=RetrySafety.SAFE,
        phase=PlanPhase.EXECUTION,
        **extra,  # type: ignore[arg-type]
    )


def test_adim_hakki_zarftan_gelir_gorev_kademesi_tavan_degildir(tmp_path):
    """Sohbet kademesi (8) bir plan adımını 8 çağrıda kesmemeli."""
    config = make_config(agent=ModelSpec(name="agent", model="gemini_web/main/auto"))
    policy = policy_for(
        config, ModelSpec(name="a", model="gemini_web/main/auto"), TaskKind.EXPLORE, "kısa iş"
    )
    deps = _deps(config, policy, tmp_path)

    scoped = step_deps(deps, _step(), remaining=40, observe=False)

    assert scoped.execution.max_model_calls == 40


def test_kalan_zarf_adim_hakkini_yine_de_sinirlar(tmp_path):
    """Zarf tükenmeye yakınsa adım kalanla yetinir; sınır yukarı değil aşağı çalışır."""
    config = make_config(agent=ModelSpec(name="agent", model="gemini_web/main/auto"))
    policy = policy_for(
        config, ModelSpec(name="a", model="gemini_web/main/auto"), TaskKind.FEATURE, "kapsamlı iş"
    )
    deps = _deps(config, policy, tmp_path)

    scoped = step_deps(deps, _step(), remaining=3, observe=False)

    assert scoped.execution.max_model_calls == 3


def test_gozlem_turu_dar_hakkini_korur(tmp_path):
    """Gözlem turu tek çağrılık sondayla açılır; zarf onu genişletmemeli."""
    config = make_config(agent=ModelSpec(name="agent", model="gemini_web/main/auto"))
    policy = policy_for(
        config, ModelSpec(name="a", model="gemini_web/main/auto"), TaskKind.FEATURE, "kapsamlı iş"
    )
    deps = _deps(config, policy, tmp_path)

    scoped = step_deps(deps, _step(), remaining=1, observe=True)

    assert scoped.execution.max_model_calls == 1
    assert scoped.execution.allow_mutation is False
