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

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .errors import FusionError
from .plugin_paths import (
    PluginPathError,
    check_plugin_name,
    command_map,
    mixed_component,
    path_list,
)
from .plugin_paths import safe_relative as _safe_relative

_LOG = logging.getLogger(__name__)

#: Bildirim dosyası adayları (ilk bulunan okunur). `.fusion-plugin/` Fusion'ın eski adıdır:
#: bir sürüm boyunca kullanımdan kalkmış takma ad olarak okunur ve uyarı verir (#413).
MANIFEST_PATHS: tuple[str, ...] = (".claude-plugin/plugin.json", ".fusion-plugin/plugin.json")
MARKETPLACE_PATHS: tuple[str, ...] = (
    ".claude-plugin/marketplace.json",
    ".fusion-plugin/marketplace.json",
)
LEGACY_MANIFEST_DIR = ".fusion-plugin"
#: Varsayılan bileşen yerleri (eklenti köküne göreli).
DEFAULT_COMMANDS = "commands"
DEFAULT_AGENTS = "agents"
DEFAULT_SKILLS = "skills"
DEFAULT_OUTPUT_STYLES = "output-styles"
DEFAULT_HOOKS = "hooks/hooks.json"
DEFAULT_MCP = ".mcp.json"
#: Eklenti kökü değişkeni. `${FUSION_PLUGIN_ROOT}` eski Fusion adıdır (takma ad, uyarılı).
ROOT_VARIABLES: tuple[str, ...] = ("${CLAUDE_PLUGIN_ROOT}", "${FUSION_PLUGIN_ROOT}")
DATA_VARIABLE = "${CLAUDE_PLUGIN_DATA}"
PROJECT_VARIABLE = "${CLAUDE_PROJECT_DIR}"
#: Eski kayıt ve klasör adları için güvenli ad kalıbı (yol bileşeni olarak kullanılır).
NAME_PATTERN = re.compile(r"^(?!\.\.?$)[^\s@:/\\\x00-\x1f\x7f]{1,128}$")
#: Claude Code'un tanıdığı üst düzey `plugin.json` alanları (plugins-reference "Fields").
KNOWN_FIELDS = frozenset(
    {
        "$schema", "name", "displayName", "version", "description", "author", "homepage",
        "repository", "license", "keywords", "metadata", "icon", "documentationUrl",
        "supportUrl", "privacyPolicyUrl", "termsOfServiceUrl", "defaultEnabled",
        "dependencies", "settings", "userConfig", "types", "channels", "skills", "commands",
        "agents", "hooks", "mcpServers", "lspServers", "outputStyles", "workflows",
        "experimental", "themes", "monitors",
    }
)  # fmt: skip
#: Fusion'ın eski `output-styles` anahtarı (takma ad, uyarılı).
LEGACY_STYLES_KEY = "output-styles"

ERR_NOT_OBJECT = "{where}: JSON nesnesi bekleniyordu"
ERR_TEXT = "{where}: '{key}' metin olmalı"
WARN_UNKNOWN = "plugin.json: tanınmayan alan(lar) yok sayıldı: {names}"
WARN_LEGACY = "{old} kullanımdan kalktı; Claude Code adı {new}"


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
    #: Satır içi `hooks`/`mcpServers` nesnelerinin JSON listesi (boş = yok).
    inline_hooks: str = ""
    inline_mcp: str = ""
    warnings: tuple[str, ...] = ()
    #: `commands` nesne haritası (JSON listesi; bkz. `plugin_paths.command_map`).
    inline_commands: str = ""
    #: Varsayılan klasörün YERİNE geçen, bildirimde ayarlanmış anahtarlar (#384).
    replaced_defaults: tuple[str, ...] = ()
    #: `skills` anahtarı bildirimde var mı? (Kökteki tek SKILL.md kuralı için, #385.)
    sets_skills: bool = False
    display_name: str = ""
    default_enabled: bool = True
    dependencies: tuple[str, ...] = ()
    #: `{name, version}` bağımlılıklarının npm semver aralığı: (`ad[@pazar]`, aralık) (#389).
    dependency_versions: tuple[tuple[str, str], ...] = ()


def check_name(value: object, where: str) -> str:
    try:
        return check_plugin_name(value, where)
    except PluginPathError as error:
        raise PluginError(str(error)) from error


def safe_relative(value: str, *, where: str, key: str) -> str:
    """`./x/y` → `x/y`, `.`/`./` → `.`; mutlak yol ya da `..` reddedilir."""
    try:
        return _safe_relative(value, where=where, key=key)
    except PluginPathError as error:
        raise PluginError(str(error)) from error


def _text(raw: Mapping[str, object], key: str, where: str) -> str:
    value = raw.get(key, "")
    if isinstance(value, Mapping):
        # `author: {name, email}` ve `repository: {type, url}` (npm biçimi) de kabul edilir.
        value = value.get("name" if key == "author" else "url", "")
    if not isinstance(value, str):
        raise PluginError(ERR_TEXT.format(where=where, key=key))
    return value.strip()


def parse_manifest(
    raw: object, *, fallback_name: str = "", where: str = "plugin.json"
) -> PluginManifest:
    """`plugin.json` içeriğini doğrula. Bildirim yoksa (`raw` None) ad klasörden gelir."""
    if raw is None:
        return PluginManifest(name=check_name(fallback_name, where))
    if not isinstance(raw, Mapping):
        raise PluginError(ERR_NOT_OBJECT.format(where=where))
    try:
        return _parse_manifest(raw, fallback_name, where)
    except PluginPathError as error:
        raise PluginError(str(error)) from error


def _parse_manifest(raw: Mapping[str, object], fallback_name: str, where: str) -> PluginManifest:
    keywords = raw.get("keywords", [])
    warnings = [WARN_UNKNOWN.format(names=", ".join(sorted(set(raw) - KNOWN_FIELDS)))]
    if set(raw) <= KNOWN_FIELDS:
        warnings.clear()
    styles_key = "outputStyles"
    if styles_key not in raw and LEGACY_STYLES_KEY in raw:
        styles_key = LEGACY_STYLES_KEY
        warnings.append(WARN_LEGACY.format(old=f"'{LEGACY_STYLES_KEY}'", new="'outputStyles'"))
    commands_raw = raw.get("commands")
    inline_commands = ""
    if isinstance(commands_raw, Mapping):
        inline_commands = command_map(commands_raw, where=where)
        commands: tuple[str, ...] | None = ()
    else:
        commands = path_list(commands_raw, key="commands", where=where)
    agents = path_list(raw.get("agents"), key="agents", where=where)
    styles = path_list(raw.get(styles_key), key="outputStyles", where=where)
    skills = path_list(raw.get("skills"), key="skills", where=where, allow_root=True)
    hooks, inline_hooks = mixed_component(raw.get("hooks"), key="hooks", where=where)
    mcp, inline_mcp = mixed_component(raw.get("mcpServers"), key="mcpServers", where=where)
    replaced = tuple(
        key
        for key, value in (("commands", commands), ("agents", agents), ("outputStyles", styles))
        if value is not None
    )
    return PluginManifest(
        name=check_name(raw.get("name", fallback_name), where),
        version=_text(raw, "version", where),
        description=_text(raw, "description", where),
        author=_text(raw, "author", where),
        homepage=_text(raw, "homepage", where),
        repository=_text(raw, "repository", where),
        license=_text(raw, "license", where),
        keywords=tuple(str(k) for k in keywords) if isinstance(keywords, list) else (),
        commands=(DEFAULT_COMMANDS,) if commands is None else commands,
        agents=(DEFAULT_AGENTS,) if agents is None else agents,
        skills=tuple(dict.fromkeys((DEFAULT_SKILLS, *(skills or ())))),
        output_styles=(DEFAULT_OUTPUT_STYLES,) if styles is None else styles,
        hooks=tuple(dict.fromkeys((DEFAULT_HOOKS, *hooks))),
        mcp_servers=tuple(dict.fromkeys((DEFAULT_MCP, *mcp))),
        inline_hooks=inline_hooks,
        inline_mcp=inline_mcp,
        warnings=tuple(warnings),
        inline_commands=inline_commands,
        replaced_defaults=replaced,
        sets_skills=skills is not None,
        display_name=_text(raw, "displayName", where),
        default_enabled=raw.get("defaultEnabled") is not False,
        dependencies=_dependencies(raw.get("dependencies")),
        dependency_versions=_dependency_versions(raw.get("dependencies")),
    )


def _dependencies(raw: object) -> tuple[str, ...]:
    """`"ad"`, `"ad@pazar"` ya da `{name, marketplace}` → `ad[@pazar]` metinleri."""
    found: list[str] = []
    for item in raw if isinstance(raw, list) else ():
        if isinstance(item, str) and item.strip():
            found.append(item.strip())
        elif isinstance(item, Mapping) and isinstance(item.get("name"), str):
            market = item.get("marketplace")
            found.append(f"{item['name']}@{market}" if isinstance(market, str) else item["name"])
    return tuple(found)


def _dependency_versions(raw: object) -> tuple[tuple[str, str], ...]:
    """`{name, marketplace?, version}` → (`ad[@pazar]`, aralık); sürümsüz girdiler atlanır."""
    found: list[tuple[str, str]] = []
    for item in raw if isinstance(raw, list) else ():
        if not isinstance(item, Mapping) or not isinstance(item.get("name"), str):
            continue
        version = item.get("version")
        if not isinstance(version, str) or not version.strip():
            continue
        market = item.get("marketplace")
        ident = f"{item['name']}@{market}" if isinstance(market, str) else item["name"]
        found.append((ident, version.strip()))
    return tuple(found)


_LEGACY_WARNED: set[str] = set()


def substitute_root(text: str, root: str, data: str = "", project: str = "") -> str:
    """`${CLAUDE_PLUGIN_ROOT}` (ve eski `${FUSION_PLUGIN_ROOT}`), `${CLAUDE_PLUGIN_DATA}`,
    `${CLAUDE_PROJECT_DIR}` → klasörler. Boş verilen değişkene dokunulmaz."""
    if ROOT_VARIABLES[1] in text and ROOT_VARIABLES[1] not in _LEGACY_WARNED:
        _LEGACY_WARNED.add(ROOT_VARIABLES[1])
        _LOG.warning(WARN_LEGACY.format(old=ROOT_VARIABLES[1], new=ROOT_VARIABLES[0]))
    for variable in ROOT_VARIABLES:
        text = text.replace(variable, root)
    if data:
        text = text.replace(DATA_VARIABLE, data)
    if project:
        text = text.replace(PROJECT_VARIABLE, project)
    return text


#: `plugin_marketplace` bu modüle (PluginError, safe_relative) bağlıdır; adları tembel yeniden
#: dışa aktarılır. Modül başında içe aktarmak, pazar modülü ilk içe aktarılan olunca döngü verirdi.
_MARKETPLACE_NAMES = frozenset({"Marketplace", "MarketplaceEntry", "MarketplaceSource"})
_MARKETPLACE_NAMES |= {"parse_marketplace"}

if TYPE_CHECKING:
    from .plugin_marketplace import (
        Marketplace,
        MarketplaceEntry,
        MarketplaceSource,
        parse_marketplace,
    )


def __getattr__(name: str) -> object:
    if name in _MARKETPLACE_NAMES:
        from . import plugin_marketplace

        return getattr(plugin_marketplace, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Marketplace",
    "MarketplaceEntry",
    "MarketplaceSource",
    "PluginError",
    "PluginManifest",
    "check_name",
    "parse_manifest",
    "parse_marketplace",
    "safe_relative",
    "substitute_root",
]
