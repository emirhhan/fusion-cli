"""Eklenti klasörünü bileşenlerine ayırma — Claude Code plugins-reference yol kuralları.

- `commands`, `agents`, `outputStyles` bildirimde ayarlanırsa varsayılan klasör TARANMAZ;
  klasör varsa "Varsayılan <klasör>/ yok sayıldı" uyarısı çıkar (#384).
- `commands` ve `outputStyles` dosya ya da klasör alır; `agents` yalnız `.md` dosyası alır;
  `commands` nesne haritası `source`/`content` taşır (#385, #402).
- `skills/` yoksa, `skills` anahtarı da yoksa kökteki `SKILL.md` tek beceri olarak yüklenir.
- Var olmayan bileşen yolu yüklenmez ve "yol bulunamadı" sorunu olarak raporlanır.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from ..core.plugins import (
    DEFAULT_AGENTS,
    DEFAULT_COMMANDS,
    DEFAULT_OUTPUT_STYLES,
    DEFAULT_SKILLS,
    LEGACY_MANIFEST_DIR,
    MANIFEST_PATHS,
    WARN_LEGACY,
    PluginError,
    PluginManifest,
    parse_manifest,
)

WARN_DEFAULT_IGNORED = (
    'Varsayılan {folder}/ klasörü yok sayıldı: bildirim "{key}" alanını ayarlıyor'
)
ERR_PATH_MISSING = "{key} yolu bulunamadı: ./{path}"
#: Claude Code'da olan ama Fusion'ın yüklemediği bileşenler açıkça raporlanır (#416).
WARN_WORKFLOWS = "workflows/ (Claude iş akışları) Fusion'da desteklenmiyor; yüklenmez"
WARN_MODS = "hooks.json 'modules' (Claude mod'ları) Fusion'da desteklenmiyor; yüklenmez"
ERR_AGENT_DIR = "agents girdisi .md dosyası olmalı (klasör kabul edilmez): ./{path}"
_DEFAULTS = {
    "commands": DEFAULT_COMMANDS,
    "agents": DEFAULT_AGENTS,
    "outputStyles": DEFAULT_OUTPUT_STYLES,
}


@dataclass(frozen=True, slots=True)
class PluginLayout:
    """Diskteki bir eklentinin bileşenleri."""

    root: Path
    manifest: PluginManifest
    has_manifest: bool
    skills: tuple[Path, ...] = ()
    #: `(komut adı, dosya)`; ad alt klasörlerle `a:b` biçimindedir (önek hariç).
    commands: tuple[tuple[str, Path], ...] = ()
    agents: tuple[Path, ...] = ()
    output_styles: tuple[Path, ...] = ()
    hook_files: tuple[Path, ...] = ()
    mcp_files: tuple[Path, ...] = ()
    #: `commands` haritasındaki `content` komutları: `(ad, gövde, açıklama, argumentHint)`.
    inline_commands: tuple[tuple[str, str, str, str], ...] = ()
    #: `source` komutlarının haritadaki açıklaması: `(ad, açıklama, argumentHint)`.
    command_meta: tuple[tuple[str, str, str], ...] = ()
    #: Yüklenemeyen bileşen yolları (Claude'un /plugin Errors sekmesindeki satırlar).
    problems: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def has_hooks(self) -> bool:
        return bool(self.hook_files or self.manifest.inline_hooks)

    @property
    def has_mcp(self) -> bool:
        return bool(self.mcp_files or self.manifest.inline_mcp)

    @property
    def is_executable(self) -> bool:
        """Kanca ya da MCP: Fusion'ın dışında süreç başlatır → kurulumda açık onay ister."""
        return self.has_hooks or self.has_mcp


def read_manifest(root: Path, fallback_name: str = "") -> tuple[PluginManifest, bool]:
    """Bildirim ve var olup olmadığı. Bozuk bildirim `PluginError`."""
    fallback = fallback_name or root.name
    for relative in MANIFEST_PATHS:
        path = root / relative
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                raise PluginError(f"{relative}: okunamadı: {error}") from error
            manifest = parse_manifest(raw, fallback_name=fallback, where=relative)
            if relative.startswith(LEGACY_MANIFEST_DIR):
                note = WARN_LEGACY.format(old=relative, new=MANIFEST_PATHS[0])
                manifest = replace(manifest, warnings=(*manifest.warnings, note))
            return manifest, True
    return parse_manifest(None, fallback_name=fallback), False


def scan_plugin(root: Path, fallback_name: str = "") -> PluginLayout:
    manifest, has_manifest = read_manifest(root, fallback_name)
    problems: list[str] = []
    notes = [
        WARN_DEFAULT_IGNORED.format(folder=_DEFAULTS[key], key=key)
        for key in manifest.replaced_defaults
        if (root / _DEFAULTS[key]).is_dir() and not _uses_default(manifest, key)
    ]
    notes.extend(_unsupported(root))
    commands = _commands(root, manifest, problems)
    inline, meta = _command_map(root, manifest, problems)
    return PluginLayout(
        root,
        manifest,
        has_manifest,
        _skills(root, manifest),
        (*commands, *((n, p) for n, p in _map_sources(root, manifest))),
        _agents(root, manifest, problems),
        _styles(root, manifest, problems),
        tuple(
            p for p in (root / rel for rel in manifest.hooks) if p.is_file() and _inside(p, root)
        ),
        tuple(
            p
            for p in (root / rel for rel in manifest.mcp_servers)
            if p.is_file() and _inside(p, root)
        ),
        inline,
        meta,
        tuple(problems),
        tuple(notes),
    )


def _unsupported(root: Path) -> list[str]:
    found = [WARN_WORKFLOWS] if (root / "workflows").is_dir() else []
    try:
        hooks = json.loads((root / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return found
    if isinstance(hooks, dict) and "modules" in hooks:
        found.append(WARN_MODS)
    return found


def _uses_default(manifest: PluginManifest, key: str) -> bool:
    paths = {"commands": manifest.commands, "agents": manifest.agents}.get(
        key, manifest.output_styles
    )
    folder = _DEFAULTS[key]
    return any(p == folder or p.startswith(f"{folder}/") for p in paths)


def _missing(root: Path, relative: str, key: str, problems: list[str], default: str) -> bool:
    path = root / relative
    if path.exists() and _inside(path, root):
        return False
    if relative != default:
        problems.append(ERR_PATH_MISSING.format(key=key, path=relative))
    return True


def _skills(root: Path, manifest: PluginManifest) -> tuple[Path, ...]:
    if not manifest.sets_skills and not (root / DEFAULT_SKILLS).is_dir():
        single = root / "SKILL.md"
        return (single,) if single.is_file() else ()
    found: list[Path] = []
    for relative in manifest.skills:
        base = root / relative
        if not base.is_dir() or not _inside(base, root):
            continue
        if relative == "." and (base / "SKILL.md").is_file():
            found.append(base / "SKILL.md")
            continue
        found.extend(p for p in sorted(base.rglob("SKILL.md")) if _inside(p, root))
    return tuple(dict.fromkeys(found))


def _commands(root: Path, manifest: PluginManifest, problems: list[str]) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    for relative in manifest.commands:
        if _missing(root, relative, "commands", problems, DEFAULT_COMMANDS):
            continue
        base = root / relative
        if base.is_file():
            found.append((base.stem, base))
            continue
        found.extend(
            (":".join(path.relative_to(base).with_suffix("").parts), path)
            for path in sorted(base.rglob("*.md"))
            if _inside(path, root)
        )
    return found


def _map_entries(manifest: PluginManifest) -> list[dict[str, object]]:
    raw = json.loads(manifest.inline_commands) if manifest.inline_commands else []
    return [item for item in raw if isinstance(item, dict)]


def _map_sources(root: Path, manifest: PluginManifest) -> list[tuple[str, Path]]:
    return [
        (str(item["name"]), root / str(item["source"]))
        for item in _map_entries(manifest)
        if "source" in item and (root / str(item["source"])).is_file()
    ]


def _command_map(
    root: Path, manifest: PluginManifest, problems: list[str]
) -> tuple[tuple[tuple[str, str, str, str], ...], tuple[tuple[str, str, str], ...]]:
    inline: list[tuple[str, str, str, str]] = []
    meta: list[tuple[str, str, str]] = []
    for item in _map_entries(manifest):
        name = str(item["name"])
        description = str(item.get("description") or "")
        hint = str(item.get("argumentHint") or "")
        if "content" in item:
            inline.append((name, str(item["content"]), description, hint))
            continue
        _missing(root, str(item["source"]), "commands", problems, "")
        meta.append((name, description, hint))
    return tuple(inline), tuple(meta)


def _agents(root: Path, manifest: PluginManifest, problems: list[str]) -> tuple[Path, ...]:
    found: list[Path] = []
    for relative in manifest.agents:
        if _missing(root, relative, "agents", problems, DEFAULT_AGENTS):
            continue
        path = root / relative
        if relative == DEFAULT_AGENTS and path.is_dir():
            found.extend(p for p in sorted(path.rglob("*.md")) if _inside(p, root))
        elif path.is_file() and path.suffix == ".md":
            found.append(path)
        else:
            problems.append(ERR_AGENT_DIR.format(path=relative))
    return tuple(found)


def _styles(root: Path, manifest: PluginManifest, problems: list[str]) -> tuple[Path, ...]:
    found: list[Path] = []
    for relative in manifest.output_styles:
        if _missing(root, relative, "outputStyles", problems, DEFAULT_OUTPUT_STYLES):
            continue
        path = root / relative
        if path.is_file():
            found.append(path)
        else:
            found.extend(p for p in sorted(path.glob("*.md")) if _inside(p, root))
    return tuple(found)


def _inside(path: Path, root: Path) -> bool:
    """Sembolik bağ eklenti kökü dışına (`~/.ssh`) çıkmıyor mu?"""
    try:
        return path.resolve().is_relative_to(root.resolve())
    except OSError:
        return False
