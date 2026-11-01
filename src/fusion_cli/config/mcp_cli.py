"""`--mcp-config` ve `--strict-mcp-config` (Claude Code CLI bayrakları; #253).

`--mcp-config` bir ya da birden çok JSON dosyası ya da JSON metni alır (`{"mcpServers": …}`).
Sunucular bu oturum için eklenir; `--strict-mcp-config` ile YALNIZ bunlar kullanılır
(kullanıcı, yerel, proje ve eklenti sunucuları yüklenmez). Hiçbir dosyaya yazılmaz.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path

from ..core.errors import ConfigError
from .models import Config, McpScope, McpServerConfig

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SessionMcp:
    servers: tuple[McpServerConfig, ...] = ()
    strict: bool = False


_STATE: list[SessionMcp] = [SessionMcp()]


def parse_mcp_config_args(values: Iterable[str]) -> tuple[McpServerConfig, ...]:
    """Her değer bir dosya yolu ya da JSON metnidir; hatalı girdi atlanıp uyarılır."""
    from .mcp_json import parse_mcp_servers_report

    servers: list[McpServerConfig] = []
    for value in values:
        text = value.strip()
        if not text:
            continue
        path = Path(text).expanduser()
        raw_text = path.read_text(encoding="utf-8") if not text.startswith("{") and path.is_file() else text
        try:
            raw = json.loads(raw_text)
        except json.JSONDecodeError as error:
            raise ConfigError(f"--mcp-config geçerli JSON ya da dosya değil: {text[:80]} ({error})") from error
        # Claude Code: --mcp-config sunucuları kullanıcı kapsamı gibi davranır (headersHelper
        # kimlik değişkenlerini görür); kayıt yeri yoktur.
        parsed, problems = parse_mcp_servers_report(raw, scope=McpScope.USER, where="--mcp-config")
        for problem in problems:
            _LOG.warning("%s", problem)
        servers.extend(parsed)
    return tuple(servers)


def set_session_mcp(values: Iterable[str] | None, *, strict: bool) -> None:
    _STATE[0] = SessionMcp(parse_mcp_config_args(values or ()), strict)


def apply_session_mcp(config: Config) -> Config:
    """Oturum bayraklarını yüklenen yapılandırmaya uygula."""
    state = _STATE[0]
    if not state.servers and not state.strict:
        return config
    if state.strict:
        return replace(config, mcp_servers=state.servers)
    names = {server.name for server in state.servers}
    kept = tuple(server for server in config.mcp_servers if server.name not in names)
    return replace(config, mcp_servers=(*kept, *state.servers))
