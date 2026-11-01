"""`-p` isteminde değer alan yerleşik komutlar (#303, #311).

Claude Code'da `-p` koşusunda `/model sonnet`, `/effort high` değeri argüman olarak alır;
`/config key=value` ayar değiştirir, `/mcp` argümansız sunucu durumunun metin özetini basar,
`/output-style <stil>` stili seçer, `/output-style` tek başına listeler. Bu komutlar modele
gitmez: cevap doğrudan sonuç metnidir. Değer isteyen bir menü açacak biçimler (`/config`
argümansız, `/model` alt komutları…) `-p`'de kullanılamaz.

Fusion'da `/config` yolu Fusion'ın nokta yollu ayarıdır (`runtime.max_tokens=8192`); `-p`'de
`/model` ve `/effort` gibi YALNIZ bu koşunun (stream-json'da sonraki turların) ayarıdır ve
kullanıcı yapılandırmasına yazılmaz. İstem borulu stdin'den gelebilir (`cat dosya | fusion
-p`): içeriğin ilk satırı `/config runtime.block_writes_outside_root=false` olsa bile kalıcı
güvenlik ayarı değişmemeli (bağımsız inceleme, bulgu 1). Kalıcı yazma REPL'in işidir.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, cast

from ..config.models import Config
from ..core.errors import ConfigError
from ..ui import print_messages as texts

if TYPE_CHECKING:
    from .print_run import _Run
    from .repl.state import ReplState

BUILTINS = frozenset({"model", "effort", "config", "output-style", "mcp"})


@dataclass(slots=True)
class _StyleHost:
    """`output_style_command`'ın beklediği (config, home, root) alanları."""

    config: Config
    home: Path
    root: Path


@dataclass(frozen=True, slots=True)
class BuiltinReply:
    """Komutun cevabı ve (değiştiyse) yeni yapılandırma."""

    text: str
    config: Config


def parse_builtin(task: str) -> tuple[str, str] | None:
    """İstem bir yerleşik komutsa (ad, argüman); değilse `None`."""
    text = task.strip()
    if not text.startswith("/") or text.startswith("//"):
        return None
    head, _, argument = text[1:].partition(" ")
    name = head.strip().lower()
    return (name, argument.strip()) if name in BUILTINS else None


def run_builtin(
    name: str,
    argument: str,
    *,
    config: Config,
    root: Path,
    mcp_errors: tuple[dict[str, str], ...] = (),
) -> BuiltinReply:
    """Yerleşik komutu çalıştır; hata da bir cevap metnidir (koşu düşmez)."""
    if name == "model":
        return _model(config, argument)
    if name == "effort":
        return _effort(config, argument)
    if name == "config":
        return _config(config, argument)
    if name == "output-style":
        return _output_style(config, argument, root)
    return BuiltinReply(_mcp_summary(config, mcp_errors, argument), config)


def _model(config: Config, argument: str) -> BuiltinReply:
    if not argument:
        return BuiltinReply(texts.PRINT_MODEL_CURRENT.format(model=config.agent.model), config)
    from .print_options import apply_model

    try:
        updated = apply_model(config, argument, None)
    except ValueError as error:
        return BuiltinReply(str(error), config)
    return BuiltinReply(texts.PRINT_MODEL_SET.format(model=updated.agent.model), updated)


def _effort(config: Config, argument: str) -> BuiltinReply:
    current = config.runtime.reasoning_effort
    if not argument:
        value = getattr(current, "value", current) or "auto"
        return BuiltinReply(texts.PRINT_EFFORT_CURRENT.format(effort=value), config)
    from .print_plan import _with_effort

    try:
        updated = _with_effort(config, argument)
    except ValueError as error:
        return BuiltinReply(str(error), config)
    return BuiltinReply(texts.PRINT_EFFORT_SET.format(effort=argument.strip().lower()), updated)


def _config(config: Config, argument: str) -> BuiltinReply:
    path, equals, raw = argument.partition("=")
    if not equals or not path.strip():
        return BuiltinReply(texts.PRINT_SLASH_UNAVAILABLE.format(name="config"), config)
    from ..config.settings_access import apply_setting, read_setting

    try:
        updated = apply_setting(config, path.strip(), raw.strip())
    except ConfigError as error:
        return BuiltinReply(str(error), config)
    value = read_setting(updated, path.strip())
    return BuiltinReply(texts.PRINT_CONFIG_SESSION.format(path=path.strip(), value=value), updated)


def _output_style(config: Config, argument: str, root: Path) -> BuiltinReply:
    from .repl.output_style_command import output_style_command

    host = _StyleHost(config, Path.home(), root)
    text = output_style_command(cast("ReplState", host), argument)
    return BuiltinReply(text, host.config)


def _mcp_summary(config: Config, errors: tuple[dict[str, str], ...], argument: str) -> str:
    if argument:
        return texts.PRINT_SLASH_UNAVAILABLE.format(name="mcp")
    rows = [
        texts.PRINT_MCP_ROW.format(
            name=server.name,
            transport=getattr(server.transport, "value", server.transport),
            status=texts.PRINT_MCP_CONFIGURED,
        )
        for server in config.mcp_servers
    ]
    rows += [
        texts.PRINT_MCP_ROW.format(
            name=item.get("name", "?"),
            transport=item.get("type", "?"),
            status=texts.PRINT_MCP_FAILED.format(message=item.get("message", "")),
        )
        for item in errors
    ]
    return "\n".join(rows) if rows else texts.PRINT_MCP_NONE


def apply_builtin(run: _Run, task: str) -> str | None:
    """Koşu üzerinde komut çalıştır; yerleşik değilse `None`, ise cevap metni."""
    parsed = parse_builtin(task)
    if parsed is None:
        return None
    plan = run.plan
    reply = run_builtin(
        parsed[0], parsed[1], config=plan.config, root=run.root, mcp_errors=plan.mcp_errors
    )
    if reply.config is not plan.config:
        run.plan = replace(plan, config=reply.config)
    return reply.text
