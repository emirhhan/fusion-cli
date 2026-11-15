"""Kullanıcının sıradaki istemini tahmin eden yan çağrı (`--prompt-suggestions`, #289).

Claude Code `-p --prompt-suggestions` (Agent SDK `promptSuggestions`) her turdan sonra
"a predicted next user prompt" taşıyan `prompt_suggestion` mesajı yayımlar; tahmini model
yapar. Burada aynı iş hakem rolünün ucuz modeliyle (`config.judge`; `/goal` değerlendiricisi
ve özetleme ile aynı rol) yapılır. Model yanıt vermez, hata döner ya da `YOK` derse `None`
döner; çağıran (stream-json) turun kanıtından üretilen takip önerisine düşer.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from pathlib import Path

from ...config.model_lookup import configured_model_specs
from ...config.models import Config
from ...core.errors import ConfigError, ProviderError
from ...core.events import EventPublisher
from ...core.types import CompletionRequest, Message
from ...providers.factory import build_provider
from ...providers.web_browser import WebBrowserError
from ...providers.web_registry import web_registry_for
from ...ui.text import strip_thinking
from .goal_judge import goal_transcript

_PROMPT = (Path(__file__).parent / "prompts" / "next_prompt.md").read_text(encoding="utf-8")
#: Tahmin kısa bir istemdir; pay bırakılır.
NEXT_PROMPT_MAX_TOKENS = 80
MAX_SUGGESTION_CHARS = 200
#: Modelin "tahmin yok" cevapları.
_NONE_WORDS = frozenset({"yok", "none", "-", "n/a"})
_QUOTES = "\"'`“”‘’«»"

_LOG = logging.getLogger(__name__)


def parse_next_prompt(text: str) -> str | None:
    """Model cevabının ilk dolu satırı; boş ya da `YOK` ise `None`."""
    cleaned = strip_thinking(text or "").strip()
    line = next((part.strip() for part in cleaned.splitlines() if part.strip()), "")
    line = line.strip(_QUOTES).strip()
    if not line or line.casefold().rstrip(".") in _NONE_WORDS:
        return None
    return line[:MAX_SUGGESTION_CHARS].rstrip()


async def predict_next_prompt(
    history: Sequence[Message],
    config: Config,
    publisher: EventPublisher | None = None,
) -> str | None:
    """Konuşmadan sıradaki kullanıcı istemini tahmin et; olmazsa `None` (hata fırlatmaz)."""
    transcript = goal_transcript(history)
    if not transcript:
        return None
    request = CompletionRequest(
        messages=(Message("user", _PROMPT.replace("{transcript}", transcript)),),
        temperature=config.runtime.utility_temperature,
        max_tokens=NEXT_PROMPT_MAX_TOKENS,
        timeout_s=config.runtime.judge_timeout_s,
        max_retries=config.runtime.max_retries,
    )
    try:
        provider = build_provider(
            config.judge,
            publisher=publisher,
            retry_delays_s=config.runtime.retry_delays_s,
            background=True,
            web_sessions=web_registry_for(config),
            model_specs=configured_model_specs(config),
        )
        async with asyncio.timeout(config.runtime.judge_timeout_s + 2.0):
            result = await provider.complete(request)
    except TimeoutError:
        return None
    except (ConfigError, ProviderError, WebBrowserError, OSError) as error:
        _LOG.debug("İstem önerisi tahmin edilemedi: %s", error)
        return None
    if not result.ok:
        return None
    return parse_next_prompt(result.text)
