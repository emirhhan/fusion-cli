"""Etkin eklentilerin beceri, komut ve ajanlarını kataloğa ekleme (P-059).

Claude Code'daki gibi her bileşen eklenti adıyla öneklenir: `skills/rapor/SKILL.md` →
`/eklenti:rapor`. Önek, üçüncü taraf bir eklentinin kullanıcının kendi becerisini aynı adla
GÖLGELEMESİNİ önler. Kaynak etiketi `eklenti`dir: `!`cmd`` bağlamı kullanıcı becerisi gibi koşar
(#386) ve beceri dizininde depo içeriği gibi işaretlenir.

Gövdedeki `${CLAUDE_PLUGIN_ROOT}` / `${FUSION_PLUGIN_ROOT}` eklentinin kurulu klasörüne çözülür
(`with_plugin_root`). Ölçüldü (31 Ekim): değişken yalnız kanca ve MCP JSON'unda çözülüyordu;
`bash ${CLAUDE_PLUGIN_ROOT}/scripts/x.sh` diyen komut ve beceriler modele değişkeni ham veriyordu.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from ..config.claude_plugins import claude_plugin_layouts
from ..config.plugin_data import plugin_data_dir
from ..config.plugin_store import active_plugins, plugin_root_of, plugins_dir
from ..core.hooks.events import HookSet
from ..core.plugins import (
    DATA_VARIABLE,
    PROJECT_VARIABLE,
    ROOT_VARIABLES,
    PluginError,
    substitute_root,
)
from .frontmatter import body_after_frontmatter

if TYPE_CHECKING:
    from ..config.plugin_scan import PluginLayout
    from .capabilities import Capability

_LOG = logging.getLogger(__name__)
#: Satır içi (`content`) komut gövdelerinin tutulduğu klasör (nokta: eklenti adı olamaz).
INLINE_DIRNAME = ".satir-ici"
#: Katalogdaki kaynak etiketi.
PLUGIN_SOURCE = "eklenti"
#: Açıklamasız komutta ilk satırdan alınacak en fazla karakter.
_SUMMARY_CHARS = 120

#: `capabilities._to_capability` imzası (döngüsel içe aktarmayı önlemek için çağırandan gelir).
Converter = Callable[..., "Capability"]


def _storage_key(root: Path, name: str = "") -> str:
    """Veri/ayar anahtarı: kurulu kaydın `ad@pazar` kimliği; kayıtsızsa bildirim adı (#391)."""
    from ..config.plugin_scan import read_manifest
    from ..config.plugin_storage import storage_key_for_root

    if not name:
        try:
            name = read_manifest(root)[0].name
        except PluginError:
            name = root.name
    return storage_key_for_root(root, name)


def with_plugin_root(text: str, path: Path, project: Path | None = None) -> str:
    """Kurulu eklenti dosyasının gövdesinde `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}`
    ve `${CLAUDE_PROJECT_DIR}`'ı çöz (#387); eklenti dışındaki dosyaya dokunma."""
    variables = (*ROOT_VARIABLES, DATA_VARIABLE, PROJECT_VARIABLE, "${user_config.")
    if not any(variable in text for variable in variables):
        return text
    folder = project or Path.cwd()
    root = plugin_root_of(path, project=folder)
    if root is None:
        return text
    data = str(plugin_data_dir(_storage_key(root), create=True)) if DATA_VARIABLE in text else ""
    text = substitute_root(text, str(root), data, str(folder))
    return _with_user_config(text, root)


def is_repository_plugin_file(path: Path, project: Path) -> bool:
    """Dosya depodan gelen bir eklentinin mi? (#386)

    Projede (`.claude/settings.json`) açılan ya da kaynağı proje klasöründe yerinde duran
    eklentinin içeriği depoyla değişir: proje becerisi gibi yalnız salt-okur `!`komut`` koşar.
    """
    from ..config.plugin_project_mcp import is_project_scope
    from ..config.plugin_store import load_state

    state = load_state()
    for item in active_plugins(root=project):
        if item.layout is None or item.record.kind == "inline":
            continue
        if not _within(path, item.layout.root):
            continue
        return is_project_scope(item, state, project) or _within(item.layout.root, project)
    return False


def _within(path: Path, folder: Path) -> bool:
    try:
        return path.resolve().is_relative_to(folder.resolve())
    except OSError:
        return False


def _with_user_config(text: str, root: Path) -> str:
    """`${user_config.KEY}` (#388): içerikte yalnız hassas olmayan değer; hassas yer tutucu."""
    if "${user_config." not in text:
        return text
    from ..config import plugin_user_config as user_config
    from ..config.plugin_scan import read_manifest

    try:
        name = read_manifest(root)[0].name
        schema = user_config.read_schema(root)
    except PluginError:
        return text
    values = user_config.effective_values(_storage_key(root, name), schema, plugins_dir())
    return user_config.substitute(text, schema, values, content=True)


def _prefixed(capability: Capability, plugin: str, name: str = "") -> Capability:
    return replace(capability, name=f"{plugin}:{name or capability.name}")


def _layouts(home: Path | None, root: Path | None = None) -> Iterator[tuple[str, PluginLayout]]:
    """`(önek, düzen)`: Fusion'ın etkin eklentileri, sonra Claude Code'un etkin kurulumları.

    `root`: kataloğun proje kökü (project/local `enabledPlugins`); verilmezse süreç cwd'si.
    """
    seen: set[str] = set()
    for item in active_plugins(root=root):
        if item.layout is not None:
            seen.add(item.record.name)
            yield item.record.name, item.layout
    if home is None:
        return
    for _plugin_id, layout in claude_plugin_layouts(home):
        if layout.name not in seen:
            seen.add(layout.name)
            yield layout.name, layout


def plugin_skills(
    convert: Converter, home: Path | None = None, root: Path | None = None
) -> Iterator[Capability]:
    for prefix, layout in _layouts(home, root):
        for path in layout.skills:
            capability = convert(path, PLUGIN_SOURCE, fallback=path.parent.name)
            yield _prefixed(capability, prefix)


def plugin_commands(
    convert: Converter, home: Path | None = None, root: Path | None = None
) -> Iterator[Capability]:
    for prefix, layout in _layouts(home, root):
        meta = {name: (text, hint) for name, text, hint in layout.command_meta}
        found = [*layout.commands, *_inline_command_files(layout)]
        for name, path in found:
            capability = convert(path, PLUGIN_SOURCE, fallback=name)
            text, hint = meta.get(name, ("", ""))
            capability = replace(
                capability,
                description=text or capability.description or _first_line(path),
                argument_hint=hint or capability.argument_hint,
            )
            yield replace(_prefixed(capability, prefix, name), kind="komut")


def _inline_command_files(layout: PluginLayout) -> list[tuple[str, Path]]:
    """`commands` haritasındaki `content` gövdeleri (#385): eklenti klasörüne yazılmaz
    (içerik karması bozulmasın); `<veri>/eklentiler/.satir-ici/<eklenti>/` altında tutulur."""
    folder = plugins_dir() / INLINE_DIRNAME / layout.name
    found: list[tuple[str, Path]] = []
    for name, body, description, hint in layout.inline_commands:
        head = {"description": description, "argument-hint": hint}
        lines = [f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in head.items()]
        text = "---\n" + "\n".join(lines) + "\n---\n" + body + "\n"
        path = folder / f"{name}.md"
        try:
            if not path.is_file() or path.read_text(encoding="utf-8") != text:
                folder.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
        except OSError as error:
            _LOG.warning("eklenti '%s' komutu '%s' yazılamadı: %s", layout.name, name, error)
            continue
        found.append((name, path))
    return found


def plugin_agents(
    convert: Converter, home: Path | None = None, root: Path | None = None
) -> Iterator[Capability]:
    for prefix, layout in _layouts(home, root):
        for path in layout.agents:
            capability = _without_ignored_fields(convert(path, PLUGIN_SOURCE, fallback=path.stem))
            name = _agent_scoped_name(layout, path, capability.name)
            yield _prefixed(capability, prefix, name)


def _without_ignored_fields(capability: Capability) -> Capability:
    """Claude (components.md "Frontmatter fields in plugin agents"): eklenti ajanlarında
    `permissionMode`, `hooks`, `mcpServers` ve `initialPrompt` yok sayılır (#405)."""
    return replace(
        capability,
        permission_mode="",
        hooks=(),
        hook_definitions=HookSet(),
        mcp_servers=(),
        inline_mcp_servers=(),
        initial_prompt="",
    )


def _agent_scoped_name(layout: PluginLayout, path: Path, name: str) -> str:
    """Ajan kökü altındaki dizinleri `eklenti:inceleme:ajan` kimliğine kat."""
    for relative in layout.manifest.agents:
        base = layout.root / relative
        if path.is_relative_to(base):
            folders = path.relative_to(base).parts[:-1]
            return ":".join((*folders, name))
    return name


def plugin_output_style_dirs() -> tuple[tuple[str, Path], ...]:
    """`(eklenti adı, stil dosyası)` çiftleri."""
    return tuple(
        (item.record.name, path)
        for item in active_plugins()
        if item.layout is not None
        for path in item.layout.output_styles
    )


def _first_line(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    for line in body_after_frontmatter(text).splitlines():
        cleaned = line.strip().lstrip("#").strip()
        if cleaned:
            return cleaned[:_SUMMARY_CHARS]
    return ""
