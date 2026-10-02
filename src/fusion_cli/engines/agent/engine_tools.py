"""Motora bağlı araçlar: alt-ajan devri, çoklu-model danışma ve kullanıcıya soru.

Bu üçü diğer araçlardan farklı DEĞİLDİR — yalnızca çalışmak için motora erişmeleri
gerekir. Bu yüzden çalışma anında, motorun bağımlılıklarına kapanmış (closure) birer
executor olarak kayıt defterine eklenirler.

Kazanç: motor döngüsünde "şu araç özel" diye bir dal yoktur. Araç eklemek her zaman
kayıt defterine bir kayıt eklemektir; ister dosya okusun, ister başka bir ajan çalıştırsın.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from ...core.events import (
    CouncilConsulted,
    TeacherConsulted,
)
from ...core.tools import Tool, ToolArgs, ToolContext, ToolResult
from ...memory.code_index import format_matches
from ...memory.lessons import as_prompt_block
from ...tools.capabilities import (
    Capability,
    CapabilityRegistry,
    load_skill_page,
    search,
    skill_file,
    skill_files,
)
from ...tools.files import display_path, resolve_path
from ...tools.forge import forge_tool, load_forged_tools
from ...tools.registry import ToolRegistry
from ...ui import messages
from . import learning_steps
from .history_tools import recent_actions_tool
from .image_tools import generate_image_tool
from .image_view import DEFAULT_QUESTION, describe_image
from .team import (
    MAX_AGENT_DEPTH,
    SubTask,
    run_subagent,
    spawn_agent_tool,
    spawn_agents_tool,
)
from .web_tools import web_work_tools

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
    extended = _clone(registry)
    extended.register(spawn_agent_tool(deps, depth=depth, run_agent=run_agent))
    extended.register(spawn_agents_tool(deps, depth=depth, run_agent=run_agent))
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
    if deps.asker is not None:
        extended.register(_ask_user_tool(deps.asker, deps))
    if deps.home is not None:
        extended.register(build_history_tool(deps.home))
    image_tool = generate_image_tool(deps)
    if image_tool is not None:
        extended.register(image_tool)
    for web_tool in web_work_tools():
        extended.register(web_tool)
    conversation = getattr(deps, "conversation_id", "")
    memory_dir = getattr(getattr(deps, "config", None), "memory_dir", None)
    if conversation and memory_dir is not None:
        extended.register(recent_actions_tool(memory_dir, conversation))
    _register_forged_tools(extended, deps)
    return extended


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


def _clone(registry: ToolRegistry) -> ToolRegistry:
    """Temel defteri kopyala; çalışma-anı eklemeleri paylaşılan defteri kirletmesin."""
    clone = ToolRegistry()
    for tool in registry:
        clone.register(tool)
    return clone


# --------------------------------------------------------------------------- #


def _council_tool(deps: AgentDeps) -> Tool:
    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        from ..fusion import run_fusion

        question = args.get("question")
        if not isinstance(question, str) or not question.strip():
            return ToolResult.failure("'question' alanı boş olmayan bir metin olmalı.")

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
    deps: AgentDeps, context: ToolContext, *, question: str, durum: str, answer: str
) -> tuple[bool, str]:
    """`.fusion/ogretmen.md`'ye HER ZAMAN yaz; ders belleğine yalnız açıksa dene.

    `(yazıldı_mı, atlama_gerekçesi)` döner — yalnız çağıranın kullanıcıya görünür
    bir not eklemesi gerekip gerekmediğine karar vermesi için.
    """
    from datetime import UTC, datetime

    from . import teacher_notebook
    from .teacher_lessons import sync_teacher_lesson

    lesson_written = False
    skip_reason = ""
    # Otomatik plan/denetim cevapları burada yazılmaz: plan tur sonunda, yalnız
    # başarılı sonuçla `teacher_memory.record_plan_outcome` üzerinden yazılır.
    if (
        deps.lessons is not None
        and deps.config.runtime.teacher_lesson_sync
        and not deps.teacher_lesson_sync_deferred
    ):
        lesson_written, skip_reason = sync_teacher_lesson(
            deps.lessons, question=question, answer=answer
        )
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    teacher_notebook.append_entry(
        context.root,
        timestamp=timestamp,
        question=question,
        durum=durum,
        answer=answer,
        lesson_written=lesson_written,
        lesson_skip_reason=skip_reason,
    )
    return lesson_written, skip_reason


def _ask_teacher_tool(deps: AgentDeps) -> Tool:
    """Web öğretmene (ChatGPT/Gemini web) tek-soru danışma (Faz 4, Görev 1).

    `council`'dan (çoklu-API-model oylama) BİLİNÇLİ olarak AYRI: öğretmen tek,
    özel bir web oturumudur (`config.teacher`, kullanıcının kendi girişine
    bağlıdır) ve amacı oylama değil, takılan bir işte tek bir dış görüş almaktır
    (bkz. `docs/superpowers/plans/2026-09-22-ogretmen-protokolu.md` §6.1).
    """

    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        from ...core.types import CompletionRequest, Message
        from ...providers.factory import build_provider
        from ...providers.web_registry import web_registry_for
        from .teacher_brief import compile_brief

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
            return ToolResult.failure("Giriş doğrulanmış bağlı web öğretmen oturumu yok.")
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
        brief = compile_brief(
            durum=durum,
            denenenler=denenenler,
            question=question,
            touched_paths=touched_paths,
            code_excerpts=_teacher_excerpts(context),
        )
        deps.publisher.publish(TeacherConsulted(question=question, brief_truncated=brief.truncated))

        runtime = deps.config.runtime
        request = CompletionRequest(
            messages=(Message("user", brief.text),),
            temperature=runtime.temperature,
            max_tokens=runtime.max_tokens,
            timeout_s=runtime.request_timeout_s,
            max_retries=runtime.max_retries,
        )
        provider = build_provider(
            teacher,
            publisher=deps.publisher,
            retry_delays_s=runtime.retry_delays_s,
            web_sessions=web_registry_for(deps.config),
        )
        result = await provider.complete(request)
        if not result.ok or not result.text:
            return ToolResult.failure(f"Öğretmene ulaşılamadı: {result.error or 'bilinmeyen hata'}")

        _lesson_written, skip_reason = _sync_and_log_teacher_answer(
            deps, context, question=question, durum=durum, answer=result.text
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
                "durum": {
                    **_STRING,
                    "description": "kısa durum özeti: ne yapmaya çalışıyorsun, nerede takıldın",
                },
                "denenenler": {
                    **_STRING,
                    "description": "hangi yaklaşımları denedin ve neden işe yaramadı",
                },
            },
            "required": ["question"],
        },
        run=_run,
    )


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
        if not options:
            return ToolResult(await asker.ask(question))
        return ToolResult(await asker.ask(question, options, recommended))

    return Tool(
        name="ask_user",
        description="Görevi netleştirmek için kullanıcıya KISA bir soru sor ve cevabını al. "
        "Görev belirsizse ya da birden çok yorumu varsa körlemesine ilerleme, bunu kullan.",
        parameters={
            "type": "object",
            "properties": {
                "question": _STRING,
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
    if not isinstance(raw, list):
        return ()
    options: list[QuestionOption] = []
    for item in raw[:5]:
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
        registry.register(_read_skill_tool(library))
    if library.agents():
        registry.register(_find_agent_tool(library))
        registry.register(_invoke_agent_tool(deps, depth=depth, run_agent=run_agent))


def _find_skill_tool(library: CapabilityRegistry) -> Tool:
    def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        query = str(args.get("query", ""))
        hits = search(library.skills(), query)
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


def _read_skill_tool(library: CapabilityRegistry) -> Tool:
    def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        name = str(args.get("name", ""))
        skill = library.get_skill(name)
        if skill is None:
            return ToolResult.failure(f"'{name}' adlı skill yok. find_skill ile ara.")
        offset = args.get("offset", 0)
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            return ToolResult.failure("offset sıfır ya da pozitif bir tam sayı olmalı.")
        extra = args.get("file")
        if isinstance(extra, str) and extra.strip():
            target = skill_file(skill.path, extra.strip())
            if target is None:
                return ToolResult.failure(
                    f"'{extra}' bu skill'in dosyası değil. Kullanılabilir: "
                    + (", ".join(skill_files(skill.path)) or "(ek dosya yok)")
                )
            return ToolResult(load_skill_page(target, offset=offset))
        page = load_skill_page(skill.path, offset=offset)
        files = skill_files(skill.path)
        if offset == 0 and files:
            page += (
                "\n\n[Bu skill'in ek dosyaları — talimat anıyorsa read_skill(name, file=...) "
                "ile oku: " + ", ".join(files) + "]"
            )
        return ToolResult(page)

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
        if depth >= MAX_AGENT_DEPTH:
            return ToolResult.failure("Alt-ajan derinlik sınırına ulaşıldı; görevi kendin yap.")
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
    return "\n".join(f"- {item.name} — {item.description}" for item in hits)


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
        turns = sanitize_turns(
            source.read(
                session_id,
                cursor=cursor,
                limit=limit + 1,
            )
        )
        if not turns:
            return ToolResult.failure(messages.READ_SESSION_EMPTY.format(session_id=session_id))
        turns = sanitize_turns(turns)
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
    """Modelden gelen tamsayıyı güvenli aralığa daralt; bozuksa varsayılanı kullan."""
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        return default
    if maximum is not None and value > maximum:
        return default
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


def _teacher_excerpts(context: ToolContext) -> list[tuple[str, str]]:
    """Öğretmene gidecek kod kesitleri: önce düzenlenen, sonra tam okunan dosyalar.

    Web öğretmeni dosyalara erişemez; yalnız yol listesi göndermek onu kodu
    görmeden tahmin yürütmeye zorluyordu. Gizli bilgi taşıyabilecek dosyalar
    (`.env*`) hiç okunmaz, diğerlerindeki anahtar biçimli değerler maskelenir.
    """
    from ...core.redaction import redact

    sirali = [*sorted(context.touched), *sorted(context.fully_read - context.touched)]
    kesitler: list[tuple[str, str]] = []
    for yol in sirali:
        if len(kesitler) >= _TEACHER_EXCERPT_FILES:
            break
        if yol.name.startswith(".env") or not yol.is_file():
            continue
        try:
            icerik = yol.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        kesitler.append((display_path(context, yol), redact(icerik)))
    return kesitler
