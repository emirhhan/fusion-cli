"""Motora bağlı araçlar: alt-ajan devri, çoklu-model danışma ve kullanıcıya soru.

Bu üçü diğer araçlardan farklı DEĞİLDİR — yalnızca çalışmak için motora erişmeleri
gerekir. Bu yüzden çalışma anında, motorun bağımlılıklarına kapanmış (closure) birer
executor olarak kayıt defterine eklenirler.

Kazanç: motor döngüsünde "şu araç özel" diye bir dal yoktur. Araç eklemek her zaman
kayıt defterine bir kayıt eklemektir; ister dosya okusun, ister başka bir ajan çalıştırsın.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Protocol

from ...core.events import Channel, CouncilConsulted, SubAgentFinished, SubAgentStarted
from ...core.tools import Tool, ToolArgs, ToolContext, ToolResult
from ...memory.code_index import format_matches
from ...tools.capabilities import (
    Capability,
    CapabilityRegistry,
    load_agent_prompt,
    load_skill_text,
    map_tools,
    search,
)
from ...tools.registry import ToolRegistry

if TYPE_CHECKING:  # pragma: no cover - yalnızca tip denetimi için
    from .loop import AgentDeps, AgentOutcome

#: Alt-ajan iç içe çağrı sınırı. Runaway özyinelemeyi keser.
MAX_AGENT_DEPTH = 1

_STRING = {"type": "string"}


class UserAsker(Protocol):
    """Kullanıcıya serbest metinli soru sorabilen taraf."""

    async def ask(self, question: str) -> str: ...


def build_agent_registry(
    deps: AgentDeps,
    *,
    depth: int,
    run_agent: Callable[..., Awaitable[AgentOutcome]],
) -> ToolRegistry:
    """Temel araçlara motora bağlı olanları ekleyerek çalışma-anı defteri üret."""
    registry = deps.base_registry
    extended = _clone(registry)
    extended.register(_spawn_agent_tool(deps, depth=depth, run_agent=run_agent))
    # Bazı modeller bu adı tercih eder; farklı isimlendirme hataya dönüşmesin.
    extended.register_alias("invoke_subagent", "spawn_agent")
    extended.register(_council_tool(deps))
    if deps.capabilities is not None:
        _register_capability_tools(extended, deps, depth=depth, run_agent=run_agent)
    if deps.code_index is not None:
        extended.register(_search_codebase_tool(deps))
    if deps.asker is not None:
        extended.register(_ask_user_tool(deps.asker, deps))
    return extended


def _clone(registry: ToolRegistry) -> ToolRegistry:
    """Temel defteri kopyala; çalışma-anı eklemeleri paylaşılan defteri kirletmesin."""
    clone = ToolRegistry()
    for tool in registry:
        clone.register(tool)
    return clone


# --------------------------------------------------------------------------- #


def derive_sub_context(context: ToolContext) -> ToolContext:
    """Alt-ajan için bağlam türet: görev listesi AYRI, değişiklik kümesi ORTAK.

    Alt-ajan temiz bir görev listesiyle çalışmalı — ana ajanın listesini ezmesi
    kullanıcının takip ettiği planı bozardı. Ama `touched` PAYLAŞILIR: alt-ajanın
    yazdığı dosya, `depth>0` olduğu için kendi doğrulama kapısını çalıştırmaz;
    küme de ayrı olsaydı ana kapı o dosyayı hiç görmez ve değişiklik iki kapının
    arasından sızardı.

    Erişim sınırı da aynen taşınır: alt-ajan ana ajandan daha geniş bir alana
    yazamamalı, yoksa kısıtlama alt-ajan çağırarak aşılırdı.
    """
    return ToolContext(
        root=context.root,
        touched=context.touched,
        restrict_to_root=context.restrict_to_root,
        extra_roots=context.extra_roots,
    )


def _spawn_agent_tool(
    deps: AgentDeps, *, depth: int, run_agent: Callable[..., Awaitable[AgentOutcome]]
) -> Tool:
    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        from .loop import AgentDeps as _Deps

        subtask = args.get("task")
        if not isinstance(subtask, str) or not subtask.strip():
            return ToolResult.failure("'task' alanı boş olmayan bir metin olmalı.")
        if depth >= MAX_AGENT_DEPTH:
            return ToolResult.failure("Alt-ajan derinlik sınırına ulaşıldı; bu görevi kendin yap.")

        deps.publisher.publish(SubAgentStarted(task=subtask))
        # Alt-ajan TEMİZ bağlamla ve KENDİ görev listesiyle çalışır; ana ajanın
        # listesini ezmez. Çıktısı ayrı bir kanaldan akar, satırlar karışmaz.
        sub_deps = _Deps(
            config=deps.config,
            publisher=deps.publisher,
            policy=deps.policy,
            tool_context=derive_sub_context(context),
            base_registry=deps.base_registry,
            asker=deps.asker,
            channel=Channel.SUBAGENT,
        )
        outcome = await run_agent(subtask, sub_deps, depth=depth + 1, self_review=False)
        deps.publisher.publish(SubAgentFinished(tool_calls=outcome.tool_calls_made))
        return ToolResult(outcome.final_text or "(alt-ajan boş yanıt verdi)")

    return Tool(
        name="spawn_agent",
        description="Odaklı bir ALT-GÖREVİ temiz bağlamlı bir alt-ajana devret; alt-ajan "
        "işi kendi araçlarıyla yapıp özet döner. Büyük bir görevi bağımsız parçalara "
        "böldüğünde kullan (ör. 'şu modülü araştır'). Basit işlerde kullanma.",
        parameters={
            "type": "object",
            "properties": {
                "task": {**_STRING, "description": "alt-ajana verilecek net, bağımsız görev"}
            },
            "required": ["task"],
        },
        run=_run,
    )


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


def _ask_user_tool(asker: UserAsker, deps: AgentDeps) -> Tool:
    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        question = args.get("question")
        if not isinstance(question, str) or not question.strip():
            return ToolResult.failure("'question' alanı boş olmayan bir metin olmalı.")
        return ToolResult(await asker.ask(question))

    return Tool(
        name="ask_user",
        description="Görevi netleştirmek için kullanıcıya KISA bir soru sor ve cevabını al. "
        "Görev belirsizse ya da birden çok yorumu varsa körlemesine ilerleme, bunu kullan.",
        parameters={
            "type": "object",
            "properties": {"question": _STRING},
            "required": ["question"],
        },
        run=_run,
    )


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
        return ToolResult(load_skill_text(skill.path))

    return Tool(
        name="read_skill",
        description="Bir SKILL'in tam talimatını yükle (find_skill ile bulduğun ad).",
        parameters={
            "type": "object",
            "properties": {"name": _STRING},
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
        from .loop import AgentDeps as _Deps

        library = deps.capabilities
        name, task = str(args.get("name", "")), str(args.get("task", ""))
        if library is None or not name or not task.strip():
            return ToolResult.failure("'name' ve 'task' alanları dolu olmalı.")
        agent = library.get_agent(name)
        if agent is None:
            return ToolResult.failure(f"'{name}' adlı agent yok. find_agent ile ara.")
        if depth >= MAX_AGENT_DEPTH:
            return ToolResult.failure("Alt-ajan derinlik sınırına ulaşıldı; görevi kendin yap.")

        deps.publisher.publish(SubAgentStarted(task=f"{name}: {task}"))
        sub_deps = _Deps(
            config=deps.config,
            publisher=deps.publisher,
            policy=deps.policy,
            tool_context=derive_sub_context(context),
            base_registry=deps.base_registry,
            asker=deps.asker,
            code_index=deps.code_index,
            lessons=deps.lessons,
            capabilities=library,
            channel=Channel.SUBAGENT,
        )
        outcome = await run_agent(
            task,
            sub_deps,
            depth=depth + 1,
            self_review=False,
            # Uzmanın kendi talimatı sistem promptuna eklenir; kısıtladığı araç
            # seti varsa yalnızca onlar sunulur.
            extra_system=load_agent_prompt(agent.path),
            allowed_tools=map_tools(agent.tools),
        )
        deps.publisher.publish(SubAgentFinished(tool_calls=outcome.tool_calls_made))
        return ToolResult(outcome.final_text or "(uzman boş yanıt verdi)")

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
