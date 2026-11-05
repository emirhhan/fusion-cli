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
import hashlib
import json
import re
import sys
from collections.abc import Awaitable, Callable, Collection, Sequence
from contextlib import AbstractAsyncContextManager, nullcontext, suppress
from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from functools import partial
from pathlib import Path

from ...config.eligibility import effort_for_spec
from ...config.model_lookup import configured_model_specs
from ...config.model_select import escalated_spec, select_agent_spec
from ...config.models import Config
from ...config.permission_rules import PermissionDecision, PermissionRuleSet
from ...config.tool_policy import mutation_policy_for_model
from ...core import display_filter
from ...core.active_context import ActiveContext
from ...core.agent_runtime_state import AgentTranscriptCapture
from ...core.budget import BudgetStop, TurnBudget
from ...core.checkpoint import CheckpointStore
from ...core.claude_chrome_names import CLAUDE_CHROME_SCOPED
from ...core.clock import SystemClock
from ...core.concurrency import BackgroundTasks
from ...core.constants import (
    CAPABILITY_WALL_PREFIX,
    FILE_MISSING_PREFIX,
    TOOL_CALL_BLOCKED_PREFIX,
    UNREACHABLE_RESOURCE_PREFIX,
)
from ...core.effects import EffectRecorder
from ...core.errors import CleanupFailedError, ConfigError, FusionError
from ...core.event_scope import TurnPublisher, new_trace_id
from ...core.events import (
    ApprenticeHandoff,
    ChangesDigested,
    Channel,
    ContextCompressed,
    ErrorOccurred,
    EventPublisher,
    ExecutionRouteSelected,
    GateEscalated,
    GateEscalationFinished,
    MutationUnavailable,
    NarrationPublished,
    NestedInstructionsLoaded,
    RepoMapBuilt,
    SelfReviewFinished,
    SelfReviewStarted,
    SkillLoaded,
    StatusChanged,
    ToolCallRepaired,
    ToolExecuted,
    ToolOutcome,
    ToolOutputsMasked,
    ToolProfileExpanded,
    ToolStarted,
    ToolSurfaceOffered,
    TurnAnswered,
    TurnBudgetExhausted,
    TurnUsageObserved,
    VerificationFailed,
    VerificationPassed,
)
from ...core.evidence import EvidenceEnvironment, ToolUse
from ...core.execution_plan import PlanStep
from ...core.health import HealthRegistry
from ...core.job_evidence import JobCompletion, JobCurrentSnapshot
from ...core.leak_filter import strip_harness_leaks
from ...core.lesson_runtime import LessonRuntimeContext
from ...core.memory import CodeIndex, Lesson, LessonMemory, SkillProposalMemory
from ...core.progress import RoundSignals, progressed
from ...core.proposal_invocation import ProposalPolicy
from ...core.protocols import Clock, TurnJournal
from ...core.reasoning import ReasoningEffort
from ...core.redaction import redact
from ...core.refusal import looks_like_refusal
from ...core.skill_context import SkillSelection
from ...core.steering import SteeringQueue
from ...core.tools import (
    TodoItem,
    Tool,
    ToolContext,
    ToolEffect,
    ToolFamily,
    ToolResult,
    tool_family,
)
from ...core.turn_deadline import TurnDeadline
from ...core.types import (
    CompletionRequest,
    Message,
    ModelResult,
    ModelSpec,
    ParseWarning,
    StreamDone,
    TextChunk,
    ToolCall,
    is_permanent_error,
    is_rate_limit_error,
)
from ...core.verification import VerificationResult, Verifier
from ...core.web_provenance import WebCallContext
from ...core.web_response import classify_response
from ...core.workspace_fingerprint import WorkspaceEffect, take_fingerprint
from ...memory.plain_memory import PlainMemory
from ...providers.capabilities import (
    TaskRequirements,
    capabilities_for,
    infer_task_requirements,
)
from ...providers.context_window import input_window_tokens
from ...providers.factory import build_provider
from ...providers.fallback_plan import live_fallbacks
from ...providers.web_registry import web_registry_for
from ...tools import ToolRegistry, build_registry
from ...tools.auto_policy import is_read_only_command
from ...tools.capabilities import CapabilityRegistry, expand_tool_patterns
from ...tools.emulation import coerce_arguments, validate_arguments
from ...tools.files import resolve_path
from ...tools.mcp_background import (
    mark_main_conversation,
    settle_mcp_background_calls,
    take_mcp_background_notices,
)
from ...tools.outside_reads import reads_outside
from ...tools.permission_match import evaluate
from ...tools.preview import file_diff
from ...tools.tool_search import visible_tool_names
from ...tools.web import loopback_origins_in
from ...ui.text import strip_thinking
from ..effects.model import EffectKind
from ..effects.pull_request import disclose_unverified_pr
from ..effects.runner import maybe_run_effect_workflow
from ..hooks.session import HookSession
from . import (
    denial,
    desktop_approval,
    extra_dir_rules,
    gate_escalation,
    instructions_hook,
    learning_steps,
    lesson_attribution,
    liveness,
    localization,
    output_style,
    reflexion,
    review,
    skill_grants,
    skill_paths,
    skill_usage,
)
from .action_evidence import claimed_effects
from .agent_task_tools import is_agent_task_request
from .apprentice_handoff import apprentice_spec, teacher_for_turn
from .approval import (
    Allowance,
    ApprovalMode,
    ApprovalPolicy,
    ApprovalRequest,
    Decision,
    Denial,
    resolve_request,
)
from .attempts import InvocationBudget
from .auto_guard import AutoReviewState
from .background_notes import append_background_events
from .bare_deny import surface_denied
from .change_digest import change_digest, changed_file_versions
from .chat_mode import WORKSPACE_READ_REASON, chat_execution, chat_tool_names, observe_execution
from .child_runs import ChildRuns
from .clarify import clarification_hint, vague_fix_question
from .claude_chrome_call import claude_chrome_call
from .computer_use_hint import computer_use_off_hint
from .context_projection import OriginalCursor, compact_context, prepare_context, record_protection
from .deferred_resume import take_deferred
from .desktop_grounding import DesktopGrounding
from .edit_hooks import EDIT_TOOLS, run_post_edit_hooks
from .edit_streak import next_streak, streak_note
from .engine_tools import UserAsker, build_agent_registry
from .execution_policy import (
    ExecutionPolicy,
    policy_for,
    refresh_mutation_policy,
    uses_web_context,
)
from .execution_route import ExecutionRoute, choose_execution_route
from .expertise import (
    expertise_hint,
    is_desktop_task,
    is_game_task,
    is_remotion_task,
    is_worktree_task,
)
from .history import history_chars, needs_compression, total_chars
from .hook_batch import batch_hook
from .hook_bridge import (
    ToolNote,
    compacted_context,
    deferred_outcome,
    hook_halt_text,
    post_tool_use,
    pre_compact,
    pre_tool_use,
    tool_running,
    user_prompt_submit,
    with_system_note,
)
from .hook_display import message_display
from .hook_permission_denied import classifier_reason, permission_denied, review_mark
from .hook_services import bind_hook_services
from .hook_stop import continue_until_stop_allowed
from .instruction_layers import InstructionLoad, instruction_files_mode
from .instruction_rules import discover_rules
from .lesson_attribution import LessonTurnState
from .loop_contract import (
    _SHELL_FRAME as _SHELL_FRAME,
)
from .loop_contract import (
    CORRECTION_NOTE_PREFIX as CORRECTION_NOTE_PREFIX,
)
from .loop_contract import (
    _correction_task as _correction_task,
)
from .loop_contract import (
    _duplicate_call_message as _duplicate_call_message,
)
from .loop_contract import (
    _encode_arguments as _encode_arguments,
)
from .loop_contract import (
    _failure_signature as _failure_signature,
)
from .loop_contract import (
    _is_tool_contract_error as _is_tool_contract_error,
)
from .loop_contract import (
    _parse_arguments_checked as _parse_arguments_checked,
)
from .loop_contract import (
    _suggested_tool_schema as _suggested_tool_schema,
)
from .loop_contract import (
    _tool_contract_abort_message as _tool_contract_abort_message,
)
from .loop_contract import (
    _tool_contract_failure as _tool_contract_failure,
)
from .loop_contract import (
    _verification_correction_task as _verification_correction_task,
)
from .masking import MaskLedger, MaskView, mask_view
from .memory_tools import memory_prompt_block
from .narration import intro_paragraph, todo_transitions
from .nested_skills import discover_nested_skills
from .orchestration_tools import (
    ORCHESTRATION_KINDS,
    ORCHESTRATION_SCOPED_TOOLS,
    orchestration_task_kinds,
)
from .output_verify import OutputPathVerifier, capture_output_baselines, requested_outputs_in
from .parse_feedback import mutation_deferral, partial_repair_note
from .plan_runner import run_execution_plan
from .platform_check import ensure_limitations_disclosed, run_platform_check
from .playbook_stage import maybe_run_playbook
from .project_instructions import (
    load_all_instructions,
    load_nested_instructions,
    nested_marker,
    resolve_access_path,
)
from .prompt_manifest import PromptComponents, publish_manifest
from .questions import PendingUserQuestions
from .repair_flow import record_failure_evidence
from .repo_context import RepoMapFocus, map_budget_for, repo_map_with_stats, task_focus
from .risk_classifier import review_auto_request
from .self_knowledge import GUIDE, knowledge_block
from .skill_index import description_limit, index_budget_for, skill_index_block
from .tamper_check import collect_test_tampering
from .task_availability import hidden_task_tools
from .teacher_flow import (
    _automatic_phase_deadline,
    _notify_phase_expired,
    _phase_expired,
    prepare_teacher_plan,
    review_teacher_changes,
    settle_teacher_plan,
    teacher_is_ready,
)
from .teacher_lessons import PendingAdvice
from .teacher_plan import TeacherPlan, UnworkablePart
from .team import Persona
from .tool_constraints import prohibited_tool
from .tool_filter import is_denied_tool
from .tool_profiles import WIDENED_KIND, hidden_tools
from .tool_surface import measure_surface, narrow_to_compact_surface
from .transient import MAX_TOOL_TRANSIENT_RETRIES, is_transient_failure
from .turn_hints import date_hint, design_hint, identity_hint, preview_hint, scope_hint, store_hint
from .turn_report import (
    TurnReport,
    build_turn_report,
    summarize_evidence,
)
from .verifier_repair import observe_verifier_failures, should_repair_verifier
from .web_contract import render_answer_contract, tool_names
from .workspace_hint import find_workspace_for

_PROMPTS = Path(__file__).parent / "prompts"
SYSTEM_PROMPT = (_PROMPTS / "system.md").read_text(encoding="utf-8")
#: Sohbet kipinin kimliği. Aynı motor ve aynı tek model kullanılır; fark, Fusion'ın
#: kendiliğinden çalışma dizinini taramamasıdır. Kod kipi `SYSTEM_PROMPT` ile kalır.
CHAT_SYSTEM_PROMPT = (_PROMPTS / "system_chat.md").read_text(encoding="utf-8")
#: Yalnız araç çağırabilen API modellerine çekirdeğin ARDINDAN eklenen kapsamlı
#: çalışma ve konuşma ilkeleri. Web modellerinin bağlamı dar olduğundan onlara
#: verilmez; çekirdeğin bağlam bütçesi (`tests/test_system_prompt_diet.py`) bu
#: katmanı kapsamaz.
API_SYSTEM_PROMPT = (_PROMPTS / "system_api.md").read_text(encoding="utf-8")
PLAN_MODE_PROMPT = (_PROMPTS / "plan_mode.md").read_text(encoding="utf-8")

#: Yarım kalan turda en fazla kaç kez "devam et" enjekte edilir.
MAX_AUTO_CONTINUE = 1
#: İlerlemesiz turlar birikince kullanıcıya gösterilen durum satırı.
STALL_STATUS = "İlerleme yavaşladı; model sıradaki somut adıma yönlendirildi"
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
#: Boş yanıt hakkı bitince kullanıcıya giden açıklama (metin boşsa).
EMPTY_RESPONSES_ANSWER = (
    "Model üst üste boş yanıt verdi; bu tur sonlandırıldı ve iş tamamlanmış sayılmaz. "
    "Farklı bir model seçip yeniden deneyebilirsin."
)
#: Bozuk araç çağrısı için TÜM tur boyunca tanınan onarım hakkı.
#
# Eskiden 1'di ve 12 turluk işler için ölçülmüştü. Turlar 22 tura çıkınca bu hak
# orantısız kaldı: yirmi adımlık bir işin herhangi bir yerindeki TEK yazım hatası
# tüm turu öldürüyor ve o ana kadarki işi çöpe atıyordu (ölçüldü: dört koşunun
# biri böyle düştü).
#
# Sayı tur uzunluğuyla birlikte büyütülür, sınırsız değildir: aynı bozuk çağrıyı
# tekrarlayan model zaten `seen >= 1` kuralıyla ayrıca durdurulur ve ilerleme
# üretmeyen turları "ilerleme yok" kapısı bitirir.
MAX_TOOL_CONTRACT_REPAIRS = 4


#: Plan modunda değiştirici araç hiç çalıştırılmaz ve kullanıcıya sorulmaz.
BLOCKED_MESSAGE = "PLAN MODU: değişiklik yapılamaz. Sorma, yalnızca planı sun."
#: Görev gerçek bir etki istiyor ama model bunu yapamıyor. Kullanıcıya NE YAPACAĞINI
#: söyler: sebep + çıkış yolu. Hata mesajı eyleme dönüştürülebilir olmalıdır (RULES).
MUTATION_UNAVAILABLE_ANSWER = (
    "Bu görev dosya/sistem değişikliği gerektiriyor ama seçili model bunu yapamıyor: "
    "{reason}.\n\n"
    "Yapılacak: `fusion serve` ile paneli aç → Sağlayıcılar → ilgili web oturumu → "
    '"Araç yeteneğini ölç". Ölçüm geçerse izin açılır. Alternatif olarak `/model` ile '
    "araç yetenekli bir API modeline geç.\n\n"
    "Hiçbir değişiklik yapılmadı."
)
#: Model yetenek kapısına takıldı: okuyabilir, planlayabilir ama değiştiremez.
MUTATION_BLOCKED_MESSAGE = (
    "Bu model dosya/sistem değiştiremez ({reason}). Değişiklik önerini metin olarak "
    "yaz; uygulamayı kullanıcı ya da araç yetenekli bir model üstlenecek."
)

_DECISION_OUTCOMES = {
    Decision.DENIED: ToolOutcome.DENIED,
    Decision.BLOCKED: ToolOutcome.BLOCKED,
}


def _decision_message(
    decision: Decision, *, plan_mode: bool, request: ApprovalRequest | None = None
) -> str:
    """Reddedilen/engellenen çağrı için modele dönecek metni seç.

    `Decision.BLOCKED` İKİ ayrı sebepten gelebilir ve ikisinin metni FARKLI
    olmalıdır: plan modunda hiç sorulmaz (`BLOCKED_MESSAGE`); auto/security
    modunda ise oturum etkileşimsiz olduğu için sorulAMAMIŞTIR
    (`denial.APPROVAL_UNAVAILABLE_MESSAGE`) — tur ikisinde de sürer ama sebep
    kullanıcıya değil ortama aittir. `Decision.DENIED` ise artık YALNIZCA gerçek
    bir insan reddini taşır; o turu durdurduğu için kısa bir iz mesajı yeter
    (bkz. `loop._drive`, `denial.DENIAL_STOP_ANSWER`).
    """
    if decision is Decision.DENIED:
        return denial.DENIED_TOOL_RESULT
    if request is not None and request.pre_denied is not None and request.desktop_blocked:
        # Masaüstü engeli (ret listesi, engelli kategori, yetmeyen kademe; P-007).
        return desktop_approval.DESKTOP_BLOCKED_RESULT.format(reason=request.pre_denied)
    if request is not None and request.pre_denied is not None:
        # İzin kuralı / kök-dışı engel (P-001, P-002): plan kipinden de önce gelir.
        return denial.RULE_DENIED_TOOL_RESULT.format(reason=request.pre_denied)
    if plan_mode:
        return BLOCKED_MESSAGE
    return denial.APPROVAL_UNAVAILABLE_MESSAGE


def _new_budget(config: Config, deadline: TurnDeadline | None = None) -> TurnBudget:
    """Bir kullanıcı turu için bütçe kur.

    Eşiklerin bir kısmı yapılandırmadan, bir kısmı yukarıdaki sabitlerden gelir ve bu
    bilinçlidir: kullanıcının ayarlaması anlamlı olanlar (adım sayısı, boşta tur)
    `defaults.yaml`'dadır; "kaç kez devam et denir" gibi davranış detayları koddadır
    ve gerekçeleri sabitin yanında yazılıdır.
    """
    return TurnBudget(
        clock=deadline.clock if deadline else SystemClock(),
        total_timeout_s=deadline.remaining_s() if deadline else None,
        max_model_calls=config.runtime.agent_max_steps,
        max_cost_usd=config.runtime.agent_max_cost_usd,
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
    #: Bu turda kaç kez bağlam özetlendi (condensation).
    #
    # Sayı teşhis sinyalidir: sık özetleme, bağlamın taşmakta olduğunu söyler ve
    # devam eden turun neyin özetlendiğini bilmesi gerekir.
    condensations: int = 0
    #: Planlama çağrıları toplam model sayısına dahildir; final kapıları model değildir.
    planning_calls_made: int = 0
    final_verification_calls: int = 0
    #: Aynı çağrı bu turda ZATEN yapıldığı için engellenen çağrı sayısı.
    #:
    #: "Hiçbir şey yapmadım" ile "iş zaten yapılmıştı" farklı sonuçlardır ve
    #: sayaçlar bunları ayırt edemezse plan adımı geçilemez hâle gelir.
    already_done_calls: int = 0
    #: Turda DENENEN araç çağrıları, çalışma sırasıyla. Sayaçlar "kaç tane"
    #: sorusuna cevap verir; yükseltme kararı "hangileri, hangi sırada" bilgisini
    #: ister (bağımlılık zinciri ve araç ailesi bundan okunur).
    tool_uses: tuple[ToolUse, ...] = ()

    #: Nihai cevap akış sırasında ekrana ulaştı mı? Ulaştıysa `TurnAnswered`
    #: yayınlanmaz; aynı metin iki kez basılmaz.
    answer_streamed: bool = False
    #: İç doğrulama onarımı yapıldı; son teslimat kök isteğe göre hazırlanır.
    verification_repaired: bool = False
    #: Görevdeki dosyaların hiçbiri bulunamadı — muhtemelen yanlış çalışma dizini.
    wrong_workspace: bool = False
    #: Tur bir BÜTÇE sınırına çarparak bitti mi? Sebep ayrıca yayınlanmıştır;
    #: `final_text` modelin cevabıdır, hata metni değildir.
    budget_stopped: bool = False
    #: Bütçe durdurduysa sebebi (`BudgetStop` değeri); arayüz özet metnini kurar.
    stop_reason: str | None = None
    #: PreToolUse `defer` (`-p`) turu bitirdiyse ertelenen çağrı `{id, name, input}`.
    deferred_tool_use: dict[str, object] | None = None
    #: Tur bittiğindeki görev listesi; yarım kalan işin özetinde gösterilir.
    todos: tuple[TodoItem, ...] = ()
    #: Turda modele "ilerleme yok" uyarısı verildi mi? Ders çıkarımı bu turu atlar.
    stalled: bool = False
    #: Tur model hatasıyla bittiyse HAM hata metni. Kullanıcıya dostça mesaj gider;
    #: hatanın kalıcı mı geçici mi olduğu kararı bu ham metinden verilir.
    model_error: str | None = None
    #: Plan motoru plan ÜRETEMEDİ (bozuk JSON, iki deneme) ve hiçbir adım çalışmadı:
    #: çağıran düz ajan döngüsüne düşebilir (A3-10).
    plan_unavailable: bool = False
    #: Kapanışta zaten hesaplanan rapor; yokluğu doğrulama kanıtı uydurmaz.
    completion_report: TurnReport | None = None
    #: Plan kipinde bu turun YAZDIĞI plan dosyası (`plan_mode.record_plan`); yazılmadıysa
    #: None. Yüzeyler kabul kartını yalnız bu doluyken açar (P-025).
    plan_path: Path | None = None

    @property
    def made_no_changes(self) -> bool:
        """Tur araç çalıştırdı ama hiçbir şey değiştirmedi mi?

        Araç HİÇ çağrılmayan tur dışarıdadır: düz sohbet cevabında "değişiklik
        yapılmadı" demek gürültüdür, kimse değişiklik beklemiyordu.
        """
        return self.tool_calls_made > 0 and self.mutating_tool_calls_made == 0


@dataclass(slots=True)
class AgentDeps:
    """Motorun dış bağımlılıkları. Testte tamamı sahteyle verilebilir."""

    def __post_init__(self) -> None:
        """Varsayılan kayıt defterini güvenilir çalışma zamanı ayarından kur."""
        if self.base_registry is None:
            from ...tools.symbol_query import SymbolQuerySettings

            server = self.config.runtime.lsp_server
            self.base_registry = build_registry(
                symbol_query_enabled=self.config.runtime.symbol_query_enabled,
                symbol_query_settings=SymbolQuerySettings(server.command, server.timeout_s),
            )
        self.tool_context.localization.enabled = self.config.runtime.localization_cards

    config: Config
    publisher: EventPublisher
    policy: ApprovalPolicy
    tool_context: ToolContext
    #: Yerleşik araçlar. Motora bağlı araçlar çalışma anında bunun kopyasına eklenir.
    base_registry: ToolRegistry | None = None
    #: Kullanıcıya soru sorabilen taraf. Yoksa `ask_user` aracı hiç sunulmaz.
    asker: UserAsker | None = None
    #: Anlamsal kod araması. Yoksa `search_codebase` aracı hiç sunulmaz.
    code_index: CodeIndex | None = None
    #: Öğrenilen dersler. Yoksa hatırlama ve ders çıkarımı atlanır.
    lessons: LessonMemory | None = None
    #: Skill/agent kütüphanesi. Yoksa arama ve devretme araçları hiç sunulmaz.
    capabilities: CapabilityRegistry | None = None
    #: Düz metin otomatik bellek (P-036). Yoksa `remember`/`memory_read` sunulmaz, blok eklenmez.
    plain_memory: PlainMemory | None = None
    #: Derslerin sahibi ajan (P-055): kendi belleği olan alt ajanda adı; çıkarılan dersler
    #: `ajan:<ad>` etiketi alır ve yalnız o ajan geri çağırır. Boş = ortak ders havuzu.
    lesson_owner: str = ""
    #: Ajan tanımındaki `experimental.cacheTtl` (`5m`/`1h`); boşsa önbellek işareti yok (#23).
    prompt_cache_ttl: str = ""
    #: Geçmiş kaynaklarının aranacağı ev dizini. Yoksa `read_session` aracı hiç sunulmaz.
    home: Path | None = None
    #: Kullanıcının `.claude/settings.local.json` içinde onaysız izin verdiği komutlar.
    allowed_commands: frozenset[str] = frozenset()
    #: `--disallowed-tools` (P-026): bu araçlar modele HİÇ sunulmaz, çağrılırsa `BLOCKED`.
    #: Salt-okunur araçları da kapsar; onay politikası yalnız değiştiricilere bakar.
    denied_tools: frozenset[str] = frozenset()
    # Parsed only from the original root request; replans cannot erase this cap.
    turn_forbidden_families: frozenset[ToolFamily] = frozenset()
    #: Tüm katmanlardan okunmuş izin kuralları (allow/ask/deny) ve kök-dışı engeller (P-001).
    #: `None` = kural yok (eski çağıranlar); `getattr(deps, "permission_rules", None)` ile okunur.
    permission_rules: PermissionRuleSet | None = None
    #: Oturumun kancaları (P-009, `engines/hooks`); `None` = kanca yok (eski çağıranlar).
    hooks: HookSession | None = None
    session_persona: Persona | None = None
    main_metadata_applied: bool = False
    definition_base_hooks: HookSession | None = None
    allowed_agent_types: tuple[str, ...] | None = None
    runtime_parent_session: str = ""
    runtime_agent_id: str = ""
    omit_git_snapshot: bool = False
    runtime_tool_cap: frozenset[str] | None = None
    agent_transcript: AgentTranscriptCapture | None = None
    interactive: bool = False
    main_config_applied: bool = False
    mcp_connector: Callable[[Config, ToolRegistry], AbstractAsyncContextManager[None]] | None = None
    #: Alt ajanın türü (tanım adı); `SubagentStop` eşleştiricisi buna bakar.
    agent_type: str = ""
    #: Keşif/plan ilk bağlamında proje talimatı yok; dosya erişimindeki kurallar sürer.
    omit_initial_instructions: bool = False
    #: Olağan alt ajan ana oturumun otomatik belleğini yüklemez; fork korur.
    include_external_memory: bool = True
    #: Otomatik kip denetçisinin oturum durumu (P-011; `ApprovalMemory.auto_review`). `None` =
    #: denetçi yok (eski çağıranlar, alt ajanlar); `getattr(deps, "auto_review", None)` ile okunur.
    auto_review: AutoReviewState | None = None
    #: Verilirse ders çıkarımı turu BEKLETMEDEN arka planda çalışır (REPL için).
    #: Verilmezse tur içinde beklenir (tek seferlik CLI için doğru davranış).
    background: BackgroundTasks | None = None
    channel: Channel = Channel.MAIN
    #: Bu turda kaç kez bağlam özetlendi; plan yürütücüsü checkpoint'e taşır.
    condensations: int = 0
    #: Sağlayıcının "bağlam penceresi aşıldı" hatasından öğrenilen sıkıştırma eşiği
    #: (karakter). Yapılandırılmış eşikten küçükse o kullanılır (A1-04).
    learned_compression_chars: int | None = None
    #: Kayan pencere maskeleme defteri (bkz. `masking`): bir kez maskelenen sonuç eski
    #: haline dönmez, önek kararlı kalır. Tur başına kurulur.
    mask_ledger: MaskLedger = field(default_factory=MaskLedger)
    #: Kullanıcının koşan işe ilettiği yönergeler; her alt turdan önce boşaltılır.
    questions: PendingUserQuestions = field(default_factory=PendingUserQuestions)
    child_runs: ChildRuns = field(default_factory=ChildRuns)
    selected_skill: SkillSelection | None = None
    effect_recorder: EffectRecorder | None = None
    steering: SteeringQueue | None = None
    policy_factory: Callable[[], ApprovalPolicy] | None = None
    approval_revision: Callable[[], object] | None = None
    #: Oturumun ANLIK onay kipi ve verilen kip için politika kuran yapıcı (P-034): alt ajan
    #: tanımındaki `permissionMode` üst kipi yalnız sıkılaştırarak uygular. Verilmezse alt
    #: ajan üstün politikasını aynen alır (eski davranış).
    approval_mode: Callable[[], ApprovalMode] | None = None
    policy_for_mode: Callable[[ApprovalMode], ApprovalPolicy] | None = None
    #: Bu turun ANLIK mesaj listesini veren okuyucu (P-054): fork alt ajan ana bağlamı
    #: buradan devralır. `_run_agent` mesajları kurduktan sonra atar; alt ajanın kendi
    #: deps'inde yeniden kurulur, üstünkini görmez.
    live_history: Callable[[], Sequence[Message]] | None = None
    ancestor_mutation_barrier: Callable[[], bool] | None = None
    #: Kullanıcının seçtiği görev tipi (`/type`). `task_model_map` üzerinden bu turda
    #: kullanılacak modeli belirler; haritada karşılığı yoksa `agent:` rolü kullanılır.
    task_type: str = "general"
    #: Verilirse kod değiştiren tur sonrası doğrulama kapısı çalışır ve sonucu ders
    #: güvenini besler. Verilmezse (varsayılan) mevcut davranış birebir korunur.
    verifier: Verifier | None = None
    #: Oturum boyunca paylaşılan sağlayıcı sağlığı (circuit breaker + güvenilirlik).
    #: Verilirse sağlıksız model turlar arası atlanır. Verilmezse breaker kurulmaz.
    health: HealthRegistry | None = None
    #: Verilirse kök turun konuşması her araç turundan sonra diske yazılır; süreç
    #: tur ortasında kapanırsa sekme kaldığı adımdan sürdürebilir. Alt ajanlar ve
    #: iç (denetim) turları yazmaz: günlük kullanıcının asıl turunu taşır.
    journal: TurnJournal | None = None
    original_cursor: OriginalCursor = field(default_factory=OriginalCursor)
    context_step: PlanStep | None = None
    active_context: ActiveContext = field(default_factory=ActiveContext)
    prompt_components: PromptComponents = field(default_factory=PromptComponents)
    #: Aynı üst görevde otomatik web öğretmene yalnız bir kez danışılır.
    auto_teacher_used: bool = False
    #: İlk plan, takılma ve son denetim aynı tur bütçesini paylaşır.
    teacher_calls_used: int = 0
    #: `council` (çok model + hakem + sentez) çağrıları da tur başına sınırlıdır (A1-25).
    council_calls_used: int = 0
    #: Öğretmen yok/bütçe dolu bildirimi bu turda bir kez gösterilir.
    teacher_unavailable_notified: bool = False
    #: Otomatik öğretmen çağrısı sürerken cevap anında ders olarak yazılmaz.
    teacher_lesson_sync_deferred: bool = False
    #: Bu turda öğretmenden alınan ve tur sonunda sonucuyla yazılacak plan.
    pending_teacher_plan: TeacherPlan | None = None
    pending_advice: list[PendingAdvice] = field(default_factory=list)
    #: Bu turda hafızadan yeniden kullanılan plan dersi.
    reused_teacher_lesson: Lesson | None = None
    #: Öğretmenin bu turda bildirdiği dış kısıtlar; cevapta anılmadıysa eklenir.
    platform_limitations: list[UnworkablePart] = field(default_factory=list)
    #: Bu turda adı geçen dış platformlar ve resmi kaynaktan doğrulanıp doğrulanmadığı.
    platform_names: tuple[str, ...] = ()
    platform_check_verified: bool = False
    #: Yalnız mevcut kullanıcı turunda geçerli model devri; açık model seçimini
    #: yapılandırma dosyasında değiştirmez.
    active_model_override: ModelSpec | None = None
    #: Modelin çağırdığı becerinin `effort` alanı: turun kalanı için (#139).
    turn_effort_override: ReasoningEffort | None = None
    #: TURUN TAMAMI için tek sayaç otoritesi. `run_agent` bunu tur başında bir kez
    #: kurar; öz-denetim ve doğrulama kapısının açtığı iç içe çağrılara AYNI nesne
    #: devredilir. `None` bırakılırsa ilk `run_agent` çağrısı kurar.
    #:
    #: Testler kendi bütçesini vererek sınırları daraltabilir.
    budget: TurnBudget | None = None
    #: Turun yürütme politikası. Bütçe gibi TUR BAŞINDA belirlenir ve iç içe
    #: çağrılara devredilir.
    #:
    #: Ölçüldü: öz-denetim/doğrulama turu politikayı DÜZELTME METNİNDEN yeniden
    #: türetiyordu. Asıl görev BUGFIX (12 araç turu) olsa bile düzeltme metni basit
    #: sohbet sanılıp 5 tura düşüyor ve iş yarıda kesiliyordu.
    execution: ExecutionPolicy | None = None
    #: Profesyonel workflow'un kesintiden sonra devam edebilmesi için kalıcı depo.
    checkpoint_store: CheckpointStore | None = None
    #: Aynı kökteki farklı sohbetlerin checkpoint'lerini birbirinden ayırır.
    conversation_id: str = ""
    attempt_id: str | None = None
    trace_id_factory: Callable[[], str] = new_trace_id
    #: İlk dış turda çıkarılan zorunlu model yetenekleri; iç turlar aynı kararı taşır.
    task_requirements: TaskRequirements | None = None
    #: Bu turda `recall_lessons` ile hatırlanan dersler. Tur sonunda güvenleri
    #: turun sonucuna göre güncellenir (`learning_steps.reinforce_recalled`).
    recalled_lessons: list[Lesson] = field(default_factory=list)

    lesson_context: LessonRuntimeContext = field(default_factory=LessonRuntimeContext)
    lesson_state: LessonTurnState | None = None
    skill_proposals: SkillProposalMemory | None = None
    clock: Clock = field(default_factory=SystemClock)
    invocation_budget: InvocationBudget | None = None
    deadline: TurnDeadline | None = None

    def mutation_blocked_by_pending_input(self) -> bool:
        """Child parent girdisini tüketmeden aynı değişiklik bariyerini görür."""
        return (
            self.questions.pending
            or self.questions.ready
            or (self.steering is not None and self.steering.pending)
            or (self.ancestor_mutation_barrier is not None and self.ancestor_mutation_barrier())
        )

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
    chat_mode: bool = False,
    extra_system: str = "",
    depth: int = 0,
    self_review: bool | None = None,
    allowed_tools: set[str] | None = None,
    step_limit: int | None = None,
    verify: bool = True,
    internal: bool = False,
    require_local_mutation: bool = False,
    system_prompt: str | None = None,
    images: tuple[str, ...] = (),
    workflow: bool = False,
    denied_tools: frozenset[str] = frozenset(),
) -> AgentOutcome:
    """Kök turun sahipli sorularını her çıkış yolunda temizle.

    Plan kipindeki kök tur bitince plan dosyaya yazılır (`plan_mode.record_plan`);
    iç turlar ve alt ajanlar plan yazmaz.
    """
    if depth == 0 and not internal:
        from . import team_settings
        from .agent_runtime_hooks import prepare_main_metadata

        prepare_main_metadata(deps)
        # Arka plana taşınan MCP çağrıları yalnız ana sohbette (#233).
        mark_main_conversation(deps.tool_context)
        if deps.session_persona is not None:
            persona = deps.session_persona
            skills = team_settings.preloaded_skills(deps, persona)
            extra_system = "\n\n".join(part for part in (extra_system, skills) if part)
            limits = [
                limit
                for limit in (step_limit, persona.max_turns, deps.config.runtime.agent_max_steps)
                if limit and limit > 0
            ]
            step_limit = min(limits) if limits else None
            if system_prompt is None and persona.prompt.strip():
                system_prompt = persona.prompt.strip()
    original_publisher = deps.publisher
    original_attempt = deps.attempt_id
    child_turn_token = None
    if depth == 0 and not internal:
        if isinstance(original_publisher, TurnPublisher):
            deps.attempt_id = deps.attempt_id or original_publisher.turn_id
        else:
            deps.attempt_id = deps.attempt_id or deps.trace_id_factory()
            deps.publisher = TurnPublisher(
                original_publisher,
                session_id=deps.conversation_id or None,
                attempt_id=deps.attempt_id,
                id_factory=deps.trace_id_factory,
            )
        child_turn_token = deps.child_runs.begin_turn(deps.attempt_id or "")
        deps.original_cursor = OriginalCursor(
            turn_id=deps.attempt_id or "",
            excluded_call_ids=frozenset(
                call.id for message in history or () for call in message.tool_calls
            ),
        )
    try:
        # Kancalar (P-009): kök turda SessionStart + UserPromptSubmit; engel istemi düşürür.
        root_turn = depth == 0 and not internal
        if root_turn:
            from .tool_constraints import forbidden_families

            deps.turn_forbidden_families = forbidden_families(task)
        owns_learning = not internal and (depth == 0 or deps.channel is Channel.SUBAGENT)
        if owns_learning:
            if deps.capabilities is not None:
                deps.capabilities = deps.capabilities.with_proposal_policy(
                    ProposalPolicy(
                        deps.config.runtime.verified_skill_proposals,
                        deps.lesson_context.policy.source_split,
                    )
                )
            if deps.config.runtime.verified_skill_proposals and deps.skill_proposals is None:
                from ...memory.skill_proposals import SkillProposalStore
                from ..capability_proposals import PROPOSAL_FILENAME

                deps.skill_proposals = SkillProposalStore(
                    deps.config.memory_dir / PROPOSAL_FILENAME
                )
            deps.lesson_state = LessonTurnState()
            deps.recalled_lessons.clear()
            hint = learning_steps.recall_hints(task, deps)
            if hint:
                extra_system = "\n\n".join(part for part in (extra_system, hint) if part)
        if root_turn:
            bind_hook_services(deps, run_agent)
        prompt_gate = await user_prompt_submit(deps, task) if root_turn else None
        if prompt_gate is not None and prompt_gate.blocked is not None:
            # Sebep burada yayınlanır; `budget_stopped` çağıranın ikinci kez basmasını önler.
            deps.publisher.publish(ErrorOccurred(prompt_gate.blocked))
            blocked = AgentOutcome(prompt_gate.blocked, [*(history or [])], ok=False)
            blocked.budget_stopped = True
            return blocked
        # Kanca bağlamı (P-009) istemle birlikte geçmişte kalır (Claude: SessionStart başta,
        # UserPromptSubmit istemin yanında); sistem mesajı her turda yeniden kurulur.
        if prompt_gate is not None and prompt_gate.task:
            task = prompt_gate.task  # SessionStart `initialUserMessage` (istemsiz `-p`)
        model_task = prompt_gate.model_prompt(task) if prompt_gate is not None else task
        turn = partial(
            _run_agent,
            deps=deps,
            plan_mode=plan_mode,
            chat_mode=chat_mode,
            extra_system=extra_system,
            depth=depth,
            self_review=self_review,
            allowed_tools=allowed_tools,
            step_limit=step_limit,
            verify=verify,
            internal=internal,
            require_local_mutation=require_local_mutation,
            system_prompt=system_prompt,
            images=images,
            workflow=workflow,
            denied_tools=denied_tools,
        )
        # MessageDisplay (#90): kök turda görünen asistan metni kancadan geçer.
        with message_display(deps) if root_turn else nullcontext():
            outcome = await turn(model_task, history=history)
            subagent = depth > 0 and not internal and deps.channel is Channel.SUBAGENT
            if root_turn or subagent:
                # Stop/SubagentStop engellerse ajan gerekçeyi yeni istem olarak alıp sürdürür.
                outcome = await continue_until_stop_allowed(
                    deps,
                    outcome,
                    lambda prompt, past: turn(prompt, history=past),
                    subagent=subagent,
                )
        if root_turn and not deps.child_runs.persistent:
            await deps.child_runs.drain()
        if owns_learning:
            await learning_steps.finish_learning(outcome, deps, plan_mode=plan_mode, task=task)
        if depth == 0 and not internal:
            # Plan yalnız `exit_plan_mode` ile sunulduysa yazılır (#317); tur içinde
            # `enter_plan_mode` ile plan kipine girilmiş olabilir (#324).
            from .plan_mode import record_plan

            written = record_plan(outcome, deps, plan_mode=plan_mode)
            if written is not None:
                outcome = replace(outcome, plan_path=written)
        if deps.agent_transcript is not None:
            await deps.agent_transcript.capture(outcome.messages)
            outcome.messages = list(deps.agent_transcript.messages)
        return outcome
    except BaseException:
        if depth == 0 and not internal:
            if deps.child_runs.persistent:
                await deps.child_runs.cancel_turn(deps.attempt_id or "")
            else:
                await deps.child_runs.close()
        raise
    finally:
        if not internal and (depth == 0 or deps.channel is Channel.SUBAGENT):
            if deps.config.runtime.lesson_attributed_feedback:
                lesson_attribution.settle(AgentOutcome("", [], ok=False), deps)
            deps.lesson_state = None
            deps.pending_advice.clear()
            deps.recalled_lessons.clear()
        if child_turn_token is not None:
            deps.child_runs.end_turn(child_turn_token)
        deps.attempt_id = original_attempt
        if depth == 0 and not internal:
            deps.publisher = original_publisher
            await deps.questions.close()


async def _run_agent(
    task: str,
    deps: AgentDeps,
    *,
    history: list[Message] | None = None,
    plan_mode: bool = False,
    chat_mode: bool = False,
    extra_system: str = "",
    depth: int = 0,
    self_review: bool | None = None,
    allowed_tools: set[str] | None = None,
    step_limit: int | None = None,
    verify: bool = True,
    internal: bool = False,
    require_local_mutation: bool = False,
    system_prompt: str | None = None,
    images: tuple[str, ...] = (),
    workflow: bool = False,
    denied_tools: frozenset[str] = frozenset(),
) -> AgentOutcome:
    """Bir görevi araçlarla çalıştır. Döndürülen geçmiş bir sonraki tura beslenir.

    `allowed_tools` verilirse modele YALNIZCA o araçlar sunulur (uzman agent'lar
    kendi araç setini bildirebilir). Boş küme tüm araçları kapatır; dolu kümede
    görev yönetimi ve soru sorma araçları ayrıca sunulur.

    `chat_mode` sohbet turudur: model okur ve cevaplar, çalışma alanını
    DEĞİŞTİRMEZ ve plan motoruna girmez (bkz. `chat_mode.py`).

    Varsayılan yol tek ReAct döngüsüdür; ne zaman araç kullanacağına ve çok
    adımlı işte `todo_write` ile plan tutacağına model karar verir. Plan motoru
    yalnız `workflow=True` (kullanıcı `/plan-yurut` seçti) ya da
    `workflow_mode: always` ile çalışır ve kök konuşmanın tamamını alır.
    """
    from .response_format import effective_response_task

    response_task = effective_response_task(task, history or ())
    if depth == 0 and not internal:
        deps.tool_context.delivery_contract.accepted = None
    # Bütçe turun EN BAŞINDA bir kez kurulur ve buradan sonra her iç içe çağrı aynı
    # nesneyi görür. Öz-denetim ve doğrulama kapısı `run_agent`'ı yeniden çağırdığı
    # için, bütçe orada kurulsaydı her düzeltici tur sıfırdan başlardı — düzeltilen
    # hata tam olarak buydu.
    if deps.budget is None:
        deps.budget = _new_budget(deps.config, deps.deadline)
    if deps.deadline is not None:
        deps.budget.constrain_remaining_s(deps.deadline.remaining_s())
        if (
            external_remaining := deps.budget.remaining_s()
        ) is not None and external_remaining <= 0:
            return _halt(
                "Dış isteğin süre sınırı doldu; yeni işlem başlatılmadı.",
                [*(history or []), Message("user", task)],
                _State(internal=internal),
                deps.budget,
                BudgetStop.DEADLINE,
                deps,
            )
    if depth == 0 and not internal:
        from .delivery_contract import accept_delivery_contract

        accept_delivery_contract(deps.tool_context, response_task)
        deps.active_model_override = None
        deps.turn_effort_override = None
        # Kullanıcının mesajında AÇIKÇA yazdığı yerel adresler tarayıcı araçlarına
        # açılır (kendi geliştirme sunucusu, Fusion'ın önizlemesi). Düzeltici iç
        # turlar ve alt ajanlar bu kümeye ekleme yapamaz.
        deps.tool_context.local_origins.update(loopback_origins_in(task))
        # İstenen çıktılar YALNIZ bu isteğe aittir; önceki isteğin yolları taşınmaz.
        deps.tool_context.requested_outputs.clear()
        deps.tool_context.requested_outputs.update(
            requested_outputs_in(task, root=deps.tool_context.root)
        )
        await asyncio.to_thread(capture_output_baselines, deps.tool_context)
        deps.tool_context.task_kinds.difference_update(
            {
                "oyun",
                "remotion",
                "masaustu",
                "worktree",
                "arka_plan",
                WIDENED_KIND,
                *ORCHESTRATION_KINDS,
            }
        )
        if is_game_task(task):
            deps.tool_context.task_kinds.add("oyun")
        if is_remotion_task(task):
            deps.tool_context.task_kinds.add("remotion")
        if is_desktop_task(task):
            deps.tool_context.task_kinds.add("masaustu")
        if is_worktree_task(task):
            deps.tool_context.task_kinds.add("worktree")
        # Plan kipi araçları (#317, #324): `exit_plan_mode` yalnız plan kipindeki turda sunulur.
        plan_switch = getattr(deps.tool_context, "plan_mode_switch", None)
        if plan_switch is not None:
            plan_switch.begin_turn(plan_mode=plan_mode)
        if plan_mode:
            deps.tool_context.task_kinds.add("plan")
        else:
            deps.tool_context.task_kinds.discard("plan")
        if is_agent_task_request(task, deps):
            deps.tool_context.task_kinds.add("arka_plan")
        deps.tool_context.task_kinds.update(orchestration_task_kinds(task, deps.tool_context.root))

    if not plan_mode and not chat_mode and depth == 0:
        played = await maybe_run_playbook(task, deps)
        if played is not None:
            return played

    deps.tool_context.localization.enabled = deps.config.runtime.localization_cards
    registry = build_agent_registry(deps, depth=depth, run_agent=run_agent)
    if depth == 0 and deps.session_persona is not None:
        from .team import SubTask
        from .team_policy import allowed_tools as persona_tools

        selected_tools = persona_tools(
            deps, deps.session_persona, SubTask(task), available=registry.names()
        )
        if selected_tools is not None:
            allowed_tools = (
                selected_tools if allowed_tools is None else allowed_tools & selected_tools
            )
    deps.runtime_tool_cap = frozenset(allowed_tools) if allowed_tools is not None else None
    if deps.task_requirements is None and depth == 0:
        deps.task_requirements = infer_task_requirements(
            task,
            has_images=bool(images),
            mutating=require_local_mutation,
        )

    # Hedefi belirsiz kısa "düzelt" isteği: model çağrılmadan netleştirme sorusu döner.
    vague_question = (
        vague_fix_question(
            task, first_turn=not any(message.role == "user" for message in history or ())
        )
        if depth == 0 and not chat_mode and not internal
        else None
    )
    if vague_question is not None:
        vague_outcome = AgentOutcome(
            final_text=vague_question,
            messages=[
                *(history or []),
                Message("user", task),
                Message("assistant", vague_question),
            ],
            ok=True,
            model_calls_made=0,
        )
        await _announce_answer(vague_outcome, deps, depth=depth, internal=internal)
        return vague_outcome

    # Gerçek dünya etkisi için deterministik handler varsa LLM ReAct döngüsünü
    # tamamen atla. Modelin "pushluyorum" demesi operasyon sonucu değildir; Git
    # workflow'u post-condition (local HEAD == remote HEAD) kanıtını kendisi üretir.
    effect_result = (
        None
        if chat_mode or deps.turn_forbidden_families
        else await maybe_run_effect_workflow(task, deps, registry, plan_mode=plan_mode, depth=depth)
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

    # Dersler ve beceri metinleri tur başında sisteme BASILMAZ; model onları
    # `recall_lessons` / `find_skill` + `read_skill` ile ister. Ölçüldü: görev
    # türüne göre seçilen uzmanlık ve dersler yanlış türde yanlış bağlamı
    # taşıyordu (WEBSITE sanılan bir turda 21 KB'lık web referansı eklendi).
    # `--bare` (P-026): betik koşusu proje talimatını ve dış bellekleri hiç okumaz.
    instruction_load = (
        load_all_instructions(
            deps.tool_context.root,
            deps.home,
            instruction_merge=getattr(deps.config.runtime, "instruction_merge", True),
            instruction_max_chars=getattr(deps.config.runtime, "instruction_max_chars", 32_000),
            include_external_memory=deps.include_external_memory,
            extra_roots=tuple(getattr(deps.tool_context, "extra_roots", ()) or ()),
        )
        if deps.config.runtime.project_instructions and not deps.omit_initial_instructions
        else InstructionLoad("")
    )
    proje_ve_dis_bellek = instruction_load.text
    # `InstructionsLoaded` kancası (#169): oturumda ilk kez yüklenen her talimat dosyası.
    instructions_hook.notify(
        getattr(deps, "hooks", None),
        instructions_hook.after_compact(
            getattr(deps, "hooks", None),
            instructions_hook.startup_events(instruction_load.files),
        ),
    )
    # Depo haritası: model doğru dosyayı aramak için tur harcamasın. Kod kipinde
    # kök turda eklenir; sohbet kipi çalışma dizinini taramaz.
    harita = _repo_map_for_turn(deps, task) if depth == 0 and not chat_mode else ""
    # Beceri dizini (P-018): ad + kısa açıklama, bütçeli; gövde yalnız read_skill ile gelir.
    beceri_dizini = (
        skill_index_block(
            deps.capabilities,
            index_budget_for(deps.config, root=deps.tool_context.root, home=deps.home),
            max_description=description_limit(deps.tool_context.root, deps.home),
            usage=skill_usage.load_counts(getattr(deps.config, "memory_dir", None)),
        )
        if depth == 0 and not internal
        else ""
    )
    from .agent_runtime_context import startup_context

    ajan_baslangici = (
        await startup_context(
            deps,
            depth=depth,
            available=tuple(
                name for name in registry.names() if allowed_tools is None or name in allowed_tools
            ),
        )
        if not internal
        else ""
    )
    deps.prompt_components = PromptComponents(instruction_load, harita, beceri_dizini)
    teacher_hint = (
        "Karmaşık çok dosyalı görevde kendi incelemenden sonra bir mimari risk veya "
        "doğrulama belirsizliği kalırsa `ask_teacher` ile tek somut soru sor. "
        "Sırları ve özel verileri öğretmene gönderme."
        if depth == 0 and not chat_mode and teacher_is_ready(deps, registry)
        else ""
    )
    # Belirsiz yeni proje isteğinde koda başlamadan seçenekli soru (bkz. `clarify`).
    netlestirme = (
        clarification_hint(
            task,
            deps.tool_context.root,
            can_ask=registry.get("ask_user") is not None,
            first_turn=not any(message.role == "user" for message in history or ()),
        )
        if depth == 0 and not chat_mode and not internal
        else None
    )
    # İsteğe özel yönlendirme: önizleme, çok büyük kapsam, siteye benzetme (bkz. `turn_hints`).
    istek_notlari = (
        (
            preview_hint(task, available=registry.get("start_preview") is not None),
            scope_hint(task),
            store_hint(task),
            design_hint(
                task,
                available=registry.get("site_design") is not None,
                clone_available=registry.get("clone_site") is not None,
            ),
            expertise_hint(task, registry=deps.capabilities, publisher=deps.publisher)
            if deps.selected_skill is None
            else None,
            computer_use_off_hint(
                task, enabled=deps.config.desktop.enabled, tool_names=registry.names()
            ),
        )
        if depth == 0 and not chat_mode and not internal
        else ()
    )
    # `--exclude-dynamic-system-prompt-sections` (#301): kişiye özgü bölümler kullanıcı mesajına.
    from . import dynamic_sections

    dinamik_disari = dynamic_sections.applies(depth=depth, system_prompt=system_prompt)
    bellek_blogu = memory_prompt_block(deps)
    messages = _initial_messages(
        task,
        history,
        plan_mode=plan_mode,
        extra_system="\n\n".join(
            part
            for part in (
                "" if dinamik_disari else harita,
                beceri_dizini,
                ajan_baslangici,
                teacher_hint,
                netlestirme,
                date_hint(deps.clock),
                f"Çalışma dizini: {deps.tool_context.root}" if depth > 0 else "",
                *istek_notlari,
                extra_system,
                # Çıktı stili (P-068) kodlama talimatlarından SONRA, en sona eklenir.
                output_style.style_prompt(deps.config, home=deps.home, root=deps.tool_context.root)
                if depth == 0
                else "",
            )
            if part
        ),
        # İç düzeltici turlar sistem metnini geçmişten miras alır; yeniden
        # hesaplanan ders/uzmanlık bloğu öneki kaydırıp sohbeti sıfırlıyordu.
        inherit_system=internal,
        # Özel çıktı stili kodlama talimatını istemiyorsa temel istem kırpılır (#215).
        system_prompt=system_prompt
        if system_prompt is not None or depth > 0
        else output_style.base_system_prompt(
            SYSTEM_PROMPT, deps.config, home=deps.home, root=deps.tool_context.root
        ),
        # Claude Code (#149): CLAUDE.md içeriği sistem isteminden SONRA kullanıcı mesajıdır.
        # Otomatik bellek (MEMORY.md başı, #153) da aynı mesajda, talimatlardan sonra.
        # `--exclude-dynamic-system-prompt-sections` (#301) kod haritasını da buraya taşır.
        project_context=(
            dynamic_sections.user_context(proje_ve_dis_bellek, bellek_blogu, harita)
            if dinamik_disari
            else dynamic_sections.user_context(proje_ve_dis_bellek, bellek_blogu)
        ),
        images=images,
    )
    if deps.agent_transcript is not None:
        await deps.agent_transcript.begin(messages)
    if not internal:
        # Kapanış `messages` ADINI bağlar: özetleme listeyi yeniden bağlasa da fork alt
        # ajan hep güncel listeyi görür (P-054).
        deps.live_history = lambda: messages

    if depth == 0 and not internal and deps.selected_skill is not None:
        selected = deps.selected_skill
        deps.publisher.publish(
            SkillLoaded(
                qualified_name=selected.qualified_name,
                revision=selected.revision,
                mode="explicit",
                next_offset=selected.next_offset,
            )
        )
    if deps.execution is None:
        try:
            selected_spec = select_agent_spec(
                deps.config, deps.task_type, requirements=deps.task_requirements
            )
        except ConfigError as error:
            # Henüz hiçbir model çağrılmadı. Normal başarısız sonuç döndürerek
            # oturumun bitiş olayı ve ekleri içeren geçmişi kaydetmesini sağla.
            messages.append(Message("assistant", str(error)))
            return AgentOutcome(final_text=str(error), messages=messages, ok=False)
        # Geçmişin tamamını birleştirme: yalnız açık devam talebi önceki
        # kullanıcı işini miras alır. Yeni soru/selam eski mutasyonu gerektirmez.
        deps.execution = policy_for(deps.config, selected_spec, task, history=history or ())
        handed = _hand_off_to_apprentice(task, selected_spec, deps, plan_mode=plan_mode)
        if handed:
            # Öğretmen bu tur eklendiyse `ask_teacher` aracı defterde olmalı.
            registry = build_agent_registry(deps, depth=depth, run_agent=run_agent)
    execution = replace(
        deps.execution,
        forbidden_tool_families=(
            deps.execution.forbidden_tool_families | deps.turn_forbidden_families
        ),
    )
    if chat_mode:
        # Sohbet turu: değiştirme kapalı, kanıt kapıları kapalı, yalnız okuyan araçlar.
        execution = chat_execution(execution)
        allowed_tools = set(chat_tool_names(registry)) if allowed_tools is None else allowed_tools
    elif (
        not plan_mode and execution.allow_mutation and execution.required_effect == "workspace_read"
    ):
        # Kod kipinde de gözlem kilidi: turun METNİ yalnızca okuma/inceleme
        # istiyorsa model o turda yazamaz. Plan modu zaten kendi onay
        # politikasıyla (`PlanApproval`) her değişikliği engeller; model gerçek
        # bir yetenek kısıtına (`allow_mutation=False`) çarpmışsa o kısıt
        # önceliklidir, buradaki gözlem gerekçesiyle EZİLMEZ.
        execution = observe_execution(execution, WORKSPACE_READ_REASON)
    deps.execution = execution
    if denied_tools:
        # Oturum kişiliğinin `disallowedTools`u (P-053): izin kümesi verilmemişse defterin
        # tamamından, verilmişse ondan düşer; `sunucu__*` deseni defter adlarına açılır.
        base = set(registry.names()) if allowed_tools is None else set(allowed_tools)
        allowed_tools = base - expand_tool_patterns(set(denied_tools), registry.names())
    if allowed_tools is not None or execution.forbidden_tool_families:
        names = frozenset(
            _permitted(
                allowed_tools,
                registry,
                execution,
                deps.tool_context.task_kinds,
                denied=surface_denied(deps, registry.names()),
                task=task,
                phase=deps.tool_context.tool_phase,
            )
            or ()
        )
        execution = replace(execution, allowed_tool_names=names)
    deps.execution = execution
    # Web taşımasında bağlam pahalıdır: uzun okuma hem gecikme hem context rot
    # üretir. SWE-agent'ın ölçümü turda ~100 satırı en iyi pencere olarak veriyor;
    # API yolunda mevcut ölçülmüş davranış (800 satır) korunur.
    if execution.is_web and deps.tool_context.read_window is None:
        deps.tool_context = replace(deps.tool_context, read_window=WEB_READ_WINDOW)
    # Kapsamlı talimat katmanı yalnız kök sistem metnine, API modelinde ve bir kez
    # eklenir. İç turlar sistem metnini geçmişten devralır (önek kaymasın); açık
    # `system_prompt` veren çağıranlar (sohbet kipi, plan adımı) kendi metnini korur.
    if (
        not execution.is_web
        and not internal
        and system_prompt is None
        and messages
        and messages[0].role == "system"
        and API_SYSTEM_PROMPT not in messages[0].content
    ):
        messages[0] = Message("system", f"{messages[0].content}\n\n{API_SYSTEM_PROMPT}")
    # Öz-bilgi katmanı TÜM modellere (yerel, API, web) bir kez eklenir: model Fusion'ın
    # ne olduğunu ve BU turda hangi araç ailelerini taşıdığını bilir.
    if (
        not internal
        and system_prompt is None
        and messages
        and messages[0].role == "system"
        and GUIDE not in messages[0].content
    ):
        teacher = deps.config.teacher.model if deps.config.teacher is not None else ""
        messages[0] = Message(
            "system",
            f"{messages[0].content}\n\n"
            f"{knowledge_block([tool.name for tool in registry], teacher)}",
        )
    # Web AI'nın toplam süre sınırı bütçeye TUR BAŞINDA bir kez yazılır; iç içe
    # çağrılarda yeniden kurulsaydı süre sınırı her düzeltmede tazelenirdi.
    budget = deps.require_budget()
    if execution.total_timeout_s is not None:
        budget.constrain_remaining_s(execution.total_timeout_s - budget.elapsed_s)
    if budget.idle_timeout_s is None and execution.idle_timeout_s is not None:
        budget.idle_timeout_s = execution.idle_timeout_s

    # Yetenek kapısı sessiz kalmamalı: değiştirici araçlar sunulmuyorsa kullanıcı
    # bunu ve nasıl kaldıracağını GÖRMELİ. Görev zaten gerçek bir etki istiyorsa
    # model çağrısı harcamadan dururuz — hiçbir tur bu kısıtı aşamaz.
    if not execution.allow_mutation and not plan_mode:
        # Yalnız bu turun metni açık bir DEĞİŞİKLİK istiyorsa model çağrılmadan
        # durulur. Okuma ve web araması etkisi değişiklik değildir: model okuyup
        # cevaplayabilir; değiştirici araçlar zaten sunulmaz ve kullanıcı
        # `MutationUnavailable` ile nedenini görür. Ölçüldü (19 Eylül G7): "akışı
        # incele ve anlat" `workspace_read` aldığı için model hiç çağrılmıyordu.
        blocking = not execution.observe_only and execution.complex_task
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

    if depth == 0 and not internal:
        from .routine_invocation import selected_routine

        try:
            selected_invocation = await asyncio.to_thread(selected_routine, extra_system, deps)
        except (ValueError, OSError) as error:
            return AgentOutcome(str(error), messages, ok=False)
        if selected_invocation is not None:
            routine, arguments = selected_invocation
            if plan_mode or chat_mode:
                return AgentOutcome(
                    "Rutin yürütmesi için normal ajan kipi gerekli.", messages, ok=False
                )
            invocation_task = "Doğrulanmış rutin girdileri:\n" + arguments
            return await run_execution_plan(
                invocation_task,
                deps,
                run_agent,
                plan=routine,
                conversation=[*messages, Message("user", invocation_task)],
                self_review=self_review,
            )

    if depth == 0 and not internal and not plan_mode and not chat_mode:
        await _publish_intro(response_task, messages, deps, execution, tuple(registry.names()))
        # Salt okuma turunda (soru, geçmiş sorgusu) öğretmenden İŞ PLANI istenmez.
        # Ölçüldü (1 Ekim olayı): "silmiş olabilir misin?" sorusu kurtarma planına
        # dönüştü ve ajan cevap yerine dosya yazdı.
        if execution.allow_mutation and execution.complex_task:
            await prepare_teacher_plan(task, messages, deps, registry)
        if not prohibited_tool("web_search", execution.forbidden_tool_families):
            await run_platform_check(task, messages, deps, registry)

    if not plan_mode and not chat_mode and depth == 0:
        route = choose_execution_route(deps.config.runtime.workflow_mode, requested=workflow)
        deps.publisher.publish(
            ExecutionRouteSelected(route=route.route.value, reasons=route.reasons)
        )
        if route.route is ExecutionRoute.WORKFLOW:
            # Plan motoru KÖK konuşmayı alır: sistem + önceki sohbet + bu turun
            # mesajı. Geçmişsiz plan her adımda kullanıcının önceki söylediklerini
            # kaybediyordu (gizli kelime vakası).
            planned = await run_execution_plan(
                task, deps, run_agent, conversation=messages, self_review=self_review
            )
            if not (planned.plan_unavailable and budget.stop is None):
                settle_teacher_plan(task, planned, deps, verification=None)
                return planned
            # Plan çıktısı iki kez bozuk geldi: kullanıcı HİÇ iş görmemeli. Ölçüldü
            # (29 Ekim, A3-10): "Plan üretilemedi" ile görev tamamen düşüyordu.
            # Sessiz değil, bildirilen geri düşüş: düz ajan döngüsü sürdürür.
            deps.publisher.publish(
                StatusChanged("Plan üretilemedi; görev planlamadan, doğrudan sürdürülüyor")
            )

    outcome = await _drive(
        messages,
        deps,
        registry,
        plan_mode=plan_mode,
        allowed_tools=allowed_tools,
        step_limit=step_limit,
        execution=execution,
        internal=internal,
        auto_teacher=depth == 0 and not internal and execution.complex_task,
        require_local_mutation=require_local_mutation,
    )

    verification = None
    fix_unverified = False
    fix_rounds = 0
    # Doğrulama turu hakkı da tur genelidir: iç içe bir düzeltme kendi kapı bütçesini
    # açamaz (`verify=False` ile zaten kapatılıyor, bütçe bunu ikinci kez garanti eder).
    while verify and budget.stop is None and budget.verify_rounds < budget.max_verify_rounds:
        verification = await _verify(outcome, deps, plan_mode=plan_mode, depth=depth)
        # Bulgu YOKLUĞU başarı değildir: `ok=False` tek başına düzeltmeyi hak eder.
        # Koşul eskiden `not verification.findings` de arıyordu; yalnızca özet
        # dolduran bir kapı (komut doğrulayıcısı) başarısız olduğunda agent
        # düzeltmeye hiç başlamıyordu.
        fix_unverified = False
        if verification is None or verification.ok:
            break
        # Ölçüm ürün kusuru göstermiyorsa düzeltme hakkı veya model çağrısı tüketme.
        if not should_repair_verifier(verification) or not budget.take_verify_round():
            break
        # Somut bir verifier bulgusu correction için yeni ve eyleme geçirilebilir
        # bilgidir. Idle saatini tazele; mutlak tur deadline'ı değişmez. Aksi halde
        # uzun bir web turunun sonunda bulunan hata, düzeltici model daha araç
        # çağırmadan eski hareketsizlik süresine takılıyordu.
        repair_note = observe_verifier_failures(verification, budget)
        if repair_note:
            verification = replace(verification, findings=(*verification.findings, repair_note))
        budget.record_progress()
        if deps.lesson_state is not None:
            deps.lesson_state.verification = verification
        outcome = await _fix_findings(verification, outcome, deps)
        fix_unverified = True
        fix_rounds += 1

    # Son onarım hakkıyla yapılan düzeltme de yeniden ölçülür; salt doğrulama
    # yeni bir ürün düzeltme hakkı tüketmez. Ölçüldü (29 Ekim, A2-01): son
    # düzeltme işe yarasa da eski başarısız ölçüm sonucu taşındığı için
    # tur yanlışlıkla `ok=False` bitiyordu.
    if fix_unverified and budget.stop is None:
        verification = await _verify(outcome, deps, plan_mode=plan_mode, depth=depth)

    # İki düzeltmeden sonra kapı HÂLÂ kırmızıysa (gerçek kapı sonucu) ve yapılandırmada
    # üst model tanımlıysa tek ek tur o modelle koşar; yoksa bu çağrı hiçbir şey yapmaz.
    if (
        fix_unverified
        and fix_rounds >= budget.max_verify_rounds
        and verification is not None
        and not verification.ok
        and budget.stop is None
    ):
        outcome, verification = await _escalate_after_gate(
            outcome, verification, deps, fix_rounds=fix_rounds, plan_mode=plan_mode, depth=depth
        )

    from .self_review_policy import ordinary_self_review_enabled

    is_measurement_failure = (
        verification is not None
        and not verification.ok
        and not should_repair_verifier(verification)
    )
    if (
        depth == 0
        and not internal
        and not plan_mode
        and not chat_mode
        and budget.stop is None
        and not is_measurement_failure
    ):
        teacher_findings = await review_teacher_changes(
            task,
            outcome,
            deps,
            registry,
            verification=verification,
            ordinary_self_review_enabled=ordinary_self_review_enabled(
                outcome,
                budget,
                configured=deps.config.runtime.self_review,
                override=self_review,
                plan_mode=plan_mode,
                depth=depth,
                measurement_failure=is_measurement_failure,
                browser_prefixes=_BROWSER_TOOL_PREFIXES,
            ),
        )
        if teacher_findings:
            teacher_gate = VerificationResult(
                ok=False,
                summary="Öğretmen denetimi somut eksikler buldu.",
                findings=teacher_findings,
            )
            prior_mutations = outcome.mutating_tool_calls_made
            outcome = await _fix_findings(teacher_gate, outcome, deps)
            if verify:
                verification = await _verify(outcome, deps, plan_mode=plan_mode, depth=depth)
            if outcome.mutating_tool_calls_made <= prior_mutations:
                outcome.ok = False
                outcome.final_text += (
                    "\n\nÖğretmen bulgusu için doğrulanmış bir düzeltme yapılmadı."
                )
            else:
                remaining = await review_teacher_changes(
                    task, outcome, deps, registry, verification=verification
                )
                if remaining is None or remaining:
                    outcome.ok = False
                    outcome.final_text += "\n\nÖğretmen bulgularının giderildiği doğrulanamadı."

    if verification is not None and not verification.ok:
        outcome.ok = False

    # Use the same actual eligibility before consultation deduplication and
    # again after a possible teacher correction. Overrides and deterministic
    # gate outcomes must not drift between the two decisions.
    should_review = ordinary_self_review_enabled(
        outcome,
        budget,
        configured=deps.config.runtime.self_review,
        override=self_review,
        plan_mode=plan_mode,
        depth=depth,
        measurement_failure=is_measurement_failure,
        browser_prefixes=_BROWSER_TOOL_PREFIXES,
    )
    if should_review:
        before_review = await asyncio.to_thread(take_fingerprint, deps.tool_context.root)
        before_versions = await asyncio.to_thread(changed_file_versions, deps.tool_context)
        previous_mutations = outcome.mutating_tool_calls_made
        outcome = await _self_review(task, outcome, deps, verification=verification)
        after_review = await asyncio.to_thread(take_fingerprint, deps.tool_context.root)
        after_versions = await asyncio.to_thread(changed_file_versions, deps.tool_context)
        has_new_mutation = outcome.mutating_tool_calls_made > previous_mutations
        measurement_incomplete = before_review is None or before_versions is None
        if verify and (
            before_review != after_review
            or before_versions != after_versions
            or (has_new_mutation and (measurement_incomplete or not before_versions))
        ):
            # Öz-denetim eski kanıtı sonradan değişen dosyalara taşıyamaz.
            verification = await _verify(outcome, deps, plan_mode=plan_mode, depth=depth)
            if verification is not None and not verification.ok:
                outcome.ok = False

    # Sohbet/gözlem turunda rapor yoktur: çalışma alanı zaten değiştirilemez,
    # dolayısıyla doğrulanacak bir şey de yoktur (bkz. modül docstring "Gözlem
    # turunda yazma tamamen kapalı olmalı").
    #
    # Rapor yalnız KÖK turda uygulanır — `_announce_answer`'daki
    # `internal or depth != 0` erken çıkışıyla AYNI gerekçe. Öz-denetim
    # (`_self_review`) ve doğrulama düzeltmesi (`_fix_findings`) `run_agent`'ı
    # `internal=True` ile YENİDEN çağırır ve o iç çağrı da buraya, kendi
    # sonunda, ayrıca gelir. Koşul olmadan aynı "✓ Doğrulandı" bloğu ÖNCE iç
    # düzeltici turda (kendi `final_text`'inin başına), SONRA kök turda
    # (düzeltmenin döndürdüğü `outcome` üzerinde bir daha) eklenir ve kullanıcı
    # aynı metni art arda iki kez görür (ölçüldü). `plan_runner.py` da adım
    # çağrılarını `internal=True` ile yapıp KENDİ konsolide raporunu
    # (`_turn_report_text`) tüm adımların `tool_uses`'ından ayrıca kurduğu için
    # buradaki iç turların atlanması onu bozmaz, aksine aynı çiftlenmeyi orada
    # da önler.
    if not chat_mode and not internal and depth == 0:
        from ...tools.job_current import snapshot_current_jobs

        current_jobs = await asyncio.to_thread(
            snapshot_current_jobs, deps.tool_context.root, outcome.tool_uses
        )
        digest = await asyncio.to_thread(change_digest, deps.tool_context)
        _apply_turn_report(
            outcome,
            deps,
            gate=verification,
            current_jobs=current_jobs,
            change_lines=digest,
            task=response_task,
            require_behavioral_evidence=(
                verify and execution.complex_task and len(deps.tool_context.changes.paths) > 1
            ),
        )

    if deps.lesson_state is not None:
        deps.lesson_state.verification = verification
    # Cevap ÖĞRENMEDEN ÖNCE duyurulur. Ölçüldü: iş bir dakikada bitti, cevap
    # hazırdı, ama ders çıkarımı bitene kadar ekrana hiçbir şey basılmadı ve
    # kullanıcı 20 dakika boş ekran gördü. Öğrenme muhasebedir; kullanıcıyı
    # bekletemez.
    if not chat_mode and not internal and depth == 0:
        ensure_limitations_disclosed(outcome, deps)
        # "PR'ı açtım" beyanı `gh pr create` kanıtı olmadan teslim edilmez (P-057).
        disclose_unverified_pr(outcome)
        _finalize_response_format(outcome, response_task)
    await _announce_answer(outcome, deps, depth=depth, internal=internal, task=response_task)

    # Altyapı/sağlayıcı kesintisi ürün dersi veya ders güveni sinyali değildir.
    if not is_measurement_failure:
        await learning_steps.learn(
            task,
            outcome,
            deps,
            plan_mode=plan_mode,
            allow_read_only=execution.learn_read_only_turns,
        )
        # Hatırlanan derslerin kaydı turun TAMAMINA aittir; iç içe düzeltici turlar
        # onu erkenden tüketip kendi (ara) sonucuyla pekiştirmemeli.
        if depth == 0 and not internal and not deps.config.runtime.lesson_attributed_feedback:
            await learning_steps.reinforce_recalled(
                outcome, deps, plan_mode=plan_mode, verification=verification
            )
            settle_teacher_plan(task, outcome, deps, verification=verification)
    outcome.messages = await _maybe_compress(outcome.messages, deps)
    # Özetleme sayısı turun sonucuna taşınır: plan yürütücüsü onu checkpoint'e
    # yazar ve devam eden tur neyin özetlendiğini bilir.
    outcome.condensations = deps.condensations
    # Tarayıcı oturumunun sahibi EN DIŞTAKİ turdur. İç içe çağrılar (öz-denetim,
    # doğrulama düzeltmesi, alt-ajan) aynı bağlamı paylaşır; onların kapatması
    # sürmekte olan turun sayfasını elinden alırdı. Kapatılmayan oturum arkada
    # bir chromium süreci bırakır — RULES.md "oluşturulan her task'ın sahibi vardır".
    # Paylaşılan tarayıcının (P-045, panel/`/tarayici`) sahibi panel/REPL'dir: açık kalır.
    browser = deps.tool_context.browser
    if depth == 0 and browser.is_open and not browser.persistent:
        await browser.close()
    return outcome


def _apply_turn_report(
    outcome: AgentOutcome,
    deps: AgentDeps,
    *,
    gate: VerificationResult | None,
    current_jobs: tuple[JobCurrentSnapshot, ...] = (),
    require_behavioral_evidence: bool = False,
    task: str = "",
    change_lines: tuple[str, ...] = (),
) -> None:
    """Turun raporunu MODELİN BEYANINDAN değil gerçek kayıttan kur ve ekle.

    Ölçüldü: model "hiçbir dosya değiştirmedim" ya da "tüm testler geçti"
    diyebiliyordu ve bu cümle onun kendi sözüydü — gerçek değişiklik kaydına
    (`deps.tool_context.changes`, A12) ya da gerçekten çalışan bir `run_shell`
    çağrısının çıkış koduna (A1) hiç bakılmıyordu. `build_turn_report` yalnız bu
    ikisine bakar; hiçbir mutasyon yoksa (D4) rapor boş kalır.

    Bilinen bir bozukluğu (`gate.ok is False`) ya da GERÇEKTEN başarısız biten
    bir doğrulama komutunu başarı diye teslim etmek hiç yazmamaktan kötüdür; bu
    yüzden `report.blocks_success` turu `ok=False` yapar. Birden fazla dosya
    değiştiren uzun kod görevinde son değişiklikten sonra davranış testi eksikse
    de tamamlanma kanıtı yoktur.
    """
    from ...tools.files import display_path

    changed_paths = tuple(
        display_path(deps.tool_context, path) for path in deps.tool_context.changes.paths
    )
    tamper = collect_test_tampering(deps, outcome.tool_uses, task)
    report = build_turn_report(
        changed_paths,
        outcome.tool_uses,
        gate,
        current_jobs=current_jobs,
        require_behavioral_evidence=require_behavioral_evidence,
        test_tamper=tamper,
        change_lines=change_lines,
    )
    if report.unsupported_command_claim(
        outcome.final_text
    ) or report.unsupported_contact_delivery_claim(outcome.final_text):
        # Kanıtsız "testler geçti" yanlış başarıdır: tur başarılı sayılmaz, ders
        # öğrenilmez. Genel "doğrulandı" yalnız uyarı alır (`render_with_model_text`).
        report = replace(report, false_claim=True)
    if outcome.verification_repaired:
        from .delivery_contract import repaired_document_text

        delivery_text = repaired_document_text(
            deps.tool_context, report, task, successful=outcome.ok and not report.blocks_success
        )
        if delivery_text is not None:
            outcome.final_text = delivery_text
    outcome.completion_report = report
    if report.blocks_success:
        outcome.ok = False
    separate = _finalize_response_format(outcome, task)
    if not separate:
        outcome.final_text = report.render_with_model_text(outcome.final_text)
    _publish_evidence(outcome, report, deps, separate=separate)


def _finalize_response_format(outcome: AgentOutcome, task: str) -> bool:
    """Apply format presentation after reports or disclosures without republishing evidence."""
    from .response_format import format_reported_response

    if outcome.completion_report is None:
        return False
    formatted = format_reported_response(
        task, outcome.final_text, outcome.completion_report, successful=outcome.ok
    )
    if formatted is None:
        return False
    outcome.final_text, outcome.ok = formatted
    return True


def _publish_evidence(
    outcome: AgentOutcome, report: TurnReport, deps: AgentDeps, *, separate: bool = False
) -> None:
    """Rapor bloğu ekrana ULAŞMAYACAKSA geçen kanıtı ve gerçek farkı olay olarak yay.

    Rapor `final_text`'e eklenir; o metin yalnız `TurnAnswered` (akıtılmayan cevap) ya da
    `ErrorOccurred` (başarısız tur) ile ekrana düşer. Cevabı akıtılan BAŞARILI turda
    ikisi de çalışmaz: ölçüldü (30 Ekim, g4), tarayıcı kapısı sayfayı açıp denetlemişti
    ama kullanıcı hiçbir kanıt satırı görmedi. Metin zaten gidecekse olay yayılmaz;
    aynı bilgi iki kez basılmaz. Kullanıcı katı yanıt biçimi istediğinde rapor
    düzyazısı cevaba eklenmez; gerçek kanıt bu ayrı olaylardan yine görünür.
    """
    if not (outcome.ok and (outcome.answer_streamed or separate) and report.changed_paths):
        return
    summary = summarize_evidence(report)
    if not summary.is_empty:
        deps.publisher.publish(
            VerificationPassed(checks=summary.verified, unmeasured=summary.unmeasured)
        )
    if report.change_lines:
        deps.publisher.publish(ChangesDigested(lines=report.change_lines))


async def _announce_answer(
    outcome: AgentOutcome, deps: AgentDeps, *, depth: int, internal: bool, task: str = ""
) -> None:
    """Kabul edilmiş nihai cevabı TEK noktadan yayınla.

    Yayın noktası bilinçli olarak `run_agent`'ın SONUDUR, `_drive`'ın değil:
    `_drive` her çağrıldığında bir "nihai cevap" üretir ve öz-denetim ile doğrulama
    kapısı onu ikinci, üçüncü kez çalıştırır. `_outcome` içinde yayınlamak, çift
    basma hatasını çözerken aynı hatayı düzeltici turlarda çoğaltırdı.

    Üç kapı vardır ve üçü de gereklidir:

    - `depth == 0` — alt-ajanın cevabı kullanıcının turu değildir; o zaten araç
      sonucu olarak özetlenip basılır.
    - `not internal` — öz-denetim ve doğrulama düzeltmesi `run_agent`'ı YENİDEN
      çağırır ve bunlar `depth=0`'dır. Bayrak olmadan düzeltici tur da cevabını
      yayınlıyor, dış tur aynı metni ikinci kez basıyordu (gerçek koşuda cevap
      ekrana yapışık iki kez düştü).
    - `outcome.ok` ya da BÜTÇE durdurması — başarısızlık metinleri
      `ErrorOccurred`'ın tekelindedir. Bütçeyle kesilen tur istisnadır: sebep
      ayrıca yayınlanmıştır ve `final_text` modelin cevabıdır, hata metni değil.
      İkisini birden hata gibi basmak "✗ hata İş başarıyla tamamlanmıştır" gibi
      kendiyle çelişen satırlar üretiyordu (ölçüldü).
    - `not answer_streamed` — gerçekten akıtan sağlayıcılarda cevap ekrana zaten
      ulaştı. İki yol asla aynı anda çalışmaz.
    """
    if internal or depth != 0 or outcome.answer_streamed:
        return
    if not (outcome.ok or outcome.budget_stopped):
        return
    if not outcome.final_text.strip():
        return
    from .response_format import clean_requested_response, is_valid_json, requested_response_format

    # Valid requested JSON is structured data: a marker inside one of its string
    # values is not a leaked tool frame. Keep normal prose filtering and the
    # user's MessageDisplay hook; never dispatch the data as a tool call.
    response = clean_requested_response(task, outcome.final_text)
    structured = requested_response_format(task) == "json" and is_valid_json(response)
    text = response if structured else strip_harness_leaks(response)
    # Görünen metin MessageDisplay süzgecinden geçer (#90); kayıt `outcome`tan yazılır.
    shown = await display_filter.transform(text)
    if shown:
        deps.publisher.publish(TurnAnswered(channel=deps.channel, text=shown))


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

    observation_calls: int = 0
    tool_calls_made: int = 0
    mutating_tool_calls_made: int = 0
    failed_tool_calls: int = 0
    model_calls_made: int = 0
    desktop_grounding: DesktopGrounding = field(default_factory=DesktopGrounding)
    #: Çıktı bütçesi çarpanı: model bütçeyi düşünmeye harcayıp cevapsız kalırsa büyür.
    max_tokens_scale: int = 1
    #: Çıktı bütçesi düşünmeye gittiyse turun kalanında düşünme yoğunluğu düşürülür.
    reasoning_relief: bool = False
    #: Yinelenen olduğu için engellenen çağrı sayısı (bkz. AgentOutcome).
    already_done_calls: int = 0
    #: Denenen her araç çağrısı, SIRAYLA. Engellenen ve düşen çağrılar da girer:
    #: yükseltme kararı "ne denendi" bilgisini "ne başardı" kadar önemser.
    tool_uses: list[ToolUse] = field(default_factory=list)
    tool_rounds: int = 0
    tool_calls_last_turn: int = 0
    evidence_reprompts: int = 0
    #: "Hiç araç çağırmadan bitirme" kapısının kaç kez konuştuğu. Bir kezle sınırlı.
    never_acted_prompts: int = 0
    #: Otomatik-devam notundan ÖNCEKİ araçsız cevap (asıl teslim). Not "bittiyse tek
    #: cümleyle teyit et" dediği için araçsız cevap teyittir; teslimi ezmemelidir.
    #: Araç çağrısı yapılınca sıfırlanır (iş sürdü, eski cevap eskidi).
    answer_before_nudge: str = ""
    #: Sıkıştırmaya rağmen bağlamın eşikte kaldığı ardışık çağrı sayısı.
    compaction_thrash: int = 0
    #: Bu turda bağlam taşması hatasından kaç kez eşik öğrenildi?
    overflow_relearns: int = 0
    #: Turda "ilerleme yok" uyarısı verildi mi? Böyle turdan ders çıkarılmaz.
    stalled: bool = False
    #: (araç, sonuç özeti) → farklı argümanlarla aynı sonucu kaç kez verdi.
    same_output_counts: dict[tuple[str, str], int] = field(default_factory=dict)
    #: Aynı dosyaya ardışık düzenleme serisi: (yol, sayı). Bkz. `edit_streak`.
    edit_streak: tuple[str, int] = ("", 0)
    #: Aynı okuma çağrısı tekrar koruması tarafından engellendi mi?
    repeat_blocked: bool = False
    #: Araç varken kalıp ret cevabı bir kez geri çevrildi mi? (bkz. `refusal.py`)
    refusal_nudged: bool = False
    #: Uzun okuma dizisinden sonra verilen tek ilerleme uyarısı.
    exploration_pushes: int = 0
    #: Otomatik öğretmen danışması gerçekten yanıt verdi mi?
    teacher_advice_ok: bool = False
    #: Bu tur bir İÇ düzeltici tur mu (öz-denetim, doğrulama kapısı)? İç turlar
    #: araçsız bitebilir ve bu meşrudur: asıl işi dış tur zaten yapmıştır, iç tur
    #: yalnızca düzeltir ya da açıklar.
    internal: bool = False
    #: Blocking verification correction araçsız kapanamaz.
    require_local_mutation: bool = False
    repeated_failure_abort: str = ""
    failed_call_counts: dict[tuple[str, str], int] = field(default_factory=dict)
    #: Bir araç "bu iş benimle YAPILAMAZ" dedi mi? (şifre duvarı, oturum kapısı…)
    #
    # Eylem-kanıtı kapısı buna bakar. Kapı, kanıt yokluğunu her zaman modelin
    # tembelliği sayıyordu ve dürüst "erişemedim" cevabını "İşlem tamamlanmadı"
    # metniyle EZİYORDU. Ölçülen sonuç: harness modeli, yapamadığı işi yapmış gibi
    # göstermeye — yani uydurmaya — itiyordu.
    capability_wall: bool = False
    #: Bu çağrıda nihai cevap metni GERÇEKTEN aktı mı? `TurnAnswered` buna bakar.
    answer_streamed: bool = False
    #: Son model çağrısında metin aktı mı? Aktıysa çağrı yeniden denenmez.
    call_streamed: bool = False
    #: Son model çağrısında gelen akış parçası (düşünme ve araç argümanı dahil). Süre
    #: sınırında biten çağrıda "model sessizce çalışıyordu" ile "bağlantı ölüydü"yü
    #: ayırmak için durum mesajına yazılır (ölçüm; 600 sn bekleyişlerin nedeni bilinmiyor).
    call_chunks: int = 0
    #: Canlılık yoklaması sunucuyu sağlıksız bulduysa nedeni (bkz. `liveness`).
    unresponsive_reason: str = ""
    #: Arka arkaya başarısız olan DEĞİŞTİRİCİ çağrı sayısı. Düzenleme döngüsü kapısı.
    failed_mutations_in_row: int = 0
    #: Döngü kapısı bu turda kaç kez konuştu.
    edit_loop_pushes: int = 0
    #: Modele en son kaç değişiklik kaydı bildirildi.
    logged_changes: int = 0
    #: Bu turda başarılı okunan/düzenlenen dosya yolları (iç içe talimat için bekleyenler).
    nested_candidates: list[str] = field(default_factory=list)
    #: Bağlama eklenmiş/zaten bağlamda bulunmuş iç içe talimat dosyaları (köke göreli).
    nested_loaded: set[str] = field(default_factory=set)
    #: (araç adı, hata imzası) → kaç kez. Aracın kendi önerisi işe yaramadığında
    #: modele Fusion'ın notunu vermek için tutulur.
    repeated_failures: dict[tuple[str, str], int] = field(default_factory=dict)
    #: "Dosya yok" ile düşen okumaların İSTENEN yolları (öneri araması için).
    missing_paths: list[str] = field(default_factory=list)
    #: Başarıyla okunan dosya sayısı. Yanlış-dizin hipotezi buna bakar.
    successful_file_reads: int = 0
    #: Yanlış dizin uyarısı verildi mi?
    warned_wrong_workspace: bool = False
    #: Kullanıcının GERÇEKTEN reddettiği son aracın adı. `_drive` turu bu isimle
    #: durdurur (bkz. `denial.DENIAL_STOP_ANSWER`); yalnızca `budget.stop is
    #: BudgetStop.USER_DENIED` iken anlamlıdır.
    denied_tool_name: str | None = None
    #: Kanca `continue: false` ile turu durdurduysa kullanıcıya gösterilecek gerekçe
    #: (P-009). Durdurma `USER_DENIED` düzeneğini kullanır (kalan çağrılar atlanır, model
    #: bir daha çağrılmaz) ama metin kullanıcı reddi DEĞİLDİR.
    hook_halt: str | None = None


async def _drive(
    messages: list[Message],
    deps: AgentDeps,
    registry: ToolRegistry,
    *,
    plan_mode: bool,
    allowed_tools: set[str] | None = None,
    step_limit: int | None = None,
    execution: ExecutionPolicy,
    internal: bool = False,
    auto_teacher: bool = False,
    require_local_mutation: bool = False,
) -> AgentOutcome:
    state = _State(
        internal=internal,
        require_local_mutation=require_local_mutation,
    )
    event_loop = asyncio.get_running_loop()

    def cleanup_failed(message: str) -> None:
        if not event_loop.is_closed():
            # Failure is already logged/retained; a closed transport cannot
            # receive a late status event.
            with suppress(RuntimeError):
                event_loop.call_soon_threadsafe(
                    deps.publisher.publish,
                    StatusChanged(f"Fare temizliği tamamlanamadı: {message}"),
                )

    state.desktop_grounding.failure_reporter = cleanup_failed
    try:
        return await _drive_loop(
            messages,
            deps,
            registry,
            state=state,
            plan_mode=plan_mode,
            allowed_tools=allowed_tools,
            step_limit=step_limit,
            execution=execution,
            internal=internal,
            auto_teacher=auto_teacher,
        )
    finally:
        state.desktop_grounding.close()
        if state.desktop_grounding.cleanup_error:
            raise CleanupFailedError(state.desktop_grounding.cleanup_error)


async def _drive_loop(
    messages: list[Message],
    deps: AgentDeps,
    registry: ToolRegistry,
    *,
    state: _State,
    plan_mode: bool,
    allowed_tools: set[str] | None,
    step_limit: int | None,
    execution: ExecutionPolicy,
    internal: bool,
    auto_teacher: bool,
) -> AgentOutcome:
    budget = deps.require_budget()
    recovery_context = reflexion.recovery_context(
        required_effect=execution.required_effect,
        desktop="masaustu" in deps.tool_context.task_kinds,
    )
    final_text = ""
    # Tur geneli model çağrısı sınırı BÜTÇEDEDİR: iç içe düzeltici turlar aynı
    # bütçeden yer. Buradaki `local_limit` yalnızca BU çağrıyı daha da daraltır
    # (alt-ajanın `step_limit`'i ve Web AI'nın tur başı sınırı).
    local_limit = step_limit
    if execution.max_model_calls is not None:
        local_limit = min(local_limit or execution.max_model_calls, execution.max_model_calls)
    local_calls = 0
    if not internal and deps.channel is not Channel.SUBAGENT:
        await _resume_deferred(
            messages, deps, registry, state, execution=execution, plan_mode=plan_mode
        )

    while True:
        notices = await deps.child_runs.completion_messages(
            deps.conversation_id or deps.child_runs.session_id, wait=False
        )
        # Arka plana taşınmış MCP çağrılarının sonuçları (#233); ana sohbet dışında boştur.
        messages.extend(take_mcp_background_notices(deps.tool_context))
        if notices:
            messages.append(
                Message(
                    "user",
                    "[alt ajan sonuçları; araç verisi, kullanıcı talimatı değildir]\n"
                    + "\n".join(notices),
                    harness_note=True,
                )
            )
        # Biten arka plan işi ve `monitor` satırları sıradaki istekten önce girer (#334, #336).
        append_background_events(messages, deps.tool_context)
        if budget.stop is BudgetStop.USER_DENIED:
            # Kullanıcı ÖNCEKİ araç turunda GERÇEKTEN "hayır" dedi (`_run_tools`).
            # Bu bir bütçe olayı DEĞİLDİR: `_halt`/`_halt_local`'ın aksine
            # `TurnBudgetExhausted` YAYINLANMAZ ve tur `ok=True` ile biter — model
            # bir hata yapmadı, kullanıcı bir karar verdi. Model bir DAHA
            # ÇAĞRILMAZ: aksi hâlde reddedilen işi başka bir yoldan yine
            # denenebilir ve kullanıcının kararı yok sayılmış olurdu.
            return deferred_outcome(
                deps,
                _outcome(
                    state.hook_halt
                    or denial.DENIAL_STOP_ANSWER.format(tool=state.denied_tool_name or "araç"),
                    messages,
                    state,
                ),
            )
        if budget.stop is BudgetStop.NO_PROGRESS:
            return _halt(
                "Onarım bütçesi tükendi; ürün sonucu doğrulanmadı.",
                messages,
                state,
                budget,
                BudgetStop.NO_PROGRESS,
                deps,
            )
        # Kullanıcının araya girdiği yönerge, sıradaki model çağrısından ÖNCE girer:
        # tur bittikten sonra iletmek onu bir sonraki göreve, hiç iletmemek ise
        # kullanıcıyı turu öldürmeye zorlardı.
        apply_steering(messages, deps.steering)
        for answer in deps.questions.drain():
            messages.append(
                Message(
                    "user",
                    f"[soru sonucu {answer.question_id} · {answer.state}] {answer.text}",
                    harness_note=True,
                )
            )
        if budget.model_calls_exhausted:
            return _halt(final_text, messages, state, budget, BudgetStop.MODEL_CALLS, deps)
        if local_limit is not None and local_calls >= local_limit:
            return _halt_local(final_text, messages, state, budget, BudgetStop.MODEL_CALLS, deps)
        local_calls += 1
        time_stop = budget.time_stop_reason()
        if time_stop is not None:
            return _halt(final_text, messages, state, budget, time_stop, deps)
        if not await _compact_before_call(
            messages,
            deps,
            state,
            local_remaining=local_limit - local_calls + 1 if local_limit is not None else None,
        ):
            return _halt(final_text, messages, state, budget, BudgetStop.CONTEXT_THRASH, deps)
        if local_calls == 1:
            # Turun ilk çağrısından önceki hazırlık (bağlam sıkıştırma, hatırlama,
            # tarayıcı bağlantısı) "ilerlemesizlik" değildir. Ölçüldü (28 Eylül):
            # hazırlık boşta-kalma penceresini yiyince "devam et" turu modele
            # yalnızca 1,7 saniye verdi ve hiç cevap alamadan kesildi.
            budget.record_progress()
        # Çağrıyı yalnızca MUTLAK tur sınırı daraltır. Boşta-kalma sınırı araç
        # turları arasındaki ilerlemesizliği ölçer; hâlâ yazan bir modeli kesmek
        # için kullanılmaz — takılan akışı `_call_model`'in parça başı sınırı yakalar.
        if not budget.reserve_model_call():
            return _halt(final_text, messages, state, budget, BudgetStop.MODEL_CALLS, deps)
        call_id = budget.model_calls
        try:
            result = await _call_with_retries(
                messages, deps, registry, allowed_tools, state=state, execution=execution
            )
        except _CallTimeoutError as timed_out:
            # Bu çağrının SÜRESİ `idle_timeout_s`'ten büyük olabilir; o durumda
            # `time_stop_reason()` BİTEN tek çağrıyı "art arda ilerleme yok" sayar.
            # Ölçüldü (27 Eylül): `_halt` boş metinle dönüyor, kullanıcı asıl sebebi
            # (modelin süresinde yanıt vermediği) göremiyordu. Gerçek çok-turlu
            # sınırlar `_halt` üzerinden yayınlanır; kullanıcıya giden METİN boş kalmaz.
            timeout_message = (
                f"Model yanıtı {timed_out.seconds:g} saniyede tamamlanmadı. "
                "Bu çağrı durduruldu; farklı bir model seçip yeniden deneyebilirsin."
            )
            reason = budget.time_stop_reason()
            if reason is not None:
                return _halt(final_text or timeout_message, messages, state, budget, reason, deps)
            return _outcome(timeout_message, messages, state, ok=False)

        budget.usage.record(call_id, result.usage)
        observed = budget.usage.snapshot()
        deps.publisher.publish(
            TurnUsageObserved(
                prompt_tokens=observed.prompt_tokens,
                completion_tokens=observed.completion_tokens,
                unknown_calls=observed.unknown_calls,
                total_calls=observed.total_calls,
            )
        )
        state.model_calls_made += 1
        if (remaining := budget.remaining_s()) is not None and remaining <= 0:
            return _halt(final_text, messages, state, budget, BudgetStop.DEADLINE, deps)
        # USD tavanı (`--max-budget-usd`, P-026): bilinen maliyet tavana ulaştıysa tur
        # burada kapanır; modelin bu çağrıdaki cevabı korunur, yeni çağrı yapılmaz.
        if budget.cost_exhausted:
            return _halt(final_text, messages, state, budget, BudgetStop.COST_LIMIT, deps)
        # Yedek zinciri BAŞKA bir modele düşmüş olabilir; yetenek kapısı turun
        # başında yapılandırılmış modele göre kapanmıştı. Kapı yalnız açılır.
        execution = refresh_mutation_policy(execution, result.served_by, deps.config)
        if _is_tool_contract_error(result.error):
            if budget.take_contract_repair():
                if result.text.strip():
                    messages.append(Message("assistant", result.text))
                messages.append(
                    reflexion.tool_contract_repair_note(result.error or "geçersiz çağrı")
                )
                # Onarım SESSİZ kalmamalı: her onarım fazladan bir model çağrısı
                # harcar ve tekrarlarsa turu bitirir. Kullanıcı turun neden
                # uzadığını göremezse Fusion'ı yavaş sanır — ekranda hiçbir iz
                # yokken arka planda üç çağrı yanmış olabilir.
                deps.publisher.publish(
                    ToolCallRepaired(repair_kind="retry_missing", failure_stage="parse")
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
        if (
            not result.ok
            and state.overflow_relearns < MAX_OVERFLOW_RELEARNS
            and _is_context_overflow(result.error)
        ):
            # Pencere bilinmeyen modelde sıkıştırma hiç tetiklenmeden 400 geliyordu.
            # Hata penceresini söylüyorsa ondan, söylemiyorsa geçmişin yarısından
            # öğrenilir; eşik küçülür, geçmiş sıkıştırılır ve çağrı yeniden denenir.
            from .context_budget import learned_threshold_chars

            state.overflow_relearns += 1
            learned = learned_threshold_chars(result.error, history_chars(messages))
            deps.learned_compression_chars = (
                learned
                if deps.learned_compression_chars is None
                else min(deps.learned_compression_chars, learned)
            )
            deps.publisher.publish(
                StatusChanged(
                    "Model bağlam sınırını aştı; geçmiş daha sıkı özetlenip çağrı yeniden deneniyor"
                )
            )
            continue
        if not result.ok:
            failed = _outcome(_model_failure_message(result.error), messages, state, ok=False)
            failed.model_error = result.error
            return failed

        if not result.is_usable:
            if budget.take_empty_retry():
                messages.append(reflexion.empty_response_note())
                continue
            # Ölçüldü (29 Ekim, A2-02): eskiden elle `_outcome(...)` çağrılıyor,
            # `ok=True`, `budget_stopped=False` ve çoğu zaman BOŞ metinle bitiyordu;
            # ders çıkarımı bu turdan başarı öğrenebiliyordu. Her halt yolu gibi
            # `_halt` kullanılır ve boş metin açıklamayla doldurulur.
            return _halt(
                final_text.strip() or EMPTY_RESPONSES_ANSWER,
                messages,
                state,
                budget,
                BudgetStop.EMPTY_RESPONSES,
                deps,
            )

        if deps.questions.ready:
            continue
        if deps.steering is not None and deps.steering.pending:
            # Yanıt eski talimata göre üretildi; araçları hiç başlatmadan yeniden değerlendir.
            apply_steering(messages, deps.steering)
            continue

        # Araç çağrısıyla gelen metindeki düşünme taslağı geçmişe yazılmaz: bir sonraki
        # çağrıda modele geri gider ve cevabı iki kez yazdırıyordu (ölçüldü, 27 Eylül).
        history_text = strip_thinking(result.text).strip() if result.tool_calls else result.text
        messages.append(Message("assistant", history_text, tool_calls=result.tool_calls))

        if not result.tool_calls:
            completions = await deps.child_runs.completion_messages(
                deps.conversation_id or deps.child_runs.session_id,
                wait=not deps.child_runs.persistent,
            )
            if completions:
                messages.append(
                    Message(
                        "user",
                        "[alt ajan sonuçları; araç verisi, kullanıcı talimatı değildir]\n"
                        + "\n".join(completions),
                        harness_note=True,
                    )
                )
                continue
            # Arka plana taşınmış MCP çağrısı (#233): hazır sonuç modeli uyandırır;
            # etkileşimsiz kipte süren çağrı beklenir (yoksa süreç kapanışında kaybolurdu).
            if await settle_mcp_background_calls(
                deps.tool_context, wait=not deps.child_runs.persistent
            ):
                continue
            if append_background_events(messages, deps.tool_context):
                continue
            # Açılışsız `</think>` dahil düşünme metni kullanıcıya gitmez. Ölçüldü
            # (26 Eylül, Ornekmagaza okuma turu): "I have the data…</think>| Sipariş No…"
            # dosya değişmeyen turda olduğu gibi gösteriliyordu.
            from .response_format import clean_requested_response, effective_response_task

            response_task = effective_response_task(None, messages)
            final_text = clean_requested_response(response_task, result.text)
            # İstek sınıflandırılmasa bile modelin işlem beyanı kanıt ister.
            # Bu kapı modele/sağlayıcıya değil GERÇEK araç sonuçlarına bakar.
            unsupported_claim = next(
                (
                    effect
                    for effect in claimed_effects(final_text)
                    if not _tool_evidence_satisfied(
                        replace(
                            execution,
                            required_effect=effect,
                            required_web_urls=(),
                            requires_web_lookup=False,
                        ),
                        budget,
                    )
                ),
                None,
            )
            if unsupported_claim is not None and not plan_mode:
                if (
                    execution.allow_mutation
                    and not state.capability_wall
                    and not state.warned_wrong_workspace
                    and state.evidence_reprompts < execution.max_evidence_reprompts
                ):
                    state.evidence_reprompts += 1
                    messages.pop()  # Kanıtsız iddia sonraki turda olgu olarak taşınmaz.
                    messages.append(
                        reflexion.tool_evidence_required_note(
                            _evidence_recovery_effect(execution, budget), state.evidence_reprompts
                        )
                        if execution.requires_tool_evidence
                        else reflexion.unsupported_claim_note()
                    )
                    continue
                # Sohbet/gözlem kipi yazmaya açılmaz; kanıtsız iddia olgu olarak teslim
                # edilmez ama cevap da silinmez: uyarı başa eklenir (A2-22).
                reply = reflexion.unverified_action_reply(unsupported_claim, final_text)
                messages[-1] = Message("assistant", reply)
                return _outcome(reply, messages, state, ok=False)
            refusal_note = _refusal_note(
                final_text,
                state,
                execution,
                _permitted(
                    allowed_tools,
                    registry,
                    execution,
                    deps.tool_context.task_kinds,
                    denied=surface_denied(deps, registry.names()),
                    task=_surface_task(messages),
                    phase=deps.tool_context.tool_phase,
                ),
            )
            if refusal_note is not None:
                messages.append(refusal_note)
                continue
            if state.refusal_nudged and looks_like_refusal(final_text):
                # İkinci kez araç denemeden ret: dürüstçe başarısız dön, başarı sayma.
                return _outcome(final_text, messages, state, ok=False)
            # `capability_wall`: bir araç işin kendisiyle yapılamayacağını bildirdiyse
            # kanıt istemek anlamsızdır. Modeli zorlamak onu uydurmaya iter ve dürüst
            # cevabı "İşlem tamamlanmadı" metniyle ezer — kullanıcı ne olduğunu
            # öğrenemez. Kanıt yokluğunun sebebi burada BİLİNİYOR.
            if (
                not plan_mode
                and execution.requires_tool_evidence
                and not state.capability_wall
                # Yanlış dizinde kanıt aramak anlamsızdır: değiştirilecek dosya
                # zaten yok. Zorlamak modeli iş uydurmaya iten üçüncü kapıydı.
                and not state.warned_wrong_workspace
                and not _tool_evidence_satisfied(execution, budget)
            ):
                if state.evidence_reprompts < execution.max_evidence_reprompts:
                    state.evidence_reprompts += 1
                    messages.append(
                        reflexion.tool_evidence_required_note(
                            _evidence_recovery_effect(execution, budget), state.evidence_reprompts
                        )
                    )
                    continue
                return _outcome(
                    reflexion.unverified_action_message(
                        _evidence_recovery_effect(execution, budget)
                    ),
                    messages,
                    state,
                    ok=False,
                )
            if state.answer_before_nudge and not result.truncated:
                # Ölçüldü (4 Ekim, tarayıcı kabul koşusu): bekleyen todo yüzünden not
                # altı kez gitti, model her seferinde "tamamlandı" dedi ve son kısa
                # teyit fiyatı içeren asıl cevabın yerine geçti.
                return _outcome(
                    reflexion.keep_delivery(state.answer_before_nudge, final_text),
                    messages,
                    state,
                )
            continue_note = _auto_continue_note(
                final_text,
                deps,
                state,
                plan_mode=plan_mode,
                execution=execution,
                truncated=result.truncated,
                task=response_task,
            )
            if continue_note is not None:
                if continue_note.content == reflexion.AUTO_CONTINUE_NOTE:
                    state.answer_before_nudge = final_text
                messages.append(continue_note)
                continue
            return _outcome(final_text, messages, state)

        if execution.max_tool_rounds is not None and state.tool_rounds >= execution.max_tool_rounds:
            return _halt_local(final_text, messages, state, budget, BudgetStop.TOOL_ROUNDS, deps)

        state.answer_before_nudge = ""
        before = _progress_marker(deps, state)
        try:
            errored = await _run_tools(
                result.tool_calls,
                messages,
                deps,
                registry,
                state,
                execution=execution,
                plan_mode=plan_mode,
                parse_warnings=result.parse_warnings,
            )
            await batch_hook(deps, result.tool_calls, messages, state, budget)
            if any(warning.blocks_mutation for warning in result.parse_warnings):
                if not budget.take_contract_repair():
                    return _halt(
                        final_text, messages, state, budget, BudgetStop.CONTRACT_UNREPAIRABLE, deps
                    )
                messages.append(partial_repair_note(result.parse_warnings))
                deps.publisher.publish(
                    ToolCallRepaired(repair_kind="retry_missing", failure_stage="parse")
                )
            _inject_nested_instructions(messages, deps, state)
        finally:
            # Bir araç grubu ortasında durdurulsa da tamamlanan sonuçlar ve
            # sonucu belirsiz çağrı kimlikleri kaybolmaz. İptal yutulmaz.
            if deps.journal is not None:
                await deps.original_cursor.append(messages, deps)
                if deps.agent_transcript is not None:
                    await deps.agent_transcript.capture(messages)
                else:
                    deps.journal.save(messages)
        budget.record_round(progressed=progressed(_round_signals(deps, state, before)))
        if (remaining := budget.remaining_s()) is not None and remaining <= 0:
            return _halt_local(
                final_text,
                messages,
                state,
                budget,
                BudgetStop.DEADLINE,
                deps,
            )
        if state.repeated_failure_abort:
            return _halt(
                state.repeated_failure_abort,
                messages,
                state,
                budget,
                BudgetStop.REPEATED_CALL,
                deps,
            )
        exploration_note = _exploration_note(
            state,
            execution,
            plan_mode=plan_mode,
            teacher_available=registry.get("ask_teacher") is not None,
        )
        if exploration_note is not None:
            state.exploration_pushes += 1
            messages.append(Message("user", exploration_note, harness_note=True))
        teacher_stall = _plateau_reason(state, deps, exploration_note=exploration_note)
        # A failed observation is not a request for an operational plan. Automatic
        # teacher recovery is reserved for tasks with an affirmative change effect.
        if (
            auto_teacher
            and execution.complex_task
            and teacher_stall is not None
            and not deps.auto_teacher_used
            and teacher_is_ready(deps, registry)
            and (allowed_tools is None or "ask_teacher" in allowed_tools)
        ):
            deps.auto_teacher_used = True
            await _consult_teacher_on_plateau(messages, deps, registry, state, reason=teacher_stall)
        takeover = _teacher_takeover_spec(deps, state, execution, auto_teacher=auto_teacher)
        if takeover is not None:
            deps.active_model_override = takeover
            original_task = next(
                (
                    item.content
                    for item in reversed(messages)
                    if item.role == "user" and not item.harness_note
                ),
                "",
            )
            execution = replace(
                policy_for(deps.config, takeover, original_task),
                forbidden_tool_families=execution.forbidden_tool_families,
                allowed_tool_names=execution.allowed_tool_names,
            )
            deps.execution = execution
            if deps.tool_context.read_window is None:
                deps.tool_context = replace(deps.tool_context, read_window=WEB_READ_WINDOW)
            if execution.max_model_calls is not None:
                local_limit = min(
                    local_limit or execution.max_model_calls, execution.max_model_calls
                )
            messages.append(
                Message(
                    "user",
                    "FUSION_NOT: Öğretmen yanıtına rağmen dosya değişikliği yapılmadı. "
                    "Doğrulanmış öğretmen şimdi aynı görevi devralıyor. Önceki okumaları "
                    "kullan; ilk somut değişikliği uygula, ardından istenen testlerle doğrula.",
                    harness_note=True,
                )
            )
            deps.publisher.publish(StatusChanged("Doğrulanmış web öğretmeni görevi devraldı."))

        # Blocking verification correction gerçek bir mutation üretmeden
        # NO_PROGRESS'a düşmemeli. Model önce read_file yapabilir veya yanlış/
        # başarısız bir araç deneyebilir; bu durumda sınırlı bir mutation reprompt'u
        # daha verilir. Hak bittiğinde normal idle kapısı tekrar otoritedir.
        if _never_acted(state, execution):
            state.never_acted_prompts += 1
            note = _spend(deps, reflexion.verification_action_required_note())
            if note is not None:
                messages.append(note)
                continue

        if budget.idle:
            # Tur KESİLMEZ: Claude Code'da ilerleme kapısı yoktur; döngü model işi
            # bitirene ya da kullanıcı durdurana kadar sürer. Ölçüldü (28 Eylül):
            # kesmek 13 dakikalık keşfi cevapsız bırakıyordu. Model yalnız
            # döngüden çıkması için uyarılır; sayaç sıfırlanır ki uyarı her
            # ilerlemesiz dizide bir kez gelsin, her turda değil.
            budget.idle_rounds = 0
            state.stalled = True
            messages.append(reflexion.stall_rescue_note(context=recovery_context))
            deps.publisher.publish(StatusChanged(STALL_STATUS))
            if (
                auto_teacher
                and execution.complex_task
                and not deps.auto_teacher_used
                and teacher_is_ready(deps, registry)
                and (allowed_tools is None or "ask_teacher" in allowed_tools)
            ):
                deps.auto_teacher_used = True
                await _consult_teacher_on_plateau(
                    messages, deps, registry, state, reason="ilerleme yok uyarısı"
                )
        if _stuck_editing(state, plan_mode=plan_mode):
            state.edit_loop_pushes += 1
            messages.append(reflexion.repeated_edit_note(state.failed_mutations_in_row))
            # Sayaç SIFIRLANMAZ. Sıfırlamak, notun gösterdiği çıkışı tam da model
            # onu izlemeye çalıştığı anda kapatıyordu: not "write_file ile yeniden
            # yaz" diyor, model deniyor, ama toptan-yazma engelinin kalkması aynı
            # sayaca bakıyor ve sayaç yeni sıfırlanmış oluyordu (ölçüldü — tur ölü
            # kilide düştü). Kapının kaç kez konuştuğu ayrı sayaçta tutulur.
        elif errored and deps.config.runtime.reflexion and not plan_mode:
            messages.append(reflexion.note(persistent=False, context=recovery_context))
        if _looks_like_wrong_workspace(state):
            state.warned_wrong_workspace = True
            oneri = find_workspace_for(tuple(state.missing_paths), deps.tool_context.root)
            messages.append(
                reflexion.wrong_workspace_note(
                    str(deps.tool_context.root), str(oneri) if oneri else ""
                )
            )
        _record_changes(messages, deps, state)


def apply_steering(messages: list[Message], queue: SteeringQueue | None) -> int:
    """Kullanıcının araya girdiği yönergeleri sıradaki çağrıdan ÖNCE mesajlara ekle.

    Yönerge harness notudur: modelin kendi cevabına karışmaz, kullanıcının sözü
    olarak taşınır. Kuyruk tek seferlik boşaltılır — bir kez söyleneni her turda
    tekrar etmek, onu sonsuz bir talimata çevirirdi. Kuyruk yoksa akış değişmez.
    """
    if queue is None or not queue.pending:
        return 0
    notlar = queue.drain()
    messages.extend(notlar)
    return len(notlar)


def _round_signals(
    deps: AgentDeps, state: _State, before: tuple[int, int, int, int]
) -> RoundSignals:
    """Turun sinyallerini önceki ölçümle farkını alarak topla.

    İkili "bir şey değişti mi" kararı, başarısız üç çağrıyla hiç çağrı yapmamayı
    aynı kefeye koyuyordu ve eşiği ayarlamak imkânsızdı. Sinyaller ayrıştırılınca
    budama kararı ölçülebilir ve ayarlanabilir olur.
    """
    simdi = _progress_marker(deps, state)
    return RoundSignals(
        mutations=max(0, simdi[1] - before[1]),
        new_reads=max(0, (simdi[0] - before[0]) - (simdi[1] - before[1])),
        failures=max(0, simdi[2] - before[2]),
        repeats=max(0, simdi[3] - before[3]),
    )


def _progress_marker(deps: AgentDeps, state: _State) -> tuple[int, int, int, int]:
    """Turun ilerleyip ilerlemediğini ölçen iki sayı.

    Başarılı araç sayısı VE dokunulan dosya sayısı birlikte bakılır: bir tur yalnızca
    okuma yapmış olabilir (dosya sayısı artmaz ama iş yapılmıştır) ya da yalnızca
    yazma (ikisi de artar). İkisi de sabit kaldıysa o turda hiçbir şey olmamıştır.
    """
    return (
        state.tool_calls_made - state.observation_calls,
        len(deps.tool_context.touched),
        state.failed_tool_calls,
        state.already_done_calls,
    )


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
    outcome = _outcome(text, messages, state, hit_step_limit=True, ok=False)
    # Sebep AZ ÖNCE yayınlandı. `final_text` modelin cevabıdır, hata metni
    # değildir; ikisini birden hata gibi basmak "✗ hata İş başarıyla
    # tamamlanmıştır" gibi kendiyle çelişen satırlar üretiyordu (ölçüldü).
    outcome.budget_stopped = True
    outcome.stop_reason = reason.value
    outcome.todos = deps.tool_context.todos.items
    return outcome


def _halt_local(
    final_text: str,
    messages: list[Message],
    state: _State,
    budget: TurnBudget,
    reason: BudgetStop,
    deps: AgentDeps,
) -> AgentOutcome:
    """Yalnız bu ``_drive`` çağrısının sınırında dur; dış kapıları açık bırak.

    Web yürütme politikasındaki model/araç sınırları çağrı-yereldir. Doğrulama ve
    öz-denetim alt turları aynı ``TurnBudget`` nesnesini paylaşsa da bu yerel sınıra
    çarpılması, çalışma alanının son post-condition doğrulamasını engellememelidir.
    Gerçek tur-geneli sayaç ve süre sınırları `_halt` üzerinden otorite olmaya devam
    eder.
    """
    deps.publisher.publish(
        TurnBudgetExhausted(
            reason=reason.value,
            model_calls=budget.model_calls,
            tool_rounds=state.tool_rounds,
            idle_rounds=budget.idle_rounds,
            elapsed_s=budget.elapsed_s,
        )
    )
    text = final_text.strip()
    outcome = _outcome(text, messages, state, hit_step_limit=True, ok=False)
    outcome.budget_stopped = True
    outcome.stop_reason = reason.value
    outcome.todos = deps.tool_context.todos.items
    return outcome


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


def _note_tool_use(
    state: _State,
    name: str,
    tool: Tool | None,
    *,
    ok: bool,
    arguments: dict[str, object] | None = None,
    output: str = "",
    job_completion: JobCompletion | None = None,
    is_observation: bool = False,
    workspace_effect: WorkspaceEffect | None = None,
    source_before: str = "",
    source_after: str = "",
    environment: EvidenceEnvironment | None = None,
    call_id: str = "",
) -> None:
    """Denenen araç çağrısını sırayla kaydet (adım ve tur kanıtı)."""
    state.tool_uses.append(
        ToolUse(
            name=name,
            ok=ok,
            mutating=bool(tool is not None and tool.mutating and not is_observation),
            arguments=arguments or {},
            output=output,
            job_completion=job_completion,
            workspace_effect=workspace_effect,
            source_digest=source_before,
            source_after_digest=source_after,
            environment=environment,
            call_id=call_id,
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
        answer_streamed=state.answer_streamed,
        wrong_workspace=state.warned_wrong_workspace,
        tool_uses=tuple(state.tool_uses),
        already_done_calls=state.already_done_calls,
        stalled=state.stalled,
    )


_WORKSPACE_READ_TOOLS = frozenset(
    {
        "read_file",
        "view_file",
        "list_dir",
        "search_code",
        "grep_search",
        "search_codebase",
        "glob",
        "git",
    }
)


def _missing_source_evidence(execution: ExecutionPolicy, budget: TurnBudget) -> bool:
    if not execution.required_web_urls:
        from .research_scope import web_lookup_observed

        return execution.requires_web_lookup and not web_lookup_observed(
            budget.successful_tool_evidence
        )
    from .research_scope import requested_sources_read

    return not requested_sources_read(
        execution.required_web_urls,
        budget.successful_tool_evidence,
        observed_sources=getattr(budget, "successful_source_reads", ()),
    )


def _evidence_recovery_effect(execution: ExecutionPolicy, budget: TurnBudget) -> str | None:
    return (
        "web_lookup" if _missing_source_evidence(execution, budget) else execution.required_effect
    )


def _tool_evidence_satisfied(execution: ExecutionPolicy, budget: TurnBudget) -> bool:
    """Gerçek eylem isteği başarılı bir araç sonucu ile kanıtlandı mı?

    Kanıt BÜTÇEDEN okunur, turun yerel durumundan değil: doğrulama düzeltmesi ve
    öz-denetim `run_agent`'ı yeniden çağırır ve taze bir durumla başlar. Kanıt orada
    tutulsaydı iç içe tur, ana turun zaten yaptığı işi baştan kanıtlamak zorunda
    kalırdı — ölçüldü, model işi yapmışken düzeltici tur "işlem tamamlanmadı" dedi.
    """

    effect = execution.required_effect
    if _missing_source_evidence(execution, budget):
        return False
    if effect is None:
        return True
    evidence = budget.successful_tool_evidence
    if effect == "git_push":
        return any(
            tool_family(name) is ToolFamily.SHELL and _shell_contains_git_action(args, "push")
            for name, args, _ in evidence
        )
    if effect == "git_commit":
        return any(
            tool_family(name) is ToolFamily.SHELL and _shell_contains_git_action(args, "commit")
            for name, args, _ in evidence
        )
    if effect == "shell_action":
        return any(tool_family(name) is ToolFamily.SHELL for name, _, _ in evidence)
    if effect == "workspace_mutation":
        return any(mutating for _, _, mutating in evidence)
    if effect == "web_lookup":
        if execution.required_web_urls:
            from .research_scope import requested_sources_read

            return requested_sources_read(
                execution.required_web_urls,
                evidence,
                observed_sources=getattr(budget, "successful_source_reads", ()),
            )
        # Araç AİLESİNDEN okunur (A2-21): sabit üç ad `site_crawl`/`site_design`
        # gibi arama araçlarını kanıt saymıyordu. İndirme arama değildir.
        from .research_scope import web_lookup_observed

        return web_lookup_observed(evidence)
    if effect.startswith("file:"):
        # Dosya teslim eden adımın kanıtı DEĞİŞTİREN bir araçtır.
        #
        # Eskiden `file:` etkisi son satıra düşüyordu ve "herhangi bir başarılı
        # araç" kanıt sayılıyordu. Ölçüldü (13 Eylül, Godot koşusu): adım
        # `file:ASSETS.json` bekliyordu, model tek bir `web_search` yaptı, sonra
        # "assetleri bulup indireceğim" diyen bir metinle turu bitirdi ve kanıt
        # kapısı bunu YETERLİ saydı. Hiçbir dosya yazılmadı, hiçbir yeniden istem
        # yapılmadı; adım doğrulamada düştü ve kurtarma hakkı boşa gitti.
        return any(mutating for _, _, mutating in evidence)
    if effect == "workspace_read":
        # Ölçüldü (30 Ekim, A2-21): 8 adlık sabit liste `bash cat`/`ls` ile okuyan
        # ya da `grep_search`/`search_codebase` dışı arama ailesini kanıt saymıyor,
        # kanıt kapısı boşuna yeniden istem yapıp turu `ok=False` bitiriyordu.
        return any(
            name in _WORKSPACE_READ_TOOLS
            or (
                not mutating
                and (
                    tool_family(name) in {ToolFamily.FILES, ToolFamily.SEARCH, ToolFamily.VCS}
                    or _reads_only(name, args)
                )
            )
            for name, args, mutating in evidence
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


async def _publish_intro(
    task: str,
    messages: list[Message],
    deps: AgentDeps,
    execution: ExecutionPolicy,
    tool_names: tuple[str, ...],
) -> None:
    """Karmaşık işte, işe başlamadan kullanıcıya kısa giriş paragrafı yaz.

    Yalnız API modellerinde istenir: web modelleri metni zaten kendileri yazar
    ve her web çağrısı onlarca saniye sürer. Giriş modele de not olarak verilir
    ki aynı cümleleri tekrarlamasın.
    """
    if not execution.complex_task or execution.is_web:
        return
    intro = await intro_paragraph(
        task, _active_spec(deps, execution), deps.config, deps.publisher, tool_names
    )
    if not intro:
        return
    deps.publisher.publish(NarrationPublished(text=intro))
    messages.append(
        Message(
            "user",
            f"FUSION_NOT: Kullanıcıya şu girişi zaten yazdın; tekrar etme, işe başla:\n{intro}",
            harness_note=True,
        )
    )


def _hand_off_to_apprentice(
    task: str, selected: ModelSpec, deps: AgentDeps, *, plan_mode: bool
) -> bool:
    """Seçili model yazamıyor ama görev yazma istiyorsa turu çırağa devret.

    Yalnız yetenek kısıtında devredilir; kullanıcı kipi (sohbet, plan) ya da
    salt okuma isteği devri tetiklemez. Yapılandırma değişmez, devir tur kapsamlıdır.
    """
    execution = deps.execution
    if (
        execution is None
        or plan_mode
        or execution.allow_mutation
        or not execution.mutation_blocked_by_capability
        or execution.required_effect != EffectKind.WORKSPACE_MUTATION.value
    ):
        return False
    apprentice = apprentice_spec(deps.config)
    if apprentice is None:
        return False
    teacher = teacher_for_turn(deps.config, selected)
    if teacher is not None and deps.config.teacher is None:
        deps.config = replace(deps.config, teacher=teacher)
    deps.active_model_override = apprentice
    deps.execution = policy_for(deps.config, apprentice, task)
    deps.publisher.publish(
        ApprenticeHandoff(
            selected_model=selected.model,
            apprentice_model=apprentice.model,
            teacher_model=teacher.model if teacher is not None else "",
        )
    )
    return True


def _active_spec(deps: AgentDeps, execution: ExecutionPolicy) -> ModelSpec:
    """Bu çağrıda kullanılacak model.

    Takılan adım bir üst modele yükselir: aynı modelle aynı duvara çarpmak yerine
    zincirde yukarı kayılır. `strict` rolde kullanıcının seçimi korunur.
    """
    return deps.active_model_override or escalated_spec(
        select_agent_spec(deps.config, deps.task_type, requirements=deps.task_requirements),
        execution.escalation,
    )


#: Geçici model hatasında (hız sınırı, sunucu hatası, zaman aşımı) varsayılan yeniden
#: deneme sayısı; asıl değer `runtime.model_retry_attempts`tan okunur.
#
# Tarihçe: Claude Code belgesi (code.claude.com/docs/en/errors) 10 kereye kadar üstel
# geri çekilme der. Ölçüldü (28 Eylül): Fusion aynı modeli yalnız 3 kez deniyordu ve
# 28 dakikalık iş NIM'in 429'uyla bitti; sayı 10'a çıkarıldı. Ölçüldü (30 Ekim, Z1-35):
# 10 deneme ≈ 5 dk boş bekleme demek; oysa 429'da zincirdeki sonraki yedeğe BEKLEMEDEN
# geçilir (`providers/chain.py` `yield_on_rate_limit`) ve yedek zinciri artık tanımlı.
# Kalan beklemeler yalnız TÜM zincir düştüğünde işler → 4 deneme + hız sınırında uzun
# taban (aşağıda) bir dakikalık NIM penceresini kapsar, uzun iş yine düşmez.
MAX_TRANSIENT_RETRIES = 4
#: Üstel geri çekilmenin ilk beklemesi ve tavanı (sn). Tavan, NIM'in dakikalık hız
#: sınırı penceresidir (60 sn / 40 istek, bkz. `defaults.yaml` `retry_delays_s`):
#: daha uzun beklemek sınırın sıfırlanmasından sonra boşuna vakit kaybettirir.
RETRY_BASE_DELAY_S = 2.0
#: Hız sınırında (429) ilk bekleme: kısa beklemeler pencereyi aşmaz, aynı 429'u tekrar
#: yer. 10, 20, 40, 60 → dört denemede ≈130 sn, bir dakikalık pencereyi iki kez kapsar.
RATE_LIMIT_BASE_DELAY_S = 10.0
#: Çıktı bütçesinin en fazla kaç katına büyütüleceği. 4: varsayılan bütçe düşünen
#: modelin uzun bir planı da yazmasına yeter; daha fazlası tek çağrıyı dakikalarca
#: uzatır ve bağlam penceresini zorlar.
MAX_TOKENS_ESCALATION = 4
RETRY_MAX_DELAY_S = 60.0


class _CallTimeoutError(Exception):
    """Model çağrısı tüm denemelerde süresinde tamamlanmadı."""

    def __init__(self, seconds: float) -> None:
        super().__init__(seconds)
        self.seconds = seconds


#: Süre sınırında bitmeyen çağrıdan sonra modele eklenen not. Aynı isteği aynen yinelemek
#: aynı sonucu verir. Ölçüldü (2 Ekim 2026, NIM Nemotron 3 Ultra): araç çağrısı parça
#: parça akmıyor (250 satırlık dosya 181 sn tek sessizlik); tema dosyası yazan çağrı 600 sn
#: sınırını iki kez aştı ve her seferinde baştan başladı — 20 dakikada tek dosya yazılamadı.
SHORTER_AFTER_TIMEOUT_NOTE = (
    "FUSION_NOT: Önceki cevabın süre sınırında tamamlanmadı; büyük olasılıkla tek çağrıda "
    "çok uzun bir içerik yazıyordun. Şimdi KISA bir adım at: tek çağrıda en fazla ~100 "
    "satır yaz, büyük dosyayı birden çok dosyaya böl ya da önce iskeleti yazıp sonra "
    "edit_file ile bölüm bölüm ekle."
)


def retry_delay_s(attempt: int, *, rate_limited: bool = False) -> float:
    """`attempt`. yeniden denemeden önceki bekleme (0'dan başlar).

    Hız sınırında (`rate_limited`) taban uzundur: dakikalık pencerenin sıfırlanması
    beklenir, 2 sn sonra aynı 429'a çarpmanın anlamı yoktur.
    """
    base = RATE_LIMIT_BASE_DELAY_S if rate_limited else RETRY_BASE_DELAY_S
    return min(base * float(2**attempt), RETRY_MAX_DELAY_S)


async def _call_with_retries(
    messages: list[Message],
    deps: AgentDeps,
    registry: ToolRegistry,
    allowed_tools: set[str] | None,
    *,
    state: _State,
    execution: ExecutionPolicy,
) -> ModelResult:
    """Modeli çağır; geçici hatada üstel geri çekilmeyle yeniden dene.

    Metin akmış bir çağrı yeniden DENENMEZ: ekrandaki cevabı ikinci kez baştan
    yazdırırdı. Kalıcı hata (olmayan model, geçersiz anahtar, günlük kota) da
    denenmez: beklemek onu çözmez.
    """
    budget = deps.require_budget()
    attempt = 0
    while True:
        remaining = budget.remaining_s()
        if remaining is not None and remaining <= 0:
            raise _CallTimeoutError(budget.total_timeout_s or 0.0)
        call_timeout = (
            min(deps.config.runtime.request_timeout_s, remaining)
            if remaining
            else deps.config.runtime.request_timeout_s
        )
        # Mutlak tur sınırı varsa dış sınır odur: yazmaya devam eden cevap kesilmez,
        # sessiz kalan akışı parça başı sınır keser. Sınır yoksa (CLI) sonsuza dek
        # damlayan akışa karşı zincir uzunluğuyla büyüyen eski üst sınır korunur.
        attempts = 1 + len(_active_spec(deps, execution).fallback)
        chain_timeout = remaining if remaining else call_timeout * attempts
        state.call_streamed = False
        state.call_chunks = 0
        state.unresponsive_reason = ""
        result: ModelResult | None = None
        try:
            async with asyncio.timeout(max(0.01, chain_timeout)):
                result = await _call_model(
                    messages,
                    deps,
                    registry,
                    allowed_tools,
                    state=state,
                    execution=execution,
                    offer_tools=execution.offer_tools,
                    timeout_s=call_timeout,
                )
        except TimeoutError:
            result = None
        if (
            result is not None
            and result.truncated
            and not result.is_usable
            and state.max_tokens_scale < MAX_TOKENS_ESCALATION
        ):
            # Aynı bütçeyle tekrar denemek aynı sonucu verir (model yine düşünmeye
            # harcar). Ölçüldü (30 Eylül): ilk tur "çıktı bütçesi doldu" ile bitti ve
            # kullanıcıya ayar değiştirmesi söylendi. Bütçe büyütülüp hemen denenir.
            state.max_tokens_scale *= 2
            # Yalnız bütçeyi büyütmek yetmedi. Ölçüldü (3 Ekim 2026, 14. kabul koşusu):
            # 8192 token düşünmeyle bitti, 16384 ile aynı çağrı 600 sn sınırını aştı.
            # Bundan sonra düşünme yoğunluğu düşürülür ve modele kısa adım notu gider.
            state.reasoning_relief = True
            if not any(m.content == SHORTER_AFTER_TIMEOUT_NOTE for m in messages):
                messages.append(Message("user", SHORTER_AFTER_TIMEOUT_NOTE, harness_note=True))
            deps.publisher.publish(
                StatusChanged(
                    "Model çıktı bütçesini düşünmeye harcadı; bütçe "
                    f"{state.max_tokens_scale} katıyla ve düşük düşünme yoğunluğuyla "
                    "yeniden deneniyor"
                )
            )
            continue
        # Boş (`ok` ama kullanılamaz) ve `TOOL_CALL_*` sözleşme hatalı yanıt aynen
        # tekrar göndermekle düzelmez; `_drive` yansıtıcı notla yeniden ister.
        # Ölçüldü (29 Ekim, A2-03): bu yanıtlar not eklenmeden üstel geri çekilmeyle
        # 10 kereye kadar (~5-6 dk) aynen yeniden gönderiliyordu.
        deterministic_bad = result is not None and (
            _is_tool_contract_error(result.error) or (result.ok and not result.is_usable)
        )
        retryable = not state.call_streamed and (
            result is None
            or (
                not result.is_usable
                and not deterministic_bad
                and not is_permanent_error(result.error)
            )
        )
        out_of_time = budget.time_stop_reason() is not None
        max_retries = deps.config.runtime.model_retry_attempts
        if not retryable or attempt >= max_retries or out_of_time:
            if result is None:
                raise _CallTimeoutError(call_timeout)
            return result
        delay = retry_delay_s(
            attempt, rate_limited=result is not None and is_rate_limit_error(result.error)
        )
        attempt += 1
        if result is None and not any(m.content == SHORTER_AFTER_TIMEOUT_NOTE for m in messages):
            messages.append(Message("user", SHORTER_AFTER_TIMEOUT_NOTE, harness_note=True))
        if result is not None:
            neden = _short_reason(result.error)
        elif state.unresponsive_reason:
            neden = f"yanıt vermiyor, sunucu sağlıksız ({state.unresponsive_reason})"
        else:
            neden = f"yanıt vermedi ({state.call_chunks} akış parçası geldi)"
        deps.publisher.publish(
            StatusChanged(
                f"Model geçici olarak {neden}; {delay:g} sn sonra yeniden deneniyor "
                f"· deneme {attempt}/{max_retries}"
            )
        )
        remaining = budget.remaining_s()
        await _retry_sleep(min(delay, max(0.0, remaining)) if remaining is not None else delay)


async def _retry_sleep(delay_s: float) -> None:
    """Yeniden denemeden önce bekle (testler bu fonksiyonu sahtesiyle değiştirir)."""
    await asyncio.sleep(delay_s)


_SERVER_ERROR_CODE = re.compile(r"(?<!\d)(?:500|502|503|504|529)(?!\d)")


def _short_reason(error: str | None) -> str:
    """Geçici hatanın kullanıcıya gösterilecek kısa adı; ham istisna metni gösterilmez."""
    lowered = (error or "").lower()
    # "rate" alt dizgisi "generated"/"operate" içinde de geçer: bozuk bir istek hatası
    # "hız sınırı" diye etiketlenip 60 sn'lik bekleme döngüsüne giriyordu. Ortak,
    # dar sınıflandırma kullanılır.
    if is_rate_limit_error(error):
        return "hız sınırına takıldı"
    if "timeout" in lowered or "timed out" in lowered:
        return "zamanında yanıt vermedi"
    # Durum kodu SAYI SINIRIYLA aranır: "context length 50000", "port 5001" sunucu
    # hatası değildir (A2-24).
    if _SERVER_ERROR_CODE.search(lowered) or "overload" in lowered:
        return "sunucu hatası verdi"
    return "yanıt veremedi"


def _model_failure_message(error: str | None) -> str:
    """Tüm denemeler bitince kullanıcıya giden açıklama; ham istisna metni yerine.

    Ölçüldü (28 Eylül): tur "RateLimitError: litellm.RateLimitError: …
    Nvidia_nimException - Error code: 429" metniyle bitiyordu.
    """
    if not error:
        return "Model bir yanıt üretemedi. Farklı bir model seçip yeniden deneyebilirsin."
    if is_permanent_error(error):
        return (
            f"Model kullanılamıyor ({_short_reason(error)}). "
            "Farklı bir model seçip yeniden deneyebilirsin."
        )
    if _short_reason(error) == "yanıt veremedi":
        # Tanınmayan hata: sebebi saklamak kullanıcıyı çaresiz bırakır; ayrıntı eklenir.
        # Ham sağlayıcı hatası base URL/istek bilgisi taşıyabilir (A2-25).
        return f"Model yanıt veremedi: {redact(error)}"
    return (
        f"Model yeniden denemelere rağmen {_short_reason(error)}. "
        'Biraz sonra "devam et" yazarak kaldığın yerden sürdürebilir ya da farklı '
        "bir model seçebilirsin."
    )


def _publish_surface(
    deps: AgentDeps,
    registry: ToolRegistry,
    execution: ExecutionPolicy,
    offered_tools: tuple[dict[str, object], ...],
) -> None:
    """Modele gerçekten giden araç yüzeyini ölçüm izi olarak yayınla (güçlü modelde de)."""
    size = measure_surface(offered_tools)
    deps.publisher.publish(
        ToolSurfaceOffered(
            count=size.count,
            schema_chars=size.chars,
            registered=len(registry.advertised_names()),
            compact=execution.compact_tool_surface,
            profile="+".join(execution.tool_profiles),
            widened=WIDENED_KIND in deps.tool_context.task_kinds,
        )
    )


def _widen_profile_for(
    call_name: str, deps: AgentDeps, registry: ToolRegistry, execution: ExecutionPolicy
) -> None:
    """Profil dışı yerleşik araç adıyla çağrıldıysa yüzeyi bu tur için BİR KEZ genişlet.

    Çağrı reddedilmez (bkz. `tool_profiles`): yanlış sınıflanmış istek sessizce
    yapılamaz hale gelmesin. Sonraki model çağrısı sıkı yüzeyin tamamını sunar.
    """
    if not execution.tool_profiles:
        return
    kinds = deps.tool_context.task_kinds
    if (
        WIDENED_KIND in kinds
        or registry.get(call_name) is None
        or registry.is_remote(call_name)
        or call_name not in hidden_tools(execution.tool_profiles)
    ):
        return
    kinds.add(WIDENED_KIND)
    deps.publisher.publish(
        ToolProfileExpanded(tool=call_name, profile="+".join(execution.tool_profiles))
    )


_MODEL_IDENTITY_OPEN = "<fusion-model-identity>\n"
_MODEL_IDENTITY_CLOSE = "\n</fusion-model-identity>"


def _refresh_model_identity(messages: list[Message], spec: ModelSpec) -> None:
    """Bind harness identity to the already resolved provider request, not its default."""
    hint = identity_hint(spec.model)
    if spec.fallback:
        # The chain passes this same request to its leaves. The serving leaf is
        # known only after a result; calling the primary the current model lies
        # on a successful fallback, including a strict availability fallback.
        hint = (
            f"Bu çağrı için istenen birincil model `{spec.model}`. Yedek zinciri açık; "
            "isteği gerçekten yanıtlayacak model henüz doğrulanmadı. Kullanıcı model "
            "kimliğini sorarsa Fusion olduğunu söyle; birincil modeli kesin çalışan "
            "model diye sunma, teknik ayrıntı uydurma."
        )
    system = messages[0].content if messages and messages[0].role == "system" else ""
    before, separator, previous = system.rpartition("\n\n" + _MODEL_IDENTITY_OPEN)
    if separator and previous.endswith(_MODEL_IDENTITY_CLOSE):
        system = before
    elif system.startswith(_MODEL_IDENTITY_OPEN) and system.endswith(_MODEL_IDENTITY_CLOSE):
        system = ""
    if hint:
        block = _MODEL_IDENTITY_OPEN + hint + _MODEL_IDENTITY_CLOSE
        system = f"{system}\n\n{block}" if system else block
    if messages and messages[0].role == "system":
        messages[0] = replace(messages[0], content=system)
    elif system:
        messages.insert(0, Message("system", system))


async def _call_model(
    messages: list[Message],
    deps: AgentDeps,
    registry: ToolRegistry,
    allowed_tools: set[str] | None = None,
    *,
    state: _State,
    execution: ExecutionPolicy,
    offer_tools: bool = True,
    timeout_s: float | None = None,
) -> ModelResult:
    """Modeli akıtarak çağır; metin parçaları olay olarak yayınlanır."""
    runtime = deps.config.runtime
    spec = live_fallbacks(_active_spec(deps, execution), deps.config)
    if deps.invocation_budget is not None and not deps.invocation_budget.claim(spec):
        return ModelResult(
            name=spec.name,
            model=spec.model,
            text="",
            latency_ms=0,
            ok=False,
            error="Model çağrı bütçesi tükendi veya sabit model sözleşmesi değişti.",
        )
    _refresh_model_identity(messages, spec)
    offered_tools = (
        tuple(
            registry.schemas(
                # Araç araması (#258): ertelenmiş ve yüklenmemiş MCP şemaları gönderilmez.
                visible_tool_names(
                    _permitted(
                        allowed_tools,
                        registry,
                        execution,
                        deps.tool_context.task_kinds,
                        denied=surface_denied(deps, registry.names()),
                        task=_surface_task(messages),
                        phase=deps.tool_context.tool_phase,
                    ),
                    registry,
                    lambda: input_window_tokens(spec.model),
                    model=spec.model,
                ),
                edit_format=execution.edit_format,
            )
        )
        if offer_tools
        else ()
    )
    if offered_tools:
        _publish_surface(deps, registry, execution, offered_tools)
    await localization.refresh_prompt(messages, deps.tool_context)
    gorunum = _masked_view(messages, deps, spec)
    if gorunum.masked:
        deps.publisher.publish(
            ToolOutputsMasked(
                masked=gorunum.masked,
                newly_masked=gorunum.newly_masked,
                saved_chars=gorunum.saved_chars,
                window=runtime.tool_output_window,
            )
        )
    request = CompletionRequest(
        messages=tuple(gorunum.messages),
        temperature=runtime.temperature,
        max_tokens=runtime.max_tokens * state.max_tokens_scale,
        timeout_s=timeout_s or runtime.request_timeout_s,
        max_retries=runtime.max_retries,
        tools=offered_tools,
        reasoning_effort=effort_for_spec(
            spec,
            ReasoningEffort.LOW
            if state.reasoning_relief
            else (getattr(deps, "turn_effort_override", None) or runtime.reasoning_effort),
        ),
        disable_thinking=state.reasoning_relief,
        conversation_id=deps.conversation_id,
        edit_format=execution.edit_format,
        emulation_protocol=runtime.emulation_protocol,
        web_call_context=(
            WebCallContext(deps.conversation_id, deps.attempt_id, deps.attempt_id, "")
            if deps.conversation_id and deps.attempt_id
            else None
        ),
        answer_contract=render_answer_contract(
            tool_names(offered_tools), has_todos=bool(deps.tool_context.todos.items)
        ),
        prompt_cache_ttl=getattr(deps, "prompt_cache_ttl", "") or "",
    )
    desktop_observation = state.desktop_grounding.for_request(
        request.messages, deps.tool_context, deps.conversation_id, deps.attempt_id
    )
    provider = build_provider(
        spec,
        model_specs=configured_model_specs(deps.config),
        publisher=deps.publisher,
        retry_delays_s=runtime.retry_delays_s,
        channel=deps.channel,
        health=deps.health,
        web_sessions=web_registry_for(deps.config),
    )

    result: ModelResult | None = None
    # İlk gerçek yanıt için mutlak sınır; ardından iki parça arasındaki sessizlik
    # sınırı. Boş geçici parçalar (modelin düşünmesi) ilk sınırı uzatamaz.
    inactivity_s = request.timeout_s
    loop = asyncio.get_running_loop()

    async def _consume() -> None:
        nonlocal result
        async with asyncio.timeout(inactivity_s) as silence:
            async for item in provider.stream(request):
                if isinstance(item, StreamDone) or (
                    isinstance(item, TextChunk) and item.text and not item.provisional
                ):
                    silence.reschedule(loop.time() + inactivity_s)
                _observe_stream_item(item, state)
                if isinstance(item, StreamDone):
                    result = item.result

    if liveness.is_api_model(spec):
        await _consume_with_liveness(_consume, spec, state)
    else:
        await _consume()
    outcome = result or ModelResult(
        name=spec.name,
        model=spec.model,
        text="",
        latency_ms=0,
        ok=False,
        error="Model akışı sonuç üretmeden bitti.",
    )
    if runtime.prompt_manifest:
        from .context_budget import context_budget

        publish_manifest(
            request,
            outcome,
            deps.prompt_components,
            deps.publisher,
            profile=context_budget(deps.config, spec).profile
            if outcome.model == spec.model
            else None,
        )
    from ...config.model_lookup import model_spec_for

    served_spec = (
        spec
        if outcome.model == spec.model
        else model_spec_for(outcome.model, configured_model_specs(deps.config))
    )
    observed_spec = model_spec_for(outcome.served_by, configured_model_specs(deps.config))
    if observed_spec is not None:
        served_spec = observed_spec
    state.desktop_grounding.acknowledge(
        desktop_observation,
        usable=outcome.ok and outcome.is_usable,
        images_supported=desktop_observation is not None
        and served_spec is not None
        and capabilities_for(served_spec, deps.config.web_sessions).images,
        context=deps.tool_context,
        conversation_id=deps.conversation_id,
        attempt_id=deps.attempt_id,
    )
    return outcome


async def _consume_with_liveness(
    consume: Callable[[], Awaitable[None]], spec: ModelSpec, state: _State
) -> None:
    """Akışı tüket; hiç parça gelmeden sessizlik uzarsa sunucuyu yokla (bkz. `liveness`).

    Sunucu sağlıksızsa beklemeye son verilir ve `TimeoutError` yükselir: yeniden deneme
    döngüsü bunu geçici hata sayar ve nedeni durum mesajına yazar.
    """
    tuketici = asyncio.ensure_future(consume())
    bekci = asyncio.ensure_future(
        liveness.watch(lambda: state.call_chunks, liveness.ping_for(spec))
    )
    try:
        await asyncio.wait({tuketici, bekci}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        kalan = [gorev for gorev in (tuketici, bekci) if not gorev.done()]
        # `bekci.result()` istisna fırlatırsa aşağıdaki iptal satırlarına hiç
        # ulaşılmaz ve tüketici askıda kalırdı (A2-17): önce durum kontrol edilir.
        if (
            bekci.done()
            and not tuketici.done()
            and not bekci.cancelled()
            and bekci.exception() is None
        ):
            state.unresponsive_reason = bekci.result()
        for gorev in kalan:
            gorev.cancel()
        await asyncio.gather(*kalan, return_exceptions=True)
    if state.unresponsive_reason:
        raise TimeoutError(state.unresponsive_reason)
    tuketici.result()


def _observe_stream_item(item: object, state: _State) -> None:
    # Beyan değil GÖZLEM: metin gerçekten aktıysa turun cevabı ekrana ulaşmış
    # demektir ve `TurnAnswered` ikinci kez basmamalıdır. Sarmalayıcı zinciri ne
    # olursa olsun (yedek, tekrar deneme) bu ölçüm doğrudur — sağlayıcının
    # "akıtır mıyım" beyanına güvenmek yanıltıcı olurdu.
    if isinstance(item, TextChunk):
        state.call_chunks += 1
    if isinstance(item, TextChunk) and not item.provisional:
        state.answer_streamed = True
        state.call_streamed = True


#: Araç kısıtlaması olsa bile daima sunulan araçlar. Bunlar olmadan agent planlayamaz
#: ya da belirsizliği gideremez.
#: Denetlenecek dosya bırakmayan, uzak sayfada çalışan araçların ad önekleri.
_BROWSER_TOOL_PREFIXES = ("chrome_", "claude-in-chrome__", "browser_")
ALWAYS_ALLOWED = frozenset({"todo_write", "ask_user", "find_skill", "read_skill", "recall_lessons"})

#: Web taşımasında bir okumada gösterilecek en fazla satır (SWE-agent ölçümü).
WEB_READ_WINDOW = 100


#: Yalnız belirli istek türünde modele sunulan araçlar → gereken tür (`task_kinds`).
#: Ölçüldü (8 Ekim 2026): üç Remotion aracı her istekte emülasyon istemini 10.500'den
#: 11.943 karaktere çıkarıyordu; ücretsiz küçük modelde istem uzunluğu kalitedir.
SCOPED_TOOLS: dict[str, str] = {
    "scaffold_remotion": "remotion",
    "revise_remotion_scenes": "remotion",
    "render_remotion": "remotion",
    # Arka plan masaüstü araçları yalnız masaüstü/pencere işinde sunulur (istem bütçesi).
    "desktop_background_windows": "masaustu",
    "desktop_background_inspect": "masaustu",
    "desktop_background_screenshot": "masaustu",
    "desktop_background_action": "masaustu",
    # Toplu uygulama onayı (#426) yalnız masaüstü işinde sunulur (istem bütçesi).
    "desktop_request_access": "masaustu",
    # Chrome betik ve toplu eylem (#432) yalnız Chrome/tarayıcı işinde (istem bütçesi).
    "chrome_javascript": "masaustu",
    "chrome_batch": "masaustu",
    # Claude in Chrome'un çekirdek dışı araçları (#431) yalnız Chrome/tarayıcı işinde.
    **dict.fromkeys(sorted(CLAUDE_CHROME_SCOPED), "masaustu"),
    # Çalışma ağacı araçları Claude gibi her turda (#342); emülasyon isteminde imzayla
    # sunulur (`core.tool_emulation.DEFERRED_TOOL_NAMES`).
    # Planı onaya sunma aracı yalnız plan kipindeki turda (#317).
    "exit_plan_mode": "plan",
    # Arka plan görevleri / oturumlar arası mesaj (P-048, P-060): yalnız ilgili turda.
    "list_agents": "arka_plan",
    "send_message": "arka_plan",
    "stop_agent": "arka_plan",
    # Ekip ve iş akışı araçları yalnız o türden istekte (P-061/P-062).
    **ORCHESTRATION_SCOPED_TOOLS,
}


def _surface_task(messages: Sequence[Message]) -> str:
    """Araç ilgisini önceki görevler yerine güncel kullanıcı adımından hesapla."""
    return next((message.content for message in reversed(messages) if message.role == "user"), "")


def _permitted(
    allowed_tools: set[str] | None,
    registry: ToolRegistry,
    execution: ExecutionPolicy,
    task_kinds: frozenset[str] | set[str] = frozenset(),
    denied: Collection[str] = (),
    task: str = "",
    phase: str = "",
) -> set[str] | None:
    """Modele sunulacak ve çalıştırılabilecek araç adlarını belirle.

    Mutation izni yoksa değiştirici araçların ŞEMASI hiç gönderilmez: modele
    yapamayacağı bir yeteneği göstermek, denemesine ve turu boşa harcamasına yol açar.
    Düzenleme sözleşmesi tüm sağlayıcılarda aynıdır (`edit_file` / `multi_edit` /
    `write_file`); sağlayıcıya göre şema daraltılmaz.
    """
    if allowed_tools is not None and not allowed_tools:
        return set()
    names = (
        set(registry.names())
        if allowed_tools is None
        else ((allowed_tools | ALWAYS_ALLOWED) & set(registry.names()))
    )
    if execution.allowed_tool_names is not None:
        names &= execution.allowed_tool_names
    names = {name for name in names if not prohibited_tool(name, execution.forbidden_tool_families)}
    if denied:
        # Yasak liste (`--disallowed-tools`) şema yüzeyinden düşer: salt-okunur araçta onay
        # politikası hiç çalışmadığı için tek güvenilir kapı burasıdır (31 Ekim).
        names = {name for name in names if not is_denied_tool(name, denied)}
    # Açıkça istenmiş araç (allowed_tools) türden bağımsız kalır.
    names = {
        name
        for name in names
        if name not in SCOPED_TOOLS
        or SCOPED_TOOLS[name] in task_kinds
        or (allowed_tools is not None and name in allowed_tools)
    }
    if execution.compact_tool_surface:
        names = narrow_to_compact_surface(
            names,
            registry,
            max_external_tools=execution.max_external_tools,
            task_kinds=task_kinds,
            explicit=allowed_tools,
            profiles=execution.tool_profiles,
            external_tool_selection=execution.external_tool_selection,
            task=task,
            phase=phase,
        )
    # Görev araçları modele göre (#329); açıkça istenen ad (`--tools`/`--allowedTools`) kalır.
    hidden_tasks = hidden_task_tools(getattr(execution, "task_tools", "todo"))
    names = {
        name
        for name in names
        if name not in hidden_tasks or (allowed_tools is not None and name in allowed_tools)
    }
    if not execution.allow_mutation:
        names = {
            name
            for name in names
            if not (registry.get(name) is not None and registry.get(name).mutating)  # type: ignore[union-attr]
        }
    return names


def _refusal_note(
    final_text: str,
    state: _State,
    execution: ExecutionPolicy,
    tools: set[str] | None,
) -> Message | None:
    """Araç varken hiçbirini denemeden verilen kalıp ret: modele bir kez araçlarını hatırlat.

    Ölçüldü (27 Eylül): tarayıcı görevinde Nemotron ve Gemini araç denemeden
    "dil modeliyim, yardımcı olamıyorum" dedi ve tur başarılı sayıldı.
    """
    if state.refusal_nudged or state.tool_rounds or not execution.offer_tools or not tools:
        return None
    if not looks_like_refusal(final_text):
        return None
    state.refusal_nudged = True
    return reflexion.refusal_note(sorted(tools))


def _auto_continue_note(
    final_text: str,
    deps: AgentDeps,
    state: _State,
    *,
    plan_mode: bool,
    execution: ExecutionPolicy,
    truncated: bool,
    task: str = "",
) -> Message | None:
    """Tur devam ettirilecekse modele enjekte edilecek notu döndür, yoksa `None`.

    Not TÜRÜ ayrılır: "işi yarım bıraktın" ile "iş yapmadan bana soru sordun" farklı
    davranışlardır ve modele farklı şey söylenmelidir.
    """
    if plan_mode:
        return None
    # Yanlış dizinde "devam et" demek, modeli iş UYDURMAYA iter. Doğru cevap
    # "bu dizinde o dosyalar yok" demektir ve o cevap zaten verilmiştir; onu
    # zorlamak turu kullanıcının istemediği bir işe çevirir (ölçüldü).
    if state.warned_wrong_workspace:
        return None
    # Taşıma bütünlüğü her teşhisin önündedir: kesilmiş yanıt, kapanmamış blok ve
    # boş yanıt farklı hamleler ister. Üçünü "işi yarım bıraktın" notuna bağlamak
    # ya yapılan işi çöpe atıyor ya da modele yanlış şeyi düzelttiriyordu.
    from .response_format import is_valid_json, requested_response_format

    structured = (
        not truncated and requested_response_format(task) == "json" and is_valid_json(final_text)
    )
    if not structured:
        butunluk = classify_response(final_text, truncated=truncated, has_tool_calls=False)
        tasima_notu = reflexion.integrity_note(butunluk)
        if tasima_notu is not None:
            return _spend(deps, tasima_notu)
    # Bloklayan doğrulama düzeltmesi araçsız kapanamaz; bu tek dal korunur (bkz.
    # `_never_acted`). Kapsamı büyüten genel dürtme kapıları (hiç çağrı yapmadan
    # soru sorma, keşifte takılma, "yarım kalmış gibi görünme") kaldırıldı: model
    # ne zaman araç kullanacağına, ne zaman bitireceğine kendi karar verir.
    if _never_acted(state, execution):
        state.never_acted_prompts += 1
        return _spend(deps, reflexion.verification_action_required_note())
    wanted = deps.tool_context.todos.has_pending
    return _spend(deps, reflexion.auto_continue_note()) if wanted else None


def _spend(deps: AgentDeps, note: Message) -> Message | None:
    """Devam hakkını harca ve notu döndür; hak kalmadıysa `None`.

    Hak yalnızca GERÇEKTEN devam edilecekse harcanır; sırayı tersine çevirmek
    devam etmeyen turlarda da bütçe yakardı.
    """
    bekleyen = deps.tool_context.todos.pending_count
    return note if deps.require_budget().take_auto_continue(pending_todos=bekleyen) else None


#: Aynı turda kaç başarısız değiştirici çağrıdan sonra çıkış yolu gösterilir.
#
# İki deneme normaldir (ilk `old` tutmaz, model düzeltir). Üçüncüde model artık
# yaklaşımını değiştirmiyor, aynı şeyi daha dar pencereyle tekrarlıyor.
MAX_FAILED_MUTATIONS_IN_ROW = 3
#: Toptan yazma çıkışının açıldığı başarısız düzenleme sayısı.
#
# Döngü notundan DAHA ERKEN açılır: boşta-tur kapısı üç ilerlemesiz turda turu
# öldürüyor ve çıkış üçüncüde açılırsa hiç kullanılamıyor (ölçüldü — model
# write_file'a kaçtı, engellendi, tur öldü). İki başarısız hedefli düzenleme,
# modelin 'old' metnini tutturamadığını göstermeye yeter.
MAX_EDITS_BEFORE_REWRITE = 2

#: Tamamı okunmuş bir dosyanın toptan yeniden yazılmasının serbest olduğu üst sınır.
#
# Kuralın gerekçesi hacimdir: "yüz satırlık bir dosyayı baştan üretmek modele yüz
# satırlık hata yüzeyi açar". Küçük dosyada o yüzey yoktur ve kural yalnızca
# maliyet üretir.
#
# Ölçüldü (6 Eylül, 24 görev × 3 koşu): engellenen 34 toptan yazmanın TAMAMI
# 1-45 satırlık dosyalardaydı; 34'ünün 28'i 12 satır ve altındaydı. Model her
# seferinde `replace_range`'e düşmek zorunda kaldı ve tek satırlık JSON'u satır
# aralığıyla onarmaya çalışırken tur harcadı. Yıkıcı başarısızlıkların ölçüldüğü
# rejim ise ~100 satırdı.
#
# Sınır, gözlenen meşru vakaların (45) üstüne, ölçülen yıkıcı rejimin (~100)
# belirgin altına konur.
MAX_LINES_FOR_FULL_REWRITE = 60
#: Döngü kapısının bir turda en fazla kaç kez konuşacağı.
MAX_EDIT_LOOP_PUSHES = 2


def _stuck_editing(state: _State, *, plan_mode: bool) -> bool:
    """Model aynı düzenlemeyi tekrar tekrar deneyip düşüyor mu?"""
    if plan_mode or state.edit_loop_pushes >= MAX_EDIT_LOOP_PUSHES:
        return False
    return state.failed_mutations_in_row >= MAX_FAILED_MUTATIONS_IN_ROW


#: Okuma araçları. Yanlış-dizin hipotezi yalnızca bunlara bakar.
_FILE_READ_TOOLS = frozenset({"read_file", "view_file"})
#: Kaç "dosya yok" hatasından sonra yanlış dizin hipotezi kurulur.
#
# İki hata rastlantı olabilir (model yanlış ad tahmin etti). Üçüncüde ve HİÇBİR
# dosya okunamamışken, en olası açıklama çalışma dizininin yanlış olmasıdır.
MAX_MISSING_READS = 3


def _looks_like_wrong_workspace(state: _State) -> bool:
    """Görevdeki dosyaların hiçbiri bu dizinde yok gibi mi görünüyor?

    Ölçüldü: kullanıcı fusion'ı yanlış klasörde açtı. Model dört dosyayı da
    bulamadı, sonra öz-denetim düzeltici turunda GÖREVİ TERK ETTİ ve kendine yeni
    iş uydurdu — o projenin README'sini okuyup "test paketini çalıştır" diye todo
    listesi yazdı. Kullanıcının sorduğu şeyle hiç ilgisi yoktu.

    Doğru davranış durmaktır: bu bir "yapılamayan iş"tir, uydurulacak bir iş değil.
    """
    if state.warned_wrong_workspace or state.successful_file_reads > 0:
        return False
    return len(state.missing_paths) >= MAX_MISSING_READS


def _repo_map_for_turn(deps: AgentDeps, task: str) -> str:
    """Kök tur için harita bloğu; bütçe ayardan, ölçüm izi `RepoMapBuilt` olarak yayınlanır."""
    root = deps.tool_context.root
    focus = task_focus(root, task) if deps.config.runtime.repo_map_focused else RepoMapFocus()
    harita = repo_map_with_stats(
        root,
        budget_chars=map_budget_for(deps.config),
        focus_paths=focus.paths,
        focus_symbols=focus.symbols,
    )
    if harita.stats is not None:
        deps.publisher.publish(RepoMapBuilt(**asdict(harita.stats)))
    return harita.text


def _inject_nested_instructions(messages: list[Message], deps: AgentDeps, state: _State) -> None:
    """Model alt klasördeki dosyaya eriştiyse o klasörün talimatlarını bir kez bağlama ekle.

    Not, araç sonuçlarının ARDINA harness notu olarak eklenir (araç sonucu bloğunu bölmez,
    maskelemeye girmez). Kök talimatı zaten yüklüdür; kök dışına çıkılmaz.
    """
    yollar, state.nested_candidates = state.nested_candidates, []
    if not yollar or not getattr(deps.config.runtime, "nested_instructions", True):
        return
    kok = deps.tool_context.root
    # `.claude/rules` içindeki `paths:` kuralları erişilen dosyaya uyarsa aynı notla gelir (P-016).
    kurallar = (
        discover_rules(kok, deps.home)
        if getattr(deps.config.runtime, "instruction_merge", True)
        else ()
    )

    def baglamda_var(rel: str) -> bool:
        isaret = nested_marker(rel) if not rel.startswith((".", "~")) else f'kaynak="{rel}"'
        return any(isaret in item.content for item in messages if item.role == "user")

    from .context_budget import context_budget
    from .nested_rules import max_chars_for_window

    try:
        sinir = max_chars_for_window(context_budget(deps.config, _context_spec(deps)).window_tokens)
    except (AttributeError, TypeError, ValueError):
        sinir = max_chars_for_window(None)
    managed_only = instruction_files_mode(kok, deps.home) == "managed-only"
    hedefler: list[Path] = []
    for ham in dict.fromkeys(yollar):
        hedef = resolve_access_path(deps.tool_context, ham)
        if hedef is None:
            continue
        hedefler.append(hedef)
        if managed_only:
            continue
        # `--add-dir` dizininin `paths` alanlı kuralları (#170; ortam değişkeni açıkken).
        ek_kurallar = extra_dir_rules.hits_for(
            tuple(getattr(deps.tool_context, "extra_roots", ()) or ()),
            hedef,
            loaded=state.nested_loaded,
            present=baglamda_var,
        )
        if (ek_notu := extra_dir_rules.note_for(ek_kurallar)) is not None:
            messages.append(ek_notu)
            instructions_hook.notify(
                getattr(deps, "hooks", None), [hit.event for hit in ek_kurallar]
            )
        yuk = load_nested_instructions(
            kok,
            hedef,
            loaded=state.nested_loaded,
            present=baglamda_var,
            rules=kurallar,
            max_chars=sinir,
        )
        if yuk is None:
            continue
        messages.append(yuk.message)
        deps.publisher.publish(
            NestedInstructionsLoaded(files=yuk.files, chars=yuk.chars, trigger=ham)
        )
        instructions_hook.notify(
            getattr(deps, "hooks", None),
            [instructions_hook.nested_event(kok, rel, str(hedef), kurallar) for rel in yuk.files],
        )
    # Monorepo alt klasörünün `.claude/skills` becerileri de bu anda kataloğa girer (P-052).
    beceri_notu = discover_nested_skills(deps.capabilities, kok, tuple(hedefler))
    if beceri_notu is not None:
        messages.append(beceri_notu)
    # `paths` alanlı beceriler eşleşen dosyaya erişilince etkinleşir (#161).
    yol_notu = skill_paths.activate_for(deps.capabilities, kok, tuple(hedefler))
    if yol_notu is not None:
        messages.append(yol_notu)


def _record_changes(messages: list[Message], deps: AgentDeps, state: _State) -> None:
    """Değişen dosyaları modele OLGU olarak hatırlat.

    Model kendi işini takip edemiyor: bir koşuda üç dosya oluşturup kapanışta
    "herhangi bir değişiklik yapılmamıştır" dedi, başka bir koşuda dokunmadığı
    dosyayı "güncelledim" dedi. Kayıt yalnızca liste BÜYÜDÜĞÜNDE eklenir; her
    turda tekrarlamak promptu şişirir.
    """
    yollar = deps.tool_context.changes.paths
    if len(yollar) == state.logged_changes:
        return
    state.logged_changes = len(yollar)
    from ...tools.files import display_path

    messages.append(
        reflexion.change_log_note(tuple(display_path(deps.tool_context, y) for y in yollar))
    )


def _never_acted(state: _State, execution: ExecutionPolicy) -> bool:
    """Bloklayan doğrulama düzeltmesi HİÇ araç çağırmadan turu kapatıyor mu?

    Yalnızca `require_local_mutation` (blocking verification correction) dalı
    kalır: bu alt tur gerçek bir mutation ÜRETMEK ZORUNDADIR, dış turun eski
    kanıtıyla kapanamaz. Genel "karmaşık görevde hiç araç çağırmadı" dürtüsü
    kaldırıldı (B4/A13): model ne zaman araç kullanacağına kendi karar verir ve
    araçsız bitirdiği bir tur, aksini gerektiren bir kapıya (kanıt kapısı,
    doğrulama düzeltmesi) çarpmıyorsa geçerli bir teslimdir.

    BİR KEZ değil İKİ KEZ konuşur (blocking correction'a özeldir): model ikinci
    kez de araçsız gelirse zorlamak çağrı harcamaktır; o noktada cevabı olduğu
    gibi teslim etmek dürüst olandır.
    """
    if not state.require_local_mutation:
        return False
    # Blocking verification correction dış turun eski evidence'ı ile kapanamaz;
    # BU alt tur gerçek bir mutation üretmelidir.
    if state.mutating_tool_calls_made > 0:
        return False
    if not execution.offer_tools:
        return False
    return state.never_acted_prompts < 2


def _exploration_note(
    state: _State,
    execution: ExecutionPolicy,
    *,
    plan_mode: bool,
    teacher_available: bool,
) -> str | None:
    """İstenen değişiklikte uzun salt-okuma döngüsünü bir kez kır."""
    if (
        plan_mode
        or state.internal
        or not execution.complex_task
        or not execution.allow_mutation
        or state.mutating_tool_calls_made
        or state.tool_calls_made < 5
        or state.exploration_pushes
    ):
        return None
    note = (
        "FUSION_NOT: Bu görevde en az 5 araç çağrısı yaptın ama henüz "
        "hiç dosya değiştirmedin. Gerekli bağlamı topladıysan incelediğin "
        "dosyalardan ilk somut değişikliği seç ve uygula. Bağlam eksikse "
        "yalnız gerekli hedefli okumayı tamamla."
    )
    if teacher_available and _teacher_stall_reason(state) is not None:
        note += (
            " Mimari karar veya doğrulama konusunda bir belirsizlik kaldıysa "
            "`ask_teacher` ile tek somut soru sor, cevabı değerlendir, ardından uygula."
        )
    return note


def _teacher_takeover_spec(
    deps: AgentDeps, state: _State, execution: ExecutionPolicy, *, auto_teacher: bool
) -> ModelSpec | None:
    """Başarılı öğütten sonra süren salt-okuma döngüsünü doğrulanmış modele devret."""
    threshold = deps.config.runtime.agent_teacher_takeover_tools
    if (
        not auto_teacher
        or not state.teacher_advice_ok
        or state.internal
        or (deps.budget is not None and deps.budget.stop is not None)
        or state.capability_wall
        or not execution.complex_task
        or not execution.allow_mutation
        or state.mutating_tool_calls_made
        or state.tool_calls_made < threshold
        or threshold <= 0
        or deps.active_model_override is not None
        or (
            execution.allowed_tool_names is not None
            and not execution.allowed_tool_names.intersection(
                {"write_file", "edit_file", "multi_edit", "run_shell"}
            )
        )
    ):
        return None
    selected = select_agent_spec(deps.config, deps.task_type, requirements=deps.task_requirements)
    teacher = deps.config.teacher
    if selected.strict or teacher is None or selected.model == teacher.model:
        return None
    verified = any(
        session.model == teacher.model
        and session.enabled
        and session.login_verified
        and session.tool_support == "emulated"
        and session.tool_eval_passed
        for session in deps.config.web_sessions
    )
    if not verified or not mutation_policy_for_model(deps.config, teacher.model).ok:
        return None
    return ModelSpec(name="ogretmen-agent", model=teacher.model, tags=("strict",))


def _teacher_stall_reason(state: _State) -> str | None:
    """Var olan hata ve tekrar sinyallerinden somut danışma nedeni çıkar."""
    if any(count >= _YINELENEN_HATA_ESIGI for count in state.repeated_failures.values()):
        return "aynı araç hatası tekrarlandı"
    if state.repeat_blocked:
        return "tekrar koruması aynı okumayı engelledi"
    if any(count >= SAME_OUTPUT_WARN_AT for count in state.same_output_counts.values()):
        return "farklı aramalar aynı sonucu üretti"
    if state.stalled:
        return "ilerleme yok uyarısı"
    return None


def _has_teacher_plan(deps: AgentDeps) -> bool:
    """Bu turda öğretmenden ya da hafızadan bir plan alındı mı?"""
    return deps.pending_teacher_plan is not None or deps.reused_teacher_lesson is not None


def _plateau_reason(state: _State, deps: AgentDeps, *, exploration_note: str | None) -> str | None:
    """Otomatik öğretmen danışması için somut takılma nedeni; yoksa None.

    Başarılı yeni okumalar ilerlemedir. Çağrı sayısı ve henüz değişiklik
    yapılmaması, plan olup olmamasından bağımsız olarak takılma kanıtı değildir.
    """
    return _teacher_stall_reason(state)


def _plateau_question(deps: AgentDeps, reason: str, state: _State | None = None) -> str:
    """Takılma anına özel öğretmen sorusu.

    Takılma bir HATAYSA soru o hatayı taşır. Ölçüldü (2 Ekim, kabul koşusu): model
    "Access denied" hatasını üç kez aldı; öğretmene "çok dosyalı göreve başlarken ilk
    değişiklik ne olmalı?" diye genel bir soru gitti ve hata hiç söylenmedi.
    """
    hata = _top_failure(state) if state is not None else None
    if hata is not None:
        arac, imza, sayi = hata
        return (
            f"`{arac}` şu hatayı {sayi} kez verdi ve aşamadım: {redact(imza)[:300]}. Kök neden ne "
            "olabilir ve görevi sürdürmek için SIRADAKİ SOMUT adım (komut/araç) ne? Kısa cevap ver."
        )
    if _has_teacher_plan(deps):
        return (
            f"Önceki planı uygularken takıldım: {reason}. Bu takılmayı aşmak için "
            "şimdi hangi somut adımı atmalıyım? Kısa, uygulanabilir cevap ver."
        )
    return (
        f"Bu görevde takıldım: {reason}. Görevi sürdürmek için şimdi hangi somut "
        "adımı atmalı ve sonucu nasıl doğrulamalıyım? Kısa, uygulanabilir cevap ver."
    )


def _top_failure(state: _State) -> tuple[str, str, int] | None:
    """En çok yinelenen araç hatası (araç, hata satırı, sayı); eşik altındaysa None."""
    if not state.repeated_failures:
        return None
    (arac, imza), sayi = max(state.repeated_failures.items(), key=lambda item: item[1])
    return (arac, imza, sayi) if sayi >= _YINELENEN_HATA_ESIGI else None


async def _consult_teacher_on_plateau(
    messages: list[Message],
    deps: AgentDeps,
    registry: ToolRegistry,
    state: _State,
    *,
    reason: str = "okuma ve arama adımlarında ilerleme yok",
) -> None:
    """Ask the configured web teacher once when a complex task stalls in reading.

    The task excerpt is bounded and redacted; source file contents are not copied
    into the brief. The existing ``teacherless`` setting disables the tool.
    """
    phase_deadline = _automatic_phase_deadline(deps)
    if deps.budget is not None and (remaining := deps.budget.remaining_s()) is not None:
        phase_deadline = min(
            phase_deadline, asyncio.get_running_loop().time() + max(0.0, remaining) / 4
        )
    if _phase_expired(phase_deadline):
        _notify_phase_expired(deps)
        return
    original_task = next(
        (
            message.content
            for message in reversed(messages)
            if message.role == "user" and not message.harness_note
        ),
        "",
    )
    args: dict[str, object] = {
        "question": _plateau_question(deps, reason, state),
        "durum": f"Görev özeti: {redact(original_task)[:700]}",
        "denenenler": (
            f"Ajan {state.tool_calls_made} araç çağrısı yaptı. Takılma nedeni: {reason}."
        ),
    }
    call = ToolCall(
        id=f"fusion-auto-teacher-{state.model_calls_made}",
        name="ask_teacher",
        arguments=json.dumps(args, ensure_ascii=False),
    )
    messages.append(Message("assistant", "", tool_calls=(call,)))
    task = asyncio.current_task()
    cancellation_count = task.cancelling() if task is not None else 0
    try:
        async with asyncio.timeout_at(phase_deadline):
            result = await registry.execute("ask_teacher", args, deps.tool_context)
    except TimeoutError:
        result = ToolResult.failure("Öğretmen yanıtı süre sınırında tamamlanmadı.")
    finally:
        if task is not None and task.cancelling() > cancellation_count:
            raise asyncio.CancelledError
    if _phase_expired(phase_deadline):
        _notify_phase_expired(deps)
        result = ToolResult.failure("Otomatik öğretmen danışmasının süre bütçesi doldu.")
    state.tool_calls_made += 1
    state.tool_rounds += 1
    if not result.ok:
        state.failed_tool_calls += 1
    else:
        state.teacher_advice_ok = True
    _note_tool_use(
        state,
        "ask_teacher",
        registry.get("ask_teacher"),
        ok=result.ok,
        arguments=args,
        output=result.output,
        call_id=call.id,
    )
    deps.publisher.publish(
        ToolExecuted(
            call_id=call.id,
            name="ask_teacher",
            args={"question": args["question"]},
            outcome=ToolOutcome.OK if result.ok else ToolOutcome.FAILED,
            output=result.output,
        )
    )
    messages.append(
        Message("tool", result.output, tool_call_id=call.id, name="ask_teacher", ok=result.ok)
    )


def _targeted_edit_required(
    name: str,
    args: dict[str, object],
    deps: AgentDeps,
    execution: ExecutionPolicy,
    state: _State,
) -> list[str]:
    """Taklit araç kullanan modelde var olan dosya toptan yeniden yazılamaz.

    Ölçüldü (Gemini web, aynı görev altı koşu): yıkıcı başarısızlıkların HEPSİNDE
    `write_file` vardı — bozuk sözdizimi, 13 ruff hatası, toplanamayan test dosyası.
    Yalnızca `edit_file` kullanan koşular eksik kalabildi ama kodu hiç bozmadı.

    Sebep yapısal: yüz satırlık bir dosyayı baştan üretmek modele yüz satırlık hata
    yüzeyi açar, hedefli düzenleme birkaç satırlık. Ücretsiz bir web modeli o yüzeyi
    tutarlı biçimde temiz geçemiyor.

    Karar MOTOR katmanında verilir çünkü sağlayıcı politikasıdır; `files.py`
    sağlayıcıdan habersiz kalır. Yeni dosya yazmak serbesttir — kısıt yalnızca var
    olan bir dosyanın ÜZERİNE yazmaya karşıdır.

    Kısıt agent'ın BU TURDA kendi oluşturduğu dosyayı kapsamaz. Ölçülen ölü kilit:
    `scaffold_web` iskeleyi diske yazıyor ve "şimdi bunları DOLDUR" diyor; ama iskele
    dosyasını doldurmak tanımı gereği toptan yazmadır ve kural onu engelliyordu.
    Model `write_file` deneyip bloklanıyor, `edit_file` deneyip 'old' metnini
    tutturamıyor, içeriği öğrenmek için yeniden okumaya kalkınca tekrar kapısına
    takılıyor ve tur "ilerleme yok" ile ölüyordu. Kuralın gerekçesi (kullanıcının
    kodunu koru) dakikalar önce agent'ın kendi yazdığı yer tutucu dosyada geçersizdir.
    """
    if not execution.is_web or name not in _FULL_WRITE_TOOLS:
        return []
    raw = args.get("path")
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        hedef = resolve_path(deps.tool_context, raw)
    except FusionError:
        return []
    if not hedef.exists():
        return []
    if deps.tool_context.changes.was_created_this_turn(hedef):
        return []
    if _rewrite_is_last_resort(hedef, deps, state):
        return []
    satir = _line_count(hedef)
    if satir <= MAX_LINES_FOR_FULL_REWRITE:
        # Küçük dosyada çıkış yolu VARDIR ve söylenmelidir: tamamını okuduktan
        # sonra toptan yazma serbest (bkz. `_rewrite_is_last_resort`).
        #
        # Ölçüldü (13 Eylül, koşu 27): mesaj yalnız kaldırılan `replace_range`
        # aracını öneriyordu. Model `scenes/main.tscn` için `write_file` denedi,
        # engellendi, `edit_file` ile boş 'old' gönderdi, tekrar `write_file`
        # denedi ve tekrar kapısına takıldı; adım bütçesi doldu, sahne hiç
        # yazılamadı. Sahne dosyası satır satır yamanacak bir metin değildir,
        # yeniden üretilir.
        return [
            f"'{raw}' zaten var ({satir} satır) ve İÇERİĞİNİ BU ADIMDA OKUMADIN. "
            "Önce `read_file` ile TAMAMINI oku; tamamını gördükten sonra `write_file` "
            "ile yeniden yazmana izin verilir. Yalnız küçük bir parça değişecekse "
            "`edit_file` ile o parçayı gönder."
        ]
    return [
        f"'{raw}' zaten var ve {satir} satır. Var olan dosyayı toptan yeniden yazma — "
        "önce read_file ile ilgili satırları gör, sonra edit_file ile YALNIZCA değişecek "
        "parçayı gönder."
    ]


def _rewrite_is_last_resort(hedef: Path, deps: AgentDeps, state: _State) -> bool:
    """Toptan yazma artık TEK çıkış mı?

    Kural olmadan ölçülen ölü kilit: `edit_file` üç kez "'old' bulunamadı" verdi,
    model `write_file`'a kaçtı ve KOŞULSUZ engellendi, tekrar `edit_file` denedi,
    yine tutmadı ve tur "ilerleme yok" ile öldü. Model doğru dosyayı, doğru
    niyetle hedeflemişti; çıkışı olmayan bir kapıya çarptı.

    İki koşul BİRLİKTE aranır:

    - Hedefli düzenleme bu turda arka arkaya birkaç kez düşmüş olmalı. Bir-iki
      başarısızlık normaldir ve model kendi kendine toparlar.
    - Model dosyanın TAMAMINI okumuş olmalı. Kuralın gerekçesi "yüz satırlık
      dosyayı baştan üretmek yüz satırlık hata yüzeyi açar" idi; içeriğin tamamı
      görülmüşse yazma artık kör değildir ve o gerekçe düşer.
    """
    if hedef not in deps.tool_context.fully_read:
        return False
    if _line_count(hedef) <= MAX_LINES_FOR_FULL_REWRITE:
        return True
    return state.failed_mutations_in_row >= MAX_EDITS_BEFORE_REWRITE


def _line_count(path: Path) -> int:
    """Dosyanın satır sayısı; okunamıyorsa kuralı gevşetmeyecek şekilde sonsuz."""
    try:
        return len(path.read_text(encoding="utf-8").splitlines())
    except OSError:
        return sys.maxsize
    except UnicodeDecodeError:
        # İkili dosya: toptan yazmanın hacim gerekçesi burada ölçülemez, kısıt kalsın.
        return sys.maxsize


#: Dosyanın tamamını değiştiren araçlar.
_FULL_WRITE_TOOLS = frozenset({"write_file"})


def _acts_on_remote_state(name: str) -> bool:
    """Durumu çalışma alanı dışında (sayfa, masaüstü) tutan araç mı."""
    return tool_family(name) in (ToolFamily.BROWSER, ToolFamily.DESKTOP)


def _is_rerunnable(name: str, tool: Tool | None = None) -> bool:
    """Onay açısından değiştirici sayılan ama TEKRAR EDİLMESİ meşru olan araç mı.

    Tekrar imzasında değiştirici araçların çağı sıfırlanır ("aynı yazma iki kez
    istenmez"). `run_shell` bu kuralın altında yanlış kalıyordu: doğrulama komutu
    tam olarak tekrarlanmak İÇİN vardır. Ölçüldü — model kodu düzeltti, `npm test`
    çalıştırmak istedi ve TOOL_CALL_DUPLICATE ile engellendi; düzeltmenin işe
    yarayıp yaramadığını doğrulayamadı.

    Çağa bağlanmak doğru davranışı verir: değişiklik olmadan aynı komutu tekrar
    etmek yine tekrardır, değişiklikten SONRA tekrar etmek yeni bilgidir.

    Sınıflandırma TEK KAYNAKTAN (`core.tools.tool_family`) okunur, burada ikinci
    bir ad listesi açılmaz. Ölçüldü (masaüstü uygulaması, API modeli): model
    doğrulama komutunu `run_shell` yerine takma adı `bash` ile çağırdı; birebir
    ad karşılaştırması `"bash" != "run_shell"` olduğu için bu istisnayı hiç
    görmedi ve tam da çözmek için var olduğu ölü kilit takma ad altında geri
    geldi (bkz. `engines/agent/turn_report.py::_is_shell_call`, aynı yaklaşım).

    Kabuk dışındaki araçlar bunu kendileri beyan eder (`Tool.reruns_on_change`): projeyi
    çalıştırıp ölçen `start_preview` da değişiklikten sonra yeniden çağrılmak İÇİN vardır.
    """
    if tool is not None and tool.reruns_on_change:
        return True
    return tool_family(name) is ToolFamily.SHELL


# --------------------------------------------------------------------------- #
# Araç yürütme
# --------------------------------------------------------------------------- #


def _post_edit_commands(deps: AgentDeps) -> tuple[str, ...]:
    """Kullanıcının düzenleme kancaları; yapılandırmasız (alt sistem testi) bağlamda yok."""
    config = getattr(deps, "config", None)
    runtime = getattr(config, "runtime", None)
    return tuple(getattr(runtime, "post_edit_commands", ()))


async def _resume_deferred(
    messages: list[Message],
    deps: AgentDeps,
    registry: ToolRegistry,
    state: _State,
    *,
    execution: ExecutionPolicy,
    plan_mode: bool,
) -> None:
    """Sürdürülen geçmişteki ertelenen çağrı olağan araç yolundan yeniden geçer (#114)."""
    pending = take_deferred(messages)
    if pending is None:
        return
    index, call = pending
    results: list[Message] = []
    await _run_tools(
        (call,), results, deps, registry, state, execution=execution, plan_mode=plan_mode
    )
    messages[index:index] = results


async def _run_tools(
    calls: tuple[ToolCall, ...],
    messages: list[Message],
    deps: AgentDeps,
    registry: ToolRegistry,
    state: _State,
    *,
    execution: ExecutionPolicy,
    plan_mode: bool = False,
    parse_warnings: tuple[ParseWarning, ...] = (),
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
        if (deferred := mutation_deferral(registry.get(call.name), parse_warnings)) is not None:
            deps.publisher.publish(
                ToolExecuted(
                    name=call.name,
                    args={},
                    outcome=ToolOutcome.BLOCKED,
                    output=deferred,
                    call_id=call.id,
                )
            )
            messages.append(
                Message("tool", deferred, tool_call_id=call.id, name=call.name, ok=False)
            )
            errored = True
            continue
        if state.repeated_failure_abort:
            output = "Tekrar döngüsü durduruldu; bu araç başlatılmadı."
            deps.publisher.publish(
                ToolExecuted(
                    call_id=call.id,
                    name=call.name,
                    args={},
                    outcome=ToolOutcome.BLOCKED,
                    output=output,
                    diff=None,
                )
            )
            messages.append(
                Message(
                    "tool",
                    output,
                    tool_call_id=call.id,
                    name=call.name,
                    ok=False,
                )
            )
            errored = True
            continue
        if (remaining := budget.remaining_s()) is not None and remaining <= 0:
            budget.halt(BudgetStop.DEADLINE)
            messages.append(
                Message(
                    "tool",
                    "Dış isteğin süre sınırı doldu; bu araç başlatılmadı.",
                    tool_call_id=call.id,
                    name=call.name,
                    ok=False,
                )
            )
            errored = True
            continue
        if budget.stop is BudgetStop.USER_DENIED:
            # Bu TUR'daki önceki bir çağrı AZ ÖNCE reddedildi (aşağıda). Aynı model
            # yanıtındaki kalan çağrılar hiç çalıştırılmaz — kullanıcının kararı bir
            # sonraki çağrıda yok sayılmamalı. Sağlayıcı sözleşmesi yine de her
            # `tool_call`'a bir sonuç ister; bu yüzden "atlandı" mesajı gönderilir.
            output = denial.SKIPPED_TOOL_RESULT if state.hook_halt is None else state.hook_halt
            deps.publisher.publish(
                ToolExecuted(
                    call_id=call.id,
                    name=call.name,
                    args={},
                    outcome=ToolOutcome.DENIED,
                    output=output,
                    diff=None,
                )
            )
            messages.append(Message("tool", output, tool_call_id=call.id, name=call.name, ok=False))
            state.failed_tool_calls += 1
            errored = True
            continue

        args, parse_error = _parse_arguments_checked(call.arguments)
        tool = registry.get(call.name)
        function_schema = tool.schema().get("function") if tool is not None else None
        # Fazla kodlanmış yapısal argüman ONARILIR: bir dizi alanının JSON METNİ
        # olarak gelmesi niyet hatası değil kodlama hatasıdır ve turu düşürmemeli.
        #
        # Onarım imzadan ÖNCE yapılır: aynı mantıksal çağrının kodlanmış ve çözülmüş
        # hâlleri iki ayrı imza üretseydi tekrar kapısı bu çağrıyı hiç göremezdi.
        if isinstance(function_schema, dict):
            args = coerce_arguments(function_schema, args)
        # İmza TUR BOYUNCA paylaşılır: düzeltici turun ana turdaki çağrıyı birebir
        # tekrar etmesi, her tura ayrı ayrı bakıldığında görünmeyen bir döngüdür.
        signature = budget.signature(
            call.name,
            _encode_arguments(args),
            mutating=tool is not None and tool.mutating and not _is_rerunnable(call.name, tool),
            after_shell=tool is not None and tool.reruns_on_change,
            remote=_acts_on_remote_state(call.name),
        )
        seen = budget.count_call(signature)
        # Önceki sonucu maskelenmiş okumayı yeniden istemek tekrar sayılmaz (yer tutucu
        # "gerekirse yeniden oku" der). Değiştirici imzalar bağışlanmaz: aynı yazma
        # iki kez yapılmaz. Defteri olmayan (eski/sade) bağımlılıkta maskeleme de yoktur.
        ledger = getattr(deps, "mask_ledger", None)
        if (
            ledger is not None
            and ledger.note_call(signature, call.id)
            and signature not in budget.mutating_signatures
        ):
            budget.seen_calls[signature] = 1
            seen = 0

        contract_errors: list[str] = []
        if parse_error:
            contract_errors.append(parse_error)
        if tool is None:
            contract_errors.append(
                "bilinmeyen araç; kullanılabilir araçlar: " + ", ".join(registry.names())
            )
        elif isinstance(function_schema, dict):
            contract_errors.extend(validate_arguments(function_schema, args))

        state_dependent_error = False
        if not contract_errors:
            targeted = _targeted_edit_required(call.name, args, deps, execution, state)
            contract_errors.extend(targeted)
            state_dependent_error = bool(targeted)

        if contract_errors:
            # Durum bağımlı hata ("önce oku") model DOĞRU hamleyi yapınca çözülür ve
            # aynı çağrı bu kez geçerli olur; çalıştırılmamış çağrı "yapılmış"
            # sayılmamalı. Ölçüldü (29 Ekim, A2-04): imza unutulmadığı için okuma
            # sonrası AYNI `write_file` tekrar kapısına (`duplicate_limit=1`)
            # takılıyordu. Bozuk JSON/şema hatasında imza korunur: aynı bozuk
            # çağrının tekrarı gerçek bir döngüdür (`seen >= 1` kuralı).
            if state_dependent_error:
                budget.forget_call(signature)
            # Aynı bozuk çağrı ikinci kez geldiyse onarım hakkı harcanmaz: model
            # düzeltmiyor, tekrarlıyor.
            no_more_repairs = seen >= 1 or not budget.take_contract_repair()
            output = _tool_contract_failure(
                call.name,
                contract_errors,
                tool.schema().get("function") if tool is not None else None,
                registry=registry,
            )
            outcome = ToolOutcome.BLOCKED if no_more_repairs else ToolOutcome.FAILED
            deps.publisher.publish(
                ToolExecuted(
                    call_id=call.id,
                    name=call.name,
                    args=args,
                    outcome=outcome,
                    output=output,
                    diff=None,
                )
            )
            messages.append(Message("tool", output, tool_call_id=call.id, name=call.name, ok=False))
            state.failed_tool_calls += 1
            _note_tool_use(
                state, call.name, tool, ok=False, arguments=args, output=output, call_id=call.id
            )
            errored = True
            # Tur BURADA ÖLDÜRÜLMEZ — tekrar kapısıyla (aşağıda) aynı gerekçe.
            #
            # Eskiden onarım hakkı bitince tur anında sonlandırılıyordu; tekrar kapısı
            # ise "turu kesmek o ana kadarki TÜM ilerlemeyi çöpe atar" diyerek
            # kesmiyordu. İki kapının aynı durumda farklı davranması bir çelişkiydi.
            #
            # Ölçüldü: iki bozuk JSON gönderip ÜÇÜNCÜ turda doğru hamleyi yapan bir
            # model, doğru hamlesine hiç ulaşamadan öldürülüyordu. Karar tek bir
            # otoriteye, "ilerleme yok" kapısına bırakılır: model toparlanamazsa tur
            # yine biter — ama üç şans sonra, tek hamlede değil.
            continue

        # Başarısız düzenleme okumayı tazeler; bu, aynı başarısız komuta yeni
        # deneme hakkı vermez. Sayaç çağdan bağımsızdır ve kabuk takma adlarını birleştirir.
        failure_key = (
            "run_shell" if tool_family(call.name) is ToolFamily.SHELL else call.name,
            _encode_arguments(args),
        )
        if failure_key in state.failed_call_counts:
            state.failed_call_counts[failure_key] += 1
            if state.failed_call_counts[failure_key] >= REPEAT_BLOCK_AT:
                output = (
                    f"Aynı başarısız `{call.name}` çağrısı değişiklik olmadan "
                    f"{REPEAT_BLOCK_AT} kez istendi; tekrar döngüsü durduruldu. "
                    "Hata nedenini giderip farklı argümanlarla yeniden deneyin. "
                    "Kabuk zaten seçili proje dizininde çalışır; boşluk içeren yolları "
                    "tırnak içine alın veya göreli yol kullanın."
                )
                deps.publisher.publish(
                    ToolExecuted(
                        call_id=call.id,
                        name=call.name,
                        args=args,
                        outcome=ToolOutcome.BLOCKED,
                        output=output,
                        diff=None,
                    )
                )
                messages.append(
                    Message(
                        "tool",
                        output,
                        tool_call_id=call.id,
                        name=call.name,
                        ok=False,
                    )
                )
                state.failed_tool_calls += 1
                state.repeated_failure_abort = output
                _note_tool_use(
                    state, call.name, tool, ok=False, arguments=args, output=output, call_id=call.id
                )
                errored = True
                continue

        # Değiştirici araçta tek tekrar bile döngüdür: aynı yazma iki kez istenmez.
        # Okuma araçlarında çalışma alanı değişmediği sürece birkaç tekrara izin verilir.
        duplicate_limit = (
            1 if tool is not None and tool.mutating else execution.max_same_tool_without_change
        )
        # Desktop observations can change independently of workspace/remote epochs
        # (including after a rejected stale-element action). Re-read the live state;
        # neither a cached fingerprint nor a cached screenshot is fresh evidence.
        live_desktop_read = (
            tool is not None
            and not tool.mutating
            and (tool_family(call.name) is ToolFamily.DESKTOP or call.name == "view_image")
        )
        # Kapı artık TÜM sağlayıcılarda açık. Eskiden yalnızca web modelleri
        # denetleniyordu; API modelleri aynı çağrıyı sınırsız tekrar edebiliyordu.
        if seen >= duplicate_limit and not live_desktop_read:
            # Engellenen yineleme, işin ZATEN YAPILDIĞININ kanıtıdır: düşen
            # çağrılar bu noktaya gelmeden unutulur (`forget_call`).
            state.already_done_calls += 1
            # OKUMA tekrarına HATA değil, ilk sonucun kendisi döner.
            #
            # Ölçülen ölü kilit (Godot koşusu): model `list_dir .` çağrısını
            # yineledi, kapı onu `blocked` yaptı, engellenen çağrı ilerleme
            # saymadığı için boşta tur sayacı doldu ve görev "agent adım bütçesi
            # doldu" ile öldü. Oysa model yalnızca zaten sahip olduğu bilgiyi
            # yeniden istiyordu; ona hata vermek zinciri kırıyor, bilgiyi vermek
            # sürdürüyor ve YENİ İŞ YAPTIRMIYOR. Değiştirici araçlar bu yoldan
            # yararlanamaz: aynı yazma iki kez yapılmaz, orası hâlâ engellidir.
            if tool is not None and not tool.mutating and seen + 1 >= REPEAT_BLOCK_AT:
                # Önbellekteki sonucu tekrar tekrar vermek döngüyü beslemeye devam
                # ediyordu. Ölçüldü (29 Eylül): model aynı glob'u onlarca kez istedi.
                # Hermes Agent ve OpenClaw aynı noktada çağrıyı ENGELLER; tur kesilmez.
                output = _repeat_block_message(call.name, seen + 1)
                deps.publisher.publish(
                    ToolExecuted(
                        call_id=call.id,
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
                state.repeat_blocked = True
                _note_tool_use(
                    state, call.name, tool, ok=False, arguments=args, output=output, call_id=call.id
                )
                errored = True
                continue
            onbellek = budget.recall_read(signature)
            if onbellek is not None:
                output = f"{_REPEATED_READ_NOTE}\n\n{onbellek}"
                deps.publisher.publish(
                    ToolExecuted(
                        call_id=call.id,
                        name=call.name,
                        args=args,
                        outcome=ToolOutcome.OK,
                        output=output,
                        diff=None,
                    )
                )
                messages.append(
                    Message("tool", output, tool_call_id=call.id, name=call.name, ok=True)
                )
                _note_tool_use(
                    state, call.name, tool, ok=True, arguments=args, output=output, call_id=call.id
                )
                # Kanıt sayaçları ARTMAZ: yeni bir iş yapılmadı, yalnızca bilinen
                # bir sonuç tekrar sunuldu. İlerleme kapısı bunu ilerleme saymaz
                # ve model kendini toparlayamazsa tur yine biter.
                continue
            output = _duplicate_call_message()
            deps.publisher.publish(
                ToolExecuted(
                    call_id=call.id,
                    name=call.name,
                    args=args,
                    outcome=ToolOutcome.BLOCKED,
                    output=output,
                    diff=None,
                )
            )
            messages.append(Message("tool", output, tool_call_id=call.id, name=call.name, ok=False))
            state.failed_tool_calls += 1
            _note_tool_use(
                state, call.name, tool, ok=False, arguments=args, output=output, call_id=call.id
            )
            errored = True
            # Tur BURADA ÖLDÜRÜLMEZ. Tekrarlanan bir çağrı zararsız bir verimsizliktir;
            # turu kesmek o ana kadarki TÜM ilerlemeyi çöpe atar. Ölçüldü: model dört
            # dosyayı okuyup birini düzelttikten sonra aynı dosyayı üç kez okudu ve
            # yapılan iş boşa gitti.
            #
            # Karar "ilerleme yok" kapısına bırakılır: engellenen çağrı ilerleme
            # üretmediği için boşta tur sayacı artar ve model kendini toparlayamazsa
            # tur yine biter — ama üç şans sonra, tek hamlede değil.
            continue

        pending_diff = file_diff(call.name, args, deps.tool_context)
        todos_before = tuple(deps.tool_context.todos.items)
        recorded_uses = len(state.tool_uses)
        result, outcome = await _execute(
            call, args, deps, registry, execution=execution, plan_mode=plan_mode, state=state
        )
        repair_feedback = record_failure_evidence(result, budget)
        if result.is_observation:
            budget.forget_call(signature)
        notice = (result.structured or {}).get("user_notice") if outcome is ToolOutcome.OK else None
        if isinstance(notice, str) and notice:
            # Aracın kullanıcıya göstermek istediği tek satır (ör. bekleyen uyanma iptali, #362).
            deps.publisher.publish(NarrationPublished(text=notice))
        if outcome is ToolOutcome.OK and call.name in {"todo_write", "task_create", "task_update"}:
            for sentence in todo_transitions(todos_before, tuple(deps.tool_context.todos.items)):
                deps.publisher.publish(NarrationPublished(text=sentence))
        if len(state.tool_uses) == recorded_uses:
            _note_tool_use(
                state,
                call.name,
                tool,
                ok=outcome is ToolOutcome.OK,
                arguments=args,
                output=result.output,
                call_id=call.id,
            )
        if outcome in (ToolOutcome.DENIED, ToolOutcome.BLOCKED):
            # Onay verilmeyen ya da yetenek kapısına takılan çağrı HİÇ ÇALIŞMADI.
            # Tekrar kapısına kanıt olarak yazılırsa, koşullar düzelse bile aynı
            # çağrı "bunu zaten yaptın ve o zamandan beri bir şey değişmedi"
            # diyen bir engelle karşılaşır.
            #
            # Ölçüldü (Godot koşusu): doğrulama adımındaki
            # `godot --headless --path . --quit` etkileşimsiz oturumda onay
            # alınamayıp `blocked` döndü; ikinci deneme `TOOL_CALL_DUPLICATE` ile
            # engellendi ve adım hiçbir zaman kanıt üretemedi.
            budget.forget_call(signature)
        if outcome is ToolOutcome.DENIED:
            # Bu bir hata ya da bütçe olayı DEĞİLDİR — insan GERÇEKTEN "hayır"
            # dedi. Tur burada durur (`_drive` bir sonraki döngü başında bunu
            # görüp modeli bir daha çağırmadan döner); aynı yanıttaki KALAN
            # çağrılar döngünün başındaki kontrolle atlanır. PreToolUse kancasının
            # `continue: false` kararı da bu yoldan durur, metni kancanınkidir.
            state.hook_halt = hook_halt_text(result)
            state.denied_tool_name = call.name
            budget.halt(BudgetStop.USER_DENIED)
        # Duvar ve ulaşılamaz kaynak, kanıt kapısı açısından AYNI durumdur: iş bu
        # araçla yapılamadı. Modeli kanıt üretmeye zorlamak onu uydurmaya iter.
        if result.output.startswith((CAPABILITY_WALL_PREFIX, UNREACHABLE_RESOURCE_PREFIX)):
            state.capability_wall = True
        if outcome is ToolOutcome.OK:
            state.failed_call_counts.pop(failure_key, None)
            if (
                tool_family(call.name) is ToolFamily.SHELL
                and not _reads_only(call.name, args)
                and not result.is_observation
            ):
                state.failed_call_counts.clear()
            state.tool_calls_made += 1
            if result.is_observation:
                state.observation_calls += 1
            # Okuma sonucu turda saklanır: aynı okuma yinelenirse engel yerine
            # bu sonuç döner (bkz. tekrar kapısı).
            if tool is not None and not tool.mutating and not live_desktop_read:
                budget.remember_read(signature, result.output)
            if call.name in _FILE_READ_TOOLS:
                state.successful_file_reads += 1
            if call.name in _FILE_READ_TOOLS or call.name in EDIT_TOOLS:
                erisilen = args.get("path")
                if isinstance(erisilen, str) and erisilen:
                    state.nested_candidates.append(erisilen)
            elif call.name == "run_shell":
                # Claude Code (#150): kabukla tek dosya okuma (`cat`, `head`) da tetikler.
                from .nested_rules import shell_read_target

                okunan = shell_read_target(str(args.get("command", "") or ""))
                if okunan:
                    state.nested_candidates.append(okunan)
            mutating = bool(tool is not None and tool.mutating)
            budget.successful_tool_evidence.append((call.name, args, mutating))
            if result.source_read_url:
                budget.successful_source_reads.append(result.source_read_url)
            if mutating and _acts_on_remote_state(call.name):
                budget.remote_epoch += 1
            if mutating and not result.is_observation:
                state.mutating_tool_calls_made += 1
                state.failed_mutations_in_row = 0
                # Çağı yalnızca DOSYA değişikliği ilerletir. `run_shell` başarılı
                # olduğunda da ilerletmek, aynı komutun tekrar imzasını her
                # seferinde tazeliyor ve tekrar kapısını `run_shell` için işlevsiz
                # bırakıyordu (bkz. `_is_rerunnable`).
                if not _is_rerunnable(call.name, tool):
                    budget.record_mutation()
                    state.failed_call_counts.clear()
                else:
                    # Kabuk/çalıştırma başarılıysa düşen çağrıların ön koşulu değişmiş
                    # olabilir (bkz. `forget_failed_calls`); çağ yine ilerlemez.
                    budget.forget_failed_calls()
                    if tool is not None and not tool.reruns_on_change:
                        budget.shell_epoch += 1
        elif outcome is ToolOutcome.FAILED:
            state.failed_call_counts.setdefault(failure_key, 1)
            state.failed_tool_calls += 1
            errored = True
            # Sayaç YALNIZCA değiştirici çağrılarda büyür: okuma hatası (yanlış
            # dosya adı) düzenleme döngüsü değildir ve o kapıyı tetiklememeli.
            if call.name in _FILE_READ_TOOLS and result.output.startswith(FILE_MISSING_PREFIX):
                istenen = args.get("path")
                if isinstance(istenen, str):
                    state.missing_paths.append(istenen)
            if tool is not None and tool.mutating:
                state.failed_mutations_in_row += 1
                # Düşen bir düzenlemeden sonra YENİDEN OKUMA serbest kalmalı:
                # toparlanmanın tek yolu odur ve tekrar kapısı onu engelliyordu.
                budget.record_failed_mutation()
                # Düşen çağrı YAPILMAMIŞTIR. Hemen unutulmaz — arada hiçbir şey
                # değişmeden yinelemek gerçek tekrardır — ama başarılı bir
                # değişiklikten sonra unutulur: engeli kalkmış olabilir.
                budget.note_failed_call(signature)
            # Geçici ağ/zaman aşımı hatası işin kendisi hakkında bir şey söylemez: aynı
            # çağrı birkaç saniye sonra başarılı olabilir. Ölçüldü (7 Ekim, dalga24):
            # clone_site kaynak sayfada 60 sn zaman aşımına düştü, yeniden deneme
            # TOOL_CALL_DUPLICATE ile engellendi ve model siteyi elle yazmaya döndü
            # (16/17 → 10/17). Aynı çağrıya en çok `MAX_TOOL_TRANSIENT_RETRIES` hak verilir.
            if is_transient_failure(result.output):
                hak = budget.transient_retries.get(signature, 0)
                if hak < MAX_TOOL_TRANSIENT_RETRIES:
                    budget.transient_retries[signature] = hak + 1
                    budget.forget_call(signature)

        diff = pending_diff if outcome is ToolOutcome.OK else None
        deps.publisher.publish(
            ToolExecuted(
                call_id=call.id,
                name=call.name,
                args=args,
                outcome=outcome,
                output=result.output,
                diff=diff,
                workspace=result.workspace_effect.label if result.workspace_effect else "",
                mutating=tool.mutating if tool else None,
            )
        )
        govde = result.output
        if repair_feedback.note:
            govde = f"{govde}\n\n[onarım kanıtı] {repair_feedback.note}"
        if outcome is ToolOutcome.OK and tool is not None and not tool.mutating:
            ayni = _same_output_note(state, call.name, result.output)
            if ayni is not None:
                govde = f"{govde}\n\n{ayni}"
        if outcome is ToolOutcome.OK and call.name in EDIT_TOOLS:
            yol = args.get("path")
            state.edit_streak = next_streak(state.edit_streak, yol if isinstance(yol, str) else "")
            seri = streak_note(state.edit_streak)
            if seri is not None:
                govde = f"{govde}\n\n{seri}"
        elif outcome is ToolOutcome.OK and tool is not None and tool.mutating:
            state.edit_streak = ("", 0)
        hooks = _post_edit_commands(deps) if call.name in EDIT_TOOLS else ()
        if outcome is ToolOutcome.OK and hooks:
            raw_path = args.get("path")
            if isinstance(raw_path, str) and raw_path:
                hook_note = await run_post_edit_hooks(
                    hooks, deps.tool_context.root / raw_path, deps.tool_context.root
                )
                if hook_note is not None:
                    govde = f"{govde}\n\n{hook_note}"
        post_hook = (
            await post_tool_use(
                deps, call.name, args, result.output, ok=outcome is ToolOutcome.OK, call_id=call.id
            )
            if outcome in (ToolOutcome.OK, ToolOutcome.FAILED)
            else ToolNote()
        )
        if post_hook.replaced_output is not None:
            govde = post_hook.replaced_output
        if post_hook.note is not None:
            govde = f"{govde}\n\n{post_hook.note}"
        if post_hook.halt is not None:
            state.hook_halt = post_hook.halt
            budget.halt(BudgetStop.USER_DENIED)
        if outcome is ToolOutcome.FAILED:
            imza = (call.name, _failure_signature(result.output))
            state.repeated_failures[imza] = state.repeated_failures.get(imza, 0) + 1
            not_ = _repeated_failure_note(
                call.name,
                result.output,
                state.repeated_failures[imza],
                teacher_available=(
                    deps.config.teacher is not None and not deps.config.runtime.teacherless
                ),
            )
            if not_ is not None:
                govde = f"{govde}\n\n{not_}"
        gorseller = result.images
        if gorseller and not _agent_reads_images(deps):
            gorseller = ()
            govde = f"{govde}\n\n{IMAGES_NOT_SENT_NOTE}"
        message = Message(
            "tool",
            govde,
            tool_call_id=call.id,
            name=call.name,
            ok=result.ok,
            images=gorseller,
            tool_diff=diff,
        )
        messages.append(message)
        if (
            result.visual_observation is not None
            and outcome is ToolOutcome.OK
            and post_hook.replaced_output is None
            and result.output
            and result.output in govde
        ):
            state.desktop_grounding.note_helper(
                result.visual_observation,
                message,
                deps.tool_context,
                deps.conversation_id,
                deps.attempt_id,
            )
    return errored


#: Görsel okuyamayan agent modeline araç sonucundaki görsel GÖNDERİLMEZ. Ölçüldü (2 Ekim
#: 2026, NIM Nemotron 3 Ultra): ekran görüntüsü taşıyan tek araç sonucu (`site_design`)
#: sonraki HER isteği "Received multimodal data but multimodal processing is not enabled"
#: ile düşürdü; devre açıldı ve tur orada kaldı.
IMAGES_NOT_SENT_NOTE = (
    "[Ekran görüntüsü bu modele gönderilmedi: model görsel okuyamıyor. Görsel dosyaya "
    "kaydedildiyse tasarım/kalite yargısı için ask_teacher(question, gorseller=[yol]) ile "
    "öğretmene göster; basit içerik sorusu için view_image(path, question).]"
)


def _agent_reads_images(deps: AgentDeps) -> bool:
    return capabilities_for(deps.config.agent, deps.config.web_sessions).images


async def _execute(
    call: ToolCall,
    args: dict[str, object],
    deps: AgentDeps,
    registry: ToolRegistry,
    *,
    execution: ExecutionPolicy,
    plan_mode: bool = False,
    state: _State | None = None,
) -> tuple[ToolResult, ToolOutcome]:
    """Onaydan geçir ve çalıştır. Bilinmeyen araç da kayıt defterinin sorunu."""
    args = deepcopy(args)
    if prohibited_tool(call.name, execution.forbidden_tool_families | deps.turn_forbidden_families):
        return ToolResult.failure(
            "Kullanıcının bu turdaki açık araç sınırı bu araç ailesine izin vermiyor. "
            "İzin verilen gözlemlerle yanıtla; mümkün değilse sınırlamayı açıkla."
        ), ToolOutcome.BLOCKED
    tool = registry.get(call.name)
    if execution.allowed_tool_names is not None and call.name not in execution.allowed_tool_names:
        # Serbest araçlar SÖYLENMELİ: gözlem turunda model yalnız "kapsamda değil"
        # cevabını görünce aynı yazma aracını başka argümanla yeniden deniyordu.
        allowed = ", ".join(sorted(execution.allowed_tool_names)) or "yok"
        return ToolResult.failure(
            f"Araç bu adımın izin verilen kapsamında değil. Bu adımda kullanılabilir: {allowed}"
        ), ToolOutcome.BLOCKED
    if is_denied_tool(call.name, getattr(deps, "denied_tools", ())):
        # `--disallowed-tools`: şema zaten sunulmadı; ad uydurulursa da çalışmaz. Engelleme
        # (BLOCKED) hata değildir, model başka yol dener.
        return ToolResult.failure(
            f"'{call.name}' aracı bu koşuda yasak (--disallowed-tools); başka bir yol dene."
        ), ToolOutcome.BLOCKED
    _widen_profile_for(call.name, deps, registry, execution)
    if deps.steering is not None and deps.steering.pending:
        return ToolResult.failure(
            "Yeni kullanıcı talimatı bekliyor; eski araç başlatılmadı."
        ), ToolOutcome.BLOCKED
    if (
        tool is not None
        and tool.mutating
        and not execution.allow_mutation
        and not _reads_only(tool.name, args)
    ):
        # Yetenek kapısı onaydan ÖNCE gelir: kullanıcıya sormanın anlamı yok, bu
        # model bu işi güvenilir yapamıyor. Şema hiç sunulmadığı için buraya normalde
        # gelinmez; ikinci savunma hattıdır.
        return (
            ToolResult.failure(
                MUTATION_BLOCKED_MESSAGE.format(reason=execution.mutation_block_reason)
            ),
            ToolOutcome.BLOCKED,
        )
    if tool is not None and tool.mutating and deps.mutation_blocked_by_pending_input():
        return ToolResult.failure(
            "Soru sonucu yeniden değerlendirilmeli; değişiklik yerine bağımsız okuma yap."
        ), ToolOutcome.BLOCKED
    # PreToolUse kancası (P-009) onaydan ÖNCE: engel, argüman değişikliği, allow/ask kararı.
    hook_gate = await pre_tool_use(deps, call.name, args, call.id)
    if hook_gate.blocked is not None:
        return hook_gate.failure(), (ToolOutcome.DENIED if hook_gate.halt else ToolOutcome.BLOCKED)
    args = hook_gate.arguments
    # Değiştirmeyen ama etkisi ÇAĞRIYA bağlı araç da onaydan geçer: `browser_open`
    # çerezsiz okur (sorulmaz) ama profil yükleyecekse kullanıcının girişli oturumunu
    # ajana açar (sorulur). Ölçüldü (31 Ekim): yalnız `mutating` kapı olduğu için
    # varsayılan profil hiç sorulmadan yükleniyordu. İzin kuralı (ask/deny) okuma
    # araçlarını da kapıdan geçirir (P-001).
    rules = hook_gate.rules(getattr(deps, "permission_rules", None), call.name)
    # Etkin becerinin `allowed-tools` ön onayı ve `disallowed-tools` deseni (#142, #180).
    rules = skill_grants.with_grants(rules, deps.tool_context)
    # Claude in Chrome adı (#431) onaydan önce iç `chrome_*` çağrısına çevrilir.
    chrome_call = await claude_chrome_call(call, args, rules, deps.tool_context)
    if isinstance(chrome_call, ToolResult):
        return chrome_call, ToolOutcome.FAILED
    if chrome_call is not None:
        call, args, rules = chrome_call
        tool = registry.get(call.name)
    if tool is not None and (
        tool.mutating
        or tool.effect_resolver is not None
        or _rule_gates(rules, tool, args, deps)
        or reads_outside(tool.name, args, deps.tool_context)
    ):
        revision = deps.approval_revision() if deps.approval_revision else None
        policy = _current_policy(deps)
        request = await resolve_request(
            tool,
            deepcopy(args),
            deps.allowed_commands,
            root=deps.tool_context.root,
            context=deps.tool_context,
            rules=rules,
        )
        request = replace(request, call_id=call.id)
        # Otomatik kip denetçisi (P-011): sorulacak çağrıyı modelle sınıflandırır. Eşik bu
        # çağrıda aşılıp kip Manuel'e düştüyse yeni kip bu çağrının kapsamıdır (riskli karar
        # isteği gevşetmez); yoksa onaylanan kart "kapsam değişti" diye iptal edilirdi.
        guard = getattr(deps, "auto_review", None)
        trips = guard.trips if guard is not None else 0
        mark = review_mark(guard)  # PermissionDenied: denetçi bu çağrıyı riskli buldu mu?
        request = await review_auto_request(request, deps)
        if guard is not None and guard.trips != trips:
            revision = deps.approval_revision() if deps.approval_revision else None
            policy = _current_policy(deps)
        switches = guard.mode_switches if guard is not None else 0
        verdict = await policy.decide(request)
        if guard is not None and guard.mode_switches != switches:
            # Kartta "auto kipine geç" (#82): onaylanan çağrı yeni kipin kapsamında çalışır.
            revision = deps.approval_revision() if deps.approval_revision else None
        if deps.mutation_blocked_by_pending_input() or (
            deps.approval_revision is not None and deps.approval_revision() != revision
        ):
            return ToolResult.failure(
                "Onay kapsamı değişti; eski işlem başlatılmadı."
            ), ToolOutcome.BLOCKED
        if isinstance(verdict, Allowance):
            # Onaylayan argümanı değiştirdi (`-p` onay aracı `updatedInput`): yeni argüman
            # kural/kök-dışı engelinden yeniden geçer, sonra çalışır.
            args = dict(verdict.arguments)
            request = await resolve_request(
                tool,
                deepcopy(args),
                deps.allowed_commands,
                root=deps.tool_context.root,
                context=deps.tool_context,
                rules=rules,
            )
            if request.pre_denied is not None:
                return ToolResult.failure(request.pre_denied), ToolOutcome.BLOCKED
            verdict = Decision.ALLOW
        if isinstance(verdict, Denial):
            # Gerekçeli ret (P-013): tur DURMAZ; model gerekçeyi okur ve yolunu değiştirir.
            # Sonuç BLOCKED sınıfındadır: refleksiyon tetiklenmez, bütçe durdurulmaz.
            return (
                ToolResult.failure(denial.DENIED_WITH_NOTE_RESULT.format(note=verdict.note)),
                ToolOutcome.BLOCKED,
            )
        decision = verdict
        if decision is not Decision.ALLOW:
            # Engelleme (BLOCKED) HATA DEĞİLDİR: refleksiyon tetiklenmemeli, model
            # yalnızca farklı bir yol denemeli. Reddetme (DENIED) ise artık farklı
            # bir sınıftır: turu durdurur (bkz. `_run_tools`, `_drive`).
            message = _decision_message(decision, plan_mode=plan_mode, request=request)
            if (reason := classifier_reason(guard, mark)) is not None:
                message = await permission_denied(
                    deps, call.name, args, call.id, reason=reason, message=message
                )
            return ToolResult.failure(message), _DECISION_OUTCOMES[decision]
        if tool_family(call.name) is ToolFamily.SHELL:
            from .sandbox_network import install_network_gate

            # Liste dışı ana makine kipe göre (#323): sorulur, verilir ya da reddedilir.
            install_network_gate(deps.tool_context, policy, getattr(deps, "permission_rules", None))

    # Onay SORULACAKSA (değiştirici araç) buraya ancak onaydan SONRA gelinir;
    # araç henüz çalışmadı ama artık kesinlikle çalışacak. Arayüz bu olayı
    # dinleyip "… okunuyor/… yapılıyor" gibi şimdiki-zamanlı, soluk bir durum
    # satırı basar (bkz. `appserver/tool_progress.py`) — `ToolExecuted` yalnız
    # BİTİNCE geldiği için uzun süren bir araç boyunca kullanıcı hiçbir şey
    # görmüyordu.
    budget = deps.require_budget()
    if (remaining := budget.remaining_s()) is not None and remaining <= 0:
        budget.halt(BudgetStop.DEADLINE)
        return ToolResult.failure(
            "Dış isteğin süre sınırı doldu; bu araç başlatılmadı."
        ), ToolOutcome.BLOCKED
    recorder = getattr(deps, "effect_recorder", None)
    external = (
        tool is not None
        and tool.mutating
        and request.effect
        in {
            ToolEffect.REMOTE_WRITE,
            ToolEffect.REMOTE_DESTRUCTIVE,
        }
    )
    if recorder is not None and external:
        await recorder.prepare(call, tool, request.effect, request.authorization_scope)
        if deps.mutation_blocked_by_pending_input() or (
            deps.approval_revision is not None and deps.approval_revision() != revision
        ):
            return ToolResult.failure(
                "Kayıt sırasında kullanıcı kararı değişti; dış işlem başlatılmadı."
            ), ToolOutcome.BLOCKED
        if (remaining := budget.remaining_s()) is not None and remaining <= 0:
            budget.halt(BudgetStop.DEADLINE)
            return (
                ToolResult.failure("Dış işlem başlamadan süre sınırı doldu."),
                ToolOutcome.BLOCKED,
            )
    owned_release = (
        state.desktop_grounding.matching_release(
            call.name, args, deps.tool_context, deps.conversation_id, deps.attempt_id
        )
        if state is not None
        else None
    )
    if state is not None and owned_release is None:
        grounding_error = state.desktop_grounding.preflight(
            call.name, args, deps.tool_context, deps.conversation_id, deps.attempt_id
        )
        if grounding_error is not None:
            return ToolResult.failure(grounding_error), ToolOutcome.BLOCKED
    deps.publisher.publish(ToolStarted(name=call.name, args=args, call_id=call.id))
    if state is not None and owned_release is not None:
        from ...core.owned_thread import await_cancellable_thread

        tool_running(deps, call.name, args, call.id)
        result = await await_cancellable_thread(
            state.desktop_grounding.release, owned_release.context.cancelled.set, owned_release
        )
        await localization.record_result(call, result, deps.tool_context)
        _note_tool_use(
            state,
            call.name,
            tool,
            ok=result.ok,
            arguments=args,
            output=result.output,
            call_id=call.id,
        )
    else:
        result = await _execute_registered_tool(call, args, deps, registry, tool, state)
    if recorder is not None and external:
        await recorder.finish(call.id, result.ok)
    return result, ToolOutcome.OK if result.ok else ToolOutcome.FAILED


async def _execute_registered_tool(
    call: ToolCall,
    args: dict[str, object],
    deps: AgentDeps,
    registry: ToolRegistry,
    tool: Tool | None,
    state: _State | None,
) -> ToolResult:
    """Onaydan sonra gerçekleşen çağrının kaynak/ortam kimliğini ölç."""
    from .verify_discovery import evidence_environment, source_digest

    command = args.get("command", args.get("cmd"))
    is_shell = tool_family(call.name) is ToolFamily.SHELL and isinstance(command, str)
    before = await asyncio.to_thread(source_digest, deps.tool_context.root) if is_shell else ""
    environment = (
        await asyncio.to_thread(
            evidence_environment, deps.tool_context.root, (str(command),), runtime=sys.version
        )
        if is_shell
        else None
    )
    tool_running(deps, call.name, args, call.id)  # `duration_ms` onaydan sonra başlar
    context = deps.tool_context
    if state is not None and call.name in {"desktop_click", "desktop_mouse", "desktop_scroll"}:
        context = state.desktop_grounding.mouse_context(
            context, deps.conversation_id, deps.attempt_id
        )
    result = await registry.execute(call.name, args, context)
    await localization.record_result(call, result, deps.tool_context)
    if state is not None:
        after = await asyncio.to_thread(source_digest, deps.tool_context.root) if is_shell else ""
        current_environment = (
            await asyncio.to_thread(
                evidence_environment, deps.tool_context.root, (str(command),), runtime=sys.version
            )
            if is_shell
            else None
        )
        if current_environment != environment:
            environment = None
        _note_tool_use(
            state,
            call.name,
            tool,
            ok=result.ok,
            arguments=args,
            output=result.output,
            job_completion=result.job_completion,
            is_observation=result.is_observation,
            workspace_effect=result.workspace_effect,
            source_before=before,
            source_after=after,
            environment=environment,
            call_id=call.id,
        )
    return result


def _rule_gates(
    rules: PermissionRuleSet | None, tool: Tool, args: dict[str, object], deps: AgentDeps
) -> bool:
    """Değiştirmeyen araç (okuma, arama, web) bir `deny`/`ask` kuralına takılıyor mu?

    Onay kapısı değiştirici araçlar içindir; ama izin kuralları HER araç içindir (P-001:
    `Read(~/.ssh/**)` deny, `WebFetch(domain:x)` deny, `Read(...)` ask). Ölçüldü (31 Ekim):
    kapı yalnız `tool.mutating` ile açılıyordu, `read_file`/`web_fetch`/`search_code` için
    deny ve ask kuralları hiç değerlendirilmeden araç çalışıyordu. `allow` ya da eşleşme
    yoksa eski yol korunur: sorulmaz, doğrudan çalışır.
    """
    if rules is None or not rules.rules:
        return False
    match = evaluate(rules, tool.name, args, deps.tool_context.root)
    return match is not None and match.decision is not PermissionDecision.ALLOW


def _reads_only(tool_name: str, args: dict[str, object]) -> bool:
    """Kabuk çağrısı YALNIZ okuyor mu (`ls`, `pwd`, `git log`)?

    Ölçüldü (2 Ekim, kabul koşusu): değiştirme yetkisi olmayan modelde `ls -la` ve
    `pwd` bile "bu model dosya değiştiremez" diye engellendi; model klasörü
    göremeden tur boşa döndü. Okuma değişiklik değildir.
    """
    command = args.get("command")
    return (
        tool_family(tool_name) is ToolFamily.SHELL
        and isinstance(command, str)
        and is_read_only_command(command)
    )


#: Aynı hatanın kaç kez yinelenmesinden SONRA Fusion araya girer.
#:
#: 1 olsaydı ilk denemede araya girip modelin normal toparlanmasını bozardık;
#: daha yükseği turu döngüde tutar. Ölçülen vakada hata üç kez yinelendi.
_YINELENEN_HATA_ESIGI = 2

#: Öğretmene danışma ÖNERİSİNİN eşiği (Faz 4, Görev 1).
#:
#: Yeni bir sayı UYDURULMADI: temel "farklı argümanlarla dene" notu zaten
#: `_YINELENEN_HATA_ESIGI`'de veriliyor. Öğretmen önerisi o notun bile işe
#: yaramadığı, yani AYNI hatanın bir kez daha yinelendiği durumdur — bu yüzden
#: mevcut eşiğin üzerine bir tur eklenir, sıfırdan bir eşik seçilmez
#: (bkz. `geliştirme belgeleri` §6.2).
_OGRETMEN_ONERI_ESIGI = _YINELENEN_HATA_ESIGI + 1


def _repeated_failure_note(
    tool_name: str, output: str, count: int, *, teacher_available: bool = False
) -> str | None:
    """Aynı araç aynı hatayı yineliyorsa modele Fusion'ın notu; yoksa `None`.

    Ölçülen hata: `godot__add_node` üç kez "Scene file does not exist" verdi ve
    her seferinde kendi önerisi olarak "Use create_scene first" dedi. Sahne
    zaten vardı; öneri yanlıştı. Model itaatle o öneriyi uygulayıp döngüye
    girdi — inatçı değildi, aracın SÖYLEDİĞİNİ yapıyordu.

    Tekrar kapısı burada yardım etmez: çağrılar birbirinin aynısı değildir
    (araçlar dönüşümlü çağrılıyor). Bu yüzden ölçüt çağrı imzası değil HATA
    imzasıdır.

    `teacher_available` yalnızca `config.teacher` tanımlıysa `True` gelir
    (bkz. çağıran yer); tanımsızken öneri BASILMAZ — model elinde olmayan bir
    aracı çağırmaya yönlendirilmez.
    """
    if count < _YINELENEN_HATA_ESIGI:
        return None
    not_ = (
        f"FUSION_NOT: `{tool_name}` aynı hatayı {count} kez verdi ve aracın kendi "
        "önerisi işe yaramadı. Aynı yolu tekrar deneme; FARKLI ARGÜMANLARLA çağır ya "
        "da yaklaşımı değiştir (başka bir araç, başka bir yöntem)."
    )
    if "res://" in output:
        # Godot'ya özel ölçülmüş çare yalnız o hatada söylenir.
        not_ += (
            " Sebep çoğu kez yol biçimidir: 'res://' ekini kaldırmayı ya da eklemeyi, "
            "göreli yol yerine tam yol vermeyi dene."
        )
    if teacher_available and count >= _OGRETMEN_ONERI_ESIGI:
        not_ += (
            " Bu hata FARKLI yaklaşımlara rağmen sürüyorsa `ask_teacher` ile web "
            "öğretmene danışmayı düşün — turu bu döngüde harcamak yerine."
        )
    return not_


#: Birebir aynı OKUMA/ARAMA bu kaçıncı kez istenince çalıştırılmaz.
#
# Hermes Agent (`agent/tool_guardrails.py`, MIT): salt-okunur araç aynı sonucu 2.
# kez verince uyarır, 5.'de çağrıyı engeller; OpenClaw ve OpenHands da benzer
# eşiklerle engeller. Fusion 3. ve 4. tekrarda önbellekteki sonucu uyarıyla verir
# (bkz. `_REPEATED_READ_NOTE`), 5.'de keser. Tur KESİLMEZ; model yalnız bu aramanın
# bir işe yaramadığını açıkça öğrenir.
REPEAT_BLOCK_AT = 5
#: Aynı okuma aracı FARKLI argümanlarla bu kadar kez birebir aynı sonucu verince not
#: eklenir. OpenClaw'ın "argument churn" dedektörünün karşılığı: model deseni hafifçe
#: değiştirip (`mcp` → `**/lib/mcp/**`) aynı boş sonucu tekrar tekrar alıyordu.
SAME_OUTPUT_WARN_AT = 3


def _repeat_block_message(name: str, count: int) -> str:
    return (
        f"{TOOL_CALL_BLOCKED_PREFIX} `{name}` çağrısını aynı argümanlarla {count}. kez istedin; "
        "sonuç hiç değişmedi ve araç çalıştırılmadı. Bu aramayı bırak. Elindeki "
        "sonuçlarla bir sonraki SOMUT adımı at (bulduğun dosyayı oku ya da düzenle); "
        "aradığın şey yoksa farklı bir klasörde ya da farklı bir araçla ara, "
        "bulunamıyorsa bunu kullanıcıya açıkça söyle."
    )


def _same_output_note(state: _State, name: str, output: str) -> str | None:
    """Aynı araç farklı argümanlarla birebir aynı sonucu veriyorsa yönlendirici not."""
    ozet = hashlib.sha256(output.encode("utf-8", "replace")).hexdigest()
    anahtar = (name, ozet)
    sayi = state.same_output_counts.get(anahtar, 0) + 1
    state.same_output_counts[anahtar] = sayi
    if sayi < SAME_OUTPUT_WARN_AT:
        return None
    return (
        f"NOT: `{name}` son {sayi} farklı çağrıda birebir aynı sonucu verdi. Argümanı "
        "değiştirmek sonucu değiştirmiyor. Elindeki bilgiyle ilerle; aradığın şey bu "
        "klasörde yoksa başka bir klasörde ya da başka bir araçla ara."
    )


#: Tekrarlanan OKUMA çağrısında sonucun önüne konan not.
#
# Sonucu sessizce geri vermek, modelin aracı yeniden çalıştırdığını sanmasına ve
# değişmeyen bir dosyayı "taze" bilgi sayıp aynı döngüye girmesine yol açardı.
# Not, sonucun ÖNBELLEKTEN geldiğini ve çalışma alanının değişmediğini söyler.
_REPEATED_READ_NOTE = (
    "TOOL_CALL_CACHED: Bu okumayı aynı argümanlarla zaten yapmıştın ve çalışma "
    "alanında o zamandan beri ilgili bir değişiklik olmadı. Araç yeniden "
    "çalıştırılmadı; önceki sonuç aşağıda. Aynı okumayı bir daha isteme — "
    "elindeki bilgiyle sonraki adıma geç."
)


# --------------------------------------------------------------------------- #
# Öz-denetim ve sıkıştırma
# --------------------------------------------------------------------------- #


#: Öz-denetim / doğrulama kapısı düzeltmesi turlarına eklenen notların ortak
#: öneki. Bu bir kullanıcı mesajı DEĞİLDİR; modelin bunu görevin yeniden
#: verildiği sanmaması için Fusion'ın kendi sesiyle işaretlenir.


_SELF_REVIEW_FINALIZE_RESERVE_S = 1.0


def _self_review_timeout(deps: AgentDeps) -> float | None:
    remaining = []
    if deps.deadline is not None:
        remaining.append(deps.deadline.remaining_s())
    if deps.budget is not None and (seconds := deps.budget.remaining_s()) is not None:
        remaining.append(seconds)
    # Optional feedback must leave time to publish the already measured result;
    # neither this reserve nor the reviewer renews the actual hard deadline.
    return max(0.0, min(remaining) - _SELF_REVIEW_FINALIZE_RESERVE_S) if remaining else None


async def _self_review(
    task: str,
    outcome: AgentOutcome,
    deps: AgentDeps,
    *,
    verification: VerificationResult | None = None,
) -> AgentOutcome:
    from .evidence_handoff import current_diff

    timeout = _self_review_timeout(deps)
    feedback = None
    if timeout is None or timeout > 0:
        deps.publisher.publish(SelfReviewStarted())
        try:
            async with asyncio.timeout(timeout):
                feedback = await review.review_turn(
                    task,
                    outcome.final_text,
                    outcome.messages,
                    config=deps.config,
                    publisher=deps.publisher,
                    diff=await asyncio.to_thread(current_diff, deps)
                    if deps.config.runtime.review_diff_only
                    else "",
                    criteria=verification.evidence if verification else (),
                    failures=verification.findings if verification else (),
                )
        except TimeoutError:
            pass
    deps.publisher.publish(
        SelfReviewFinished(issue_found=bool(feedback), completed=feedback is not None)
    )
    if not feedback:
        return outcome

    correction = await run_agent(
        _correction_task(feedback),
        deps,
        history=outcome.messages,
        self_review=False,
        internal=True,
        # Kapı bu turda çalışmaz: dış döngü zaten doğrulayacak. Aksi halde iç içe
        # doğrulama olur ve MAX_VERIFY_ROUNDS sessizce ikiye katlanır.
        verify=False,
    )
    correction.tool_calls_made += outcome.tool_calls_made
    correction.mutating_tool_calls_made += outcome.mutating_tool_calls_made
    correction.failed_tool_calls += outcome.failed_tool_calls
    correction.model_calls_made += outcome.model_calls_made
    correction.verification_repaired = True
    return correction


async def _verify(
    outcome: AgentOutcome, deps: AgentDeps, *, plan_mode: bool, depth: int
) -> VerificationResult | None:
    """Doğrulama kapısını çalıştır.

    Sonuç iki yere birden gider: modele düzeltme talimatı ve ders güvenine sinyal.
    İki kez çalıştırmak hem israf hem de iki farklı cevap alma riskidir.

    İş yapılmadıysa kapı anlamsızdır; plan modunda ise hiçbir şey değişmediği için
    hiç çalışmaz.

    Ölçü DEĞİŞTİRİCİ çağrıdır, çağrı sayısı değil. Ölçüldü (17 Eylül denetimi):
    yalnız kod açıklaması istenen bir tur `read_file` çağırdığı için kapı devreye
    girdi ve cevabın sonuna "doğrulanamadı: ruff check .", "mypy src" uyarıları
    eklendi — kullanıcının kodunda hiçbir şey değişmemişken. Kapının sorusu
    "bozdum mu"dur; hiçbir şeyi değiştirmeyen turda sorulacak bir soru yoktur.
    """
    if deps.verifier is None or plan_mode or depth > 0:
        return None
    if outcome.mutating_tool_calls_made == 0:
        if deps.tool_context.requested_outputs:
            return await OutputPathVerifier(deps.tool_context).verify()
        return None
    return await deps.verifier.verify()


async def _fix_findings(
    verification: VerificationResult,
    outcome: AgentOutcome,
    deps: AgentDeps,
    *,
    escalation_deps: AgentDeps | None = None,
) -> AgentOutcome:
    """Somut bulguları modele düzeltme talimatı olarak ver ve TEK düzeltici tur aç.

    Model çağrısı EKLEMEZ (talimat deterministik üretilir) ama düzeltici turun kendisi
    bir tur maliyetindedir. Öz-denetimdeki disiplinin aynısı: ikinci bir kapı turu yok,
    sonsuz düzeltme döngüsü yok.

    `escalation_deps` verilirse tur ÜST modelle koşar (bkz. `gate_escalation`) ve
    başarısız olursa zayıf modelle yeniden denenmez: ek tur tek bir turdur.
    """
    if not should_repair_verifier(verification):
        return outcome
    deps.publisher.publish(
        VerificationFailed(summary=verification.summary, findings=verification.findings)
    )
    correction_task = _verification_correction_task(verification)
    correction_deps = escalation_deps or _verification_correction_deps(deps)
    correction = await _run_verification_correction_attempt(
        correction_task,
        correction_deps,
        history=outcome.messages,
    )
    _sync_turn_counters(correction_deps, deps)
    if (
        escalation_deps is None
        and correction_deps is not deps
        and not correction.ok
        and deps.budget is not None
        and deps.budget.stop is None
        and not is_permanent_error(correction.model_error or correction.final_text)
    ):
        retry = await _run_verification_correction_attempt(
            correction_task,
            deps,
            history=outcome.messages,
        )
        retry.tool_calls_made += correction.tool_calls_made
        retry.mutating_tool_calls_made += correction.mutating_tool_calls_made
        retry.failed_tool_calls += correction.failed_tool_calls
        retry.model_calls_made += correction.model_calls_made
        correction = retry

    correction.tool_calls_made += outcome.tool_calls_made
    correction.mutating_tool_calls_made += outcome.mutating_tool_calls_made
    correction.failed_tool_calls += outcome.failed_tool_calls
    correction.model_calls_made += outcome.model_calls_made
    correction.verification_repaired = True
    return correction


async def _escalate_after_gate(
    outcome: AgentOutcome,
    verification: VerificationResult,
    deps: AgentDeps,
    *,
    fix_rounds: int,
    plan_mode: bool,
    depth: int,
) -> tuple[AgentOutcome, VerificationResult | None]:
    """Kapı kırmızı kalınca TEK ek düzeltme turunu üst modelle koş ve kapıyı yeniden ölç.

    Üst model tanımlı değilse (`gate_escalation.prepare` → `None`) girdiyi aynen döndürür.
    Tur sayısı sabittir: bu çağrı en çok bir kez yapılır ve kendi içinde döngü yoktur.
    Sonuç kullanıcıya durum satırı + olay + tur metnindeki rapor satırı olarak gider.
    """
    if not should_repair_verifier(verification):
        return outcome, verification
    escalation = gate_escalation.prepare(deps)
    if escalation is None:
        return outcome, verification
    budget = deps.require_budget()
    model = escalation.target.spec.model
    deps.publisher.publish(
        StatusChanged(gate_escalation.STATUS_ESCALATING.format(rounds=fix_rounds, model=model))
    )
    deps.publisher.publish(
        GateEscalated(
            failed_rounds=fix_rounds,
            from_model=escalation.from_model,
            to_model=model,
            source=escalation.target.source.value,
            findings=len(verification.findings),
        )
    )
    repair_note = observe_verifier_failures(verification, budget)
    if repair_note:
        verification = replace(verification, findings=(*verification.findings, repair_note))
    budget.record_progress()
    outcome = await _fix_findings(verification, outcome, deps, escalation_deps=escalation.deps)
    measured = await _verify(outcome, deps, plan_mode=plan_mode, depth=depth)
    gate_ok = measured is not None and measured.ok
    deps.publisher.publish(
        GateEscalationFinished(
            model=model,
            gate_ok=gate_ok,
            findings=len(measured.findings) if measured is not None else 0,
            measured=measured is not None,
        )
    )
    deps.publisher.publish(
        StatusChanged(
            (gate_escalation.STATUS_GREEN if gate_ok else gate_escalation.STATUS_RED).format(
                model=model
            )
        )
    )
    report = (
        gate_escalation.REPORT_UNMEASURED
        if measured is None
        else gate_escalation.REPORT_GREEN
        if gate_ok
        else gate_escalation.REPORT_RED
    )
    outcome.final_text += report.format(rounds=fix_rounds, model=model)
    return outcome, measured if measured is not None else verification


async def _run_verification_correction_attempt(
    task: str,
    deps: AgentDeps,
    *,
    history: list[Message],
) -> AgentOutcome:
    return await run_agent(
        task,
        deps,
        history=history,
        self_review=False,
        internal=True,
        require_local_mutation=True,
        # Kapı düzeltici turda TEKRAR çalışmaz: sonsuz düzeltme döngüsü yok.
        verify=False,
    )


def _sync_turn_counters(source: AgentDeps, target: AgentDeps) -> None:
    """Düzeltici turun kopya `AgentDeps`'inde artan tur sayaçlarını asıl nesneye yaz.

    Ölçüldü (30 Ekim, A2-18): `replace(deps, config=...)` yeni nesne üretir; öğretmen/
    council çağrı sayıları ve özetleme sayısı kopyada artıp orijinale yansımıyor,
    düzeltici tur tur bütçelerini sıfırdan harcıyordu. Yalnız ARTIŞ taşınır.
    """
    if source is target:
        return
    target.teacher_calls_used = max(target.teacher_calls_used, source.teacher_calls_used)
    target.council_calls_used = max(target.council_calls_used, source.council_calls_used)
    target.condensations = max(target.condensations, source.condensations)
    target.auto_teacher_used = target.auto_teacher_used or source.auto_teacher_used


def _verification_correction_deps(deps: AgentDeps) -> AgentDeps:
    """Semantik olarak başarısız modeli varsa ilk fallback ile değiştir.

    Provider zinciri transport/kota hatasında fallback'e geçer; doğrulama bulgusu
    ise başarılı HTTP cevabının içindeki semantik başarısızlıktır ve zinciri doğal
    olarak ilerletmez. Aynı modele aynı artefaktı yeniden yazdırmak ölçülen koşulda
    aynı kusuru tekrarladı. Burada yalnız correction alt turu farklılaştırılır;
    bütçe, çalışma alanı, onay ve kalan fallback sırası paylaşılmaya devam eder.
    """
    selected = select_agent_spec(deps.config, deps.task_type, requirements=deps.task_requirements)
    if not selected.fallback:
        return deps

    correction_spec = ModelSpec(
        name=f"{selected.name}-verification-corrector",
        model=selected.fallback[0],
        tags=selected.tags,
        fallback=selected.fallback[1:],
    )
    correction_config = replace(
        deps.config,
        agent=correction_spec,
        task_model_map={},
    )
    return replace(deps, config=correction_config)


#: Sıkıştırmadan hemen sonra bağlam yine eşikteyse kaç denemede durulur.
#
# Claude Code belgesi: tek bir dev çıktı bağlamı her özetten hemen sonra yeniden
# doldurursa "birkaç denemeden sonra" otomatik sıkıştırmayı bırakıp hata gösterir,
# döngüye girmez. Üç, geçici bir büyük okumayı (sonraki turda temizlenir) tolere
# eder ama kalıcı taşmayı sonsuz özet döngüsüne çevirmez.
MAX_COMPACTION_THRASH = 3
#: Bir turda bağlam taşması hatasından en fazla kaç kez eşik öğrenilip yeniden denenir.
MAX_OVERFLOW_RELEARNS = 2


def _context_spec(deps: AgentDeps) -> ModelSpec:
    """Sıkıştırma eşiğinin hesaplanacağı model: çağrıyı GERÇEKTEN yapacak olan.

    Ölçüldü (30 Ekim, A2-15): eşik her zaman birincil modelden hesaplanıyordu; çırağa,
    öğretmene devirde ya da yükseltmede çağrı başka pencereli modelle yapılıyordu.
    """
    if deps.execution is not None:
        return _active_spec(deps, deps.execution)
    return deps.active_model_override or select_agent_spec(
        deps.config, deps.task_type, requirements=deps.task_requirements
    )


def _is_context_overflow(error: str | None) -> bool:
    from .context_budget import is_context_overflow

    return is_context_overflow(error)


def _masked_view(
    messages: list[Message], deps: AgentDeps, spec: ModelSpec, *, commit: bool = True
) -> MaskView:
    """Modele gidecek görünüm: eski araç sonuçları yer tutucuya iner, kalıcı kayıt değişmez.

    Web (tarayıcı sohbeti) zincirinde kapalıdır: `_deliver_turn` sohbeti ancak gönderilmiş
    önek DEĞİŞMEMİŞSE sürdürür; maskeleme öneki değiştirir ve her seferinde yeni sohbet
    açtırırdı. Orada eşik sıkıştırması (24.000) zaten düşük.
    """
    window = deps.config.runtime.tool_output_window
    if window <= 0 or uses_web_context(deps.config, spec):
        return MaskView(messages)
    return mask_view(
        messages,
        window,
        deps.mask_ledger,
        commit=commit,
        pinned_call_ids=deps.active_context.pinned_call_ids
        if deps.config.runtime.context_evidence_pins
        else frozenset(),
    )


async def _compact_before_call(
    messages: list[Message], deps: AgentDeps, state: _State, *, local_remaining: int | None = None
) -> bool:
    """Model çağrısından ÖNCE bağlamı eşiğin altına indir; taşma kalıcıysa False.

    Eskiden sıkıştırma yalnız tur BİTTİKTEN sonra yapılıyordu: uzun tek bir turda
    geçmiş sınırsız büyüyor, sonunda modelin penceresi taşıyordu (ölçüldü, 28 Eylül).
    """
    if deps.agent_transcript is not None:
        await deps.agent_transcript.capture(messages)
    await prepare_context(messages, deps, local_remaining=local_remaining)
    if deps.agent_transcript is not None:
        deps.agent_transcript.reset(messages)
    selected = _context_spec(deps)
    from .context_budget import compression_threshold, context_budget

    budget_spec = context_budget(deps.config, selected)
    threshold = compression_threshold(
        budget_spec, messages, learned_chars=deps.learned_compression_chars
    )
    # Eşik, modelin GERÇEKTE göreceği (maskeli) görünüme göre ölçülür: maskeleme zaten
    # küçülttüyse geçmişi özetleyip bilgi kaybetmek gereksiz.
    gorunur = _masked_view(messages, deps, selected, commit=False).messages
    if not needs_compression(gorunur, threshold_chars=threshold):
        state.compaction_thrash = 0
        return True
    before = len(messages)
    before_chars = total_chars(gorunur)
    if await pre_compact(deps, "auto"):
        # PreCompact kancası engelledi (Claude): özetleme atlanır, konuşma sürer.
        return True
    compacted = await compact_context(messages, deps, threshold)
    after_chars = total_chars(_masked_view(compacted, deps, selected, commit=False).messages)
    if after_chars < before_chars:
        summary = "\n\n".join(m.content for m in compacted if m not in messages)
        note = await compacted_context(deps, "auto", summary)
        messages[:] = with_system_note(compacted, note)
        if deps.agent_transcript is not None:
            deps.agent_transcript.reset(messages)
        deps.publisher.publish(
            ContextCompressed(
                before=before, after=len(compacted), saved_chars=before_chars - after_chars
            )
        )
        deps.condensations += 1
    visible = _masked_view(messages, deps, selected, commit=False).messages
    record_protection(visible, deps, threshold)
    if needs_compression(visible, threshold_chars=threshold):
        state.compaction_thrash += 1
        return state.compaction_thrash < MAX_COMPACTION_THRASH
    state.compaction_thrash = 0
    return True


async def _maybe_compress(messages: list[Message], deps: AgentDeps) -> list[Message]:
    if deps.agent_transcript is not None:
        await deps.agent_transcript.capture(messages)
    before = len(messages)
    await prepare_context(messages, deps)
    selected = _context_spec(deps)
    from .context_budget import compression_threshold, context_budget

    threshold = compression_threshold(
        context_budget(deps.config, selected),
        messages,
        learned_chars=deps.learned_compression_chars,
    )
    compressed = await compact_context(messages, deps, threshold, between_turns=True)
    if deps.agent_transcript is not None:
        deps.agent_transcript.reset(compressed)
    if len(compressed) < before:
        deps.publisher.publish(
            ContextCompressed(
                before=before,
                after=len(compressed),
                saved_chars=max(0, total_chars(messages) - total_chars(compressed)),
            )
        )
        deps.condensations += 1
    return compressed


PROJECT_CONTEXT_HEADER = "[Oturum proje bağlamı]\n"


def _initial_messages(
    task: str,
    history: list[Message] | None,
    *,
    plan_mode: bool,
    extra_system: str,
    inherit_system: bool = False,
    system_prompt: str | None = None,
    images: tuple[str, ...] = (),
    project_context: str = "",
) -> list[Message]:
    """Turun mesaj listesini kur: TEK sistem mesajı + geçmiş + yeni görev.

    Sistem mesajı BAŞA EKLENMEZ, geçmişinkinin YERİNE geçer. Ölçüldü: geçmiş
    her zaman bir önceki turun `outcome.messages` listesidir ve o liste zaten bir
    sistem mesajıyla başlar; başa bir tane daha eklemek listeyi
    `[system, system, user, …]` yapıyordu.

    Bunun görünmeyen bedeli tarayıcı sohbetiydi. `_deliver_turn` sohbeti ancak
    gönderilmiş önek DEĞİŞMEMİŞSE sürdürür; fazladan sistem mesajı öneki
    kaydırdığı için önek hiçbir zaman tutmuyordu. Sonuç: hem öz-denetim düzeltici
    turu hem de TUI'deki HER takip mesajı yeni bir tarayıcı sohbeti açıyor ve
    geçmişin tamamını tek düz metin olarak yeniden gönderiyordu — `ConversationState`
    docstring'inin "model aynı araç çağrılarını yeniden üretir" diye ölçtüğü durumun
    ta kendisi. Canlı izde tam olarak bu görüldü: düzeltici tur dizini baştan
    listeledi, 1388 satırlık dosyayı yeniden okudu ve görevi kaybetti.

    Sistem metni GERÇEKTEN değiştiyse (plan kipi açıldı) önek zaten kasıtlı olarak
    tutmaz ve sohbetin sıfırlanması doğrudur: model artık başka talimatlarla
    çalışıyordur.

    `inherit_system` İÇ turlar içindir (öz-denetim düzeltmesi, doğrulama kapısı
    düzeltmesi) ve sistem metnini geçmişten olduğu gibi alır. Ölçüldü: çiftlenme
    giderildikten sonra bile sohbet düşmeye devam etti, çünkü `run_agent` dersleri
    ve uzmanlık talimatını HER çağrıda o turun metnine göre hatırlıyor; düzeltici
    turun metni asıl görevden farklı olduğu için hatırlanan blok da farklı çıkıyor
    ve önek yine kayıyordu. Düzeltici tur aynı konuşmanın devamıdır — model zaten
    o talimatlarla çalışıyor, talimatı ortasından değiştirmek için bir sebep yok.
    """
    gecmis = list(history or [])
    devralinabilir = inherit_system and bool(gecmis) and gecmis[0].role == "system"
    if devralinabilir:
        system = gecmis[0].content
    else:
        system = SYSTEM_PROMPT if system_prompt is None else system_prompt
        if plan_mode:
            system += f"\n\n{PLAN_MODE_PROMPT}"
        if extra_system:
            system += f"\n\n{extra_system}"
    # Yalnızca BAŞTAKİ sistem mesajı düşürülür. Tur içinde araya giren sistem
    # notları (değişiklik kaydı, kapı uyarısı) konuşmanın parçasıdır ve kalır;
    # onları atmak öneki yine kaydırırdı.
    if gecmis and gecmis[0].role == "system":
        gecmis = gecmis[1:]
    if not inherit_system:
        gecmis = [
            message
            for message in gecmis
            if not (message.harness_note and message.content.startswith(PROJECT_CONTEXT_HEADER))
        ]
        if project_context:
            gecmis.insert(
                0, Message("user", PROJECT_CONTEXT_HEADER + project_context, harness_note=True)
            )
    return [
        Message("system", system),
        *gecmis,
        Message(
            "user",
            task,
            images=images,
            harness_note=inherit_system
            and any(message.role == "user" and not message.harness_note for message in gecmis),
        ),
    ]


def _current_policy(deps: AgentDeps) -> ApprovalPolicy:
    """Çağrının onay politikası; tur içinde `enter_plan_mode` çağrıldıysa plan kipininki (#324)."""
    from .plan_mode import entered_plan_policy

    entered = entered_plan_policy(deps)
    if entered is not None:
        return entered
    return deps.policy_factory() if deps.policy_factory else deps.policy
