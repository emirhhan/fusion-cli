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
    extended.register(_council_tool(deps))
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
            tool_context=ToolContext(root=context.root),
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
