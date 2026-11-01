"""Motora bağlı araçlar: alt-ajan devri, çoklu-model danışma ve kullanıcıya soru.

Bu üçü diğer araçlardan farklı DEĞİLDİR — yalnızca çalışmak için motora erişmeleri
gerekir. Bu yüzden çalışma anında, motorun bağımlılıklarına kapanmış (closure) birer
executor olarak kayıt defterine eklenirler.

Kazanç: motor döngüsünde "şu araç özel" diye bir dal yoktur. Araç eklemek her zaman
kayıt defterine bir kayıt eklemektir; ister dosya okusun, ister başka bir ajan çalıştırsın.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from pathlib import Path
from time import monotonic as _monotonic
from typing import TYPE_CHECKING, Protocol

from ...config.models import Config
from ...core.errors import FusionError
from ...core.events import (
    CouncilConsulted,
    EventPublisher,
    SkillLoaded,
    StatusChanged,
    TeacherConsulted,
)
from ...core.redaction import strip_driver_log
from ...core.refusal import looks_like_refusal
from ...core.tools import Tool, ToolArgs, ToolContext, ToolFamily, ToolResult, tool_family
from ...core.types import CompletionRequest, ModelResult, ModelSpec, is_web_session_error
from ...memory.code_index import format_matches
from ...memory.lessons import as_prompt_block
from ...tools.capabilities import (
    Capability,
    CapabilityRegistry,
    search,
    skill_file,
    skill_files,
)
from ...tools.files import display_path, resolve_path
from ...tools.forge import forge_tool, load_forged_tools
from ...tools.plugin_capabilities import with_plugin_root
from ...tools.registry import ToolRegistry
from ...tools.skill_pages import read_skill_page
from ...ui import messages
from . import learning_steps
from .agent_task_tools import agent_task_tools
from .arg_coerce import coerce_bool, coerce_int, coerce_list
from .clone_tools import clone_tools
from .history_tools import recent_actions_tool
from .image_tools import generate_image_tool
from .image_view import DEFAULT_QUESTION, describe_image
from .memory_tools import memory_read_tool, remember_tool
from .orchestration_tools import register_orchestration_tools
from .preview_log_tools import preview_log_tools
from .preview_tools import preview_tool
from .secret_paths import is_secret_path
from .teacher_lessons import AdviceBinding
from .team import (
    DEPTH_LIMIT_MESSAGE,
    SubTask,
    depth_limit_reached,
    run_subagent,
    spawn_agent_tool,
    spawn_agents_tool,
)
from .web_tools import web_work_tools

#: Asıl öğretmen cevap vermezse denenecek en fazla yedek öğretmen. Her deneme bir web
#: oturumunda 30-120 sn sürebilir (ölçüldü, 29 Eylül); birden fazlası turu boğar.
TEACHER_FALLBACKS = 1
#: Bir turda en fazla kaç `council` çağrısı (pahalı: çok model + hakem + sentez).
COUNCIL_TURN_LIMIT = 3
#: Öğretmen zincirinin toplam süre payı: `request_timeout_s` çarpanı (A1-20).
TEACHER_TOTAL_BUDGET_FACTOR = 2.0

if TYPE_CHECKING:  # pragma: no cover - yalnızca tip denetimi için
    from .loop import AgentDeps, AgentOutcome

#: Tek `read_session` sonucunun modele taşıyabileceği en fazla karakter. 12 bin
#: karakter, bir araç sayfasını küçük tutarken birkaç kısa turu birlikte görmeye
#: yeter; devam imleci büyük tek turları kayıpsız böler.
READ_SESSION_CHAR_BUDGET = 12_000
#: Devam bilgisinin gövde bütçesinden önceden ayrılan üst sınırı.
_READ_SESSION_METADATA_BUDGET = 160
_READ_SESSION_DEFAULT_LIMIT = 20
_READ_SESSION_MAX_LIMIT = 100

_STRING = {"type": "string"}


@dataclass(frozen=True, slots=True)
class QuestionOption:
    """`ask_user` için kullanıcıya gösterilecek kısa cevap adayı."""

    label: str
    description: str = ""


class UserAsker(Protocol):
    """Kullanıcıya serbest metinli soru sorabilen taraf."""

    async def ask(
        self,
        question: str,
        options: tuple[QuestionOption, ...] = (),
        recommended: str | None = None,
    ) -> str: ...


def build_agent_registry(
    deps: AgentDeps,
    *,
    depth: int,
    run_agent: Callable[..., Awaitable[AgentOutcome]],
) -> ToolRegistry:
    """Temel araçlara motora bağlı olanları ekleyerek çalışma-anı defteri üret."""
    registry = deps.base_registry
    assert registry is not None
    # Chrome eklentisine giden yol yoksa (`fusion agent`, terminal) chrome_* araçları
    # sunulmaz. Ölçüldü (2 Ekim, kabul koşusu): model bunları dört kez çağırdı ve her
    # seferinde "yalnız masaüstü uygulamasında" cevabı aldı.
    extended = _clone(registry, chrome=getattr(deps.tool_context, "chrome", None) is not None)
    from .agent_runtime_tools import runtime_tools

    extended.register(spawn_agent_tool(deps, depth=depth, run_agent=run_agent, canonical=True))
    for runtime_tool in runtime_tools(deps, depth=depth, run_agent=run_agent):
        extended.register(runtime_tool)
    # Claude Code modele tek alt ajan aracı (`Agent`) sunar; `Task` onun eski adıdır (#8).
    # Eski Fusion adları adıyla çağrılırsa çalışır ama şema olarak sunulmaz.
    for legacy in (
        spawn_agent_tool(
            deps, depth=depth, run_agent=run_agent, canonical=True, legacy_name="Task"
        ),
        spawn_agent_tool(deps, depth=depth, run_agent=run_agent),
        spawn_agents_tool(deps, depth=depth, run_agent=run_agent),
    ):
        extended.register(replace(legacy, advertised=False))
    for agent_tool in agent_task_tools(deps, depth=depth, run_agent=run_agent):
        extended.register(agent_tool)
    # Bazı modeller bu adı tercih eder; farklı isimlendirme hataya dönüşmesin.
    extended.register_alias("invoke_subagent", "spawn_agent")
    extended.register(_council_tool(deps))
    # `teacherless` yalnız `ask_teacher`'ı kapatır; `council` bundan ETKİLENMEZ
    # (Faz 4, Görev 3 — §6.1 kararı: ikisi bilinçli olarak ayrı araçlar).
    if deps.config.teacher is not None and not deps.config.runtime.teacherless:
        extended.register(_ask_teacher_tool(deps))
    if deps.capabilities is not None:
        _register_capability_tools(extended, deps, depth=depth, run_agent=run_agent)
    if deps.config.vision is not None:
        extended.register(_view_image_tool(deps))
    if deps.code_index is not None:
        extended.register(_search_codebase_tool(deps))
    if deps.lessons is not None and deps.config.runtime.lessons:
        extended.register(_recall_lessons_tool(deps))
    plain_memory = getattr(deps, "plain_memory", None)
    if plain_memory is not None:
        extended.register(remember_tool(plain_memory))
        extended.register(memory_read_tool(plain_memory))
    if deps.asker is not None:
        extended.register(_ask_user_tool(deps.asker, deps))
    if deps.home is not None:
        extended.register(build_history_tool(deps.home))
    image_tool = generate_image_tool(deps)
    if image_tool is not None:
        extended.register(image_tool)
    for web_tool in (*web_work_tools(), *clone_tools()):
        extended.register(web_tool)
    extended.register(preview_tool(deps))
    for log_tool in preview_log_tools(deps):
        extended.register(log_tool)
    conversation = getattr(deps, "conversation_id", "")
    memory_dir = getattr(getattr(deps, "config", None), "memory_dir", None)
    if conversation and memory_dir is not None:
        extended.register(recent_actions_tool(memory_dir, conversation))
    if getattr(deps.tool_context, "cron", None) is not None:
        from ...core.clock import SystemClock
        from ...tools.cron_tools import cron_tools

        for cron_tool in cron_tools(SystemClock()):
            extended.register(cron_tool)
    _register_forged_tools(extended, deps)
    # Ekip (P-061) ve dinamik iş akışı (P-062) araçları kendi modülünde kaydolur.
    register_orchestration_tools(extended, deps, depth=depth, run_agent=run_agent)
    runtime = getattr(deps.config, "runtime", None)
    kapali = (
        frozenset(getattr(runtime, "disabled_tools", ()))
        | _disabled_desktop_tools(deps, extended)
        | _subagent_removed_tools(deps, depth)
    )
    return _without(extended, kapali) if kapali else extended


#: Claude Code'un her alt ajandan aldığı araçların Fusion karşılıkları (#28):
#: AskUserQuestion, ScheduleWakeup, Workflow. Plan kipi araçları Fusion'da araç değildir.
SUBAGENT_REMOVED_TOOLS = frozenset({"ask_user", "schedule_wakeup", "workflow_run"})
#: Derinlik sınırındaki ajandan alınan Agent aracı ve eski adları.
_AGENT_TOOL_NAMES = frozenset({"Agent", "Task", "spawn_agent", "spawn_agents", "invoke_subagent"})


def _subagent_removed_tools(deps: AgentDeps, depth: int) -> frozenset[str]:
    if depth <= 0:
        return frozenset()
    from .team import depth_limit_reached

    if depth_limit_reached(deps, depth):
        return SUBAGENT_REMOVED_TOOLS | _AGENT_TOOL_NAMES
    return SUBAGENT_REMOVED_TOOLS


def _disabled_desktop_tools(deps: AgentDeps, registry: ToolRegistry) -> frozenset[str]:
    """Bilgisayar kullanımı kapalıysa (`desktop.enabled: false`, P-006) masaüstü ailesi.

    Ölçüldü (31 Ekim): kullanıcının computer use'u kapatacağı bir ayar yoktu; `desktop_*`
    araçları her turda kayıtlıydı.
    """
    desktop = getattr(deps.config, "desktop", None)
    if desktop is None or desktop.enabled:
        return frozenset()
    return frozenset(tool.name for tool in registry if tool_family(tool.name) is ToolFamily.DESKTOP)


def _register_forged_tools(registry: ToolRegistry, deps: AgentDeps) -> None:
    """Araç üretme primitifini ve daha önce üretilmiş araçları defter'e ekle.

    Denetlendi (6 Eylül): `tools/forge.py` yazılmış ama HİÇ kaydedilmemişti; model
    `make_tool` diye bir araç göremiyor, üretilmiş araçlar da sonraki turlarda
    çağrılamıyordu. Modülün var olması, Fusion'ın onu kullanabildiği anlamına gelmez.
    """
    registry.register(
        Tool(
            name="make_tool",
            description=(
                "Tekrar eden mekanik iş için kendine küçük bir Python aracı yaz. "
                "Kaynak `def run(args)` tanımlamalı; araç sonraki adımlarda adıyla çağrılır."
            ),
            parameters={
                "type": "object",
                "properties": {"name": _STRING, "source": _STRING},
                "required": ["name", "source"],
            },
            run=forge_tool,
            mutating=True,
        )
    )
    for uretilmis in load_forged_tools(deps.tool_context.root):
        if registry.get(uretilmis.name) is None:
            registry.register(uretilmis)


def teacher_candidates(config: Config, teacher: ModelSpec) -> list[ModelSpec]:
    """Asıl öğretmen ve ardından girişi doğrulanmış diğer tarayıcı oturumları."""
    adaylar = [teacher]
    for session in config.web_sessions:
        # Ölçüldü (30 Ekim, A1-20): sabit adı "en fazla 1 yedek" der ama sınır
        # `TEACHER_FALLBACKS + 2` idi; üç web oturumu varsa Codex payı kesilirdi.
        # Web yedekleri sabitle sınırlanır; Codex (kullanıcı açtıysa) ayrı pay.
        if len(adaylar) > TEACHER_FALLBACKS:
            break
        if (
            session.model != teacher.model
            and session.transport == "browser"
            and session.enabled
            and session.login_verified
        ):
            adaylar.append(ModelSpec(name=f"ogretmen-yedek-{len(adaylar)}", model=session.model))
    # Codex ChatGPT'nin KODLAMA limitini harcar: yalnız kullanıcı açtıysa yedek olur.
    from ...providers.codex_cli import PREFIX, codex_ready

    if (
        config.runtime.teacher_codex_fallback
        and teacher.model != f"{PREFIX}default"
        and codex_ready()
    ):
        adaylar.append(ModelSpec(name="ogretmen-codex", model=f"{PREFIX}default"))
    return adaylar


def _without(registry: ToolRegistry, names: frozenset[str]) -> ToolRegistry:
    """Kapatılan araçlar ve onlara bağlı takma adlar olmadan yeni defter."""
    kapali_calistiricilar = {tool.run for tool in registry if tool.name in names}
    kalan = ToolRegistry()
    for tool in registry:
        if tool.name not in names and tool.run not in kapali_calistiricilar:
            if registry.is_remote(tool.name):
                kalan.register_or_replace(tool)
            else:
                kalan.register(tool)
    return kalan


def _clone(registry: ToolRegistry, *, chrome: bool = True) -> ToolRegistry:
    """Temel defteri kopyala; çalışma-anı eklemeleri paylaşılan defteri kirletmesin."""
    clone = ToolRegistry()
    for tool in registry:
        if not chrome and tool.name.startswith("chrome_"):
            continue
        if registry.is_remote(tool.name):
            # Uzak araç işareti kopyada da kalmalı: sıkı araç yüzeyi (T1-63/M1-12) sayar.
            clone.register_or_replace(tool)
        else:
            clone.register(tool)
    return clone


# --------------------------------------------------------------------------- #


def _council_tool(deps: AgentDeps) -> Tool:
    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        from ..fusion import run_fusion

        question = args.get("question")
        if not isinstance(question, str) or not question.strip():
            return ToolResult.failure("'question' alanı boş olmayan bir metin olmalı.")

        # Ölçüldü (30 Ekim, A1-25): `ask_teacher` tur ve saat bütçesine bağlıydı,
        # çok modelli + hakemli `council` hiçbir sınıra değil; zayıf model her adımda
        # çağırıp ücretsiz kotayı ve süreyi yakabilirdi.
        if deps.council_calls_used >= COUNCIL_TURN_LIMIT:
            return ToolResult.failure(
                f"Bu turda council çağrı sınırına ulaşıldı ({COUNCIL_TURN_LIMIT}). "
                "Elindeki bilgi ve araçlarla devam et."
            )
        deps.council_calls_used += 1
        deps.publisher.publish(CouncilConsulted(question=question))
        result = await run_fusion(
            question,
            deps.config,
            publisher=deps.publisher,
            task_type="reasoning",
            synthesis=True,
        )
        if not result.final_answer:
            return ToolResult.failure("Council: hiçbir model yanıt veremedi.")
        return ToolResult(f"[council · kazanan: {result.winner}]\n{result.final_answer}")

    return Tool(
        name="council",
        description="ZOR bir kararı birden çok modele paralel danış (fusion + hakem + "
        "sentez) ve ortak akılla en sağlam cevabı al. Mimari seçim, karmaşık hata teşhisi "
        "gibi tek modelin yanılabileceği durumlarda kullan. Basit adımlarda KULLANMA; yavaştır.",
        parameters={
            "type": "object",
            "properties": {
                "question": {**_STRING, "description": "danışılacak zor soru ya da karar"}
            },
            "required": ["question"],
        },
        run=_run,
    )


def _sync_and_log_teacher_answer(
    deps: AgentDeps,
    context: ToolContext,
    *,
    question: str,
    durum: str,
    answer: str,
    binding: AdviceBinding | None = None,
) -> tuple[bool, str]:
    """`.fusion/ogretmen.md`'ye HER ZAMAN yaz; ders belleğine yalnız açıksa dene.

    `(yazıldı_mı, atlama_gerekçesi)` döner — yalnız çağıranın kullanıcıya görünür
    bir not eklemesi gerekip gerekmediğine karar vermesi için.
    """
    from datetime import UTC, datetime

    from . import teacher_notebook
    from .teacher_lessons import pending_advice

    lesson_written = False
    skip_reason = "Tavsiye henüz doğrulanmadı; ilgili değişiklik ve son kontrol bekleniyor."
    advice = pending_advice(deps, question, answer, binding)
    from ...core.events import TeacherAdviceOffered

    deps.publisher.publish(TeacherAdviceOffered(advice.advice_id))
    if deps.lessons is not None and deps.config.runtime.teacher_lesson_sync:
        deps.pending_advice.append(advice)
    timestamp = datetime.fromtimestamp(deps.clock.now(), UTC).isoformat(timespec="seconds")
    teacher_notebook.append_entry(
        context.root,
        timestamp=timestamp,
        question=question,
        durum=durum,
        answer=answer,
        lesson_written=lesson_written,
        lesson_skip_reason=skip_reason,
        advice_id=advice.advice_id,
    )
    return lesson_written, skip_reason


def _ask_teacher_tool(deps: AgentDeps) -> Tool:
    """Web öğretmene (ChatGPT/Gemini web) tek-soru danışma (Faz 4, Görev 1).

    `council`'dan (çoklu-API-model oylama) BİLİNÇLİ olarak AYRI: öğretmen tek,
    özel bir web oturumudur (`config.teacher`, kullanıcının kendi girişine
    bağlıdır) ve amacı oylama değil, takılan bir işte tek bir dış görüş almaktır
    (bkz. `geliştirme belgeleri` §6.1).
    """

    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        from ...core.types import Message
        from .teacher_brief import PLAN_FRAME, TEACHER_FRAME, compile_brief

        teacher = deps.config.teacher
        if teacher is None:
            # Araç `config.teacher is not None` iken sunulur (bkz.
            # `build_agent_registry`); buraya düşmek programlama hatasıdır ama
            # yine de anlaşılır bir mesajla biter — sessiz kırılma yok.
            return ToolResult.failure(
                "Öğretmen yapılandırılmamış. `config.yaml`'a bir `teacher:` bölümü "
                "eklemen gerekir (örnek: `defaults.yaml`'daki `teacher:` yorumu)."
            )
        from .execution_policy import is_web_model

        if is_web_model(deps.config, teacher.model) and not any(
            session.model == teacher.model
            and session.transport == "browser"
            and session.enabled
            and session.login_verified
            for session in deps.config.web_sessions
        ):
            return ToolResult.failure(
                "Giriş doğrulanmış bağlı web öğretmen oturumu yok. Öğretmen olmadan, "
                "kendi bilgin ve araçlarınla işe devam et."
            )
        question = args.get("question")
        if not isinstance(question, str) or not question.strip():
            return ToolResult.failure("'question' alanı boş olmayan bir metin olmalı.")

        from time import time as _simdi

        from .teacher_budget import TURN_LIMIT, check_and_spend

        if deps.teacher_calls_used >= TURN_LIMIT:
            return ToolResult.failure(
                f"Bu turda öğretmen çağrısı sınırına ulaşıldı ({TURN_LIMIT}). "
                "Çırak mevcut bilgilerle devam edecek."
            )

        butce = check_and_spend(context.root, now=_simdi())
        if not butce.allowed:
            dakika = round(butce.reset_in_s / 60)
            return ToolResult.failure(
                f"Öğretmen çağrı bütçesi bu saat için doldu ({butce.limit}/saat). "
                f"~{dakika} dakika sonra sıfırlanır. Ağa HİÇ ÇIKILMADI."
            )
        deps.teacher_calls_used += 1

        durum_ham = args.get("durum")
        denenenler_ham = args.get("denenenler")
        durum = durum_ham if isinstance(durum_ham, str) else ""
        denenenler = denenenler_ham if isinstance(denenenler_ham, str) else ""

        # "İlgili kod" modelin BEYANI değil, turun merkezi kaydından gelir —
        # model unutabilir/yanlış hatırlayabilir, bu küme unutmaz.
        touched_paths = sorted(
            display_path(context, yol) for yol in (context.touched | context.fully_read)
        )
        kesitler = _teacher_excerpts(context)
        if kesitler:
            # Dosya içeriği makineyi terk ediyor: kullanıcı HANGİ dosyaların gittiğini görmeli.
            deps.publisher.publish(
                StatusChanged(
                    "Öğretmene şu dosyaların içeriği gönderiliyor: "
                    + ", ".join(yol for yol, _ in kesitler)
                )
            )
        from .evidence_handoff import current_diff, evidence_text
        from .teacher_lessons import bind_advice

        selector = args.get("criterion_id")
        binding = await asyncio.to_thread(
            bind_advice, deps, selector if isinstance(selector, str) else ""
        )
        binding_text = evidence_text((binding.criterion,)) if binding else ""
        verification = deps.lesson_state.verification if deps.lesson_state else None
        failures = verification.failure_evidence if verification else ()
        brief = compile_brief(
            durum=durum
            + (
                "\nDanışma yalnız bu ölçülmüş kriterin düzeltmesine bağlıdır:\n" + binding_text
                if binding
                else ""
            ),
            denenenler=(
                denenenler
                + "\n"
                + await asyncio.to_thread(current_diff, deps)
                + "\nBaşarısızlık kanıtları:\n"
                + evidence_text(failures)
            ),
            question=question,
            char_budget=deps.config.runtime.teacher_max_brief_chars,
            touched_paths=touched_paths,
            code_excerpts=kesitler,
            # İç akışın (`teacher_flow`) plan isteği; şemada yoktur, model veremez.
            frame=PLAN_FRAME if args.get("bicim") == "plan" else TEACHER_FRAME,
        )
        if binding_text and binding_text not in brief.text:
            binding = None  # Bütçe içinde sunulmayan kriter tavsiyeye atfedilemez.
        deps.publisher.publish(TeacherConsulted(question=question, brief_truncated=brief.truncated))

        runtime = deps.config.runtime
        gorseller = _teacher_images(args.get("gorseller"), context)
        if isinstance(gorseller, ToolResult):
            return gorseller
        request = CompletionRequest(
            messages=(Message("user", brief.text, images=gorseller),),
            temperature=runtime.temperature,
            max_tokens=runtime.max_tokens,
            timeout_s=runtime.request_timeout_s,
            max_retries=runtime.max_retries,
        )
        result, refused = await _consult_candidates(deps, teacher, request)
        if result is None or not result.ok or not result.text:
            if refused:
                return _teacher_refused()
            # Ham sürücü günlüğü (Playwright "Call log") ne ekrana ne modele gider (30 Ekim).
            hata = strip_driver_log(result.error) if result is not None and result.error else None
            # Ulaşılamayan öğretmen turu bozmamalı: bu turda bir daha sorulmaz ve
            # model kendi bilgisi ve araçlarıyla işi sürdürür.
            deps.teacher_calls_used = TURN_LIMIT
            # Modele "kullanıcıya söyleme" denir ama kullanıcı çırak-only'ye düşüldüğünü
            # bilmeli (A1-21): captcha/oturum süresi dolması sessiz kalite kaybıdır.
            deps.publisher.publish(
                StatusChanged(
                    f"Öğretmen devre dışı: {hata or 'bilinmeyen hata'}. "
                    "Bu tur kendi bilgisiyle sürecek; oturumu Ayarlar'dan kontrol et."
                )
            )
            return ToolResult.failure(
                f"Öğretmene ulaşılamadı: {hata or 'bilinmeyen hata'}\n\n"
                "ÖĞRETMEN OLMADAN DEVAM ET: Bu turda öğretmene tekrar sorma. İşi kendi "
                "bilginle ve araçlarınla (dosya okuma/arama, web araştırması, komutlar) "
                "sürdür; durma, kullanıcıya öğretmeni açmasını da söyleme.",
                # Oturum/arayüz arızası aynı turda tekrar sorulunca düzelmez; çağıran
                # (`teacher_flow._ask`) ikinci deneme yapmaz.
                structured={"teacher": "session_error"} if is_web_session_error(hata) else None,
            )
        if looks_like_refusal(result.text):
            return _teacher_refused()

        _lesson_written, skip_reason = await asyncio.to_thread(
            _sync_and_log_teacher_answer,
            deps,
            context,
            question=question,
            durum=durum,
            answer=result.text,
            binding=binding,
        )
        cevap = f"[öğretmen · {result.model}]\n{result.text}"
        if skip_reason and "çelişebilir" in skip_reason:
            # Yalnız ÇAKIŞMA durumunda kullanıcıya görünür bir not eklenir —
            # "zaten kayıtlı" gibi sıradan atlama sessiz kalır (bkz. §6.3).
            cevap += (
                f"\n\n[not: bu cevaptan çıkan ders belleğe YAZILMADI, {skip_reason}. "
                "Yanlış pozitif olabilir; istersen `fusion config teacher-lesson-sync "
                "false` ile bu eşitlemeyi tamamen kapatabilirsin.]"
            )
        return ToolResult(cevap)

    return Tool(
        name="ask_teacher",
        description="Karmaşık çok dosyalı işte mimari risk veya bağımsız doğrulama "
        "konusunda web öğretmene (ChatGPT/Gemini) TEK somut soru sor. "
        "Tekrarlanan hatalarda da kullan. `council` oylamasından farklıdır; "
        "basit görevde gereksiz yere çağırma. Gizli bilgileri soruya ekleme.",
        parameters={
            "type": "object",
            "properties": {
                "question": {**_STRING, "description": "öğretmene sorulacak TEK, net soru"},
                "criterion_id": {
                    **_STRING,
                    "description": "Varsa mevcut doğrulamada başarısız ölçülen tek kriter kimliği; "
                    "tavsiye yalnız bu hedef/beklentiye bağlanır.",
                },
                "durum": {
                    **_STRING,
                    "description": "kısa durum özeti: ne yapmaya çalışıyorsun, nerede takıldın",
                },
                "denenenler": {
                    **_STRING,
                    "description": "hangi yaklaşımları denedin ve neden işe yaramadı",
                },
                "gorseller": {
                    "type": "array",
                    "items": _STRING,
                    "description": "öğretmene gösterilecek ekran görüntüsü/kare yolları "
                    "(en çok 4; görseli kendin göremiyorsan kullan)",
                },
            },
            "required": ["question"],
        },
        run=_run,
    )


#: Öğretmene tek soruda gösterilecek en fazla görsel (web taşımasının sınırıyla aynı).
MAX_TEACHER_IMAGES = 4
#: Görsel başına üst sınır: tam sayfa ekran görüntüleri birkaç MB olabilir.
MAX_TEACHER_IMAGE_BYTES = 6 * 1024 * 1024
_IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _teacher_images(raw: object, context: ToolContext) -> tuple[str, ...] | ToolResult:
    """`gorseller` yollarını data URI'ye çevir; geçersizse modele açıklayıcı hata.

    Ana model (Nemotron) görsel okuyamıyor; ekran görüntüsünü ve render karelerini
    görebilen öğretmene göstermenin yolu budur (görsel kalite için "göz").
    """
    import base64

    from ...tools.files import resolve_path

    if raw is None:
        return ()
    if not isinstance(raw, list) or len(raw) > MAX_TEACHER_IMAGES:
        return ToolResult.failure(
            f"'gorseller' en çok {MAX_TEACHER_IMAGES} yollu bir liste olmalı."
        )
    gorseller = []
    for oge in raw:
        if not isinstance(oge, str):
            return ToolResult.failure("'gorseller' yalnız dosya yolu içermeli.")
        try:
            yol = resolve_path(context, oge)
        except FusionError as err:
            return ToolResult.failure(str(err))
        # `resolve_path` kısıtsız kipte kök dışına izin verir; üçüncü tarafa giden
        # görsel için bu yetmez. Ölçüldü (29 Ekim, A1-18): model diskteki herhangi
        # bir png/jpg'yi (ör. `~/Pictures/...`) öğretmene gönderebiliyordu.
        if not _inside_allowed_roots(context, yol) or is_secret_path(yol):
            return ToolResult.failure(
                f"Görsel proje dışında ya da gizli bilgi taşıyabilecek bir yerde: {oge}. "
                "Öğretmene yalnız proje içindeki görseller gönderilir."
            )
        tur = _IMAGE_TYPES.get(yol.suffix.lower())
        if tur is None or not yol.is_file():
            return ToolResult.failure(f"Görsel bulunamadı ya da türü desteklenmiyor: {oge}")
        veri = yol.read_bytes()
        if len(veri) > MAX_TEACHER_IMAGE_BYTES:
            return ToolResult.failure(f"Görsel çok büyük (>{MAX_TEACHER_IMAGE_BYTES} bayt): {oge}")
        gorseller.append(f"data:{tur};base64,{base64.b64encode(veri).decode()}")
    return tuple(gorseller)


#: `ask_teacher` sonucunda "öğretmen reddetti" işareti. Ulaşılamayan öğretmenden farklıdır:
#: oturum ayaktadır, yalnız BU soru cevaplanmamıştır; sonraki soru cevaplanabilir.
TEACHER_REFUSED = "refused"


def _teacher_refused() -> ToolResult:
    return ToolResult.failure(
        "Öğretmenler soruyu kalıp bir retle geri çevirdi; çırak mevcut bilgilerle "
        "devam etsin, soruyu daha somut biçimde yeniden sorabilir.",
        structured={"teacher": TEACHER_REFUSED},
    )


async def _consult_candidates(
    deps: AgentDeps, teacher: ModelSpec, request: CompletionRequest
) -> tuple[ModelResult | None, bool]:
    """Adayları sırayla sor; (son sonuç, herhangi biri kalıp ret verdi mi) döndür.

    Ölçüldü (2 Ekim 2026, kabul koşuları): Gemini web aynı plan sorusunu bir çağrıda
    cevapladı, bir sonrakinde kalıp retle geri çevirdi; yedek ChatGPT oturumu captcha
    bekliyordu. Sonuç "öğretmene ulaşılamadı" oldu ve tur boyunca bir daha sorulmadı.
    Kalıp ret veren ilk adaya bu yüzden BİR kez daha sorulur.
    """
    # Sağlayıcı katmanı yalnız gerektiğinde yüklenir; testler de bu adı yamalar.
    from ...providers.factory import build_provider
    from ...providers.web_registry import web_registry_for

    runtime = deps.config.runtime

    async def _sor(aday: ModelSpec) -> ModelResult:
        provider = build_provider(
            aday,
            publisher=deps.publisher,
            retry_delays_s=runtime.retry_delays_s,
            web_sessions=web_registry_for(deps.config),
        )
        return await provider.complete(request)

    result: ModelResult | None = None
    reddeden: ModelSpec | None = None
    # Toplam süre sınırı (A1-20): her aday bir web turu (30-120 sn); zincir ve kalıp
    # ret yeniden sorusu birlikte turu dakikalarca bloklamasın. Süre dolunca yeni
    # aday BAŞLATILMAZ (süren çağrı kesilmez).
    bitis = _monotonic() + TEACHER_TOTAL_BUDGET_FACTOR * max(runtime.request_timeout_s, 1.0)
    for aday in teacher_candidates(deps.config, teacher):
        if result is not None and _monotonic() >= bitis:
            break
        if result is not None:
            deps.publisher.publish(
                StatusChanged(f"Öğretmen cevap vermedi; yedek öğretmen deneniyor ({aday.model})")
            )
        result = await _sor(aday)
        if result.ok and result.text and not looks_like_refusal(result.text):
            return result, False
        if result.ok and result.text and reddeden is None:
            reddeden = aday
    if reddeden is None:
        return result, False
    if _monotonic() >= bitis:
        return result, True
    deps.publisher.publish(StatusChanged("Öğretmen soruyu geri çevirdi; bir kez daha soruluyor"))
    return await _sor(reddeden), True


def _view_image_tool(deps: AgentDeps) -> Tool:
    """Diskteki bir görsele bakıp ne olduğunu öğrenmeyi sağlar."""

    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        raw_path = args.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            return ToolResult.failure("'path' alanı boş olmayan bir metin olmalı.")
        soru = args.get("question")
        question = soru.strip() if isinstance(soru, str) and soru.strip() else DEFAULT_QUESTION
        path = resolve_path(context, raw_path)
        aciklama, sorun = await describe_image(deps.config, path, question)
        if sorun is not None:
            return ToolResult.failure(f"{display_path(context, path)}: {sorun}")
        return ToolResult(f"{display_path(context, path)} — {aciklama}")

    return Tool(
        name="view_image",
        description="Yerel bir GÖRSELE bak ve içinde ne olduğunu öğren. Dosya ADI içeriği "
        "anlatmaz: 'player.png' bir logo, 'arkaplan.jpg' bir ekran görüntüsü olabilir. "
        "Bir asseti kullanmadan ÖNCE bununla bak; uygun olup olmadığına ancak o zaman "
        "karar verebilirsin. İsteğe bağlı 'question' ile ne öğrenmek istediğini sor.",
        parameters={
            "type": "object",
            "properties": {
                "path": {**_STRING, "description": "görselin yolu (png/jpg/gif/webp/bmp)"},
                "question": {**_STRING, "description": "görsel hakkında sorulacak soru"},
            },
            "required": ["path"],
        },
        run=_run,
    )


def _search_codebase_tool(deps: AgentDeps) -> Tool:
    def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            return ToolResult.failure("'query' alanı boş olmayan bir metin olmalı.")
        index = deps.code_index
        if index is None:  # pragma: no cover - araç yalnızca indeks varken kaydedilir
            return ToolResult.failure("Kod indeksi kullanılamıyor.")
        return ToolResult(format_matches(index.search(query)))

    return Tool(
        name="search_codebase",
        description="Kod tabanında ANLAMSAL ara. 'Auth nerede yönetiliyor?' gibi KAVRAMSAL "
        "soruları grep'ten iyi cevaplar; ilgili dosya:satır parçalarını döner. "
        "Kesin bir metni ararken bunu değil search_code kullan.",
        parameters={
            "type": "object",
            "properties": {"query": {**_STRING, "description": "kavramsal arama sorgusu"}},
            "required": ["query"],
        },
        run=_run,
    )


def _recall_lessons_tool(deps: AgentDeps) -> Tool:
    """Öğrenilmiş dersleri modelin İSTEĞİYLE getiren salt-okunur araç.

    Dersler tur başında sisteme basılmaz: görev türüne göre seçilen dersler yanlış
    türde yanlış bağlamı taşıyordu. Model bir teknolojide ya da hatada geçmiş
    deneyime ihtiyaç duyduğunda burada arar.
    """

    def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        query = str(args.get("query", "")).strip()
        if not query:
            return ToolResult.failure(messages.RECALL_LESSONS_EMPTY_QUERY)
        recalled = learning_steps.recall_lessons(query, deps)
        from ...core.lesson_runtime import LessonDelivery
        from .lesson_attribution import offer

        offer(recalled, deps, LessonDelivery.TOOL)
        return ToolResult(as_prompt_block(recalled) or messages.RECALL_LESSONS_NONE)

    return Tool(
        name="recall_lessons",
        description=(
            "Bu projede ve kullandığı teknolojilerde daha önce ÖĞRENİLMİŞ dersleri "
            "ara (kaçınılacak hatalar, işe yarayan yollar). Tanıdık bir hata ya da "
            "araç tuhaflığıyla karşılaşınca çağır."
        ),
        parameters={
            "type": "object",
            "properties": {"query": {**_STRING, "description": "konu, hata ya da teknoloji"}},
            "required": ["query"],
        },
        run=_run,
    )


def _ask_user_tool(asker: UserAsker, deps: AgentDeps) -> Tool:
    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        question = args.get("question")
        if not isinstance(question, str) or not question.strip():
            return ToolResult.failure("'question' alanı boş olmayan bir metin olmalı.")
        options = _question_options(args.get("options"))
        recommended = args.get("recommended")
        if not isinstance(recommended, str) or recommended not in {item.label for item in options}:
            recommended = None
        required = coerce_bool(args.get("required", True))
        if not isinstance(required, bool):
            return ToolResult.failure("'required' alanı doğru/yanlış olmalı.")
        answer = asker.ask(question, options, recommended) if options else asker.ask(question)
        if not required:
            receipt = deps.questions.start(answer)
            return ToolResult(
                f"Soru {receipt.question_id} yanıt bekliyor. Cevap varsayma; "
                "bağımsız okuma ve planlamaya devam et."
            )
        text = await answer
        return (
            ToolResult(text)
            if text
            else ToolResult.failure(
                "Kullanıcı cevap vermedi; bu karara bağlı işlem başlatılmamalı."
            )
        )

    return Tool(
        name="ask_user",
        description="Görevi netleştirmek için kullanıcıya KISA bir soru sor ve cevabını al. "
        "Görev belirsizse ya da birden çok yorumu varsa körlemesine ilerleme, bunu kullan.",
        parameters={
            "type": "object",
            "properties": {
                "question": _STRING,
                "required": {
                    "type": "boolean",
                    "description": "Zorunlu cevap için true; bağımsız okumaya devam "
                    "edebilen isteğe bağlı soru için false.",
                },
                "options": {
                    "type": "array",
                    "description": "Kullanıcıya sunulacak 2-5 kısa cevap seçeneği.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": _STRING,
                            "description": _STRING,
                        },
                        "required": ["label"],
                    },
                    "maxItems": 5,
                },
                "recommended": {
                    **_STRING,
                    "description": "Önerilen seçeneğin label değeri.",
                },
            },
            "required": ["question"],
        },
        run=_run,
    )


def _question_options(raw: object) -> tuple[QuestionOption, ...]:
    """Model payload'ını daralt; bozuk seçenek soru aracının tamamını düşürmesin."""
    raw = coerce_list(raw)
    if not isinstance(raw, list):
        return ()
    options: list[QuestionOption] = []
    for item in raw[:5]:
        # Zayıf modeller seçenekleri düz metin listesi verir (`["Flask", "Django"]`);
        # sessizce atmak soruyu seçeneksiz gönderirdi (A1-22).
        if isinstance(item, str):
            item = {"label": item}
        if not isinstance(item, dict):
            continue
        label = item.get("label")
        description = item.get("description", "")
        if not isinstance(label, str) or not label.strip():
            continue
        if not isinstance(description, str):
            description = ""
        normalized = label.strip()
        if normalized in {option.label for option in options}:
            continue
        options.append(QuestionOption(normalized, description.strip()))
    return tuple(options)


# --------------------------------------------------------------------------- #
# Skill / agent kütüphanesi
# --------------------------------------------------------------------------- #


def _register_capability_tools(
    registry: ToolRegistry,
    deps: AgentDeps,
    *,
    depth: int,
    run_agent: Callable[..., Awaitable[AgentOutcome]],
) -> None:
    """Kütüphanede içerik varsa arama ve devretme araçlarını aç.

    Boş bir kütüphane için araç sunmak modelin bulunmayan bir şeyi aramasına yol
    açar; bu yüzden yalnızca gerçekten girdi varken kaydedilir.
    """
    library = deps.capabilities
    if library is None:
        return
    if library.skills():
        registry.register(_find_skill_tool(library))
        registry.register(_read_skill_tool(library, publisher=deps.publisher))
    if library.agents():
        registry.register(_find_agent_tool(library))
        registry.register(_invoke_agent_tool(deps, depth=depth, run_agent=run_agent))


def _find_skill_tool(library: CapabilityRegistry) -> Tool:
    def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        query = str(args.get("query", ""))
        # `disable-model-invocation` beceriler modele görünmez; yalnız kullanıcı `/ad` ile çağırır.
        hits = search(tuple(s for s in library.skills() if s.model_invocable), query)
        return ToolResult(_format(hits) or "(eşleşen skill yok)")

    return Tool(
        name="find_skill",
        description="Uzman SKILL kütüphanesinde ara. Adları ezbere bilmezsin; ihtiyaç "
        "duyduğunda ARA, sonra read_skill ile talimatı yükle. Tahmin etme.",
        parameters={
            "type": "object",
            "properties": {"query": {**_STRING, "description": "aranan yetenek"}},
            "required": ["query"],
        },
        run=_run,
    )


def _skill_page_result(path: Path, args: ToolArgs, offset: int) -> ToolResult:
    revision = args.get("revision", "")
    page = read_skill_page(
        path, offset=offset, revision=revision if isinstance(revision, str) else ""
    )
    if page.error:
        return ToolResult.failure(page.error)
    # Eklenti becerisinde `${CLAUDE_PLUGIN_ROOT}` kurulu klasöre çözülür (sayfa ham metne göre).
    text = f"[revision={page.revision}]\n{with_plugin_root(page.text, path)}"
    if page.next_offset is not None:
        text += (
            f"\n\n[KIRPILDI: Devamı için read_skill(offset={page.next_offset}). "
            f"Aynı revision={page.revision} değerini de gönder.]"
        )
    return ToolResult(text, structured={"revision": page.revision, "next_offset": page.next_offset})


#: Modelin yükleyemeyeceği (yalnız kullanıcının çağırdığı) beceri.
SKILL_USER_ONLY = (
    "'{name}' yalnız kullanıcı /{name} ile çağırır; model yükleyemez. Gerekiyorsa kullanıcıya "
    "/{name} yazmasını öner."
)


def _skill_receipt(
    publisher: EventPublisher | None,
    skill: Capability,
    result: ToolResult,
    offset: int,
    reference: str = "",
) -> None:
    if publisher is None or not result.ok or result.structured is None:
        return
    revision = result.structured.get("revision")
    next_offset = result.structured.get("next_offset")
    if isinstance(revision, str):
        publisher.publish(
            SkillLoaded(
                qualified_name=skill.qualified_name,
                revision=revision,
                offset=offset,
                next_offset=next_offset if isinstance(next_offset, int) else None,
                reference=reference,
            )
        )


def _read_skill_tool(
    library: CapabilityRegistry,
    *,
    publisher: EventPublisher | None = None,
) -> Tool:
    def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        name = str(args.get("name", ""))
        skill = library.get_skill(name)
        if skill is None:
            adaylar = library.candidates(name)
            if adaylar:
                # Aynı ad farklı içerikli birden çok kaynakta: "yok" demek modeli yanıltır.
                return ToolResult.failure(
                    f"'{name}' birden çok kaynakta var; birini nitelikli adıyla çağır: "
                    + ", ".join(adaylar)
                )
            return ToolResult.failure(f"'{name}' adlı skill yok. find_skill ile ara.")
        extra = args.get("file")
        has_file = isinstance(extra, str) and bool(extra.strip())
        if not skill.model_invocable and not has_file:
            # `disable-model-invocation` / `user-invocable-only` (P-051): gövde yalnız kullanıcı
            # `/ad` ile çağırınca bağlama girer. Ölçüldü (31 Ekim): beceri yalnız dizinden
            # gizleniyordu; adını bilen model `read_skill` ile yükleyebiliyordu. Ek dosya
            # okuması açık kalır: kullanıcının çağırdığı becerinin gövdesi onlara başvurur.
            return ToolResult.failure(SKILL_USER_ONLY.format(name=skill.name))
        offset = coerce_int(args.get("offset", 0))
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            return ToolResult.failure("offset sıfır ya da pozitif bir tam sayı olmalı.")
        if has_file and isinstance(extra, str):
            target = skill_file(skill.path, extra.strip())
            if target is None:
                return ToolResult.failure(
                    f"'{extra}' bu skill'in dosyası değil. Kullanılabilir: "
                    + (", ".join(skill_files(skill.path)) or "(ek dosya yok)")
                )
            result = _skill_page_result(target, args, offset)
            _skill_receipt(publisher, skill, result, offset, extra.strip())
            return result
        result = _skill_page_result(skill.path, args, offset)
        if not result.ok:
            return result
        page = result.output
        files = skill_files(skill.path)
        if offset == 0 and files:
            page += (
                "\n\n[Bu skill'in ek dosyaları — talimat anıyorsa read_skill(name, file=...) "
                "ile oku: " + ", ".join(files) + "]"
            )
        _skill_receipt(publisher, skill, result, offset)
        return ToolResult(page, structured=result.structured)

    return Tool(
        name="read_skill",
        description=(
            "Bir SKILL'in talimatını yükle (find_skill ile bulduğun ad). Çıktı "
            "KIRPILDI diyorsa aynı adı bildirilen offset ile yeniden çağır. Skill'in "
            "references/ gibi ek dosyaları file ile okunur."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": _STRING,
                "file": {
                    **_STRING,
                    "description": "skill klasöründeki ek dosya (ör. references/examples.md)",
                },
                "revision": {**_STRING, "description": "İlk sayfadaki sürüm; devamda zorunlu."},
                "offset": {
                    "type": "integer",
                    "description": "Kaçıncı karakterden itibaren okunacağı.",
                },
            },
            "required": ["name"],
        },
        run=_run,
    )


def _find_agent_tool(library: CapabilityRegistry) -> Tool:
    def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        hits = search(library.agents(), str(args.get("query", "")))
        return ToolResult(_format(hits) or "(eşleşen agent yok)")

    return Tool(
        name="find_agent",
        description="Uzman AGENT kütüphanesinde ara. Uygun bir uzman bulursan işi "
        "invoke_agent ile ona devret.",
        parameters={
            "type": "object",
            "properties": {"query": {**_STRING, "description": "aranan uzmanlık"}},
            "required": ["query"],
        },
        run=_run,
    )


def _invoke_agent_tool(
    deps: AgentDeps, *, depth: int, run_agent: Callable[..., Awaitable[AgentOutcome]]
) -> Tool:
    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        library = deps.capabilities
        name, task = str(args.get("name", "")), str(args.get("task", ""))
        if library is None or not name or not task.strip():
            return ToolResult.failure("'name' ve 'task' alanları dolu olmalı.")
        if library.get_agent(name) is None:
            return ToolResult.failure(f"'{name}' adlı agent yok. find_agent ile ara.")
        if depth_limit_reached(deps, depth):
            return ToolResult.failure(DEPTH_LIMIT_MESSAGE)
        # Uzmanın kendi talimatı sistem promptuna eklenir; kısıtladığı araç seti
        # varsa yalnızca onlar sunulur (bkz. `team.resolve_persona`).
        run = await run_subagent(
            deps, SubTask(task=task.strip(), persona=name), depth=depth, run_agent=run_agent
        )
        return ToolResult(run.text if run.text else "(uzman boş yanıt verdi)")

    return Tool(
        name="invoke_agent",
        description="Bir UZMAN AGENT'a alt-görev devret (find_agent ile bulduğun ad). "
        "Uzman kendi talimatı ve araçlarıyla çalışıp sonucu döner.",
        parameters={
            "type": "object",
            "properties": {"name": _STRING, "task": _STRING},
            "required": ["name", "task"],
        },
        run=_run,
    )


def _format(hits: tuple[Capability, ...]) -> str:
    return "\n".join(f"- {item.qualified_name} — {item.description}" for item in hits)


# --------------------------------------------------------------------------- #
# Devralınan oturum geçmişi
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class _HistoryPage:
    """Sınırlandırılmış araç gövdesi ve varsa kesin devam konumu."""

    body: str
    next_cursor: int | None
    next_text_cursor: int = 0


def build_history_tool(home: Path) -> Tool:
    """`read_session` — devralınan oturumun ayrıntısını imleçle oku.

    Künye ajana NEREYE bakacağını söyler; bu araç oraya BAKMASINI sağlar. Oturumun
    tamamı hiçbir zaman bağlama yüklenmez: medyan bir oturum 1,3 MB'tır.
    """

    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        from ...history import source_by_name
        from ...history.sanitize import sanitize_turns

        source_name = args.get("source")
        session_id = args.get("session_id")
        if not isinstance(source_name, str) or not isinstance(session_id, str):
            return ToolResult.failure(messages.READ_SESSION_INVALID_ARGUMENTS)
        source = source_by_name(home, source_name)
        if source is None:
            return ToolResult.failure(
                messages.READ_SESSION_UNKNOWN_SOURCE.format(source=source_name)
            )
        cursor = _bounded_int(args.get("cursor"), default=0, minimum=0)
        limit = _bounded_int(
            args.get("limit"),
            default=_READ_SESSION_DEFAULT_LIMIT,
            minimum=1,
            maximum=_READ_SESSION_MAX_LIMIT,
        )
        text_cursor = _bounded_int(args.get("text_cursor"), default=0, minimum=0)
        # Kaynak okuması disk G/Ç'dir (medyan oturum 1,3 MB): olay döngüsünü bloklamamak
        # için iş parçacığında yapılır (A1-23). `sanitize_turns` tur sayısını DEĞİŞTİRMEZ
        # (1:1 maskeleme), bu yüzden `cursor` kaynak konumuyla tutarlı kalır; ikinci
        # gereksiz geçiş kaldırıldı.
        raw_turns = await asyncio.to_thread(
            source.read,
            session_id,
            cursor=cursor,
            limit=limit + 1,
        )
        turns = sanitize_turns(raw_turns)
        if not turns:
            return ToolResult.failure(messages.READ_SESSION_EMPTY.format(session_id=session_id))
        if text_cursor > len(turns[0].text):
            return ToolResult.failure(
                messages.READ_SESSION_INVALID_TEXT_CURSOR.format(cursor=text_cursor)
            )
        page = _history_page(turns, cursor, limit, text_cursor)
        return ToolResult(_history_page_output(page))

    return Tool(
        name="read_session",
        description=messages.READ_SESSION_DESCRIPTION,
        parameters={
            "type": "object",
            "properties": {
                "source": _STRING,
                "session_id": _STRING,
                "cursor": {"type": "integer"},
                "limit": {"type": "integer"},
                "text_cursor": {"type": "integer"},
            },
            "required": ["source", "session_id"],
        },
        run=_run,
    )


def _bounded_int(
    value: object,
    *,
    default: int,
    minimum: int,
    maximum: int | None = None,
) -> int:
    """Modelden gelen tamsayıyı güvenli aralığa KISTIR; sayı değilse varsayılanı kullan.

    Aralık dışı değer varsayılana çevrilmez: `limit=500` sessizce 20 olurdu (A1-23).
    """
    if not isinstance(value, int) or isinstance(value, bool):
        return default
    if value < minimum:
        return minimum
    if maximum is not None and value > maximum:
        return maximum
    return value


def _history_page(
    turns: tuple[object, ...], cursor: int, limit: int, text_cursor: int
) -> _HistoryPage:
    """Turları karakter bütçesine sığdır ve devam konumunu hesapla."""
    from ...history.models import Turn

    visible = tuple(turn for turn in turns[:limit] if isinstance(turn, Turn))
    body_budget = READ_SESSION_CHAR_BUDGET - _READ_SESSION_METADATA_BUDGET
    parts: list[str] = []
    used = 0
    for index, turn in enumerate(visible):
        offset = text_cursor if index == 0 else 0
        prefix = ("\n\n" if parts else "") + f"[{turn.role}] "
        available = body_budget - used - len(prefix)
        if available <= 0:
            return _HistoryPage("".join(parts), cursor + index, offset)
        remaining_text = turn.text[offset:]
        if len(remaining_text) > available:
            parts.append(prefix + remaining_text[:available])
            return _HistoryPage("".join(parts), cursor + index, offset + available)
        parts.append(prefix + remaining_text)
        used += len(prefix) + len(remaining_text)
    if len(turns) > limit:
        return _HistoryPage("".join(parts), cursor + limit)
    return _HistoryPage("".join(parts), None)


def _history_page_output(page: _HistoryPage) -> str:
    """Gövdeye açık tamamlanma/devam üstverisi ekle ve sert bütçeyi koru."""
    if page.next_cursor is None:
        metadata = messages.READ_SESSION_COMPLETE
    else:
        metadata = messages.READ_SESSION_CONTINUATION.format(
            cursor=page.next_cursor,
            text_cursor=page.next_text_cursor,
        )
    body = page.body[: READ_SESSION_CHAR_BUDGET - len(metadata)]
    return body + metadata


#: Öğretmene kesit olarak gönderilen en fazla dosya sayısı; düzenlenenler önce gelir.
_TEACHER_EXCERPT_FILES = 4
#: Bir kesit için dosyadan okunan en fazla karakter (dosyanın tamamı belleğe alınmaz).
_TEACHER_EXCERPT_CHARS = 60_000


def _inside_allowed_roots(context: ToolContext, path: Path) -> bool:
    """Yol proje kökünde ya da `--add-dir` ile AÇIKÇA verilen dizinlerde mi?"""
    try:
        concrete = path.resolve()
        izinli = (context.root.resolve(), *(extra.resolve() for extra in context.extra_roots))
    except OSError:
        return False
    return any(concrete == izin or izin in concrete.parents for izin in izinli)


def _teacher_excerpts(context: ToolContext) -> list[tuple[str, str]]:
    """Öğretmene gidecek kod kesitleri: önce düzenlenen, sonra tam okunan dosyalar.

    Web öğretmeni dosyalara erişemez; yalnız yol listesi göndermek onu kodu
    görmeden tahmin yürütmeye zorluyordu. Üçüncü tarafa giden içerik şu kurallarla
    sınırlanır (A1-18, ölçüldü 29 Ekim: eskiden yalnız `.env*` adı atlanıyordu, boyut
    ve konum denetimi yoktu):

    - sır dosyası adı/konumu (`id_rsa`, `*.pem`, `credentials.json`, `secrets.enc`,
      `.npmrc`, `terraform.tfstate`, `.ssh/` altı…) hiç okunmaz — bkz. `secret_paths`;
    - proje kökü (ve `--add-dir`) DIŞINDaki dosya gönderilmez;
    - dosyadan en çok `_TEACHER_EXCERPT_CHARS` karakter okunur;
    - kalan anahtar biçimli değerler `redact()` ile maskelenir.
    """
    from ...core.redaction import redact

    sirali = [*sorted(context.touched), *sorted(context.fully_read - context.touched)]
    kesitler: list[tuple[str, str]] = []
    for yol in sirali:
        if len(kesitler) >= _TEACHER_EXCERPT_FILES:
            break
        if is_secret_path(yol) or not yol.is_file() or not _inside_allowed_roots(context, yol):
            continue
        try:
            with yol.open(encoding="utf-8") as dosya:
                icerik = dosya.read(_TEACHER_EXCERPT_CHARS)
        except (OSError, UnicodeDecodeError):
            continue
        kesitler.append((display_path(context, yol), redact(icerik)))
    return kesitler
