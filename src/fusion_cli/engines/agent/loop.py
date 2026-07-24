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
from dataclasses import dataclass, field, replace
from pathlib import Path

from ...config.models import Config
from ...core.concurrency import BackgroundTasks
from ...core.events import (
    Channel,
    ContextCompressed,
    EventPublisher,
    LessonsLearned,
    LessonsRecalled,
    SelfReviewFinished,
    SelfReviewStarted,
    StepLimitReached,
    ToolExecuted,
    ToolOutcome,
)
from ...core.memory import CodeIndex, Lesson, LessonMemory
from ...core.tools import ToolContext, ToolResult
from ...core.types import CompletionRequest, Message, ModelResult, StreamDone, ToolCall
from ...core.verification import Verifier
from ...memory.lessons import as_prompt_block
from ...providers.factory import build_provider
from ...tools import ToolRegistry, build_registry
from ...tools.capabilities import CapabilityRegistry
from . import compaction, learning, reflexion, review
from .approval import ApprovalPolicy, Decision, build_request
from .classify import classify_task, recall_scope, scope_of
from .engine_tools import UserAsker, build_agent_registry
from .verification import resolve_turn_success

_PROMPTS = Path(__file__).parent / "prompts"
SYSTEM_PROMPT = (_PROMPTS / "system.md").read_text(encoding="utf-8")
PLAN_MODE_PROMPT = (_PROMPTS / "plan_mode.md").read_text(encoding="utf-8")

#: Yarım kalan turda en fazla kaç kez "devam et" enjekte edilir.
MAX_AUTO_CONTINUE = 1
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
    #: Verilirse kod değiştiren tur sonrası doğrulama kapısı çalışır ve sonucu ders
    #: güvenini besler. Verilmezse (varsayılan) mevcut davranış birebir korunur.
    verifier: Verifier | None = None


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
) -> AgentOutcome:
    """Bir görevi araçlarla çalıştır. Döndürülen geçmiş bir sonraki tura beslenir.

    `allowed_tools` verilirse modele YALNIZCA o araçlar sunulur (uzman agent'lar
    kendi araç setini bildirebilir). Görev yönetimi ve soru sorma her zaman açıktır.
    """
    registry = build_agent_registry(deps, depth=depth, run_agent=run_agent)
    kind = classify_task(task)
    recalled = _recall_lessons(task, deps, scope=recall_scope(kind))
    remembered = as_prompt_block(recalled)
    messages = _initial_messages(
        task,
        history,
        plan_mode=plan_mode,
        extra_system="\n\n".join(part for part in (remembered, extra_system) if part),
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

    await _learn(task, outcome, deps, plan_mode=plan_mode, scope=scope_of(kind))
    await _reinforce_recalled(recalled, outcome, deps, plan_mode=plan_mode)
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
    # Hedef kipi gibi ısrarcı görevler daha çok adım ister; varsayılan yapılandırmadan gelir.
    limit = step_limit or deps.config.runtime.agent_max_steps

    for _ in range(limit):
        result = await _call_model(messages, deps, registry, allowed_tools)
        if not result.ok:
            return AgentOutcome(result.error or "", messages, state.tool_calls_made, ok=False)

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
    request = CompletionRequest(
        messages=tuple(messages),
        temperature=runtime.temperature,
        max_tokens=runtime.max_tokens,
        timeout_s=runtime.request_timeout_s,
        max_retries=runtime.max_retries,
        tools=tuple(registry.schemas(_permitted(allowed_tools, registry))),
    )
    provider = build_provider(deps.config.agent, publisher=deps.publisher, channel=deps.channel)

    result: ModelResult | None = None
    async for item in provider.stream(request):
        if isinstance(item, StreamDone):
            result = item.result
    return result or ModelResult(
        name=deps.config.agent.name,
        model=deps.config.agent.model,
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
        result, outcome = await _execute(call, args, deps, registry)
        if outcome is ToolOutcome.OK:
            state.tool_calls_made += 1
        elif outcome is ToolOutcome.FAILED:
            errored = True

        deps.publisher.publish(
            ToolExecuted(name=call.name, args=args, outcome=outcome, output=result.output)
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
    )
    correction.tool_calls_made += outcome.tool_calls_made
    return correction


def _recall_lessons(task: str, deps: AgentDeps, *, scope: str | None) -> tuple[Lesson, ...]:
    """Göreve benzer, güveni eşiğin üstünde ve kapsamına uyan dersleri hatırla."""
    if deps.lessons is None or not deps.config.runtime.lessons:
        return ()
    recalled = deps.lessons.recall(task, scope=scope)
    if recalled:
        deps.publisher.publish(LessonsRecalled(count=len(recalled)))
    return recalled


async def _reinforce_recalled(
    recalled: tuple[Lesson, ...], outcome: AgentOutcome, deps: AgentDeps, *, plan_mode: bool
) -> None:
    """Enjekte edilen derslerin güvenini turun sonucuna göre güncelle.

    Tur başarısı: model temiz bitti, adım sınırına dayanılmadı ve (doğrulama kapısı
    devredeyse) kapı geçti. Kod değiştiren turdan sonra kapı çalıştırılır; böylece
    "doğrulamadan bitirme" gibi kurallar dekoratif kalmaz, gerçekten uygulanır.
    """
    if deps.lessons is None or not deps.config.runtime.lessons:
        return
    if plan_mode or not recalled:
        return
    verification = None
    if deps.verifier is not None and outcome.tool_calls_made > 0:
        verification = await deps.verifier.verify()
    success = resolve_turn_success(
        outcome_ok=outcome.ok, hit_step_limit=outcome.hit_step_limit, verification=verification
    )
    deps.lessons.reinforce(tuple(lesson.text for lesson in recalled), success=success)


async def _learn(
    task: str, outcome: AgentOutcome, deps: AgentDeps, *, plan_mode: bool, scope: str
) -> None:
    """Turdan ders çıkar ve belleğe yaz.

    Yalnızca GERÇEK İŞ yapıldıysa (araç çağrısı varsa) çalışır: sohbet turlarından
    ders çıkarmak hem boşuna model çağrısıdır hem de belleği değersiz kayıtla doldurur.
    """
    if deps.lessons is None or not deps.config.runtime.lessons:
        return
    if plan_mode or outcome.tool_calls_made == 0:
        return

    work = _extract_and_store(task, list(outcome.messages), deps, scope=scope)
    if deps.background is None:
        await work
    else:
        deps.background.spawn(work)


async def _extract_and_store(
    task: str, messages: list[Message], deps: AgentDeps, *, scope: str
) -> None:
    """Ders çıkarımının asıl işi. Arka planda çalışabilmesi için ayrı tutulur."""
    if deps.lessons is None:
        return
    lessons = await learning.extract_lessons(
        task, messages, config=deps.config, publisher=deps.publisher
    )
    # Yazım kapısı: yalnızca ölçülebilir kanıtı olan, sır içermeyen, mevcut derslerle
    # çakışmayan adaylar belleğe girer. Bellek çöple/zehirle dolmasın.
    screened = learning.screen_lessons(
        lessons,
        deps.lessons.all(),
        has_evidence=learning.has_measurable_evidence(messages),
    )
    # Öğrenilen ders, görevin kapsamıyla etiketlenir: benzer kapsamda daha isabetli
    # geri çağrılır, alakasız kapsamda enjekte edilmez.
    scoped = tuple(replace(lesson, scope=scope) for lesson in screened)
    stored = learning.store_lessons(scoped, deps.lessons)
    if stored:
        deps.publisher.publish(LessonsLearned(count=stored))


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
