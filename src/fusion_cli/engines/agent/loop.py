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

import json
from dataclasses import dataclass, field
from pathlib import Path

from ...config.eligibility import effort_for_spec
from ...config.model_select import select_agent_spec
from ...config.models import Config
from ...core.concurrency import BackgroundTasks
from ...core.events import (
    Channel,
    ContextCompressed,
    EventPublisher,
    SelfReviewFinished,
    SelfReviewStarted,
    StepLimitReached,
    ToolExecuted,
    ToolOutcome,
    VerificationFailed,
)
from ...core.health import HealthRegistry
from ...core.memory import CodeIndex, LessonMemory
from ...core.tools import ToolContext, ToolResult
from ...core.types import CompletionRequest, Message, ModelResult, StreamDone, ToolCall
from ...core.verification import VerificationResult, Verifier
from ...memory.lessons import as_prompt_block
from ...providers.factory import build_provider
from ...tools import ToolRegistry, build_registry
from ...tools.capabilities import CapabilityRegistry
from ...tools.preview import file_diff
from . import compaction, learning_steps, reflexion, review, skill_recall
from .approval import ApprovalPolicy, Decision, build_request
from .classify import TaskKind, classify_task, recall_scope, scope_of
from .engine_tools import UserAsker, build_agent_registry
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
#: Kullanıcı reddettiğinde modele dönen açıklama. Hata DEĞİLDİR; refleksiyon tetiklemez.
DENIED_MESSAGE = "Kullanıcı bu işlemi onaylamadı. Farklı bir yol dene ya da nedenini açıkla."
#: Plan modunda değiştirici araç hiç çalıştırılmaz ve kullanıcıya sorulmaz.
BLOCKED_MESSAGE = "PLAN MODU: değişiklik yapılamaz. Sorma, yalnızca planı sun."

_DECISION_MESSAGES = {
    Decision.DENIED: DENIED_MESSAGE,
    Decision.BLOCKED: BLOCKED_MESSAGE,
}
_DECISION_OUTCOMES = {
    Decision.DENIED: ToolOutcome.DENIED,
    Decision.BLOCKED: ToolOutcome.BLOCKED,
}


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
    if not plan_mode and depth == 0:
        played = await maybe_run_playbook(task, deps)
        if played is not None:
            return played
        if deps.config.runtime.workflow_mode:
            return await run_workflow_stages(task, deps, run_agent)

    registry = build_agent_registry(deps, depth=depth, run_agent=run_agent)
    kind = classify_task(task)
    recalled = learning_steps.recall_lessons(task, deps, scope=recall_scope(kind))
    remembered = as_prompt_block(recalled)
    expertise = _recall_skill(kind, deps, depth=depth)
    messages = _initial_messages(
        task,
        history,
        plan_mode=plan_mode,
        extra_system="\n\n".join(part for part in (remembered, expertise, extra_system) if part),
    )

    outcome = await _drive(
        messages,
        deps,
        registry,
        plan_mode=plan_mode,
        allowed_tools=allowed_tools,
        step_limit=step_limit,
    )

    should_review = deps.config.runtime.self_review if self_review is None else self_review
    if should_review and not plan_mode and depth == 0 and outcome.final_text.strip():
        outcome = await _self_review(task, outcome, deps)

    verification = None
    for _ in range(MAX_VERIFY_ROUNDS if verify else 0):
        verification = await _verify(outcome, deps, plan_mode=plan_mode, depth=depth)
        # Bulgu YOKLUĞU başarı değildir: `ok=False` tek başına düzeltmeyi hak eder.
        # Koşul eskiden `not verification.findings` de arıyordu; yalnızca özet
        # dolduran bir kapı (komut doğrulayıcısı) başarısız olduğunda agent
        # düzeltmeye hiç başlamıyordu.
        if verification is None or verification.ok:
            break
        outcome = await _fix_findings(verification, outcome, deps)

    await learning_steps.learn(task, outcome, deps, plan_mode=plan_mode, scope=scope_of(kind))
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
    tool_calls_made: int = 0
    auto_continues: int = 0
    tool_calls_last_turn: int = 0


async def _drive(
    messages: list[Message],
    deps: AgentDeps,
    registry: ToolRegistry,
    *,
    plan_mode: bool,
    allowed_tools: set[str] | None = None,
    step_limit: int | None = None,
) -> AgentOutcome:
    state = _State()
    final_text = ""
    bos_deneme = 0
    # Hedef kipi gibi ısrarcı görevler daha çok adım ister; varsayılan yapılandırmadan gelir.
    limit = step_limit or deps.config.runtime.agent_max_steps

    for _ in range(limit):
        result = await _call_model(messages, deps, registry, allowed_tools)
        if not result.ok:
            return AgentOutcome(result.error or "", messages, state.tool_calls_made, ok=False)

        if not result.is_usable:
            # Model BOŞ cevap döndü (metin yok, araç çağrısı yok) ama teknik olarak
            # başarılı. Ölçüldü: agent turu bu yüzden hiçbir iş yapmadan bitiyordu.
            # Tek modelli zincirde yedek yoktur, o yüzden
            # çare yeniden denemektir — sınırlı, ısrar ederse tur biter.
            bos_deneme += 1
            if bos_deneme <= MAX_EMPTY_RETRIES:
                messages.append(reflexion.empty_response_note())
                continue
            return AgentOutcome(final_text, messages, state.tool_calls_made)

        messages.append(Message("assistant", result.text, tool_calls=result.tool_calls))

        if not result.tool_calls:
            final_text = result.text
            if _should_auto_continue(final_text, deps, state, plan_mode=plan_mode):
                state.auto_continues += 1
                messages.append(reflexion.auto_continue_note())
                continue
            return AgentOutcome(final_text, messages, state.tool_calls_made)

        errored = await _run_tools(result.tool_calls, messages, deps, registry, state)
        if errored and deps.config.runtime.reflexion and not plan_mode:
            messages.append(reflexion.note(persistent=False))

    deps.publisher.publish(StepLimitReached(limit=limit))
    return AgentOutcome(final_text, messages, state.tool_calls_made, hit_step_limit=True)


async def _call_model(
    messages: list[Message],
    deps: AgentDeps,
    registry: ToolRegistry,
    allowed_tools: set[str] | None = None,
) -> ModelResult:
    """Modeli akıtarak çağır; metin parçaları olay olarak yayınlanır."""
    runtime = deps.config.runtime
    spec = select_agent_spec(deps.config, deps.task_type)
    request = CompletionRequest(
        messages=tuple(messages),
        temperature=runtime.temperature,
        max_tokens=runtime.max_tokens,
        timeout_s=runtime.request_timeout_s,
        max_retries=runtime.max_retries,
        tools=tuple(registry.schemas(_permitted(allowed_tools, registry))),
        reasoning_effort=effort_for_spec(spec, runtime.reasoning_effort),
    )
    provider = build_provider(
        spec,
        publisher=deps.publisher,
        retry_delays_s=runtime.retry_delays_s,
        channel=deps.channel,
        health=deps.health,
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


def _permitted(allowed_tools: set[str] | None, registry: ToolRegistry) -> set[str] | None:
    if allowed_tools is None:
        return None
    return (allowed_tools | ALWAYS_ALLOWED) & set(registry.names())


def _should_auto_continue(
    final_text: str, deps: AgentDeps, state: _State, *, plan_mode: bool
) -> bool:
    if plan_mode or state.auto_continues >= MAX_AUTO_CONTINUE:
        return False
    return reflexion.looks_unfinished(
        final_text,
        tool_calls_last_turn=state.tool_calls_last_turn,
        has_pending_todos=deps.tool_context.todos.has_pending,
    )


# --------------------------------------------------------------------------- #
# Araç yürütme
# --------------------------------------------------------------------------- #


async def _run_tools(
    calls: tuple[ToolCall, ...],
    messages: list[Message],
    deps: AgentDeps,
    registry: ToolRegistry,
    state: _State,
) -> bool:
    """Araçları sırayla çalıştır; en az biri hata döndürdüyse True."""
    state.tool_calls_last_turn = len(calls)
    errored = False

    for call in calls:
        args = parse_arguments(call.arguments)
        # Diff, dosya değişmeden ÖNCE hesaplanmalı: sonrasında eski içerik kaybolur.
        pending_diff = file_diff(call.name, args, deps.tool_context)
        result, outcome = await _execute(call, args, deps, registry)
        if outcome is ToolOutcome.OK:
            state.tool_calls_made += 1
        elif outcome is ToolOutcome.FAILED:
            errored = True

        # Diff yalnızca değişiklik gerçekten uygulandıysa gösterilir; reddedilen ya da
        # engellenen bir çağrıda yeşil/kırmızı blok "oldu" izlenimi vermemeli.
        diff = pending_diff if outcome is ToolOutcome.OK else None
        deps.publisher.publish(
            ToolExecuted(
                name=call.name, args=args, outcome=outcome, output=result.output, diff=diff
            )
        )
        messages.append(
            Message("tool", result.output, tool_call_id=call.id, name=call.name, ok=result.ok)
        )
    return errored


async def _execute(
    call: ToolCall, args: dict[str, object], deps: AgentDeps, registry: ToolRegistry
) -> tuple[ToolResult, ToolOutcome]:
    """Onaydan geçir ve çalıştır. Bilinmeyen araç da kayıt defterinin sorunu."""
    tool = registry.get(call.name)
    if tool is not None and tool.mutating:
        decision = await deps.policy.decide(build_request(tool, args, deps.allowed_commands))
        if decision is not Decision.ALLOW:
            # Reddetme ve engelleme HATA DEĞİLDİR: refleksiyon tetiklenmemeli,
            # model yalnızca farklı bir yol denemeli.
            return ToolResult(_DECISION_MESSAGES[decision]), _DECISION_OUTCOMES[decision]

    result = await registry.execute(call.name, args, deps.tool_context)
    return result, ToolOutcome.OK if result.ok else ToolOutcome.FAILED


def parse_arguments(raw: str) -> dict[str, object]:
    """Modelin ürettiği ham JSON'u sözlüğe çevir; bozuksa boş sözlük.

    Boş sözlük döndürmek bilinçlidir: araç kendi doğrulamasını yapar ve modele hangi
    alanın eksik olduğunu söyler. Burada patlamak bu bilgiyi kaybettirir.
    """
    try:
        parsed = json.loads(raw or "{}")
    except (json.JSONDecodeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


# --------------------------------------------------------------------------- #
# Öz-denetim ve sıkıştırma
# --------------------------------------------------------------------------- #


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
