"""`plugin.json` bileşen yolu kuralları ve ad kuralları — Claude Code plugins-reference.

Belge (https://code.claude.com/docs/en/plugins-reference, "Path rules", "Component path
forms", "How each key combines with its default location", "name"):

- Her bileşen yolu eklenti köküne göreli ve `./` ile başlar; `commands/foo.md` geçersizdir.
  `skills` ayrıca `"."` ve `"./"` (eklenti kökü) kabul eder.
- `commands`, `agents`, `outputStyles` varsayılan klasörün YERİNE geçer; `skills` varsayılana
  EKLENİR; `hooks` ve `mcpServers` varsayılan dosyayla BİRLEŞİR.
- `commands` ayrıca `{ad: {source|content, description, argumentHint, …}}` haritası olabilir;
  `hooks`/`mcpServers` dosya yolu, satır içi nesne ya da ikisini karıştıran dizi olabilir.
- Ad boş olamaz; boşluk, `@`, `:`, yol ayırıcı, denetim ve çift yön biçim karakteri içeremez.

Bu modül yalnız stdlib kullanır; disk işi `config/plugin_scan.py`'dedir.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping
from pathlib import PurePosixPath

from .errors import FusionError

#: Eklenti kökü (yalnız `skills` ve pazar kaynağı için geçerli).
ROOT = "."

ERR_UNSAFE_PATH = "{where}: '{key}' eklenti kökü dışına çıkamaz: {value!r}"
ERR_DOT_PREFIX = "{where}: '{key}' yolu './' ile başlamalı: {value!r}"
ERR_PATHS = "{where}: '{key}' göreli yol ya da yol listesi olmalı"
ERR_MIXED = "{where}: '{key}' yol, nesne ya da ikisini karıştıran dizi olmalı"
ERR_COMMAND_MAP = "{where}: commands.{name}: 'source' ya da 'content' alanlarından tam biri olmalı"
ERR_NAME_EMPTY = "{where}: 'name' boş olamaz"
ERR_NAME_CHARS = (
    "{where}: 'name' boşluk, '@', ':', yol ayırıcı ya da denetim karakteri içeremez: {value!r}"
)
WARN_KEBAB = 'Eklenti adı "{name}" kebab-case değil (küçük harf, rakam ve tire önerilir)'
ERR_RESERVED = (
    'Eklenti adı "{name}" ayrılmış: Anthropic\'in kendi eklentilerinden biri gibi görünüyor'
)
WARN_RESERVED = 'Eklenti adı "{name}" Anthropic\'in kendi eklentilerinden biri gibi okunuyor'

_KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_FORBIDDEN = frozenset(" @:/\\")
_RESERVED_PREFIXES = ("claude-", "anthropic-", "anthropics-", "cc-plugin-")
_RESERVED_EXACT = frozenset({"claude", "anthropic", "anthropics", "claude-code", "claude-mods"})
_BRAND_WORDS = frozenset({"claude", "anthropic", "anthropics"})
_SEPARATORS = re.compile(r"[\s._-]+")


class PluginPathError(FusionError):
    """Bileşen yolu ya da ad kuralı ihlali (çağıran `PluginError`'a çevirir)."""


def safe_relative(value: str, *, where: str, key: str, allow_root: bool = True) -> str:
    """`./x/y` → `x/y`; `.`/`./` → `.`; mutlak yol, `..` ve sürücü harfi reddedilir.

    Ölçüldü (1 Kasım): `PurePosixPath('./').parts` boştur; eski kod `parts[0]`'a erişip
    `IndexError` ile çöküyor, tek bozuk girdi bütün pazar akışlarını düşürüyordu (#378).
    """
    text = value.strip().replace("\\", "/")
    path = PurePosixPath(text)
    parts = path.parts
    if not text or path.is_absolute() or ".." in parts or (parts and ":" in parts[0]):
        raise PluginPathError(ERR_UNSAFE_PATH.format(where=where, key=key, value=value))
    if not parts:
        if not allow_root:
            raise PluginPathError(ERR_UNSAFE_PATH.format(where=where, key=key, value=value))
        return ROOT
    return str(path)


def component_path(value: str, *, where: str, key: str, allow_root: bool = False) -> str:
    """Bileşen yolu: `./` öneki zorunlu (`skills` için `.` de olur)."""
    text = value.strip()
    if allow_root and text in {".", "./"}:
        return ROOT
    if not text.replace("\\", "/").startswith("./"):
        raise PluginPathError(ERR_DOT_PREFIX.format(where=where, key=key, value=value))
    return safe_relative(text, where=where, key=key, allow_root=allow_root)


def path_list(
    raw: object, *, key: str, where: str, allow_root: bool = False
) -> tuple[str, ...] | None:
    """Yol ya da yol listesi; alan yoksa None."""
    if raw is None:
        return None
    items = [raw] if isinstance(raw, str) else raw
    if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
        raise PluginPathError(ERR_PATHS.format(where=where, key=key))
    found = (component_path(i, where=where, key=key, allow_root=allow_root) for i in items)
    return tuple(dict.fromkeys(found))


def mixed_component(raw: object, *, key: str, where: str) -> tuple[tuple[str, ...], str]:
    """`hooks`/`mcpServers`: (dosya yolları, satır içi nesnelerin JSON listesi)."""
    if raw is None:
        return (), ""
    items = raw if isinstance(raw, list) else [raw]
    paths: list[str] = []
    inline: list[object] = []
    for item in items:
        if isinstance(item, str):
            paths.append(component_path(item, where=where, key=key))
        elif isinstance(item, Mapping):
            inline.append(dict(item))
        else:
            raise PluginPathError(ERR_MIXED.format(where=where, key=key))
    encoded = json.dumps(inline, ensure_ascii=False, sort_keys=True) if inline else ""
    return tuple(dict.fromkeys(paths)), encoded


def command_map(raw: Mapping[str, object], *, where: str) -> str:
    """`commands` nesne haritası → JSON listesi `[{name, source, content, description, …}]`."""
    entries: list[dict[str, object]] = []
    for name, value in raw.items():
        if not isinstance(value, Mapping):
            raise PluginPathError(ERR_COMMAND_MAP.format(where=where, name=name))
        source, content = value.get("source"), value.get("content")
        if (source is None) == (content is None):
            raise PluginPathError(ERR_COMMAND_MAP.format(where=where, name=name))
        entry: dict[str, object] = {"name": str(name)}
        if isinstance(source, str):
            entry["source"] = component_path(source, where=where, key=f"commands.{name}")
        elif isinstance(content, str):
            entry["content"] = content
        else:
            raise PluginPathError(ERR_COMMAND_MAP.format(where=where, name=name))
        for field in ("description", "argumentHint", "model"):
            if isinstance(value.get(field), str):
                entry[field] = value[field]
        entry["name"] = check_plugin_name(str(name), f"{where}: commands")
        entries.append(entry)
    return json.dumps(entries, ensure_ascii=False, sort_keys=True)


def check_plugin_name(value: object, where: str) -> str:
    """Claude'un ad kuralı: boş değil; boşluk/@/:/ayırıcı/denetim/çift yön karakteri yok."""
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        raise PluginPathError(ERR_NAME_EMPTY.format(where=where))
    bad = any(char in _FORBIDDEN or unicodedata.category(char) in {"Cc", "Cf"} for char in text)
    # `.`/`..` klasör adı olarak kullanılır; eklenti kökü dışına çıkmasın.
    if bad or text in {".", ".."}:
        raise PluginPathError(ERR_NAME_CHARS.format(where=where, value=value))
    return text


def name_warnings(name: str) -> tuple[str, ...]:
    """`claude plugin validate` uyarıları: kebab-case dışı ad, markaya benzeyen ad."""
    found: list[str] = []
    if not _KEBAB.match(name):
        found.append(WARN_KEBAB.format(name=name))
    level = reserved_level(name)
    if level == "warning":
        found.append(WARN_RESERVED.format(name=name))
    return tuple(found)


def reserved_level(name: str) -> str:
    """`error` (ayrılmış), `warning` (marka sözcüğü içeriyor) ya da boş."""
    normal = _SEPARATORS.sub("-", name.lower()).strip("-")
    words = set(normal.split("-"))
    if normal in _RESERVED_EXACT or normal.startswith(_RESERVED_PREFIXES):
        return "error"
    if "official" in words and words & {"claude", "anthropic"}:
        return "error"
    return "warning" if words & _BRAND_WORDS else ""


def reserved_error(name: str) -> str:
    return ERR_RESERVED.format(name=name) if reserved_level(name) == "error" else ""
