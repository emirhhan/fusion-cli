"""Agent döngüsü: tek model + araçlar + öz-denetim.

Bir tur şöyle akar:

    model çağrısı ──▶ araç istedi mi?
                       ├── evet → onay → çalıştır → sonucu geçmişe ekle → tekrar
                       └── hayır → nihai cevap

Üzerine üç iyileştirme katmanı biner:

- **Refleksiyon** — bir araç hata döndürdüğünde modele "farklı yaklaş" notu enjekte
  edilir. Ek model çağrısı YOK; bedava bir davranış düzeltmesidir.
- **Otomatik devam** — model işi yarım bırakmış görünüyorsa bir kez "devam et" denir.
- **Öz-eleştiri** — tur bitince denetçi model sonucu kontrol eder; somut bir sorun
  bulursa TEK düzeltici tur çalışır. Sonsuz düzeltme döngüsü yoktur.

Motor konsolu tanımaz: tüm ilerleme olay olarak yayınlanır. Araçlar arasında ayrım
yapmaz: alt-ajan devri de dosya okumak da kayıt defterinden geçer.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ...config.eligibility import effort_for_spec
from ...config.model_select import select_agent_spec
from ...config.models import Config
from ...core.budget import BudgetStop, TurnBudget
from ...core.clock import SystemClock
from ...core.concurrency import BackgroundTasks
from ...core.errors import FusionError
from ...core.events import (
    Channel,
    ContextCompressed,
    EventPublisher,
    MutationUnavailable,
    SelfReviewFinished,
    SelfReviewStarted,
    ToolExecuted,
    ToolOutcome,
    TurnBudgetExhausted,
    VerificationFailed,
)
from ...core.health import HealthRegistry
from ...core.memory import CodeIndex, LessonMemory
from ...core.tools import ToolContext, ToolResult
from ...core.types import CompletionRequest, Message, ModelResult, StreamDone, ToolCall
from ...core.verification import VerificationResult, Verifier
from ...memory.lessons import as_prompt_block
from ...providers.factory import build_provider
from ...providers.web_registry import web_registry_for
from ...tools import ToolRegistry, build_registry
from ...tools.capabilities import CapabilityRegistry
from ...tools.emulation import render_tool_example, validate_arguments
from ...tools.preview import file_diff
from ..effects.runner import maybe_run_effect_workflow
from . import compaction, learning_steps, reflexion, review, skill_recall
from .approval import ApprovalPolicy, Decision, SecurityApproval, build_request
from .classify import TaskKind, classify_task, recall_scope, scope_of
from .engine_tools import UserAsker, build_agent_registry
from .execution_policy import ExecutionPolicy, is_complex_kind, policy_for
from .playbook_stage import maybe_run_playbook, run_workflow_stages

_PROMPTS = Path(__file__).parent / "prompts"
SYSTEM_PROMPT = (_PROMPTS / "system.md").read_text(encoding="utf-8")
PLAN_MODE_PROMPT = (_PROMPTS / "plan_mode.md").read_text(encoding="utf-8")

#: Yarım kalan turda en fazla kaç kez "devam et" enjekte edilir.
MAX_AUTO_CONTINUE = 1
#: Doğrulama kapısının bir turda en fazla kaç kez çalışacağı.
#:
#: 1 yetmiyordu: düzeltici tur KENDİ hatasını üretebiliyor. Gerçek koşuda kapı beş
#: sorunu bildirdi, model düzeltirken index.html'i yeniden yazdı ve <script> etiketini
#: düşürdü — sayfa tamamen boş kaldı, kapı bir daha bakmadığı için öyle teslim edildi.
#: 2 bu regresyonu yakalar; daha fazlası sonsuz düzeltme döngüsü riskidir.
MAX_VERIFY_ROUNDS = 2

#: Boş cevapta kaç kez daha denenir. Sınırsız denemek kotayı ve zamanı tüketir;
#: hiç denememek turu iş yapmadan bitirir (ölçüldü).
MAX_EMPTY_RETRIES = 2
#: Bozuk araç çağrısı için tanınan onarım hakkı. Model düzeltmiyorsa tekrarlıyordur.
MAX_TOOL_CONTRACT_REPAIRS = 1


#: Kullanıcı reddettiğinde modele dönen açıklama. Hata DEĞİLDİR; refleksiyon tetiklemez.
DENIED_MESSAGE = "Kullanıcı bu işlemi onaylamadı. Farklı bir yol dene ya da nedenini açıkla."
#: Plan modunda değiştirici araç hiç çalıştırılmaz ve kullanıcıya sorulmaz.
BLOCKED_MESSAGE = "PLAN MODU: değişiklik yapılamaz. Sorma, yalnızca planı sun."
#: Görev gerçek bir etki istiyor ama model bunu yapamıyor. Kullanıcıya NE YAPACAĞINI
#: söyler: sebep + çıkış yolu. Hata mesajı eyleme dönüştürülebilir olmalıdır (RULES).
MUTATION_UNAVAILABLE_ANSWER = (
    "Bu görev dosya/sistem değişikliği gerektiriyor ama seçili model bunu yapamıyor: "
    "{reason}.\n\n"
    "Yapılacak: `fusion serve` ile paneli aç → Sağlayıcılar → ilgili web oturumu → "
    "\"Araç yeteneğini ölç\". Ölçüm geçerse izin açılır. Alternatif olarak `/model` ile "
    "araç yetenekli bir API modeline geç.\n\n"
    "Hiçbir değişiklik yapılmadı."
)
#: Model yetenek kapısına takıldı: okuyabilir, planlayabilir ama değiştiremez.
MUTATION_BLOCKED_MESSAGE = (
    "Bu model dosya/sistem değiştiremez ({reason}). Değişiklik önerini metin olarak "
    "yaz; uygulamayı kullanıcı ya da araç yetenekli bir model üstlenecek."
)

_DECISION_MESSAGES = {
    Decision.DENIED: DENIED_MESSAGE,
    Decision.BLOCKED: BLOCKED_MESSAGE,
}
_DECISION_OUTCOMES = {
    Decision.DENIED: ToolOutcome.DENIED,
    Decision.BLOCKED: ToolOutcome.BLOCKED,
}


def _new_budget(config: Config) -> TurnBudget:
    """Bir kullanıcı turu için bütçe kur.

    Eşiklerin bir kısmı yapılandırmadan, bir kısmı yukarıdaki sabitlerden gelir ve bu
    bilinçlidir: kullanıcının ayarlaması anlamlı olanlar (adım sayısı, boşta tur)
    `defaults.yaml`'dadır; "kaç kez devam et denir" gibi davranış detayları koddadır
    ve gerekçeleri sabitin yanında yazılıdır.
    """
    return TurnBudget(
        clock=SystemClock(),
        max_model_calls=config.runtime.agent_max_steps,
        max_verify_rounds=MAX_VERIFY_ROUNDS,
        max_empty_retries=MAX_EMPTY_RETRIES,
        max_contract_repairs=MAX_TOOL_CONTRACT_REPAIRS,
        max_auto_continues=MAX_AUTO_CONTINUE,
        max_idle_rounds=config.runtime.agent_max_idle_rounds,
    )


@dataclass(slots=True)
class AgentOutcome:
    """Bir agent turunun sonucu."""

    final_text: str
    messages: list[Message]
    tool_calls_made: int = 0
    #: Adım sınırına dayanıldı mı?
    hit_step_limit: bool = False
    #: Tur temiz bitti mi? Model akışı hata verirse False. Ders güvenini besler.
    ok: bool = True
    #: Başarıyla çalışan değiştirici araç sayısı. Koşullu denetim/öğrenme kapısı kullanır.
    mutating_tool_calls_made: int = 0
    #: Başarısız araç sayısı. Basit salt-okuma turu ile sorunlu turu ayırır.
    failed_tool_calls: int = 0
    #: Bu turda yapılan gerçek model çağrısı sayısı (teşhis ve bütçe için).
    model_calls_made: int = 0


@dataclass(slots=True)
class AgentDeps:
    """Motorun dış bağımlılıkları. Testte tamamı sahteyle verilebilir."""

    config: Config
    publisher: EventPublisher
    policy: ApprovalPolicy
    tool_context: ToolContext
    #: Yerleşik araçlar. Motora bağlı araçlar çalışma anında bunun kopyasına eklenir.
    base_registry: ToolRegistry = field(default_factory=build_registry)
    #: Kullanıcıya soru sorabilen taraf. Yoksa `ask_user` aracı hiç sunulmaz.
    asker: UserAsker | None = None
    #: Anlamsal kod araması. Yoksa `search_codebase` aracı hiç sunulmaz.
    code_index: CodeIndex | None = None
    #: Öğrenilen dersler. Yoksa hatırlama ve ders çıkarımı atlanır.
    lessons: LessonMemory | None = None
    #: Skill/agent kütüphanesi. Yoksa arama ve devretme araçları hiç sunulmaz.
    capabilities: CapabilityRegistry | None = None
    #: Kullanıcının `.claude/settings.local.json` içinde onaysız izin verdiği komutlar.
    allowed_commands: frozenset[str] = frozenset()
    #: Verilirse ders çıkarımı turu BEKLETMEDEN arka planda çalışır (REPL için).
    #: Verilmezse tur içinde beklenir (tek seferlik CLI için doğru davranış).
    background: BackgroundTasks | None = None
    channel: Channel = Channel.MAIN
    #: Kullanıcının seçtiği görev tipi (`/type`). `task_model_map` üzerinden bu turda
    #: kullanılacak modeli belirler; haritada karşılığı yoksa `agent:` rolü kullanılır.
    task_type: str = "general"
    #: Verilirse kod değiştiren tur sonrası doğrulama kapısı çalışır ve sonucu ders
    #: güvenini besler. Verilmezse (varsayılan) mevcut davranış birebir korunur.
    verifier: Verifier | None = None
    #: Oturum boyunca paylaşılan sağlayıcı sağlığı (circuit breaker + güvenilirlik).
    #: Verilirse sağlıksız model turlar arası atlanır. Verilmezse breaker kurulmaz.
    health: HealthRegistry | None = None
    #: TURUN TAMAMI için tek sayaç otoritesi. `run_agent` bunu tur başında bir kez
    #: kurar; öz-denetim ve doğrulama kapısının açtığı iç içe çağrılara AYNI nesne
    #: devredilir. `None` bırakılırsa ilk `run_agent` çağrısı kurar.
    #:
    #: Testler kendi bütçesini vererek sınırları daraltabilir.
    budget: TurnBudget | None = None

    def require_budget(self) -> TurnBudget:
        """Bütçeyi döndür; kurulmamışsa programlama hatasıdır.

        `run_agent` her çalıştığında bütçenin kurulu olduğunu garanti eder; bu metot
        yalnızca döngü içindeki kodun `None` kontrolü yapmasını gereksiz kılar.
        """
        if self.budget is None:
            raise FusionError("Tur bütçesi kurulmadan agent döngüsü çalıştırılamaz.")
        return self.budget


async def run_agent(
    task: str,
    deps: AgentDeps,
    *,
    history: list[Message] | None = None,
    plan_mode: bool = False,
    extra_system: str = "",
    depth: int = 0,
    self_review: bool | None = None,
    allowed_tools: set[str] | None = None,
    step_limit: int | None = None,
    verify: bool = True,
) -> AgentOutcome:
    """Bir görevi araçlarla çalıştır. Döndürülen geçmiş bir sonraki tura beslenir.

    `allowed_tools` verilirse modele YALNIZCA o araçlar sunulur (uzman agent'lar
    kendi araç setini bildirebilir). Görev yönetimi ve soru sorma her zaman açıktır.
    """
    # Bütçe turun EN BAŞINDA bir kez kurulur ve buradan sonra her iç içe çağrı aynı
    # nesneyi görür. Öz-denetim ve doğrulama kapısı `run_agent`'ı yeniden çağırdığı
    # için, bütçe orada kurulsaydı her düzeltici tur sıfırdan başlardı — düzeltilen
    # hata tam olarak buydu.
    if deps.budget is None:
        deps.budget = _new_budget(deps.config)

    if not plan_mode and depth == 0:
        played = await maybe_run_playbook(task, deps)
        if played is not None:
            return played

    registry = build_agent_registry(deps, depth=depth, run_agent=run_agent)
    kind = classify_task(task)

    # Gerçek dünya etkisi için deterministik handler varsa LLM ReAct döngüsünü
    # tamamen atla. Modelin "pushluyorum" demesi operasyon sonucu değildir; Git
    # workflow'u post-condition (local HEAD == remote HEAD) kanıtını kendisi üretir.
    effect_result = await maybe_run_effect_workflow(
        task, deps, registry, plan_mode=plan_mode, depth=depth
    )
    if effect_result is not None:
        effect_messages = list(history or [])
        effect_messages.append(Message("user", task))
        effect_messages.append(Message("assistant", effect_result.final_text))
        return AgentOutcome(
            final_text=effect_result.final_text,
            messages=effect_messages,
            tool_calls_made=effect_result.tool_calls_made,
            ok=effect_result.ok,
            mutating_tool_calls_made=effect_result.mutating_tool_calls_made,
            failed_tool_calls=effect_result.failed_tool_calls,
            model_calls_made=0,
        )

    if not plan_mode and depth == 0 and deps.config.runtime.workflow_mode:
        return await run_workflow_stages(task, deps, run_agent)

    recalled = learning_steps.recall_lessons(task, deps, scope=recall_scope(kind))
    remembered = as_prompt_block(recalled)
    expertise = _recall_skill(kind, deps, depth=depth)
    messages = _initial_messages(
        task,
        history,
        plan_mode=plan_mode,
        extra_system="\n\n".join(part for part in (remembered, expertise, extra_system) if part),
    )

    selected_spec = select_agent_spec(deps.config, deps.task_type)
    execution = policy_for(deps.config, selected_spec, kind, task)
    # Web AI'nın toplam süre sınırı bütçeye TUR BAŞINDA bir kez yazılır; iç içe
    # çağrılarda yeniden kurulsaydı süre sınırı her düzeltmede tazelenirdi.
    budget = deps.require_budget()
    if budget.total_timeout_s is None and execution.total_timeout_s is not None:
        budget.total_timeout_s = execution.total_timeout_s

    # Yetenek kapısı sessiz kalmamalı: değiştirici araçlar sunulmuyorsa kullanıcı
    # bunu ve nasıl kaldıracağını GÖRMELİ. Görev zaten gerçek bir etki istiyorsa
    # model çağrısı harcamadan dururuz — hiçbir tur bu kısıtı aşamaz.
    if not execution.allow_mutation and not plan_mode:
        blocking = execution.required_effect is not None
        deps.publisher.publish(
            MutationUnavailable(reason=execution.mutation_block_reason, blocking=blocking)
        )
        if blocking:
            return AgentOutcome(
                final_text=MUTATION_UNAVAILABLE_ANSWER.format(
                    reason=execution.mutation_block_reason
                ),
                messages=[*(history or []), Message("user", task)],
                ok=False,
            )

    outcome = await _drive(
        messages,
        deps,
        registry,
        plan_mode=plan_mode,
        allowed_tools=allowed_tools,
        step_limit=step_limit,
        execution=execution,
    )

    should_review = deps.config.runtime.self_review if self_review is None else self_review
    # Başarısız provider/transport veya kanıtsız eylem sonucu cevap kalitesi değildir.
    # Denetçiye göndermek hatayı maskeleyip ek çağrılar üretir.
    if should_review and not outcome.ok:
        should_review = False
    if should_review and execution.conditional_self_review:
        should_review = _web_self_review_needed(task, kind, outcome, deps)
    if should_review and not plan_mode and depth == 0 and outcome.final_text.strip():
        outcome = await _self_review(task, outcome, deps)

    verification = None
    # Doğrulama turu hakkı da tur genelidir: iç içe bir düzeltme kendi kapı bütçesini
    # açamaz (`verify=False` ile zaten kapatılıyor, bütçe bunu ikinci kez garanti eder).
    while verify and budget.take_verify_round():
        verification = await _verify(outcome, deps, plan_mode=plan_mode, depth=depth)
        # Bulgu YOKLUĞU başarı değildir: `ok=False` tek başına düzeltmeyi hak eder.
        # Koşul eskiden `not verification.findings` de arıyordu; yalnızca özet
        # dolduran bir kapı (komut doğrulayıcısı) başarısız olduğunda agent
        # düzeltmeye hiç başlamıyordu.
        if verification is None or verification.ok:
            break
        outcome = await _fix_findings(verification, outcome, deps)

    await learning_steps.learn(
        task,
        outcome,
        deps,
        plan_mode=plan_mode,
        scope=scope_of(kind),
        allow_read_only=execution.learn_read_only_turns,
    )
    await learning_steps.reinforce_recalled(
        recalled, outcome, deps, plan_mode=plan_mode, verification=verification
    )
    outcome.messages = await _maybe_compress(outcome.messages, deps)
    return outcome


# --------------------------------------------------------------------------- #
# Döngü
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class _State:
    """TEK bir `_drive` çağrısının muhasebesi.

    Tur geneli sayaçlar burada DEĞİL `deps.budget` içindedir: iç içe düzeltici turlar
    aynı bütçeyi paylaşmalıdır. Buradakiler yalnızca bu çağrının raporlanan sonucunu
    üretir ve çağıran tarafından toplanır.
    """

    tool_calls_made: int = 0
    mutating_tool_calls_made: int = 0
    failed_tool_calls: int = 0
    model_calls_made: int = 0
    tool_rounds: int = 0
    tool_calls_last_turn: int = 0
    evidence_reprompts: int = 0
    tool_contract_abort: str = ""
    successful_tool_evidence: list[tuple[str, dict[str, object], bool]] = field(
        default_factory=list
    )


async def _drive(
    messages: list[Message],
    deps: AgentDeps,
    registry: ToolRegistry,
    *,
    plan_mode: bool,
    allowed_tools: set[str] | None = None,
    step_limit: int | None = None,
    execution: ExecutionPolicy,
) -> AgentOutcome:
    state = _State()
    budget = deps.require_budget()
    final_text = ""
    # Tur geneli model çağrısı sınırı BÜTÇEDEDİR: iç içe düzeltici turlar aynı
    # bütçeden yer. Buradaki `local_limit` yalnızca BU çağrıyı daha da daraltır
    # (alt-ajanın `step_limit`'i ve Web AI'nın tur başı sınırı).
    local_limit = step_limit
    if execution.max_model_calls is not None:
        local_limit = min(local_limit or execution.max_model_calls, execution.max_model_calls)
    local_calls = 0

    while True:
        if budget.model_calls_exhausted or (
            local_limit is not None and local_calls >= local_limit
        ):
            return _halt(final_text, messages, state, budget, BudgetStop.MODEL_CALLS, deps)
        local_calls += 1
        remaining = budget.remaining_s()
        if budget.out_of_time():
            return _halt(final_text, messages, state, budget, BudgetStop.DEADLINE, deps)

        try:
            if remaining is None:
                result = await _call_model(
                    messages,
                    deps,
                    registry,
                    allowed_tools,
                    execution=execution,
                    offer_tools=execution.offer_tools,
                )
            else:
                async with asyncio.timeout(max(1.0, remaining)):
                    result = await _call_model(
                        messages,
                        deps,
                        registry,
                        allowed_tools,
                        execution=execution,
                        offer_tools=execution.offer_tools,
                        timeout_s=min(deps.config.runtime.request_timeout_s, remaining),
                    )
        except TimeoutError:
            return _halt(final_text, messages, state, budget, BudgetStop.DEADLINE, deps)

        state.model_calls_made += 1
        budget.record_model_call()
        if _is_tool_contract_error(result.error):
            if budget.take_contract_repair():
                if result.text.strip():
                    messages.append(Message("assistant", result.text))
                messages.append(
                    reflexion.tool_contract_repair_note(result.error or "geçersiz çağrı")
                )
                continue
            budget.halt(BudgetStop.CONTRACT_UNREPAIRABLE)
            _publish_budget_stop(deps, budget, state)
            return _outcome(
                _tool_contract_abort_message(result.error or "geçersiz çağrı"),
                messages,
                state,
                ok=False,
            )
        if not result.ok:
            return _outcome(result.error or "", messages, state, ok=False)

        if not result.is_usable:
            if budget.take_empty_retry():
                messages.append(reflexion.empty_response_note())
                continue
            budget.halt(BudgetStop.EMPTY_RESPONSES)
            _publish_budget_stop(deps, budget, state)
            return _outcome(final_text, messages, state)

        messages.append(Message("assistant", result.text, tool_calls=result.tool_calls))

        if not result.tool_calls:
            final_text = result.text
            if (
                not plan_mode
                and execution.requires_tool_evidence
                and not _tool_evidence_satisfied(execution, state)
            ):
                if state.evidence_reprompts < execution.max_evidence_reprompts:
                    state.evidence_reprompts += 1
                    messages.append(
                        reflexion.tool_evidence_required_note(execution.required_effect)
                    )
                    continue
                return _outcome(
                    reflexion.unverified_action_message(execution.required_effect),
                    messages,
                    state,
                    ok=False,
                )
            if _should_auto_continue(
                final_text,
                deps,
                state,
                plan_mode=plan_mode,
                execution=execution,
                truncated=result.truncated,
            ):
                messages.append(reflexion.auto_continue_note())
                continue
            return _outcome(final_text, messages, state)

        if (
            execution.max_tool_rounds is not None
            and state.tool_rounds >= execution.max_tool_rounds
        ):
            return _halt(final_text, messages, state, budget, BudgetStop.TOOL_ROUNDS, deps)

        before = _progress_marker(deps, state)
        errored = await _run_tools(
            result.tool_calls, messages, deps, registry, state, execution=execution
        )
        budget.record_round(progressed=_progress_marker(deps, state) != before)
        if state.tool_contract_abort:
            budget.halt(BudgetStop.REPEATED_CALL)
            _publish_budget_stop(deps, budget, state)
            return _outcome(state.tool_contract_abort, messages, state, ok=False)
        if budget.idle:
            return _halt(final_text, messages, state, budget, BudgetStop.NO_PROGRESS, deps)
        if errored and deps.config.runtime.reflexion and not plan_mode:
            messages.append(reflexion.note(persistent=False))


def _progress_marker(deps: AgentDeps, state: _State) -> tuple[int, int]:
    """Turun ilerleyip ilerlemediğini ölçen iki sayı.

    Başarılı araç sayısı VE dokunulan dosya sayısı birlikte bakılır: bir tur yalnızca
    okuma yapmış olabilir (dosya sayısı artmaz ama iş yapılmıştır) ya da yalnızca
    yazma (ikisi de artar). İkisi de sabit kaldıysa o turda hiçbir şey olmamıştır.
    """
    return state.tool_calls_made, len(deps.tool_context.touched)


def _halt(
    final_text: str,
    messages: list[Message],
    state: _State,
    budget: TurnBudget,
    reason: BudgetStop,
    deps: AgentDeps,
) -> AgentOutcome:
    """Bütçe sebebiyle turu bitir, sebebini YAYINLA ve sonucu döndür.

    `ok=False`: bütçeyle kesilen bir tur tamamlanmış sayılmaz. Ders çıkarımı ve
    öz-denetim bu bayrağa bakar; kesilen turu başarı gibi öğrenmek zararlıdır.
    """
    budget.halt(reason)
    _publish_budget_stop(deps, budget, state)
    text = final_text.strip()
    return _outcome(text, messages, state, hit_step_limit=True, ok=False)


def _publish_budget_stop(deps: AgentDeps, budget: TurnBudget, state: _State) -> None:
    if budget.stop is None:
        return
    deps.publisher.publish(
        TurnBudgetExhausted(
            reason=budget.stop.value,
            model_calls=budget.model_calls,
            tool_rounds=state.tool_rounds,
            idle_rounds=budget.idle_rounds,
            elapsed_s=budget.elapsed_s,
        )
    )


def _outcome(
    final_text: str,
    messages: list[Message],
    state: _State,
    *,
    hit_step_limit: bool = False,
    ok: bool = True,
) -> AgentOutcome:
    return AgentOutcome(
        final_text=final_text,
        messages=messages,
        tool_calls_made=state.tool_calls_made,
        hit_step_limit=hit_step_limit,
        ok=ok,
        mutating_tool_calls_made=state.mutating_tool_calls_made,
        failed_tool_calls=state.failed_tool_calls,
        model_calls_made=state.model_calls_made,
    )


def _tool_evidence_satisfied(execution: ExecutionPolicy, state: _State) -> bool:
    """Gerçek eylem isteği başarılı bir araç sonucu ile kanıtlandı mı?"""

    effect = execution.required_effect
    if effect is None:
        return True
    evidence = state.successful_tool_evidence
    if effect == "git_push":
        return any(
            name == "run_shell" and _shell_contains_git_action(args, "push")
            for name, args, _ in evidence
        )
    if effect == "git_commit":
        return any(
            name == "run_shell" and _shell_contains_git_action(args, "commit")
            for name, args, _ in evidence
        )
    if effect == "shell_action":
        return any(name == "run_shell" for name, _, _ in evidence)
    if effect == "workspace_mutation":
        return any(mutating for _, _, mutating in evidence)
    if effect == "web_lookup":
        return any(
            name in {"web_search", "web_fetch", "read_url_content"}
            for name, _, _ in evidence
        )
    if effect == "workspace_read":
        return any(
            name
            in {
                "read_file",
                "view_file",
                "list_dir",
                "search_code",
                "grep_search",
                "search_codebase",
                "glob",
                "git",
            }
            for name, _, _ in evidence
        )
    return bool(evidence)


def _shell_contains_git_action(args: dict[str, object], action: str) -> bool:
    command = args.get("command")
    if not isinstance(command, str):
        return False
    # Yalnızca gerçek bir komut segmentindeki git çağrısını kabul et.
    # `echo git push` gibi yalnızca metin basan komutlar kanıt sayılmaz;
    # `cd repo && git -C . push`, `sudo git push` ve `env X=1 git push` sayılır.
    pattern = (
        rf"(?:^|(?:&&|\|\||;|\n)\s*)"
        rf"(?:(?:sudo|command)\s+)?"
        rf"(?:env(?:\s+[A-Za-z_][A-Za-z0-9_]*=[^\s;&|]+)+\s+)?"
        rf"git\b(?:(?![;&|\n]).){{0,180}}\b{re.escape(action)}\b"
    )
    return bool(re.search(pattern, command, re.IGNORECASE))


async def _call_model(
    messages: list[Message],
    deps: AgentDeps,
    registry: ToolRegistry,
    allowed_tools: set[str] | None = None,
    *,
    execution: ExecutionPolicy,
    offer_tools: bool = True,
    timeout_s: float | None = None,
) -> ModelResult:
    """Modeli akıtarak çağır; metin parçaları olay olarak yayınlanır."""
    runtime = deps.config.runtime
    spec = select_agent_spec(deps.config, deps.task_type)
    request = CompletionRequest(
        messages=tuple(messages),
        temperature=runtime.temperature,
        max_tokens=runtime.max_tokens,
        timeout_s=timeout_s or runtime.request_timeout_s,
        max_retries=runtime.max_retries,
        tools=(
            tuple(registry.schemas(_permitted(allowed_tools, registry, execution)))
            if offer_tools
            else ()
        ),
        reasoning_effort=effort_for_spec(spec, runtime.reasoning_effort),
    )
    provider = build_provider(
        spec,
        publisher=deps.publisher,
        retry_delays_s=runtime.retry_delays_s,
        channel=deps.channel,
        health=deps.health,
        web_sessions=web_registry_for(deps.config),
    )

    result: ModelResult | None = None
    async for item in provider.stream(request):
        if isinstance(item, StreamDone):
            result = item.result
    return result or ModelResult(
        name=spec.name,
        model=spec.model,
        text="",
        latency_ms=0,
        ok=False,
        error="Model akışı sonuç üretmeden bitti.",
    )


#: Araç kısıtlaması olsa bile daima sunulan araçlar. Bunlar olmadan agent planlayamaz
#: ya da belirsizliği gideremez.
ALWAYS_ALLOWED = frozenset({"todo_write", "ask_user", "find_skill", "read_skill"})


def _permitted(
    allowed_tools: set[str] | None,
    registry: ToolRegistry,
    execution: ExecutionPolicy,
) -> set[str] | None:
    """Modele sunulacak araç adlarını belirle.

    Mutation izni yoksa değiştirici araçların ŞEMASI hiç gönderilmez: modele
    yapamayacağı bir yeteneği göstermek, denemesine ve turu boşa harcamasına yol açar.
    """
    names = set(registry.names()) if allowed_tools is None else (
        (allowed_tools | ALWAYS_ALLOWED) & set(registry.names())
    )
    if not execution.allow_mutation:
        names = {
            name
            for name in names
            if not (registry.get(name) is not None and registry.get(name).mutating)  # type: ignore[union-attr]
        }
    return names


def _should_auto_continue(
    final_text: str,
    deps: AgentDeps,
    state: _State,
    *,
    plan_mode: bool,
    execution: ExecutionPolicy,
    truncated: bool,
) -> bool:
    if plan_mode:
        return False
    # Gerçek çıktı bütçesi dolduysa sağlayıcıdan bağımsız olarak bir kez devam et.
    if truncated:
        wanted = True
    elif not execution.heuristic_auto_continue:
        # Web modellerinde kısa ama geçerli ".env / README" gibi cevaplar eski
        # sezgisel tarafından yarım sanılıyordu. Bekleyen todo yoksa ek çağrı açma.
        wanted = deps.tool_context.todos.has_pending
    else:
        wanted = reflexion.looks_unfinished(
            final_text,
            tool_calls_last_turn=state.tool_calls_last_turn,
            has_pending_todos=deps.tool_context.todos.has_pending,
        )
    # Hak yalnızca GERÇEKTEN devam edilecekse harcanır; sırayı tersine çevirmek
    # devam etmeyen turlarda da bütçe yakardı.
    return wanted and deps.require_budget().take_auto_continue()


# --------------------------------------------------------------------------- #
# Araç yürütme
# --------------------------------------------------------------------------- #


async def _run_tools(
    calls: tuple[ToolCall, ...],
    messages: list[Message],
    deps: AgentDeps,
    registry: ToolRegistry,
    state: _State,
    *,
    execution: ExecutionPolicy,
) -> bool:
    """Çalıştırmadan ÖNCE doğrula; bozuk ve tekrar eden çağrı zincirini kes.

    Sıra önemlidir: sözleşme ihlali (bozuk JSON, bilinmeyen araç, eksik alan) araç
    hiç çalışmadan yakalanır ve modele düzeltme şansı verilir. İkinci kez aynı hata
    gelirse tur sonlandırılır — düzeltemeyen bir model sonsuza kadar denemez.
    """
    state.tool_calls_last_turn = len(calls)
    state.tool_rounds += 1
    errored = False

    budget = deps.require_budget()
    for call in calls:
        args, parse_error = _parse_arguments_checked(call.arguments)
        tool = registry.get(call.name)
        # İmza TUR BOYUNCA paylaşılır: düzeltici turun ana turdaki çağrıyı birebir
        # tekrar etmesi, her tura ayrı ayrı bakıldığında görünmeyen bir döngüdür.
        signature = budget.signature(
            call.name,
            _encode_arguments(args),
            mutating=tool is not None and tool.mutating,
        )
        seen = budget.count_call(signature)

        contract_errors: list[str] = []
        if parse_error:
            contract_errors.append(parse_error)
        if tool is None:
            contract_errors.append(
                "bilinmeyen araç; kullanılabilir araçlar: " + ", ".join(registry.names())
            )
        else:
            function_schema = tool.schema().get("function")
            if isinstance(function_schema, dict):
                contract_errors.extend(validate_arguments(function_schema, args))

        if contract_errors:
            # Aynı bozuk çağrı ikinci kez geldiyse onarım hakkı harcanmaz: model
            # düzeltmiyor, tekrarlıyor.
            no_more_repairs = seen >= 1 or not budget.take_contract_repair()
            output = _tool_contract_failure(
                call.name,
                contract_errors,
                tool.schema().get("function") if tool is not None else None,
            )
            outcome = ToolOutcome.BLOCKED if no_more_repairs else ToolOutcome.FAILED
            deps.publisher.publish(
                ToolExecuted(
                    name=call.name,
                    args=args,
                    outcome=outcome,
                    output=output,
                    diff=None,
                )
            )
            messages.append(
                Message("tool", output, tool_call_id=call.id, name=call.name, ok=False)
            )
            state.failed_tool_calls += 1
            errored = True
            if no_more_repairs:
                state.tool_contract_abort = _tool_contract_abort_message(output)
            continue

        # Değiştirici araçta tek tekrar bile döngüdür: aynı yazma iki kez istenmez.
        # Okuma araçlarında çalışma alanı değişmediği sürece birkaç tekrara izin verilir.
        duplicate_limit = (
            1
            if tool is not None and tool.mutating
            else execution.max_same_tool_without_change
        )
        # Kapı artık TÜM sağlayıcılarda açık. Eskiden yalnızca web modelleri
        # denetleniyordu; API modelleri aynı çağrıyı sınırsız tekrar edebiliyordu.
        if seen >= duplicate_limit:
            output = (
                "TOOL_CALL_DUPLICATE: Aynı araç aynı argümanlarla, çalışma alanında "
                "ilgili bir değişiklik olmadan tekrarlandı. Fusion çağrıyı çalıştırmadı "
                "ve döngüyü güvenli biçimde sonlandırdı."
            )
            deps.publisher.publish(
                ToolExecuted(
                    name=call.name,
                    args=args,
                    outcome=ToolOutcome.BLOCKED,
                    output=output,
                    diff=None,
                )
            )
            messages.append(
                Message("tool", output, tool_call_id=call.id, name=call.name, ok=False)
            )
            state.failed_tool_calls += 1
            state.tool_contract_abort = _tool_contract_abort_message(output)
            errored = True
            continue

        pending_diff = file_diff(call.name, args, deps.tool_context)
        result, outcome = await _execute(call, args, deps, registry, execution=execution)
        if outcome is ToolOutcome.OK:
            state.tool_calls_made += 1
            mutating = bool(tool is not None and tool.mutating)
            state.successful_tool_evidence.append((call.name, args, mutating))
            if mutating:
                state.mutating_tool_calls_made += 1
                budget.record_mutation()
        elif outcome is ToolOutcome.FAILED:
            state.failed_tool_calls += 1
            errored = True

        diff = pending_diff if outcome is ToolOutcome.OK else None
        deps.publisher.publish(
            ToolExecuted(
                name=call.name,
                args=args,
                outcome=outcome,
                output=result.output,
                diff=diff,
            )
        )
        messages.append(
            Message(
                "tool",
                result.output,
                tool_call_id=call.id,
                name=call.name,
                ok=result.ok,
            )
        )
    return errored


def _encode_arguments(args: dict[str, object]) -> str:
    """Argümanları tekrar tespiti için KARARLI bir metne çevir.

    Anahtar sırası sabitlenir: aynı çağrının farklı sırayla gelmesi onu yeni bir
    çağrı yapmaz. Serileştirilemeyen bir değer varsa `repr` yeterlidir — burada
    amaç eşitlik karşılaştırması, yeniden üretilebilir bir kayıt değil.
    """
    try:
        return json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return repr(args)


async def _execute(
    call: ToolCall,
    args: dict[str, object],
    deps: AgentDeps,
    registry: ToolRegistry,
    *,
    execution: ExecutionPolicy,
) -> tuple[ToolResult, ToolOutcome]:
    """Onaydan geçir ve çalıştır. Bilinmeyen araç da kayıt defterinin sorunu."""
    tool = registry.get(call.name)
    if tool is not None and tool.mutating and not execution.allow_mutation:
        # Yetenek kapısı onaydan ÖNCE gelir: kullanıcıya sormanın anlamı yok, bu
        # model bu işi güvenilir yapamıyor. Şema hiç sunulmadığı için buraya normalde
        # gelinmez; ikinci savunma hattıdır.
        return (
            ToolResult(MUTATION_BLOCKED_MESSAGE.format(reason=execution.mutation_block_reason)),
            ToolOutcome.BLOCKED,
        )
    if tool is not None and tool.mutating:
        decision = await deps.policy.decide(build_request(tool, args, deps.allowed_commands))
        if decision is not Decision.ALLOW:
            # Reddetme ve engelleme HATA DEĞİLDİR: refleksiyon tetiklenmemeli,
            # model yalnızca farklı bir yol denemeli.
            return ToolResult(_DECISION_MESSAGES[decision]), _DECISION_OUTCOMES[decision]

    result = await registry.execute(call.name, args, deps.tool_context)
    return result, ToolOutcome.OK if result.ok else ToolOutcome.FAILED


def _parse_arguments_checked(raw: str) -> tuple[dict[str, object], str | None]:
    """Ham argümanları ayrıştır; bozuk JSON kanıtını SİLMEDEN.

    Hatayı yutup boş sözlük döndürmek, modele "argümanların boştu" demek olurdu;
    oysa sorun JSON'un kendisidir ve model bunu bilmeden düzeltemez.
    """
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        return {}, f"arguments geçerli JSON olmalı ({error})"
    if not isinstance(parsed, dict):
        return {}, "arguments bir JSON nesnesi olmalı"
    return parsed, None


def _is_tool_contract_error(detail: str | None) -> bool:
    return bool(detail and detail.startswith("TOOL_CALL_"))


def _tool_contract_failure(
    name: str,
    errors: list[str],
    function_schema: object,
) -> str:
    lines = ["TOOL_CALL_INVALID", f"tool: {name}", "errors:"]
    lines.extend(f"- {error}" for error in errors)
    if isinstance(function_schema, dict):
        lines.append("valid_example:")
        lines.append(render_tool_example(function_schema))
    return "\n".join(lines)


def _tool_contract_abort_message(detail: str) -> str:
    return (
        "TOOL_CALL_ABORTED: Araç sözleşmesi düzeltilemedi veya aynı çağrı tekrarlandı. "
        "Fusion güvenlik için bu turu sonlandırdı; işlem tamamlanmış kabul edilmemelidir.\n"
        + detail
    )


# --------------------------------------------------------------------------- #
# Öz-denetim ve sıkıştırma
# --------------------------------------------------------------------------- #


def _web_self_review_needed(
    task: str, kind: TaskKind, outcome: AgentOutcome, deps: AgentDeps
) -> bool:
    """Run Web-AI review only when it can improve a valid model answer.

    Provider/authentication/timeout failures are transport failures, not answer-quality
    problems. Sending them to the same model for review hides the real error and creates
    two extra browser calls. Tool failures remain reviewable after the model produces a
    usable final answer.
    """
    if not outcome.ok:
        return False
    if outcome.hit_step_limit or outcome.failed_tool_calls > 0:
        return True
    if outcome.mutating_tool_calls_made > 0:
        return True

    lowered = task.lower()
    explicit_no_tools = any(
        marker in lowered
        for marker in (
            "araç kullanma",
            "arac kullanma",
            "tool kullanma",
            "araç çağırma",
            "arac cagirma",
        )
    )
    direct_response = bool(
        re.search(
            r"^\s*(?:sadece|yalnızca|yalnizca)\b.{0,220}\b"
            r"(?:yaz|söyle|soyle|cevapla|döndür|dondur)\b",
            lowered,
            re.DOTALL,
        )
    )
    if outcome.tool_calls_made == 0 and (explicit_no_tools or direct_response):
        return False

    if outcome.tool_calls_made == 0 and len(task.strip()) <= 160:
        risky_markers = (
            "kod", "python", "javascript", "typescript", "dosya", "proje",
            "test", "hata", "bug", "düzelt", "duzelt", "sil", "değiştir",
            "degistir", "uygula", "patch",
        )
        if not any(marker in lowered for marker in risky_markers):
            return False

    if is_complex_kind(kind):
        return True
    # Güvenlik kipinde kullanıcı her değişikliği tek tek onaylamıştır; araç çalışan
    # bir turu denetimsiz bırakmak o kipin amacına aykırı olurdu.
    return isinstance(deps.policy, SecurityApproval) and outcome.tool_calls_made > 0


async def _self_review(task: str, outcome: AgentOutcome, deps: AgentDeps) -> AgentOutcome:
    deps.publisher.publish(SelfReviewStarted())
    feedback = await review.review_turn(
        task, outcome.final_text, outcome.messages, config=deps.config, publisher=deps.publisher
    )
    deps.publisher.publish(SelfReviewFinished(issue_found=bool(feedback)))
    if not feedback:
        return outcome

    correction = await run_agent(
        "Bir öz-denetim aşağıdaki sorunu işaret etti. Gerekiyorsa düzelt; haklı değilse "
        f"kısaca neden sorun olmadığını açıkla.\n\n{feedback}",
        deps,
        history=outcome.messages,
        self_review=False,
        # Kapı bu turda çalışmaz: dış döngü zaten doğrulayacak. Aksi halde iç içe
        # doğrulama olur ve MAX_VERIFY_ROUNDS sessizce ikiye katlanır.
        verify=False,
    )
    correction.tool_calls_made += outcome.tool_calls_made
    correction.mutating_tool_calls_made += outcome.mutating_tool_calls_made
    correction.failed_tool_calls += outcome.failed_tool_calls
    correction.model_calls_made += outcome.model_calls_made
    return correction


def _recall_skill(kind: TaskKind, deps: AgentDeps, *, depth: int) -> str:
    """Görev türüne uyan uzmanlık talimatını promta ekle.

    Modelin `find_skill` çağırmasını beklemek yerine dersler gibi OTOMATİK enjekte
    edilir; ölçüldü ki prompta duyuru koymak 3 koşunun yalnızca 1'inde işe yarıyor.

    Yalnızca ana turda: alt-ajanlar zaten dar bir göreve odaklıdır ve kendi
    talimatlarını taşır.
    """
    if depth > 0:
        return ""
    # İkisi farklı işe yarar ve birlikte verilir: fusion referansı NASIL inşa
    # edileceğini somut ölçeklerle söyler, kullanıcının skill'i hangi YÖNÜN
    # seçileceğini anlatır.
    parcalar = [skill_recall.reference_block(kind)]
    if deps.capabilities is not None:
        parcalar.append(
            skill_recall.as_prompt_block(
                skill_recall.select_skill(deps.capabilities.skills(), kind)
            )
        )
    return "\n\n".join(parca for parca in parcalar if parca)


async def _verify(
    outcome: AgentOutcome, deps: AgentDeps, *, plan_mode: bool, depth: int
) -> VerificationResult | None:
    """Doğrulama kapısını çalıştır.

    Sonuç iki yere birden gider: modele düzeltme talimatı ve ders güvenine sinyal.
    İki kez çalıştırmak hem israf hem de iki farklı cevap alma riskidir.

    İş yapılmadıysa (araç çağrısı yok) kapı anlamsızdır; plan modunda ise hiçbir şey
    değişmediği için hiç çalışmaz.
    """
    if deps.verifier is None or plan_mode or depth > 0:
        return None
    if outcome.tool_calls_made == 0:
        return None
    return await deps.verifier.verify()


async def _fix_findings(
    verification: VerificationResult, outcome: AgentOutcome, deps: AgentDeps
) -> AgentOutcome:
    """Somut bulguları modele düzeltme talimatı olarak ver ve TEK düzeltici tur aç.

    Model çağrısı EKLEMEZ (talimat deterministik üretilir) ama düzeltici turun kendisi
    bir tur maliyetindedir. Öz-denetimdeki disiplinin aynısı: ikinci bir kapı turu yok,
    sonsuz düzeltme döngüsü yok.
    """
    deps.publisher.publish(
        VerificationFailed(summary=verification.summary, findings=verification.findings)
    )
    # Bulgu yoksa özet tek başına talimat olur: elde bundan fazlası yok, ama
    # "doğrulama düştü" bilgisi bile modele hiçbir şey söylememekten iyidir.
    ayrintilar = verification.findings or ((verification.summary,) if verification.summary else ())
    bulgular = "\n".join(f"- {finding}" for finding in ayrintilar)
    correction = await run_agent(
        "Doğrulama kapısı üretilen çıktıda şu somut sorunları buldu. Hepsini düzelt; "
        "düzeltemeyeceğin varsa nedenini tek cümleyle yaz.\n\n"
        f"{bulgular}",
        deps,
        history=outcome.messages,
        self_review=False,
        # Kapı düzeltici turda TEKRAR çalışmaz: sonsuz düzeltme döngüsü yok.
        verify=False,
    )
    correction.tool_calls_made += outcome.tool_calls_made
    correction.mutating_tool_calls_made += outcome.mutating_tool_calls_made
    correction.failed_tool_calls += outcome.failed_tool_calls
    correction.model_calls_made += outcome.model_calls_made
    return correction


async def _maybe_compress(messages: list[Message], deps: AgentDeps) -> list[Message]:
    before = len(messages)
    compressed = await compaction.compress(messages, config=deps.config, publisher=deps.publisher)
    if len(compressed) < before:
        deps.publisher.publish(ContextCompressed(before=before, after=len(compressed)))
    return compressed


def _initial_messages(
    task: str, history: list[Message] | None, *, plan_mode: bool, extra_system: str
) -> list[Message]:
    system = SYSTEM_PROMPT
    if plan_mode:
        system += f"\n\n{PLAN_MODE_PROMPT}"
    if extra_system:
        system += f"\n\n{extra_system}"
    return [Message("system", system), *(history or []), Message("user", task)]
