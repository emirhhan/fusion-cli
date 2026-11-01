"""Eklenti `userConfig` seçenekleri ve kaydedilen değerleri (Claude Code, #388).

Claude Code (https://code.claude.com/docs/en/plugins/manifest-reference.md "User configuration",
https://code.claude.com/docs/en/plugins/cli-reference.md "plugin configure"):
- Anahtar harf/rakam/`_` (rakamla başlamaz); değer katı nesne: `type` (string, number, boolean,
  directory, file), `title`, `description` zorunlu; `required`, `default`, `options`, `multiple`,
  `sensitive`, `min`/`max` isteğe bağlı; bilinmeyen alan doğrulamayı düşürür.
- Hassas olmayan değerler `pluginConfigs`'e, hassaslar güvenli depoya gider.
- `${user_config.KEY}` MCP yapılandırmasında ve beceri/ajan içeriğinde çözülür (içerikte yalnız
  hassas olmayanlar; hassas değer yer tutucu olur); kanca süreçlerine her seçenek
  `CLAUDE_PLUGIN_OPTION_<KEY>` olarak verilir.

Fusion'da: hassas olmayanlar `<eklentiler>/plugin-configs.json` (`{"pluginConfigs": {ad:
{"options": {...}}}}`), hassaslar yalnız sahibinin okuyabildiği (0600)
`<eklentiler>/.credentials.json` dosyasına yazılır (Claude'un Keychain yokken kullandığı
`~/.claude/.credentials.json` karşılığı).
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ..core.atomic_file import atomic_replace_text
from ..core.plugins import MANIFEST_PATHS, PluginError

CONFIG_FILE = "plugin-configs.json"
SECRET_FILE = ".credentials.json"
CONFIGS_KEY = "pluginConfigs"
ENV_PREFIX = "CLAUDE_PLUGIN_OPTION_"
SENSITIVE_PLACEHOLDER = "[sensitive user_config.{key}]"
TYPES = frozenset({"string", "number", "boolean", "directory", "file"})
_FIELDS = frozenset(
    {"type", "title", "description", "required", "default", "options", "multiple", "sensitive"}
    | {"min", "max"}
)
_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_REFERENCE = re.compile(r"\$\{user_config\.([A-Za-z_][A-Za-z0-9_]*)\}")
ERR_SCHEMA = "userConfig.{key}: {reason}"
ERR_VALUE = "{key}: {reason}"
ERR_UNKNOWN = "{key}: bildirimde böyle bir seçenek yok"


@dataclass(frozen=True, slots=True)
class UserOption:
    key: str
    type: str
    title: str
    description: str
    required: bool = False
    default: object = None
    sensitive: bool = False
    options: tuple[str, ...] = ()
    multiple: bool = False
    minimum: float | None = None
    maximum: float | None = None


def _option(key: str, raw: object) -> UserOption:
    if not _KEY.match(key):
        raise PluginError(ERR_SCHEMA.format(key=key, reason="geçersiz anahtar"))
    if not isinstance(raw, Mapping):
        raise PluginError(ERR_SCHEMA.format(key=key, reason="nesne bekleniyordu"))
    unknown = sorted(str(k) for k in raw if k not in _FIELDS)
    if unknown:
        raise PluginError(ERR_SCHEMA.format(key=key, reason=f"bilinmeyen alan {unknown[0]}"))
    kind, title, description = raw.get("type"), raw.get("title"), raw.get("description")
    if kind not in TYPES:
        raise PluginError(ERR_SCHEMA.format(key=key, reason=f"geçersiz type {kind!r}"))
    if not isinstance(title, str) or not isinstance(description, str):
        raise PluginError(ERR_SCHEMA.format(key=key, reason="title ve description zorunlu"))
    options = raw.get("options") or ()
    if not isinstance(options, list | tuple) or not all(
        isinstance(item, str) and 1 <= len(item) <= 64 for item in options
    ):
        raise PluginError(ERR_SCHEMA.format(key=key, reason="options 1-64 karakterlik metinler"))
    low, high = raw.get("min"), raw.get("max")
    return UserOption(
        key,
        str(kind),
        title,
        description,
        raw.get("required") is True,
        raw.get("default"),
        raw.get("sensitive") is True,
        tuple(options),
        raw.get("multiple") is True,
        float(low) if isinstance(low, int | float) else None,
        float(high) if isinstance(high, int | float) else None,
    )


def parse_schema(raw: object) -> tuple[UserOption, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, Mapping):
        raise PluginError("userConfig: nesne bekleniyordu")
    return tuple(_option(str(key), value) for key, value in raw.items())


def read_schema(root: Path) -> tuple[UserOption, ...]:
    """Eklenti kökündeki bildirimin `userConfig`'i (bildirim yoksa boş)."""
    for relative in MANIFEST_PATHS:
        path = root / relative
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                raise PluginError(f"{relative}: okunamadı: {error}") from error
            return parse_schema(raw.get("userConfig") if isinstance(raw, Mapping) else None)
    return ()


def coerce(option: UserOption, text: str) -> object:
    """Tek satırlık metni seçeneğin türüne çevir; geçersizse `PluginError`."""
    if "\n" in text:
        raise PluginError(ERR_VALUE.format(key=option.key, reason="tek satır olmalı"))
    if option.required and not text.strip():
        raise PluginError(ERR_VALUE.format(key=option.key, reason="boş olamaz"))
    if option.type == "boolean":
        if text.lower() not in ("true", "false"):
            raise PluginError(ERR_VALUE.format(key=option.key, reason="true ya da false"))
        return text.lower() == "true"
    if option.type == "number":
        try:
            number = float(text)
        except ValueError as error:
            raise PluginError(ERR_VALUE.format(key=option.key, reason="sayı değil")) from error
        if (option.minimum is not None and number < option.minimum) or (
            option.maximum is not None and number > option.maximum
        ):
            raise PluginError(ERR_VALUE.format(key=option.key, reason="sınırların dışında"))
        return int(number) if number.is_integer() else number
    if option.options and text not in option.options:
        allowed = ", ".join(option.options)
        raise PluginError(ERR_VALUE.format(key=option.key, reason=f"şunlardan biri: {allowed}"))
    return text


def _store(base: Path, secret: bool) -> Path:
    return base / (SECRET_FILE if secret else CONFIG_FILE)


def _read_all(path: Path) -> dict[str, dict[str, object]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    block = raw.get(CONFIGS_KEY) if isinstance(raw, Mapping) else None
    if not isinstance(block, Mapping):
        return {}
    found: dict[str, dict[str, object]] = {}
    for name, entry in block.items():
        options = entry.get("options") if isinstance(entry, Mapping) else None
        if isinstance(options, Mapping):
            found[str(name)] = dict(options)
    return found


def saved_values(name: str, base: Path) -> dict[str, object]:
    """Kaydedilmiş değerler (hassaslar dahil)."""
    return {
        **_read_all(_store(base, False)).get(name, {}),
        **_read_all(_store(base, True)).get(name, {}),
    }


def _write(path: Path, data: Mapping[str, dict[str, object]], secret: bool) -> None:
    payload = {CONFIGS_KEY: {name: {"options": options} for name, options in data.items()}}
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not secret:
        atomic_replace_text(path, text)
        return
    # Hassas dosya hiçbir an başkalarınca okunabilir olmasın: 0600 ile açılıp yerine konur.
    temporary = path.with_name(path.name + ".tmp")
    descriptor = os.open(temporary, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)
    temporary.replace(path)


def save_values(
    name: str, schema: tuple[UserOption, ...], values: Mapping[str, str], base: Path
) -> tuple[str, ...]:
    """Hepsini önce doğrula, sonra kaydet (biri geçersizse hiçbiri yazılmaz); kaydedilen adlar."""
    by_key = {option.key: option for option in schema}
    parsed: dict[str, tuple[UserOption, object]] = {}
    for key, text in values.items():
        option = by_key.get(key)
        if option is None:
            raise PluginError(ERR_UNKNOWN.format(key=key))
        if not isinstance(text, str):
            raise PluginError(ERR_VALUE.format(key=key, reason="metin olmalı"))
        parsed[key] = (option, coerce(option, text))
    for secret in (False, True):
        chosen = {k: v for k, (o, v) in parsed.items() if o.sensitive is secret}
        if chosen:
            path = _store(base, secret)
            current = _read_all(path)
            current[name] = {**current.get(name, {}), **chosen}
            _write(path, current, secret)
    return tuple(parsed)


def effective_values(name: str, schema: tuple[UserOption, ...], base: Path) -> dict[str, object]:
    """Kaydedilen değer, yoksa `default` (ikisi de yoksa seçenek yok sayılır)."""
    saved = saved_values(name, base)
    found: dict[str, object] = {}
    for option in schema:
        value = saved.get(option.key, option.default)
        if value is not None:
            found[option.key] = value
    return found


def _text(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value)


def substitute(
    text: str, schema: tuple[UserOption, ...], values: Mapping[str, object], *, content: bool
) -> str:
    """`${user_config.KEY}` → değer. `content=True` (beceri/ajan): hassas değer yer tutucudur."""
    sensitive = {option.key for option in schema if option.sensitive}

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if content and key in sensitive:
            return SENSITIVE_PLACEHOLDER.format(key=key)
        return _text(values[key]) if key in values else match.group(0)

    return _REFERENCE.sub(replace, text) if "${user_config." in text else text


def option_env(values: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
    """Kanca sürecine `CLAUDE_PLUGIN_OPTION_<KEY>` (anahtar büyük harfle)."""
    return tuple((ENV_PREFIX + key.upper(), _text(value)) for key, value in values.items())


def substitute_tree(
    raw: object, schema: tuple[UserOption, ...], values: Mapping[str, object]
) -> object:
    """JSON ağacındaki metinlerde `${user_config.KEY}` (MCP yapılandırması: hassaslar dahil)."""
    if isinstance(raw, str):
        return substitute(raw, schema, values, content=False)
    if isinstance(raw, list):
        return [substitute_tree(item, schema, values) for item in raw]
    if isinstance(raw, Mapping):
        return {key: substitute_tree(value, schema, values) for key, value in raw.items()}
    return raw


def plugin_values(root: Path, name: str) -> tuple[tuple[UserOption, ...], dict[str, object]]:
    """Eklentinin şeması ve etkin değerleri; şema bozuksa boş (yükleme bozulmaz)."""
    from .plugin_store import plugins_dir

    try:
        schema = read_schema(root)
    except PluginError:
        return (), {}
    return schema, effective_values(name, schema, plugins_dir()) if schema else {}
