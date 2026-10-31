"""Oturum hedefinin tur sonu değerlendiricisi (`/goal`, P-058).

Claude Code `/goal`'ı "oturum kapsamlı, istem tabanlı Stop kancası" olarak kurar: her
tur bitince küçük/hızlı bir model hedef koşulunun karşılanıp karşılanmadığına karar
verir. Burada aynı iş hakem rolünün modeliyle (`config.judge`; sıkıştırma ve öz-denetim
ile aynı ucuz rol) yapılır. Karar `core.session_goal.GoalVerdict`'e çevrilir; model
yanıt vermez ya da yanıt okunamazsa `UNKNOWN` döner ve yüzey otomatik devam ETMEZ.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ...config.models import Config
from ...core.errors import ConfigError, ProviderError
from ...core.events import EventPublisher
from ...core.session_goal import GoalVerdict, parse_verdict
from ...core.types import CompletionRequest, Message
from ...providers.factory import build_provider
from ...providers.web_browser import WebBrowserError
from ...providers.web_registry import web_registry_for
from ...ui.text import strip_thinking

_PROMPT = (Path(__file__).parent / "prompts" / "goal_judge.md").read_text(encoding="utf-8")
#: Kayda girilen son mesaj sayısı ve mesaj/toplam karakter tavanları: karar son turun
#: kanıtına dayanır, tüm geçmiş ucuz modelin bağlamını boğar.
TRANSCRIPT_MESSAGES = 14
MESSAGE_CHARS = 1_500
TRANSCRIPT_CHARS = 9_000
#: Karar JSON'u kısa; pay bırakılır.
JUDGE_MAX_TOKENS = 300
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
_ROLE_LABELS = {"user": "KULLANICI", "assistant": "AJAN", "tool": "ARAÇ SONUCU"}

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GoalJudgement:
    """Değerlendiricinin kararı ve kısa gerekçesi."""

    verdict: GoalVerdict
    reason: str


def goal_transcript(history: Sequence[Message]) -> str:
    """Son mesajları rol etiketiyle kısaltılmış düz metne çevir (sistem mesajları hariç)."""
    parts: list[str] = []
    for message in list(history)[-TRANSCRIPT_MESSAGES:]:
        label = _ROLE_LABELS.get(message.role)
        if label is None:
            continue
        body = message.content.strip()
        if message.role == "assistant" and message.tool_calls:
            names = ", ".join(call.name for call in message.tool_calls)
            body = f"{body}\n[araç çağrıları: {names}]".strip()
        if not body:
            continue
        if len(body) > MESSAGE_CHARS:
            body = body[:MESSAGE_CHARS] + " …"
        parts.append(f"[{label}] {body}")
    text = "\n\n".join(parts)
    return text[-TRANSCRIPT_CHARS:]


def parse_judgement(text: str) -> GoalJudgement:
    """Model yanıtından karar; JSON yoksa ya da bozuksa `UNKNOWN`."""
    cleaned = strip_thinking(text or "").strip()
    match = _JSON_OBJECT.search(cleaned)
    if match is None:
        return GoalJudgement(GoalVerdict.UNKNOWN, cleaned[:200])
    try:
        payload = json.loads(match.group(0))
    except ValueError:
        return GoalJudgement(GoalVerdict.UNKNOWN, cleaned[:200])
    if not isinstance(payload, dict):
        return GoalJudgement(GoalVerdict.UNKNOWN, "")
    verdict = parse_verdict(str(payload.get("karar") or payload.get("verdict") or ""))
    reason = str(payload.get("gerekce") or payload.get("reason") or "").strip()
    return GoalJudgement(verdict, reason)


async def judge_goal(
    condition: str,
    history: Sequence[Message],
    config: Config,
    publisher: EventPublisher | None = None,
) -> GoalJudgement:
    """Koşul karşılandı mı? Sağlayıcı hatası/zaman aşımı `UNKNOWN` (hata fırlatmaz)."""
    prompt = _PROMPT.replace("{condition}", condition).replace(
        "{transcript}", goal_transcript(history) or "(kayıt boş)"
    )
    request = CompletionRequest(
        messages=(Message("user", prompt),),
        temperature=config.runtime.utility_temperature,
        max_tokens=JUDGE_MAX_TOKENS,
        timeout_s=config.runtime.judge_timeout_s,
        max_retries=config.runtime.max_retries,
    )
    try:
        # Arka plan çağrısı: ilerleme satırı gösterilmez, token muhasebeye girer.
        provider = build_provider(
            config.judge,
            publisher=publisher,
            retry_delays_s=config.runtime.retry_delays_s,
            background=True,
            web_sessions=web_registry_for(config),
        )
        async with asyncio.timeout(config.runtime.judge_timeout_s + 2.0):
            result = await provider.complete(request)
    except TimeoutError:
        return GoalJudgement(GoalVerdict.UNKNOWN, "değerlendirici zamanında yanıt vermedi")
    except (ConfigError, ProviderError, WebBrowserError, OSError) as error:
        _LOG.warning("Hedef değerlendirmesi yapılamadı: %s", error)
        return GoalJudgement(GoalVerdict.UNKNOWN, "değerlendirici modeline ulaşılamadı")
    if not result.ok:
        return GoalJudgement(GoalVerdict.UNKNOWN, "değerlendirici hata döndürdü")
    return parse_judgement(result.text)
