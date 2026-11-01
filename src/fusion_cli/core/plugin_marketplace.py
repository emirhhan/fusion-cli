"""`marketplace.json` ayrıştırma — Claude Code marketplace-reference.

Belge (https://code.claude.com/docs/en/plugins/marketplace-reference.md):
- `name`, `owner` (`owner.name` zorunlu) ve `plugins` zorunlu; her girdi AYRI doğrulanır,
  bozuk tek girdi pazarı düşürmez (#397). Bilinmeyen anahtar yok sayılır; yinelenen ad hata.
- Pazar adı harf/rakam ile başlar, harf, rakam, `.`, `_`, `-` içerir; resmî ve ayrılmış adlar
  reddedilir (#411).
- Göreli kaynak `./` ile başlar, `.` tek başına köktür; çıplak ad yalnız `metadata.pluginRoot`
  altında ve `/` içermeden. `sha` tam 40 karakter küçük harf; eklenti kaynağında `git` türü
  yoktur (Fusion'ın eski adı olarak uyarıyla okunur) (#399).
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass

from .plugins import PluginError, safe_relative

ERR_NOT_OBJECT = "{where}: JSON nesnesi bekleniyordu"
ERR_PLUGINS = "{where}: 'plugins' liste olmalı"
ERR_OWNER = "{where}: 'owner.name' boş olamaz"
ERR_MARKET_NAME = (
    "{where}: pazar adı harf ya da rakamla başlamalı; yalnız harf, rakam, '.', '_', '-': {value!r}"
)
ERR_MARKET_RESERVED = (
    "{where}: pazar adı ayrılmış ya da resmî bir Anthropic/Claude pazarını taklit ediyor: {value!r}"
)
ERR_ENTRY_NAME = (
    "eklenti adı harf ya da rakamla başlamalı; yalnız harf, rakam, '.', '_', '-': {value!r}"
)
ERR_DUPLICATE = '{where}: yinelenen eklenti adı "{name}"'
ERR_SOURCE = "'{name}' için kaynak anlaşılamadı (./göreli yol, github ya da url)"
ERR_DOT = "'{name}' kaynağı './' ile başlamalı: {value!r}"
ERR_SHA = "'{name}' sha tam 40 karakterlik küçük harf commit olmalı: {value!r}"
WARN_ENTRY_SKIPPED = "{where}: plugins[{index}] atlandı: {error}"
WARN_GIT_SOURCE = "'{name}' kaynağında 'git' türü kullanımdan kalktı; Claude Code adı 'url'"

_ID_PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_OFFICIAL = frozenset(
    {
        "claude-code-marketplace", "claude-code-plugins", "claude-plugins-official",
        "anthropic-marketplace", "anthropic-plugins", "agent-skills", "anthropic-agent-skills",
        "life-sciences", "knowledge-work-plugins", "claude-for-legal",
        "claude-for-financial-services", "financial-services-plugins", "first-party-plugins",
        "claude-tag-plugins", "claude-community", "claude-plugins-community", "healthcare",
        "anthropic-plugin-directory", "claude-plugin-directory",
    }
)  # fmt: skip
_RESERVED = frozenset(
    {
        "inline", "builtin", "skills-dir", "synced", "claude-plugin-test", "npm", "pip", "uv",
        "cargo", "github", "gh", "constructor", "hasownproperty", "isprototypeof",
        "propertyisenumerable", "tolocalestring", "tostring", "valueof",
    }
)  # fmt: skip
_IMITATED_PREFIXES = ("claude-plugins", "claude-code-plugins", "anthropic-plugins")
_SPELLING = re.compile(r"[^a-z0-9_]+")


@dataclass(frozen=True, slots=True)
class MarketplaceSource:
    """Pazar yerindeki bir eklentinin nereden alınacağı."""

    #: `path` (pazar köküne göreli) | `git` (klonlanır).
    kind: str
    location: str
    ref: str = ""
    #: Beklenen commit (kurulumda doğrulanır; uyuşmazsa kurulmaz).
    sha: str = ""
    #: `git-subdir`: depodaki eklenti alt klasörü (#399).
    subdir: str = ""


@dataclass(frozen=True, slots=True)
class MarketplaceEntry:
    name: str
    source: MarketplaceSource
    description: str = ""
    version: str = ""
    category: str = ""
    #: Girdinin taşıdığı plugin.json alanları (JSON metni; boş = yok) ve strict modu (#398).
    fields: str = ""
    strict: bool = True


#: Girdinin kendi alanları: bildirime aktarılmaz (Claude marketplace-reference "Plugin entries").
_ENTRY_ONLY_KEYS = frozenset(
    {"name", "source", "strict", "category", "tags", "relevance", "metadata", "headers"}
    | {"headersHelper"}
)


def _entry_fields(raw: Mapping[str, object]) -> str:
    fields = {str(k): v for k, v in raw.items() if str(k) not in _ENTRY_ONLY_KEYS}
    return json.dumps(fields, ensure_ascii=False, sort_keys=True) if fields else ""


@dataclass(frozen=True, slots=True)
class Marketplace:
    name: str
    owner: str
    entries: tuple[MarketplaceEntry, ...]
    description: str = ""
    #: Atlanan girdilerin ve kullanımdan kalkan biçimlerin uyarıları.
    warnings: tuple[str, ...] = ()


def is_reserved_marketplace(name: str) -> bool:
    """Resmî ad, taklit (resmî adın başka yazımı ya da ASCII dışı), ayrılmış ad, `claudeai-`."""
    lowered = name.lower()
    spelled = _SPELLING.sub("-", lowered.rstrip(".")).strip("-")
    if lowered in _RESERVED or lowered.startswith("claudeai-") or not name.isascii():
        return True
    if spelled in _OFFICIAL or lowered in _OFFICIAL:
        return True
    words = set(spelled.split("-"))
    if not words & {"claude", "anthropic"}:
        return False
    return "official" in words or spelled.startswith(_IMITATED_PREFIXES)


def check_marketplace_name(value: object, where: str) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not _ID_PART.match(text) or ".." in text:
        raise PluginError(ERR_MARKET_NAME.format(where=where, value=value))
    if is_reserved_marketplace(text):
        raise PluginError(ERR_MARKET_RESERVED.format(where=where, value=value))
    return text


def parse_marketplace(raw: object, *, where: str = "marketplace.json") -> Marketplace:
    """`marketplace.json` içeriğini doğrula; bozuk girdi atlanır ve uyarı olur."""
    if not isinstance(raw, Mapping):
        raise PluginError(ERR_NOT_OBJECT.format(where=where))
    name = check_marketplace_name(raw.get("name"), where)
    owner = raw.get("owner")
    owner_name = owner.get("name") if isinstance(owner, Mapping) else owner
    if not isinstance(owner_name, str) or not owner_name.strip():
        raise PluginError(ERR_OWNER.format(where=where))
    plugins = raw.get("plugins")
    if not isinstance(plugins, list):
        raise PluginError(ERR_PLUGINS.format(where=where))
    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), Mapping) else {}
    assert isinstance(metadata, Mapping)
    root = ""
    if isinstance(metadata.get("pluginRoot"), str):
        root = safe_relative(str(metadata["pluginRoot"]), where=where, key="pluginRoot")
    entries, warnings = _entries(plugins, where, root)
    description = raw.get("description") or metadata.get("description") or ""
    return Marketplace(
        name,
        owner_name.strip(),
        entries,
        description if isinstance(description, str) else "",
        warnings,
    )


def _entries(
    plugins: list[object], where: str, root: str
) -> tuple[tuple[MarketplaceEntry, ...], tuple[str, ...]]:
    entries: list[MarketplaceEntry] = []
    warnings: list[str] = []
    for index, item in enumerate(plugins):
        try:
            entry, notes = _entry(item, root)
        except PluginError as error:
            warnings.append(WARN_ENTRY_SKIPPED.format(where=where, index=index, error=error))
            continue
        if any(existing.name == entry.name for existing in entries):
            raise PluginError(ERR_DUPLICATE.format(where=where, name=entry.name))
        entries.append(entry)
        warnings.extend(notes)
    return tuple(entries), tuple(warnings)


def _entry(raw: object, plugin_root: str) -> tuple[MarketplaceEntry, tuple[str, ...]]:
    if not isinstance(raw, Mapping):
        raise PluginError("JSON nesnesi bekleniyordu")
    name = raw.get("name")
    if not isinstance(name, str) or not _ID_PART.match(name) or _has_control(name):
        raise PluginError(ERR_ENTRY_NAME.format(value=name))
    source, notes = _source(raw.get("source"), name, plugin_root)
    entry = MarketplaceEntry(
        name=name,
        source=source,
        description=str(raw.get("description") or ""),
        version=str(raw.get("version") or ""),
        category=str(raw.get("category") or ""),
        fields=_entry_fields(raw),
        strict=raw.get("strict") is not False,
    )
    return entry, notes


def _has_control(text: str) -> bool:
    return any(unicodedata.category(char) in {"Cc", "Cf"} for char in text)


def _source(raw: object, name: str, plugin_root: str) -> tuple[MarketplaceSource, tuple[str, ...]]:
    if isinstance(raw, str) and raw.strip():
        return MarketplaceSource("path", _relative(raw.strip(), name, plugin_root)), ()
    if not isinstance(raw, Mapping):
        raise PluginError(ERR_SOURCE.format(name=name))
    kind = str(raw.get("source") or "")
    ref = str(raw.get("ref") or "")
    sha = str(raw.get("sha") or "")
    if sha and not _SHA.match(sha):
        raise PluginError(ERR_SHA.format(name=name, value=sha))
    if kind == "github" and isinstance(raw.get("repo"), str):
        return MarketplaceSource("git", f"https://github.com/{raw['repo']}", ref, sha), ()
    if kind == "git-subdir" and isinstance(raw.get("url"), str) and raw.get("path"):
        url = str(raw["url"])
        if not url.startswith(("https://", "http://", "git@", "file://")) and url.count("/") == 1:
            url = f"https://github.com/{url}"
        subdir = safe_relative(str(raw["path"]), where="marketplace.json", key=f"{name}.path")
        return MarketplaceSource("git", url, ref, sha, subdir), ()
    if kind in {"url", "git"} and isinstance(raw.get("url"), str):
        notes = (WARN_GIT_SOURCE.format(name=name),) if kind == "git" else ()
        return MarketplaceSource("git", str(raw["url"]), ref, sha), notes
    raise PluginError(ERR_SOURCE.format(name=name))


def _relative(text: str, name: str, plugin_root: str) -> str:
    key = f"{name}.source"
    if text == "." or text.startswith("./"):
        return safe_relative(text, where="marketplace.json", key=key)
    if plugin_root and "/" not in text and "\\" not in text and not text.startswith("."):
        return safe_relative(f"{plugin_root}/{text}", where="marketplace.json", key=key)
    raise PluginError(ERR_DOT.format(name=name, value=text))
