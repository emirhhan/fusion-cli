"""İstem önerileri (#216, Claude Code "Prompt suggestions").

Claude Code: yanıt bittikten sonra boş girdide sönük (ghost) bir sonraki istem önerisi
görünür; Tab ya da Sağ ok öneriyi girdiye alır, yazmaya başlamak öneriyi kaldırır. Boş
girdide Enter öneriyi kendiliğinden göndermez (v2.1.136'dan beri). Ayar `settings.json`
`promptSuggestionEnabled` (varsayılan açık); `CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION`
ortam değişkeni (1/true/yes/on ya da 0/false/no/off) ayarın önüne geçer.

Fusion: öneri turun kendi kanıtından üretilen ilk takip önerisidir
(`core.followups.suggest_followups`, `FollowupsSuggested` olayı); öneri için ayrı model
çağrısı açılmaz. Kanıt yoksa öneri de yoktur.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from pathlib import Path

from ...core.events import Event, FollowupsSuggested

_LOG = logging.getLogger(__name__)
SETTING_KEY = "promptSuggestionEnabled"
ENV_KEY = "CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION"
_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})


def _setting(path: Path) -> bool | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        _LOG.debug("ayar okunamadı (%s): %s", path, type(error).__name__)
        return None
    value = data.get(SETTING_KEY) if isinstance(data, dict) else None
    return value if isinstance(value, bool) else None


def enabled(root: Path, home: Path, environ: Mapping[str, str] | None = None) -> bool:
    """Ortam değişkeni > yerel > proje > kullanıcı `settings.json`; hiçbiri yoksa açık."""
    env = (os.environ if environ is None else environ).get(ENV_KEY, "").strip().lower()
    if env in _TRUE:
        return True
    if env in _FALSE:
        return False
    result = True
    for path in (
        home / ".claude" / "settings.json",
        root / ".claude" / "settings.json",
        root / ".claude" / "settings.local.json",
    ):
        value = _setting(path)
        if value is not None:
            result = value
    return result


class SuggestionSink:
    """Turun ilk takip önerisini yakalayan dinleyici; `take` bir kez verir."""

    def __init__(self) -> None:
        self._text = ""

    def handle(self, event: Event) -> None:
        if isinstance(event, FollowupsSuggested) and event.items:
            self._text = str(event.items[0][1]).strip()

    def reset(self) -> None:
        self._text = ""

    def take(self) -> str:
        text, self._text = self._text, ""
        return text


def offer(buffer: object, text: str) -> bool:
    """Boş tampona sönük öneriyi koy (prompt_toolkit `Suggestion`); konduysa True."""
    if not text or _has_text(buffer):
        return False
    from prompt_toolkit.auto_suggest import Suggestion

    buffer.suggestion = Suggestion(text)  # type: ignore[attr-defined]
    return True


def accept(buffer: object) -> bool:
    """Tab/Sağ ok: boş girdideki öneriyi girdiye al (göndermez); öneri yoksa False."""
    suggestion = getattr(buffer, "suggestion", None)
    if suggestion is None or not suggestion.text or _has_text(buffer):
        return False
    buffer.insert_text(suggestion.text)  # type: ignore[attr-defined]
    return True


def available(buffer: object) -> bool:
    suggestion = getattr(buffer, "suggestion", None)
    return bool(suggestion is not None and suggestion.text and not _has_text(buffer))


def _has_text(buffer: object) -> bool:
    """Tamponda yazı var mı? Metni olmayan nesne dolu sayılır (öneri konmaz)."""
    text = getattr(buffer, "text", None)
    return not isinstance(text, str) or bool(text)
