"""Fork alt ajan: ana konuşmanın bağlamını devralan izole alt görev (P-054).

Claude Code'un `/subtask` ve beceri frontmatter'ındaki `context: fork` davranışının
karşılığı. Olağan alt ajan TEMİZ bağlamla başlar (yalnız görev metni + kişilik); fork alt
ajan ana konuşmanın o ana kadarki mesajlarını başlangıç geçmişi olarak alır,
üst sistem istemiyle ve kendi adım bütçesiyle koşar, sonucu tek özet olarak döner. Ana
konuşmaya yalnız bu özet eklenir; alt ajanın kendi araç çağrıları ana geçmişe karışmaz.

Devredilen görünüm Claude Code'daki gibi TAM geçmiştir (#31): sistem mesajı gövdeden
ayrılır ve aynen sistem istemi olarak devredilir, mesajlar kırpılmaz. Cevapsız araç
çağrıları (o an çalışan `Agent` dahil) devredilmez: sağlayıcı sınırı orphan çağrıyı reddeder.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from ...core.types import Message

if TYPE_CHECKING:
    from .loop import AgentDeps, AgentOutcome

#: Alt ajanın başlangıç mesajına eklenen açıklama.
FORK_BRIEF = (
    "Bu görev ana konuşmanın bağlamını DEVRALAN bir alt görevdir: yukarıdaki mesajlar ana "
    "konuşmadır, onları yeniden yapma; yalnız verilen alt görevi yap ve kısa bir sonuç döndür."
)

LiveHistory = Callable[[], Sequence[Message]]


def fork_history(messages: Sequence[Message] | None) -> list[Message]:
    """Ana geçmişin alt ajana devredilen görünümü: sistemsiz TAM geçmiş (#31).

    Claude Code fork'u ana oturumun bütün mesaj geçmişini alır; Fusion kırpmaz, yalnız
    cevapsız araç çağrılarını düşürür (sağlayıcı sınırı orphan çağrıyı reddeder). Bağlam
    büyürse alt ajanın kendi otomatik özetlemesi devreye girer.
    """
    return drop_orphan_tool_calls(
        [message for message in (messages or ()) if message.role != "system"]
    )


def drop_orphan_tool_calls(messages: Sequence[Message]) -> list[Message]:
    """Cevabı olmayan araç çağrılarını ve çağrısı olmayan araç sonuçlarını düşür.

    Ölçüldü (31 Ekim): `spawn_agent baglam_miras=true` çalışırken ana döngü assistant
    mesajını `tool_calls` ile geçmişe araç ÇALIŞMADAN ekler (`loop.py`), yani canlı
    geçmişin son mesajı cevapsız bir çağrıdır. Alt ajan bunun arkasına kendi `user`
    görevini eklediğinde OpenAI/Anthropic uyumlu uçlar "orphan tool call" (400) döner.
    Çağrının bir kısmı cevaplı (paralel çağrı yarıda) ise o tur bütünüyle düşer.
    """
    kept: list[Message] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        if message.role == "tool":
            index += 1  # çağrısı önceki turda atılmış sonuç
            continue
        if message.role != "assistant" or not message.tool_calls:
            kept.append(message)
            index += 1
            continue
        end = index + 1
        while end < len(messages) and messages[end].role == "tool":
            end += 1
        answered = {result.tool_call_id for result in messages[index + 1 : end]}
        if {call.id for call in message.tool_calls} <= answered:
            kept.extend(messages[index:end])
        index = end
    return kept


def parent_history(deps: AgentDeps) -> list[Message]:
    """Üst ajanın ANLIK geçmişi (`deps.live_history`); yoksa boş liste."""
    source: LiveHistory | None = getattr(deps, "live_history", None)
    if source is None:
        return []
    try:
        return list(source())
    except Exception:
        return []


async def run_forked_turn(
    task: str,
    deps: AgentDeps,
    *,
    history: list[Message] | None = None,
    plan_mode: bool = False,
    extra_system: str = "",
    system_prompt: str | None = None,
    allowed_tools: set[str] | None = None,
    denied_tools: frozenset[str] = frozenset(),
    images: tuple[str, ...] = (),
    step_limit: int | None = None,
    persona: str = "",
    inherit_context: bool = True,
    background: bool = False,
    **_ignored: object,
) -> AgentOutcome:
    """`/subtask <görev>`: turu fork alt ajan olarak koştur, ana geçmişe yalnız özeti ekle.

    `run_agent` ile aynı imzayı taşır ki REPL, TUI ve masaüstü turu çağıranı değiştirmeden
    bu yola geçebilsin. Turun oturum kişiliği/beceri metni (`extra_system`) alt ajanın
    brifine, araç kısıtı (`allowed_tools`) araç TAVANI olarak, görseller ve adım tavanı
    aynen geçer. Ölçüldü (31 Ekim): bunlar `**_ignored` ile atılıyordu; `context: fork`
    becerisinin talimatı hiç uygulanmıyor, salt-okur kişilik fork içinde yazabiliyordu.
    `chat_mode`/`workflow` gibi kalan tur ayarları alt ajanda anlamsızdır, yok sayılır.
    `persona`: becerinin `agent:` alanı (P-020); o alt ajan tanımı fork'u koşar.
    `inherit_context=False`: becerinin `context: fork`u (Claude Code #141) — alt ajan konuşma
    geçmişini GÖRMEZ, gövde kendi başına yeter; ana geçmişe yine yalnız özet eklenir.
    `background=True`: becerinin `background` alanı (varsayılan) — etkileşimli oturumda fork
    arka planda başlar, sonuç tamamlanınca konuşmaya gelir (Claude Code #141).
    """
    from .loop import AgentOutcome, run_agent
    from .team import SubTask, run_subagent

    snapshot = list(history or [])
    seed = list(snapshot) if inherit_context else []
    if system_prompt is not None:
        if seed and seed[0].role == "system":
            seed[0] = Message("system", system_prompt)
        else:
            seed.insert(0, Message("system", system_prompt))
    deps.live_history = lambda: seed
    subtask = SubTask(
        task=task.strip(),
        persona=persona,
        read_only=plan_mode,
        inherit_context=inherit_context,
        brief=extra_system,
        tool_cap=frozenset(allowed_tools) if allowed_tools is not None else None,
        tool_deny=frozenset(denied_tools),
        images=tuple(images),
        step_limit=step_limit,
    )
    if background and getattr(deps, "interactive", False):
        text, ok = await _launch_background(deps, subtask, run_agent)
        return AgentOutcome(
            final_text=text,
            messages=[
                *snapshot,
                Message("user", task, images=tuple(images)),
                Message("assistant", text),
            ],
            ok=ok,
        )
    run = await run_subagent(deps, subtask, depth=0, run_agent=run_agent)
    messages = [
        *snapshot,
        Message("user", task, images=tuple(images)),
        Message("assistant", run.text),
    ]
    return AgentOutcome(
        final_text=run.text,
        messages=messages,
        ok=run.ok,
        tool_calls_made=run.tool_calls,
    )


#: Arka planda başlayan beceri fork'unun konuşmaya düşen notu.
BACKGROUND_STARTED = "Beceri alt ajanı arka planda başladı ({agent}); sonuç tamamlanınca gelir."


async def _launch_background(
    deps: AgentDeps, subtask: object, run_agent: object
) -> tuple[str, bool]:
    """Fork'u Agent aracının arka plan yolundan başlat; kapalıysa ön planda bekler."""
    import json

    from .agent_runtime_tools import launch_agent

    result = await launch_agent(
        deps,
        subtask,  # type: ignore[arg-type]
        {"run_in_background": True},
        depth=0,
        run_agent=run_agent,  # type: ignore[arg-type]
    )
    if not result.ok:
        return result.output, False
    try:
        receipt = json.loads(result.output)
    except ValueError:
        return result.output, True
    if receipt.get("status") == "async_launched":
        return BACKGROUND_STARTED.format(agent=receipt.get("agentId", "")), True
    return str(receipt.get("content", "")), True
