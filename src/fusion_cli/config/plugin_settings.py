"""Eklenti kökündeki `settings.json` varsayılanları (Claude Code plugins-reference, #389).

Claude Code: eklenti açıkken kökündeki `settings.json` varsayılan ayar olarak uygulanır; şu an
yalnız `agent` (ana sohbeti eklentinin bir ajanıyla başlatır) ve `subagentStatusLine` desteklenir.
Kullanıcı/proje ayarındaki `agent` ve Fusion yapılandırması önce gelir; eklenti yalnız boşsa
doldurur. Önek yoksa ad eklentinin kendi ajanına çözülür (`<eklenti>:<ajan>`). Birden çok etkin
eklenti `agent` bildirirse ada göre ilk eklenti kazanır. `subagentStatusLine` Fusion'da alt ajan
durum satırı olmadığından okunmaz.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

_LOG = logging.getLogger(__name__)

SETTINGS_FILE = "settings.json"


def _agent_of(root: Path, plugin: str) -> str:
    path = root / SETTINGS_FILE
    if not path.is_file():
        return ""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _LOG.warning("eklenti '%s' settings.json okunamadı: %s", plugin, error)
        return ""
    agent = raw.get("agent") if isinstance(raw, dict) else None
    if not isinstance(agent, str) or not agent.strip():
        return ""
    name = agent.strip()
    return name if ":" in name else f"{plugin}:{name}"


def plugin_default_agent(root: Path | None = None) -> str:
    """Etkin eklentilerin `settings.json` `agent` varsayılanı; yoksa boş."""
    from .plugin_store import active_plugins

    try:
        active = active_plugins(root=root)
    except (OSError, ValueError) as error:
        _LOG.warning("eklenti ayarları okunamadı: %s", error)
        return ""
    for item in sorted(active, key=lambda i: i.record.name):
        if item.layout is not None:
            agent = _agent_of(item.layout.root, item.layout.name)
            if agent:
                return agent
    return ""
