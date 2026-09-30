"""Claude gibi konuşma: giriş paragrafı ve adımlar arasında ara anlatım.

Ölçüldü (30 Eylül, masaüstü): nemotron çırak araç çağırırken hiç metin
yazmıyordu; sohbette yalnız alt alta adım satırları görünüyordu. Talimat
(`prompts/system_api.md`) bunu istiyordu ama model uymuyordu. Bu modül iki
şeyi harness düzeyinde garanti eder:

- **Giriş paragrafı:** karmaşık işte, işi yapan ilk çağrıdan önce modelden
  araçsız kısa bir giriş istenir (isteği nasıl anladığı, nasıl ilerleyeceği).
- **Ara anlatım:** modelin kendi görev listesinde yeni bir adıma geçildiğinde
  bu, kısa bir cümleyle sohbete yazılır. Metin modelin kendi planından gelir.
"""

from __future__ import annotations

import asyncio

from ...config.models import Config
from ...core.errors import ConfigError, ProviderError
from ...core.events import EventPublisher
from ...core.tools import TodoItem, TodoStatus
from ...core.types import CompletionRequest, Message, ModelSpec
from ...providers.factory import build_provider
from ...providers.web_browser import WebBrowserError
from ...providers.web_registry import web_registry_for
from ...ui.text import strip_thinking

#: Giriş için üretim sınırı: iki üç cümle ~60-120 token; pay bırakılır.
INTRO_MAX_TOKENS = 220
#: Giriş çağrısının süre sınırı. Çırağın ölçülen yanıtı ~1 sn (NIM super);
#: giriş kozmetiktir, uzarsa atlanır ve iş beklemeden başlar.
INTRO_TIMEOUT_S = 30.0
#: Görev metninden girişe verilen kesit: uzun istemin tamamı gerekmez.
_TASK_CHARS = 2_000

_INTRO_PROMPT = (
    "Aşağıdaki isteğe işe başlamadan önce kullanıcıya iki üç cümlelik kısa bir "
    "giriş yaz: isteği nasıl anladığını ve nasıl ilerleyeceğini söyle. Kod, liste, "
    "başlık yazma; soru sorma; henüz bir şey yapmış gibi konuşma. Kullanıcının "
    "dilinde yaz.\n\nİstek:\n{task}"
)


async def intro_paragraph(
    task: str, spec: ModelSpec, config: Config, publisher: EventPublisher | None
) -> str:
    """Araçsız kısa giriş metni; üretilemezse boş döner (iş beklemeden başlar)."""
    request = CompletionRequest(
        messages=(Message("user", _INTRO_PROMPT.format(task=task[:_TASK_CHARS])),),
        temperature=config.runtime.utility_temperature,
        max_tokens=INTRO_MAX_TOKENS,
        timeout_s=INTRO_TIMEOUT_S,
        max_retries=0,
    )
    try:
        provider = build_provider(
            spec,
            publisher=publisher,
            retry_delays_s=(),
            background=True,
            web_sessions=web_registry_for(config),
        )
        async with asyncio.timeout(INTRO_TIMEOUT_S):
            result = await provider.complete(request)
    except (TimeoutError, ConfigError, ProviderError, WebBrowserError):
        # Giriş yardımcı bir çağrıdır; sağlayıcı kurulamazsa ana tur sürer.
        return ""
    return strip_thinking(result.text).strip() if result.ok else ""


def todo_transitions(before: tuple[TodoItem, ...], after: tuple[TodoItem, ...]) -> tuple[str, ...]:
    """Görev listesinde yeni başlayan adımları anlatım cümlelerine çevir."""
    running_before = {item.content for item in before if item.status is TodoStatus.IN_PROGRESS}
    return tuple(
        f"Şimdi “{item.content}” adımına geçiyorum."
        for item in after
        if item.status is TodoStatus.IN_PROGRESS and item.content not in running_before
    )
