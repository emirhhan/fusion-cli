"""Eklenti paketi ve pazar yeri bildirimi (P-059) — Claude Code `.claude-plugin/` biçimi.

Bir eklenti, birlikte dağıtılan bileşenlerin klasörüdür:

    benim-eklentim/
      .claude-plugin/plugin.json   {"name": "benim-eklentim", "version": "1.2.0", ...}
      skills/<ad>/SKILL.md         beceriler          → `/benim-eklentim:<ad>`
      commands/<ad>.md             komutlar           → `/benim-eklentim:<ad>`
      agents/<ad>.md               alt ajanlar        → `benim-eklentim:<ad>`
      output-styles/<ad>.md        çıktı stilleri     → `benim-eklentim:<ad>`
      hooks/hooks.json             kancalar           (komut çalıştırır)
      .mcp.json                    MCP sunucuları     (süreç başlatır)

`plugin.json` alanları bileşen yollarını değiştirebilir (`"commands": "./ozel"` ya da liste;
`"hooks"`/`"mcpServers"` dosya yolu ya da satır içi nesne). Fusion kendi adıyla
`.fusion-plugin/plugin.json`'ı da okur. Pazar yeri `.claude-plugin/marketplace.json`:
`{"name": …, "owner": {…}, "plugins": [{"name", "source", "description", "version"}]}`;
`source` göreli yol (`./plugins/x`) ya da `{"source": "github", "repo": "o/r", "ref", "sha"}` /
`{"source": "url", "url": "https://….git", "ref", "sha"}` olabilir.

Bu modül YALNIZ ayrıştırır ve doğrular (stdlib); disk ve ağ işi üst katmanlardadır.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath

from .errors import FusionError

#: Bildirim dosyası adayları (ilk bulunan okunur).
MANIFEST_PATHS: tuple[str, ...] = (".claude-plugin/plugin.json", ".fusion-plugin/plugin.json")
MARKETPLACE_PATHS: tuple[str, ...] = (
    ".claude-plugin/marketplace.json",
    ".fusion-plugin/marketplace.json",
)
#: Varsayılan bileşen yerleri (eklenti köküne göreli).
DEFAULT_COMMANDS = "commands"
DEFAULT_AGENTS = "agents"
DEFAULT_SKILLS = "skills"
DEFAULT_OUTPUT_STYLES = "output-styles"
DEFAULT_HOOKS = "hooks/hooks.json"
DEFAULT_MCP = ".mcp.json"
#: Kanca/MCP komutlarında eklenti kökü değişkenleri (Claude Code adı + Fusion adı).
ROOT_VARIABLES: tuple[str, ...] = ("${CLAUDE_PLUGIN_ROOT}", "${FUSION_PLUGIN_ROOT}")
#: Ad kuralı (Claude Code: kebab-case). Ad komut önekidir (`/ad:komut`).
NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
#: Fusion'ın tanıdığı `plugin.json` alanları; ötekiler uyarı olur, kurulumu engellemez.
KNOWN_FIELDS = frozenset(
    {
        "name",
        "version",
        "description",
        "author",
        "homepage",
        "repository",
        "license",
        "keywords",
        "commands",
        "agents",
        "skills",
        "outputStyles",
        "output-styles",
        "hooks",
        "mcpServers",
        "$schema",
    }
)

ERR_NOT_OBJECT = "{where}: JSON nesnesi bekleniyordu"
ERR_NAME = "{where}: 'name' küçük harf, rakam, '-', '.', '_' olmalı (en çok 64): {value!r}"
ERR_TEXT = "{where}: '{key}' metin olmalı"
ERR_PATHS = "{where}: '{key}' göreli yol ya da yol listesi olmalı"
ERR_UNSAFE_PATH = "{where}: '{key}' eklenti kökü dışına çıkamaz: {value!r}"
ERR_PLUGINS = "{where}: 'plugins' liste olmalı"
ERR_SOURCE = "{where}: '{name}' için kaynak anlaşılamadı (göreli yol, github ya da url)"
WARN_UNKNOWN = "plugin.json: tanınmayan alan(lar) yok sayıldı: {names}"


class PluginError(FusionError):
    """Eklenti ya da pazar yeri bildirimi geçersiz; mesaj kullanıcıya gösterilir."""


@dataclass(frozen=True, slots=True)
class PluginManifest:
    """`plugin.json`'ın ayrıştırılmış hâli. Yollar eklenti köküne göreli POSIX metnidir."""

    name: str
    version: str = ""
    description: str = ""
    author: str = ""
    homepage: str = ""
    repository: str = ""
    license: str = ""
    keywords: tuple[str, ...] = ()
    commands: tuple[str, ...] = (DEFAULT_COMMANDS,)
    agents: tuple[str, ...] = (DEFAULT_AGENTS,)
    skills: tuple[str, ...] = (DEFAULT_SKILLS,)
    output_styles: tuple[str, ...] = (DEFAULT_OUTPUT_STYLES,)
    hooks: tuple[str, ...] = (DEFAULT_HOOKS,)
    mcp_servers: tuple[str, ...] = (DEFAULT_MCP,)
    #: Satır içi `hooks`/`mcpServers` nesnesi (JSON metni; boş = yok).
    inline_hooks: str = ""
    inline_mcp: str = ""
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MarketplaceSource:
    """Pazar yerindeki bir eklentinin nereden alınacağı."""

    #: `path` (pazar köküne göreli) | `git` (klonlanır).
    kind: str
    location: str
    ref: str = ""
    #: Beklenen commit (kurulumda doğrulanır; uyuşmazsa kurulmaz).
    sha: str = ""


@dataclass(frozen=True, slots=True)
class MarketplaceEntry:
    name: str
    source: MarketplaceSource
    description: str = ""
    version: str = ""
    category: str = ""


@dataclass(frozen=True, slots=True)
class Marketplace:
    name: str
    owner: str
    entries: tuple[MarketplaceEntry, ...]
    description: str = ""


def check_name(value: object, where: str) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not NAME_PATTERN.match(text):
        raise PluginError(ERR_NAME.format(where=where, value=value))
    return text


def safe_relative(value: str, *, where: str, key: str) -> str:
    """`./x/y` → `x/y`; mutlak yol ya da `..` reddedilir."""
    text = value.strip().replace("\\", "/")
    path = PurePosixPath(text)
    if not text or path.is_absolute() or ".." in path.parts or ":" in path.parts[0]:
        raise PluginError(ERR_UNSAFE_PATH.format(where=where, key=key, value=value))
    return str(path)


def _text(raw: Mapping[str, object], key: str, where: str) -> str:
    value = raw.get(key, "")
    if isinstance(value, Mapping):
        # `author: {name, email}` ve `repository: {type, url}` (npm biçimi) de kabul edilir.
        value = value.get("name" if key == "author" else "url", "")
    if not isinstance(value, str):
        raise PluginError(ERR_TEXT.format(where=where, key=key))
    return value.strip()


def _paths(raw: Mapping[str, object], key: str, default: str, where: str) -> tuple[str, ...]:
    """Yol ya da yol listesi. Claude Code'daki gibi özel yollar varsayılanı TAMAMLAR."""
    value = raw.get(key)
    if value is None:
        return (default,)
    items = [value] if isinstance(value, str) else value
    if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
        raise PluginError(ERR_PATHS.format(where=where, key=key))
    custom = tuple(safe_relative(item, where=where, key=key) for item in items)
    return tuple(dict.fromkeys((default, *custom)))


def _component(
    raw: Mapping[str, object], key: str, default: str, where: str
) -> tuple[tuple[str, ...], str]:
    """`hooks`/`mcpServers`: yol(lar) ya da satır içi nesne → (yollar, satır içi JSON)."""
    value = raw.get(key)
    if isinstance(value, Mapping):
        return (default,), json.dumps(value, ensure_ascii=False, sort_keys=True)
    return _paths(raw, key, default, where), ""


def parse_manifest(
    raw: object, *, fallback_name: str = "", where: str = "plugin.json"
) -> PluginManifest:
    """`plugin.json` içeriğini doğrula. Bildirim yoksa (`raw` None) ad klasörden gelir."""
    if raw is None:
        return PluginManifest(name=check_name(fallback_name, where))
    if not isinstance(raw, Mapping):
        raise PluginError(ERR_NOT_OBJECT.format(where=where))
    keywords = raw.get("keywords", [])
    unknown = sorted(set(raw) - KNOWN_FIELDS)
    hooks, inline_hooks = _component(raw, "hooks", DEFAULT_HOOKS, where)
    mcp, inline_mcp = _component(raw, "mcpServers", DEFAULT_MCP, where)
    styles_key = "outputStyles" if "outputStyles" in raw else "output-styles"
    return PluginManifest(
        name=check_name(raw.get("name", fallback_name), where),
        version=_text(raw, "version", where),
        description=_text(raw, "description", where),
        author=_text(raw, "author", where),
        homepage=_text(raw, "homepage", where),
        repository=_text(raw, "repository", where),
        license=_text(raw, "license", where),
        keywords=tuple(str(k) for k in keywords) if isinstance(keywords, list) else (),
        commands=_paths(raw, "commands", DEFAULT_COMMANDS, where),
        agents=_paths(raw, "agents", DEFAULT_AGENTS, where),
        skills=_paths(raw, "skills", DEFAULT_SKILLS, where),
        output_styles=_paths(raw, styles_key, DEFAULT_OUTPUT_STYLES, where),
        hooks=hooks,
        mcp_servers=mcp,
        inline_hooks=inline_hooks,
        inline_mcp=inline_mcp,
        warnings=(WARN_UNKNOWN.format(names=", ".join(unknown)),) if unknown else (),
    )


def parse_marketplace(raw: object, *, where: str = "marketplace.json") -> Marketplace:
    """`marketplace.json` içeriğini doğrula; bozuk tek girdi bütün pazarı düşürür (açık hata)."""
    if not isinstance(raw, Mapping):
        raise PluginError(ERR_NOT_OBJECT.format(where=where))
    name = check_name(raw.get("name"), where)
    owner = raw.get("owner", "")
    owner_name = owner.get("name", "") if isinstance(owner, Mapping) else owner
    plugins = raw.get("plugins", [])
    if not isinstance(plugins, list):
        raise PluginError(ERR_PLUGINS.format(where=where))
    root = ""
    metadata = raw.get("metadata")
    if isinstance(metadata, Mapping) and isinstance(metadata.get("pluginRoot"), str):
        root = safe_relative(str(metadata["pluginRoot"]), where=where, key="pluginRoot")
    entries = tuple(_entry(item, where, root) for item in plugins)
    description = raw.get("description", "")
    return Marketplace(
        name,
        str(owner_name or ""),
        entries,
        description if isinstance(description, str) else "",
    )


def _entry(raw: object, where: str, plugin_root: str) -> MarketplaceEntry:
    if not isinstance(raw, Mapping):
        raise PluginError(ERR_NOT_OBJECT.format(where=f"{where}: plugins[]"))
    name = check_name(raw.get("name"), f"{where}: plugins[]")
    return MarketplaceEntry(
        name=name,
        source=_source(raw.get("source"), where, name, plugin_root),
        description=str(raw.get("description") or ""),
        version=str(raw.get("version") or ""),
        category=str(raw.get("category") or ""),
    )


def _source(raw: object, where: str, name: str, plugin_root: str) -> MarketplaceSource:
    if isinstance(raw, str) and raw.strip():
        text = raw.strip()
        if not text.startswith((".", "/")) and plugin_root:
            text = f"{plugin_root}/{text}"
        return MarketplaceSource("path", safe_relative(text, where=where, key=f"{name}.source"))
    if isinstance(raw, Mapping):
        kind = str(raw.get("source") or "")
        ref = str(raw.get("ref") or "")
        sha = str(raw.get("sha") or "")
        if kind == "github" and isinstance(raw.get("repo"), str):
            return MarketplaceSource("git", f"https://github.com/{raw['repo']}", ref, sha)
        if kind in {"url", "git"} and isinstance(raw.get("url"), str):
            return MarketplaceSource("git", str(raw["url"]), ref, sha)
    raise PluginError(ERR_SOURCE.format(where=where, name=name))


def substitute_root(text: str, root: str) -> str:
    """`${CLAUDE_PLUGIN_ROOT}` / `${FUSION_PLUGIN_ROOT}` → eklenti klasörü."""
    for variable in ROOT_VARIABLES:
        text = text.replace(variable, root)
    return text
