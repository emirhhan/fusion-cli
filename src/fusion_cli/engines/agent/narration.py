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
import re

from ...config.model_lookup import configured_model_specs
from ...config.models import Config
from ...core.errors import ConfigError, ProviderError
from ...core.events import EventPublisher
from ...core.tool_emulation import CALL_OPEN, PAYLOAD_OPEN
from ...core.tools import TodoItem, TodoStatus
from ...core.types import CompletionRequest, Message, ModelSpec
from ...providers.factory import build_provider
from ...providers.web_browser import WebBrowserError
from ...providers.web_registry import web_registry_for
from ...ui.text import strip_thinking
from .response_format import requested_response_format

#: Giriş için üretim sınırı: iki üç cümle ~60-120 token; pay bırakılır.
INTRO_MAX_TOKENS = 220
#: Giriş çağrısının süre sınırı. Çırağın ölçülen yanıtı ~1 sn (NIM super);
#: giriş kozmetiktir, uzarsa atlanır ve iş beklemeden başlar.
INTRO_TIMEOUT_S = 30.0
#: Görev metninden girişe verilen kesit: uzun istemin tamamı gerekmez.
_TASK_CHARS = 2_000
#: Cosmetic narration is a paragraph, never a place to carry executable output.
_INTRO_MAX_CHARS = 1_000
_INTRO_STRUCTURE = re.compile(
    r"```|~~~|[{}\[\]]|<\s*[!/A-Za-z|]|"
    r"(?m:^[ \t]*(?:#{1,6}\s|[-*+]\s|\d+[.)]\s))|\n\s*\n"
)

_INTRO_PROMPT = (
    "Aşağıdaki isteğe işe başlamadan önce kullanıcıya bir iki cümlelik giriş yaz: "
    "ilk olarak neye bakacağını ve işi nasıl ilerleteceğini birinci tekil şahıs ve "
    'şimdiki zamanla söyle. Örnek: "Önce hata veren testi ve çağırdığı modülü '
    'okuyorum, sonra düzeltip testi yeniden çalıştıracağım." "Anladığım kadarıyla", '
    '"Elbette", "Harika" gibi girişlerle başlama; isteği tekrar etme. Kod, liste, '
    "başlık yazma; soru sorma; henüz bir şey yapmış gibi konuşma. Kullanıcının "
    "dilinde yaz.\n\nElindeki araçlar: {tools}. Yalnız bunlarla yapabileceğin şeyi söyle; "
    "listede olmayan bir aracı, eklentiyi ya da bağlantıyı kullanacağını söyleme.\n\n"
    "İstek:\n{task}"
)


async def intro_paragraph(
    task: str,
    spec: ModelSpec,
    config: Config,
    publisher: EventPublisher | None,
    tool_names: tuple[str, ...] = (),
) -> str:
    """Araçsız kısa giriş metni; üretilemezse boş döner (iş beklemeden başlar).

    Ölçüldü (17. kabul koşusu): giriş araç listesini bilmiyordu ve bağlı olmayan
    Fusion Browser eklentisini kullanacağını yazdı; bu cümle modele "zaten
    söyledin" notu olarak geri verildiği için sonraki adımları da kirletebilir.
    """
    if requested_response_format(task) is not None:
        return ""
    istem = _INTRO_PROMPT.format(task=task[:_TASK_CHARS], tools=", ".join(tool_names) or "yok")
    request = CompletionRequest(
        messages=(Message("user", istem),),
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
            model_specs=configured_model_specs(config),
        )
        async with asyncio.timeout(INTRO_TIMEOUT_S):
            result = await provider.complete(request)
    except (TimeoutError, ConfigError, ProviderError, WebBrowserError):
        # Giriş yardımcı bir çağrıdır; sağlayıcı kurulamazsa ana tur sürer.
        return ""
    if not result.ok or result.tool_calls:
        return ""
    metin = strip_thinking(result.text).strip()
    # A tool-free request is not proof of a tool-free answer. A live intro
    # contained prose followed by a partial write_file JSON/HTML payload; it
    # would otherwise be published and fed back to the main agent as its own
    # prior statement. Reject even incomplete payloads before sentence trimming
    # can disguise them as a valid intro. This cosmetic call is never retried.
    if (
        len(metin) > _INTRO_MAX_CHARS
        or _INTRO_STRUCTURE.search(metin)
        or any(marker in metin for marker in (CALL_OPEN, PAYLOAD_OPEN))
        or any(re.search(rf"(?<!\w){re.escape(name)}\s*\(", metin) for name in tool_names if name)
    ):
        return ""
    # Token sınırında kesilen giriş cümle ortasında biter (A2-38): son TAM cümleye kadar kırp.
    return _drop_cut_sentence(metin) if result.truncated else metin


def _drop_cut_sentence(text: str) -> str:
    """Yarım kalan son cümleyi at; hiç tam cümle yoksa boş döner (giriş atlanır)."""
    son = max(text.rfind(isaret) for isaret in ".!?…")
    return text[: son + 1].strip() if son >= 0 else ""


def todo_transitions(before: tuple[TodoItem, ...], after: tuple[TodoItem, ...]) -> tuple[str, ...]:
    """Görev listesinde yeni başlayan adımları anlatım cümlelerine çevir."""
    running_before = {item.content for item in before if item.status is TodoStatus.IN_PROGRESS}
    return tuple(
        f"Şimdi “{item.content}” adımına geçiyorum."
        for item in after
        if item.status is TodoStatus.IN_PROGRESS and item.content not in running_before
    )
