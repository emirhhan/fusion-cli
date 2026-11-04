"""Masaüstü yan sohbeti (#444; Claude Desktop ⌘; / Ctrl+;).

Claude Desktop: yan sohbet ana oturumdan dallanır; ana sohbetin bağlamını alır ama ana sohbete
hiçbir şey geri eklemez. Fusion'da `yan_sohbet.sor` ana geçmişin son kullanıcı/asistan
mesajlarını ve yan sohbetin kendi önceki soru-cevaplarını bağlam yapıp agent modeline ARAÇSIZ
tek çağrı yapar. Yanıt ana geçmişe, transkripte ya da belleğe yazılmaz; dosya ve araç yoktur.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from ..core.protocols import LlmProvider
from ..core.types import CompletionRequest, Message

SIDE_CHAT_ROUTE = "yan_sohbet.sor"
#: Ana sohbetten alınan en çok mesaj ve her birinin karakter sınırı (istem bütçesi).
MAX_MAIN_MESSAGES = 30
MAX_MESSAGE_CHARS = 4_000
MAX_QUESTION_CHARS = 4_000
#: Yan sohbetin kendi geçmişinden taşınan en çok soru-cevap.
MAX_SIDE_TURNS = 20
SIDE_SYSTEM = (
    "Bu bir yan sohbettir. Ana sohbetin bağlamı aşağıda; onu okuyabilirsin ama ana göreve "
    "devam etmezsin, dosya değiştirmezsin, araç çağırmazsın. Kullanıcının yan sorusunu kısa ve "
    "doğrudan yanıtla. Bu yanıt ana sohbete eklenmez."
)

if TYPE_CHECKING:
    from ..config.models import Config

ProviderFactory = Callable[["Config"], LlmProvider]


def _main_context(history: Sequence[Message]) -> list[Message]:
    rows = [
        Message(m.role, m.content[:MAX_MESSAGE_CHARS])
        for m in history
        if m.role in ("user", "assistant") and isinstance(m.content, str) and m.content.strip()
    ]
    return rows[-MAX_MAIN_MESSAGES:]


def _side_turns(raw: object) -> list[Message]:
    if not isinstance(raw, list):
        return []
    roles = {"kullanici": "user", "asistan": "assistant"}
    turns = [
        Message(roles[item["rol"]], item["metin"][:MAX_MESSAGE_CHARS])
        for item in raw
        if isinstance(item, dict)
        and item.get("rol") in roles
        and isinstance(item.get("metin"), str)
        and item["metin"].strip()
    ]
    return turns[-2 * MAX_SIDE_TURNS :]


def build_messages(history: Sequence[Message], side: object, question: str) -> tuple[Message, ...]:
    """Yan sohbet çağrısının mesajları: sistem + ana bağlam + yan geçmiş + soru."""
    main = _main_context(history)
    context = "\n\n".join(f"[{m.role}] {m.content}" for m in main) or "(ana sohbet boş)"
    return (
        Message("system", f"{SIDE_SYSTEM}\n\n--- Ana sohbet ---\n{context}"),
        *_side_turns(side),
        Message("user", question),
    )


def _default_provider(config: Config) -> LlmProvider:
    from ..config.model_lookup import configured_model_specs
    from ..providers.factory import build_provider
    from ..providers.web_registry import web_registry_for

    return build_provider(
        config.agent,
        publisher=None,
        retry_delays_s=config.runtime.retry_delays_s,
        background=True,
        web_sessions=web_registry_for(config),
        model_specs=configured_model_specs(config),
    )


async def ask_side(
    config: Config,
    history: Sequence[Message],
    data: dict[str, Any],
    *,
    provider_factory: ProviderFactory | None = None,
) -> dict[str, Any]:
    """`yan_sohbet.sor` {soru, gecmis?}: araçsız tek model çağrısı; ana geçmiş değişmez."""
    question = data.get("soru")
    if not isinstance(question, str) or not question.strip():
        return {"ok": False, "metin": "Yan soru boş olamaz."}
    if len(question) > MAX_QUESTION_CHARS:
        return {"ok": False, "metin": f"Yan soru en çok {MAX_QUESTION_CHARS} karakter olabilir."}
    runtime = config.runtime
    request = CompletionRequest(
        messages=build_messages(history, data.get("gecmis"), question.strip()),
        temperature=runtime.temperature,
        max_tokens=runtime.max_tokens,
        timeout_s=runtime.request_timeout_s,
        max_retries=runtime.max_retries,
    )
    provider = (provider_factory or _default_provider)(config)
    result = await provider.complete(request)
    if not result.ok or not result.text.strip():
        return {"ok": False, "metin": result.error or "Model yanıt vermedi."}
    return {"ok": True, "metin": result.text.strip()}
