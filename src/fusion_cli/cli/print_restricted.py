"""`fusion -p --restricted` — Claude Code kısıtlı kipi (#301).

Claude: paylaşılan makinede değerlendirme düzeneği `claude`ı sürerken komut çalıştırılmamalı
ve makinenin kullanıcı/proje ayarları okunmamalıdır. Kısıtlı kipte:

- komut ya da kod çalıştıran yerleşik araçlar ve WebFetch kaldırılır; `--tools` içinde TEK
  TEK adı verilenler kalır (`default` ön ayarı bunları geri getirmez),
- yerleşik dosya araçları çalışma dizinlerine (proje kökü + `--add-dir`) sınırlanır,
- yalnız yönetilen ayarlar ve `--settings` yüklenir (`--setting-sources` boş liste gibi),
- `bypassPermissions` reddedilir.

Fusion'da Claude'un yerleşik araçlarına karşılık gelmeyen (masaüstü, tarayıcı, iş, Python…)
araçlar da kod çalıştırabildiği için kaldırılır: kalan küme Claude'un komut çalıştırmayan
yerleşiklerinin Fusion karşılıklarıdır. Yapılandırmadaki MCP sunucuları ve bağlayıcılar
(kullanıcı/proje kaydı) bağlanmaz; komut satırındaki `--mcp-config` bağlanır. Alt ajanlar
aynı araç tavanını devralır (`deps.runtime_tool_cap`).
"""

from __future__ import annotations

from dataclasses import replace

from ..config.models import Config
from ..config.setting_sources import set_setting_sources
from ..engines.agent.approval import ApprovalMode
from ..tools.capabilities import CLAUDE_TOOL_MAP
from ..ui import print_messages as texts
from .print_options import ToolSelection

#: Komut/kod çalıştırmayan Claude yerleşikleri (Bash, PowerShell, WebFetch hariç).
_SAFE_CLAUDE_TOOLS = (
    "read",
    "write",
    "edit",
    "notebookedit",
    "grep",
    "glob",
    "ls",
    "websearch",
    "agent",
    "task",
    "sendmessage",
    "listagents",
    "taskstop",
    "skill",
    "askuserquestion",
    "todowrite",
)
RESTRICTED_TOOLS: frozenset[str] = frozenset().union(
    *(CLAUDE_TOOL_MAP[name] for name in _SAFE_CLAUDE_TOOLS)
)


def prepare_restricted_sources() -> None:
    """Kullanıcı/proje/yerel ayar katmanlarını kapat (`load_config`'ten ÖNCE çağrılır)."""
    set_setting_sources(())


def apply_restricted_config(config: Config) -> Config:
    """Dosya araçlarını çalışma dizinlerine sınırla; yapılandırma MCP'si bağlanmaz."""
    runtime = replace(
        config.runtime, block_reads_outside_root=True, block_writes_outside_root=True
    )
    return replace(config, runtime=runtime, mcp_servers=(), hosted_connectors=())


def check_restricted_mode(mode: ApprovalMode) -> None:
    """Kısıtlı kipte `bypassPermissions` (ve `--dangerously-skip-permissions`) reddedilir."""
    if mode is ApprovalMode.BYPASS:
        raise ValueError(texts.PRINT_RESTRICTED_BYPASS)


def restricted_selection(
    selection: ToolSelection, tools_flag: str | None, mcp_patterns: frozenset[str]
) -> ToolSelection:
    """`--tools` tek tek ad vermediyse araç kümesini güvenli yerleşiklere daralt."""
    explicit = tools_flag is not None and tools_flag.strip().lower() not in ("", "default")
    if explicit:
        return selection  # `--tools` ile adı verilen araçlar (Bash dahil) kalır
    if tools_flag is not None and not tools_flag.strip():
        return selection  # `--tools ""`: zaten hiçbir yerleşik yok
    base = RESTRICTED_TOOLS | mcp_patterns
    allowed = base if selection.allowed is None else selection.allowed & base
    return replace(selection, allowed=frozenset(allowed))
