"""`--agents` JSON sınırı: dosya yaratmadan doğrulanmış, tiplenmiş ajan tanımları."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import replace
from pathlib import Path
from typing import NoReturn

from ..core.errors import ConfigError
from .capabilities import Capability, _capability_from_fields
from .frontmatter import normalize_agent_fields

_LOG = logging.getLogger(__name__)
#: Komut satırından tek seferde alınan tanımların bellek sınırı; dosya okunmaz.
MAX_SESSION_AGENTS_BYTES = 128 * 1024
MAX_AGENT_NAME_CHARS = 256
_IDENTITY_DIRECTORY = ".cli-agents"
_TEXT_FIELDS = frozenset(
    {
        "prompt",
        "description",
        "model",
        "permissionMode",
        "initialPrompt",
        "memory",
        "effort",
        "isolation",
    }
)
_LIST_FIELDS = frozenset({"tools", "disallowedTools", "skills"})
_BOOL_FIELDS = frozenset({"background", "omitClaudeMd"})
_IGNORED_FIELDS = frozenset({"color", "experimental"})
_KNOWN_FIELDS = (
    _TEXT_FIELDS
    | _LIST_FIELDS
    | _BOOL_FIELDS
    | _IGNORED_FIELDS
    | {
        "hooks",
        "mcpServers",
        "maxTurns",
        "autoCompactWindow",
    }
)
_IGNORED_WARNING = "CLI ajan tanımının desteklenmeyen uyumluluk alanları yok sayıldı"


def session_agents_from_json(raw: str, *, root: Path) -> tuple[Capability, ...]:
    """Tek JSON sınırından değişmez katalog girdileri üret; hiçbir dosyaya dokunma."""
    try:
        size = len(raw.encode("utf-8"))
    except UnicodeError as error:
        raise ConfigError("CLI ajan tanımı geçerli UTF-8 metni olmalı.") from error
    if size > MAX_SESSION_AGENTS_BYTES:
        raise ConfigError("CLI ajan tanımları 128 KiB sınırını aşıyor; tanımları küçültün.")
    try:
        definitions: object = json.loads(
            raw, object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant
        )
    except (json.JSONDecodeError, RecursionError) as error:
        raise ConfigError("CLI ajan tanımı geçerli bir JSON nesnesi olmalı.") from error
    if not isinstance(definitions, dict):
        raise ConfigError("CLI ajan tanımları adlarla anahtarlanmış JSON nesnesi olmalı.")
    agents: list[Capability] = []
    for name, entry in definitions.items():
        _validate_name(name)
        fields = _validated_fields(entry)
        prompt = fields.pop("prompt")
        assert isinstance(prompt, str)  # Şema bu alanın metin olduğunu doğrular.
        fields["name"] = name
        identity = hashlib.sha256(name.encode()).hexdigest()
        path = root / _IDENTITY_DIRECTORY / f"{identity}.md"
        capability = _capability_from_fields(
            path, "cli", normalize_agent_fields(fields), fallback=name
        )
        agents.append(replace(capability, inline_prompt=prompt))
    return tuple(agents)


def _invalid_constant(value: str) -> NoReturn:
    raise ConfigError("CLI ajan tanımında NaN/Infinity geçersizdir; standart JSON kullanın.")


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    fields: dict[str, object] = {}
    for key, value in pairs:
        if key in fields:
            raise ConfigError(
                "CLI ajan tanımında yinelenen JSON alanı var; her alanı bir kez yazın."
            )
        fields[key] = value
    return fields


def _validate_name(name: str) -> None:
    if (
        not name
        or len(name) > MAX_AGENT_NAME_CHARS
        or name.startswith("-")
        or any(char.isspace() or not char.isprintable() or char in ":/\\" for char in name)
    ):
        raise ConfigError(
            "CLI ajan adı 1–256 karakter olmalı; boşluk, yol ayırıcı veya ':' içeremez, "
            "'-' ile başlayamaz."
        )


def _validated_fields(entry: object) -> dict[str, object]:
    if not isinstance(entry, dict) or "prompt" not in entry:
        raise ConfigError("CLI ajan tanımı nesne olmalı ve metin 'prompt' alanını içermeli.")
    unknown = set(entry) - _KNOWN_FIELDS
    if unknown:
        raise ConfigError("CLI ajan tanımında bilinmeyen alan var: " + ", ".join(sorted(unknown)))
    ignored = set(entry) & _IGNORED_FIELDS
    if ignored:
        _LOG.warning(_IGNORED_WARNING, extra={"alanlar": tuple(sorted(ignored))})
    fields: dict[str, object] = {key: value for key, value in entry.items() if key not in ignored}
    for key, value in fields.items():
        _validate_field(key, value)
    return fields


def _validate_field(key: str, value: object) -> None:
    if key in _TEXT_FIELDS and not isinstance(value, str):
        raise ConfigError(f"CLI ajan tanımında '{key}' metin olmalı.")
    if key in _BOOL_FIELDS and not isinstance(value, bool):
        raise ConfigError(f"CLI ajan tanımında '{key}' true veya false olmalı.")
    if key in _LIST_FIELDS and not (
        isinstance(value, str)
        or (isinstance(value, list) and all(isinstance(item, str) for item in value))
    ):
        raise ConfigError(f"CLI ajan tanımında '{key}' metin veya metin listesi olmalı.")
    if key == "maxTurns" and (type(value) is not int or value <= 0):
        raise ConfigError("CLI ajan tanımında maxTurns pozitif tam sayı olmalı.")
    if key == "hooks" and not isinstance(value, dict):
        raise ConfigError("CLI ajan tanımında hooks nesne olmalı.")
    if key == "mcpServers" and not (
        isinstance(value, list) and all(isinstance(item, (str, dict)) for item in value)
    ):
        raise ConfigError("CLI ajan tanımında mcpServers ad ve tanım listesi olmalı.")
    if key == "autoCompactWindow":
        raise ConfigError("CLI ajan tanımında autoCompactWindow bu sürümde desteklenmiyor.")
