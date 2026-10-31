"""Etkin eklentilerin beceri, komut ve ajanlarını kataloğa ekleme (P-059).

Claude Code'daki gibi her bileşen eklenti adıyla öneklenir: `skills/rapor/SKILL.md` →
`/eklenti:rapor`. Önek, üçüncü taraf bir eklentinin kullanıcının kendi becerisini aynı adla
GÖLGELEMESİNİ önler. Kaynak etiketi `eklenti`dir: `!`cmd`` bağlamı çalıştırılmaz ve beceri
dizininde depo içeriği gibi işaretlenir.

Gövdedeki `${CLAUDE_PLUGIN_ROOT}` / `${FUSION_PLUGIN_ROOT}` eklentinin kurulu klasörüne çözülür
(`with_plugin_root`). Ölçüldü (31 Ekim): değişken yalnız kanca ve MCP JSON'unda çözülüyordu;
`bash ${CLAUDE_PLUGIN_ROOT}/scripts/x.sh` diyen komut ve beceriler modele değişkeni ham veriyordu.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from ..config.plugin_store import active_plugins, plugin_root_of
from ..core.plugins import ROOT_VARIABLES, substitute_root
from .frontmatter import body_after_frontmatter

if TYPE_CHECKING:
    from .capabilities import Capability

#: Katalogdaki kaynak etiketi.
PLUGIN_SOURCE = "eklenti"
#: Açıklamasız komutta ilk satırdan alınacak en fazla karakter.
_SUMMARY_CHARS = 120

#: `capabilities._to_capability` imzası (döngüsel içe aktarmayı önlemek için çağırandan gelir).
Converter = Callable[..., "Capability"]


def with_plugin_root(text: str, path: Path) -> str:
    """Kurulu eklenti dosyasının metninde kök değişkenlerini çöz; eklenti dışında dokunma."""
    if not any(variable in text for variable in ROOT_VARIABLES):
        return text
    root = plugin_root_of(path)
    return substitute_root(text, str(root)) if root is not None else text


def _prefixed(capability: Capability, plugin: str, name: str = "") -> Capability:
    return replace(capability, name=f"{plugin}:{name or capability.name}")


def plugin_skills(convert: Converter) -> Iterator[Capability]:
    for item in active_plugins():
        if item.layout is None:
            continue
        for path in item.layout.skills:
            capability = convert(path, PLUGIN_SOURCE, fallback=path.parent.name)
            yield _prefixed(capability, item.record.name)


def plugin_commands(convert: Converter) -> Iterator[Capability]:
    for item in active_plugins():
        if item.layout is None:
            continue
        for name, path in item.layout.commands:
            capability = convert(path, PLUGIN_SOURCE, fallback=name)
            if not capability.description:
                capability = replace(capability, description=_first_line(path))
            yield replace(_prefixed(capability, item.record.name, name), kind="komut")


def plugin_agents(convert: Converter) -> Iterator[Capability]:
    for item in active_plugins():
        if item.layout is None:
            continue
        for path in item.layout.agents:
            capability = convert(path, PLUGIN_SOURCE, fallback=path.stem)
            yield _prefixed(capability, item.record.name)


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
