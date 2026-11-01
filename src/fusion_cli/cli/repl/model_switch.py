"""`/model <ad>` — agent modelini doğrudan değiştirip varsayılan olarak kaydet (#211).

Claude Code'da `/model <model>` modeli değiştirir ve yeni oturumlar için varsayılan olarak
kaydeder. Fusion'da ad şu sırayla çözülür (ağ yok): tam `<sağlayıcı>/<model>` kimliği,
`claude-…` kimliği (`anthropic/` öneki), aday adı, Claude takma adı (sonnet/opus/haiku/fable)
için aynı aileden aday. Fusion'ın `agent|judge|cand|add|rm` alt komutları ayrı kalır.
"""

from __future__ import annotations

import logging

from ...config.model_select import set_agent_model
from ...config.writer import write_model_section
from ...core.errors import ConfigError, FusionError
from ...config.models import Config
from ...engines.agent.agent_launch_model import CLAUDE_ALIASES, claude_family
from ...ui import messages

_LOG = logging.getLogger(__name__)

#: Fusion'a özgü alt komutlar; bunlar doğrudan model adı sayılmaz.
FUSION_SUBCOMMANDS = frozenset({"agent", "judge", "cand", "add", "rm"})


def is_direct_model(parts: list[str]) -> bool:
    """`/model <ad>` biçimi mi? (tek kelime, Fusion alt komutu değil)"""
    return len(parts) == 1 and parts[0].lower() not in FUSION_SUBCOMMANDS


def resolve_model(config: Config, word: str) -> str | None:
    """Kullanıcının yazdığı adı tam model kimliğine çevir; çözülemezse None."""
    wanted = word.strip()
    if "/" in wanted:
        return wanted
    if wanted.startswith("claude-"):
        return f"anthropic/{wanted}"
    by_name = config.candidate_by_name(wanted)
    if by_name is not None:
        return by_name.model
    alias = wanted.lower()
    if alias in CLAUDE_ALIASES:
        if claude_family(config.agent.model) == alias:
            return config.agent.model
        match = next((c for c in config.candidates if claude_family(c.model) == alias), None)
        return match.model if match is not None else None
    return None


def switch_and_save(config: Config, word: str) -> tuple[Config, str]:
    """Agent modelini değiştir ve kullanıcı yapılandırmasına yaz.

    Yazma başarısız olursa değişiklik bu oturumda yine geçerlidir; mesaj bunu söyler.
    """
    model = resolve_model(config, word)
    if model is None:
        raise ConfigError(messages.REPL_MODEL_UNRESOLVED.format(model=word))
    updated = set_agent_model(config, model)
    try:
        path = write_model_section(updated)
    except (OSError, FusionError) as error:
        _LOG.warning("model varsayılanı yazılamadı: %s", type(error).__name__)
        return updated, messages.REPL_MODEL_SESSION_ONLY.format(model=model)
    return updated, messages.REPL_MODEL_SAVED.format(model=model, path=path)
