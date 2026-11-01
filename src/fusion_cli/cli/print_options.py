"""`fusion -p` bayraklarının yorumu (Claude Code `--print` paritesi).

Komut gövdesi ince kalsın diye her bayrağın anlamı burada: boru stdin'i (#278), JSON
şeması (#301), izin kipi (#291), araç kuralları (#286-#290), sistem istemi (#295), model
(#296), `--settings` (#297) ve `--mcp-config` (#298). Hatalar `ValueError` olarak döner;
komut onları Claude'daki gibi stderr'e yazıp sıfır dışı kodla çıkar.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import BinaryIO

from ..config.mcp_json import merge_mcp_servers, parse_project_mcp
from ..config.models import Config, McpServerConfig
from ..config.permission_rules import PermissionDecision, PermissionRule, parse_rule
from ..core.errors import ConfigError
from ..engines.agent.approval import ApprovalMode, parse_mode
from ..tools.capabilities import CLAUDE_TOOL_MAP
from ..ui import print_messages as texts

#: Claude: boru stdin'i 10 MB ile sınırlı.
STDIN_LIMIT_BYTES = 10 * 1024 * 1024
#: `--max-turns` verilmezse Claude'da sınır yoktur; pratikte erişilmeyecek bir tavan.
UNLIMITED_TURNS = 1_000_000
#: `--settings` için Claude üst sınırı (2 MiB).
SETTINGS_LIMIT_BYTES = 2 * 1024 * 1024
_MCP_PREFIX = "mcp__"
#: Claude izin kipi adları → Fusion kipi (`parse_mode` takma adları da geçerli).
_CLAUDE_MODES = {
    "default": ApprovalMode.SECURITY,
    "manual": ApprovalMode.SECURITY,
    "acceptedits": ApprovalMode.ACCEPT_EDITS,
    "plan": ApprovalMode.PLAN,
    "auto": ApprovalMode.AUTO,
    "dontask": ApprovalMode.DONT_ASK,
    "bypasspermissions": ApprovalMode.BYPASS,
    "bypass": ApprovalMode.BYPASS,
}


def read_print_prompt(prompt: str, stdin: BinaryIO | None, *, is_tty: bool) -> tuple[str, str]:
    """İstem + boru stdin'i (#278). Dönüş: (görev, uyarı). Sınır aşımı `ValueError`."""
    text = prompt.strip()
    if text == "-":
        text = ""
    if is_tty or stdin is None:
        return text, ""
    try:
        raw = stdin.read(STDIN_LIMIT_BYTES + 1)
    except (OSError, ValueError) as error:
        return text, texts.PRINT_STDIN_UNREADABLE.format(error=error)
    if len(raw) > STDIN_LIMIT_BYTES:
        raise ValueError(texts.PRINT_STDIN_TOO_LARGE.format(limit=STDIN_LIMIT_BYTES // 2**20))
    piped = raw.decode("utf-8", errors="replace").strip()
    return "\n\n".join(part for part in (text, piped) if part), ""


def parse_permission_mode(raw: str | None, *, skip_permissions: bool) -> ApprovalMode:
    """`--permission-mode` (Claude adları birincil); verilmezse `default` (#291)."""
    if skip_permissions:
        return ApprovalMode.BYPASS
    if raw is None or not raw.strip():
        return ApprovalMode.SECURITY
    key = raw.strip().lower().replace("-", "").replace("_", "")
    if key in _CLAUDE_MODES:
        return _CLAUDE_MODES[key]
    try:
        return parse_mode(raw)
    except ValueError:
        raise ValueError(texts.PRINT_UNKNOWN_PERMISSION_MODE.format(given=raw)) from None


def parse_json_schema(raw: str | None) -> dict[str, object] | None:
    """Satır içi JSON ya da dosya yolu (#301); geçersiz şemada Claude'un hatası."""
    if raw is None or not raw.strip():
        return None
    text = raw.strip()
    if not text.startswith("{"):
        try:
            text = Path(text).expanduser().read_text(encoding="utf-8")
        except OSError:
            raise ValueError(texts.PRINT_INVALID_JSON_SCHEMA) from None
    try:
        schema = json.loads(text)
    except json.JSONDecodeError:
        raise ValueError(texts.PRINT_INVALID_JSON_SCHEMA) from None
    if not isinstance(schema, dict) or not _schema_is_valid(schema):
        raise ValueError(texts.PRINT_INVALID_JSON_SCHEMA)
    return schema


def _schema_is_valid(schema: dict[str, object]) -> bool:
    try:
        from jsonschema import exceptions, validators
    except ImportError:  # isteğe bağlı bağımlılık; yoksa en temel biçim denetimi
        kind = schema.get("type")
        return kind is None or isinstance(kind, (str, list))
    try:
        validators.validator_for(schema).check_schema(schema)
    except exceptions.SchemaError:
        return False
    return True


def schema_errors(value: object, schema: dict[str, object]) -> tuple[str, ...]:
    """Değeri tam JSON Schema ile denetle (jsonschema yoksa Fusion alt kümesi)."""
    try:
        from jsonschema import validators
    except ImportError:
        from ..core.json_schema import validate_instance

        return tuple(validate_instance(value, schema))
    validator = validators.validator_for(schema)(schema)
    return tuple(
        f"$.{'.'.join(str(p) for p in error.absolute_path)}: {error.message}".replace("$.:", "$:")
        for error in validator.iter_errors(value)
    )


@dataclass(frozen=True, slots=True)
class ToolSelection:
    """`--allowedTools/--disallowedTools/--tools` çözümü."""

    rules: tuple[PermissionRule, ...] = ()
    #: Bağlamdan tamamen çıkan araçlar (çıplak yasak adı; `sunucu__*` deseni olabilir).
    denied: frozenset[str] = frozenset()
    #: `--tools` daraltması; None = varsayılan küme.
    allowed: frozenset[str] | None = None
    unmapped: tuple[str, ...] = ()


def split_tool_values(raw: Iterable[str] | None) -> tuple[str, ...]:
    """Virgülle ya da tekrarla verilen değerler; parantez içindeki virgül bölünmez."""
    values: list[str] = []
    for chunk in raw or ():
        depth, current = 0, ""
        for char in chunk:
            depth += (char == "(") - (char == ")")
            if char == "," and depth == 0:
                values.append(current.strip())
                current = ""
            else:
                current += char
        values.append(current.strip())
    return tuple(value for value in values if value)


def _fusion_names(name: str, servers: Sequence[str]) -> frozenset[str] | None:
    """Çıplak Claude adını Fusion araç adlarına çevir; karşılığı yoksa None."""
    if name == "*":
        return frozenset({"*"})
    if name.startswith(_MCP_PREFIX):
        rest = name[len(_MCP_PREFIX) :]
        if rest in ("", "*"):
            return frozenset(f"{server}__*" for server in servers)
        return frozenset({rest if "__" in rest else f"{rest}__*"})
    mapped = CLAUDE_TOOL_MAP.get(name.lower())
    if mapped is not None:
        return mapped
    return frozenset({name}) if name[:1].islower() else None


def tool_selection(
    allowed: Iterable[str] | None,
    disallowed: Iterable[str] | None,
    tools: str | None,
    *,
    mcp_servers: Sequence[str] = (),
) -> ToolSelection:
    """Claude anlamı: allow = ön-onay kuralı, deny = çıkar/kural, --tools = daralt."""
    rules: list[PermissionRule] = []
    unmapped: list[str] = []
    for entry in split_tool_values(allowed):
        rule = parse_rule(entry, PermissionDecision.ALLOW, source="cli")
        if rule is not None:
            rules.append(rule)
            if rule.tool != "*" and _fusion_names(rule.tool, mcp_servers) is None:
                unmapped.append(entry)
    denied: set[str] = set()
    for entry in split_tool_values(disallowed):
        rule = parse_rule(entry, PermissionDecision.DENY, source="cli")
        if rule is None:
            continue
        names = _fusion_names(rule.tool, mcp_servers)
        if rule.specifier is not None or names is None:
            rules.append(rule)
            if names is None:
                unmapped.append(entry)
            continue
        denied |= names
    narrowed = _narrowed_tools(tools, mcp_servers, unmapped)
    if "*" in denied:
        narrowed, denied = frozenset(), denied - {"*"}
    return ToolSelection(tuple(rules), frozenset(denied), narrowed, tuple(unmapped))


def _narrowed_tools(
    tools: str | None, servers: Sequence[str], unmapped: list[str]
) -> frozenset[str] | None:
    """`--tools`: "" hepsi kapalı, "default" küme aynen; MCP araçları etkilenmez (#290)."""
    if tools is None or tools.strip().lower() == "default":
        return None
    names: set[str] = {f"{server}__*" for server in servers}
    for entry in split_tool_values([tools]):
        mapped = _fusion_names(entry, servers)
        if mapped is None:
            unmapped.append(entry)
        else:
            names |= mapped
    return frozenset(names)


def read_text_flag(flag: str, path: str | None) -> str:
    """`--system-prompt-file` gibi dosya bayraklarını oku."""
    if not path:
        return ""
    try:
        return Path(path).expanduser().read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(
            texts.PRINT_FILE_UNREADABLE.format(flag=flag, path=path, error=error)
        ) from None


def system_prompts(
    *,
    system_prompt: str | None,
    system_prompt_file: str | None,
    append: str | None,
    append_file: str | None,
) -> tuple[str | None, str]:
    """(çekirdeğin yerine geçen metin | None, ek metin). Dosya içeriği önce gelir (#295)."""
    replacement = "\n\n".join(
        part
        for part in (read_text_flag("--system-prompt-file", system_prompt_file), system_prompt)
        if part
    )
    extra = "\n\n".join(
        part
        for part in (read_text_flag("--append-system-prompt-file", append_file), append)
        if part
    )
    return (replacement or None), extra


def apply_model(config: Config, model: str | None, fallback: str | None) -> Config:
    """`--model` takma ad ya da tam kimlik; `--fallback-model a,b` sıralı yedek (#296)."""
    agent = config.agent
    if model and model.strip():
        from ..engines.agent.agent_launch_model import resolve_agent_model

        try:
            resolved = resolve_agent_model(
                model.strip(),
                agent,
                candidates=config.candidates,
                launch=config.agent_launch,
                keep_builtin_model=True,
            )
        except ConfigError as error:
            raise ValueError(texts.PRINT_MODEL_UNRESOLVED.format(error=error)) from None
        agent = resolved or agent.with_identity(model.strip())
    if fallback and fallback.strip():
        chain = tuple(item.strip() for item in fallback.split(",") if item.strip())
        agent = replace(agent, fallback=chain)
    return config if agent is config.agent else replace(config, agent=agent)


def load_mcp_configs(
    config: Config, sources: Sequence[str], *, strict: bool
) -> tuple[Config, tuple[dict[str, str], ...]]:
    """`--mcp-config` dosya/dizgeleri; bozuk girdi atlanır ve hata listesine düşer (#298)."""
    found: list[McpServerConfig] = []
    errors: list[dict[str, str]] = []
    for source in sources:
        try:
            text = source if source.lstrip().startswith("{") else Path(source).read_text("utf-8")
            found.extend(parse_project_mcp(json.loads(text)))
        except (OSError, ValueError, ConfigError) as error:
            errors.append({"source": source, "error": str(error)})
    base = () if strict else config.mcp_servers
    servers = merge_mcp_servers(base, tuple(found))
    if servers == config.mcp_servers:
        return config, tuple(errors)
    return replace(config, mcp_servers=servers), tuple(errors)


def load_settings(raw: str | None) -> dict[str, object]:
    """`--settings` dosya yolu ya da satır içi JSON (≤2 MiB)."""
    if raw is None or not raw.strip():
        return {}
    text = raw.strip()
    try:
        if not text.startswith("{"):
            path = Path(text).expanduser()
            if path.stat().st_size > SETTINGS_LIMIT_BYTES:
                raise ValueError("2 MiB sınırı aşıldı")
            text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, ValueError) as error:
        raise ValueError(texts.PRINT_SETTINGS_INVALID.format(error=error)) from None
    if not isinstance(data, dict):
        raise ValueError(texts.PRINT_SETTINGS_INVALID.format(error="kök bir nesne olmalı"))
    return data


def settings_rules(settings: dict[str, object]) -> tuple[PermissionRule, ...]:
    """`--settings` içindeki `permissions.allow/ask/deny` kuralları (oturumluk)."""
    block = settings.get("permissions")
    if not isinstance(block, dict):
        return ()
    rules: list[PermissionRule] = []
    for decision in PermissionDecision:
        entries = block.get(decision.value)
        for entry in entries if isinstance(entries, list) else ():
            rule = parse_rule(entry, decision, source="--settings")
            if rule is not None:
                rules.append(rule)
    return tuple(rules)


def checked_session_id(raw: str | None) -> str | None:
    """`--session-id` geçerli bir UUID olmalı (Claude)."""
    if raw is None or not raw.strip():
        return None
    try:
        return str(uuid.UUID(raw.strip()))
    except ValueError:
        raise ValueError(texts.PRINT_SESSION_ID_INVALID) from None
