"""`/sandbox` paneli: Kip / Geçersiz kılmalar / Yapılandırma sekmeleri, Linux'ta Bağımlılıklar
(Claude, #352).

Claude Code (sandboxing › Enabling; commands › /sandbox): argümansız `/sandbox` sekmeli bir panel
açar — Mode (auto-allow ya da regular permissions), Overrides (`allowUnsandboxedCommands`;
kapalıyken "Strict sandbox mode"), Config (etkin ayarlar). Dependencies sekmesi yalnız Linux'ta
ve bir araç eksikken görünür; zorunlu araç (bwrap, socat) eksikse yalnız o sekme gösterilir.
Kip ve geçersiz kılma seçimi projenin `.claude/settings.local.json`'ına yazılır.

Seçici (REPL `pick`, TUI modalı) bir sekmeyi gösterir; başlıkta sekme çubuğu vardır, ←/→ ya da
Tab sekme değiştirir (düz listede "Sekme ›" satırları). Argümanlı metin alt komutları
(`/sandbox on`, `/sandbox izin x.com`…) betiklenebilir yol olarak kalır. rg Fusion'da isteğe
bağlıdır (yoksa yalnız kök düzeyi korunur), Claude'daki seccomp süzgeci gibi yan sekmede çıkar.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from ...config.models import Config
from ...config.sandbox_admin import SandboxStatus, apply_sandbox_action, sandbox_status
from ...core.errors import ConfigError
from ...ui.picker import Choice
from ..sandbox_view import format_change, format_status
from .model_flows import FlowResult, Picker

__all__ = ["dependency_report", "missing_tools", "panel_choices", "sandbox_panel", "visible_tabs"]

MODE_AUTO = "kip:oto"
MODE_REGULAR = "kip:normal"
MODE_OFF = "kip:kapali"
OVERRIDE_ALLOW = "gecersiz:izin"
OVERRIDE_STRICT = "gecersiz:kati"
SHOW_CONFIG = "yapilandirma"
SHOW_DEPENDENCIES = "bagimliliklar"
TAB_MODE, TAB_OVERRIDES, TAB_CONFIG, TAB_DEPS = "kip", "gecersiz", "yapilandirma", "bagimlilik"
TAB_LABELS = {
    TAB_MODE: "Kip",
    TAB_OVERRIDES: "Geçersiz kılmalar",
    TAB_CONFIG: "Yapılandırma",
    TAB_DEPS: "Bağımlılıklar",
}
_TAB_PREFIX = "sekme:"
_NEXT, _PREV = f"{_TAB_PREFIX}+", f"{_TAB_PREFIX}-"
HOTKEYS = {"right": _NEXT, "tab": _NEXT, "left": _PREV}
#: Sekme değiştirme sınırı (döngü güvencesi).
_MAX_SWITCHES = 24
_REQUIRED_LINUX = ("bwrap", "socat")
_OPTIONAL_LINUX = ("rg",)


def _mark(active: bool) -> str:
    return "● " if active else "  "


def missing_tools(platform: str | None = None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(eksik zorunlu, eksik isteğe bağlı) araçlar; Linux dışında ikisi de boş."""
    if not (platform or sys.platform).startswith("linux"):
        return (), ()
    required = tuple(tool for tool in _REQUIRED_LINUX if shutil.which(tool) is None)
    optional = tuple(tool for tool in _OPTIONAL_LINUX if shutil.which(tool) is None)
    return required, optional


def visible_tabs(platform: str | None = None) -> tuple[str, ...]:
    """Claude: Linux'ta zorunlu araç eksikse yalnız Bağımlılıklar; eksik varsa ek sekme."""
    required, optional = missing_tools(platform)
    if required:
        return (TAB_DEPS,)
    base = (TAB_MODE, TAB_OVERRIDES, TAB_CONFIG)
    return (*base, TAB_DEPS) if optional else base


def _tab_options(tab: str, status: SandboxStatus, platform: str | None) -> list[Choice]:
    auto = status.enabled and status.auto_allow
    regular = status.enabled and not status.auto_allow
    if tab == TAB_MODE:
        return [
            Choice(MODE_AUTO, f"{_mark(auto)}Sandbox, otomatik izinle", "auto-allow"),
            Choice(MODE_REGULAR, f"{_mark(regular)}Sandbox, normal izinlerle", "regular"),
            Choice(MODE_OFF, f"{_mark(not status.enabled)}Sandbox kapalı", ""),
        ]
    if tab == TAB_OVERRIDES:
        return [
            Choice(
                OVERRIDE_ALLOW,
                f"{_mark(status.allow_unsandboxed)}Sandbox dışı yeniden denemeye izin",
                "allowUnsandboxedCommands: true",
            ),
            Choice(
                OVERRIDE_STRICT,
                f"{_mark(not status.allow_unsandboxed)}Katı sandbox kipi",
                "Strict sandbox mode: dangerouslyDisableSandbox yok sayılır",
            ),
        ]
    if tab == TAB_CONFIG:
        lines = [line for line in format_status(status).splitlines() if line.strip()]
        return [Choice(SHOW_CONFIG, line, "") for line in lines]
    report = dependency_report(platform).splitlines()
    return [Choice(SHOW_DEPENDENCIES, line, "") for line in report]


def panel_choices(
    status: SandboxStatus, tab: str = TAB_MODE, *, platform: str | None = None
) -> list[Choice]:
    """Etkin sekmenin satırları (etkin seçim ●) ve diğer sekmelere geçiş satırları."""
    tabs = visible_tabs(platform)
    current = tab if tab in tabs else tabs[0]
    switches = [
        Choice(f"{_TAB_PREFIX}{name}", f"Sekme › {TAB_LABELS[name]}", "←/→ ya da Tab")
        for name in tabs
        if name != current
    ]
    return [*_tab_options(current, status, platform), *switches]


def panel_title(tab: str, platform: str | None = None) -> str:
    """Sekme çubuğu: etkin sekme köşeli parantezde."""
    bar = "  ".join(
        f"[{TAB_LABELS[name]}]" if name == tab else TAB_LABELS[name]
        for name in visible_tabs(platform)
    )
    return f"Sandbox   {bar}"


def _switch(selected: str, tab: str, tabs: tuple[str, ...]) -> str:
    index = tabs.index(tab) if tab in tabs else 0
    if selected == _NEXT:
        return tabs[(index + 1) % len(tabs)]
    if selected == _PREV:
        return tabs[(index - 1) % len(tabs)]
    target = selected.removeprefix(_TAB_PREFIX)
    return target if target in tabs else tab


def dependency_report(platform: str | None = None) -> str:
    """Sandbox araçlarının bu makinedeki durumu (Linux: bwrap, socat; macOS: sandbox-exec)."""
    name = platform or sys.platform
    tools = ("bwrap", "socat", "rg") if name.startswith("linux") else ("sandbox-exec",)
    lines = [f"Bağımlılıklar ({name}):"]
    for tool in tools:
        found = shutil.which(tool)
        lines.append(f"  {'✓' if found else '✗'} {tool}" + (f" ({found})" if found else " yok"))
    return "\n".join(lines)


def _actions(selected: str) -> tuple[tuple[str, str], ...]:
    return {
        MODE_AUTO: (("ac", ""), ("oto", "on")),
        MODE_REGULAR: (("ac", ""), ("oto", "off")),
        MODE_OFF: (("kapat", ""),),
        OVERRIDE_ALLOW: (("disari", "on"),),
        OVERRIDE_STRICT: (("disari", "off"),),
    }.get(selected, ())


def _choose(status: SandboxStatus, picker: Picker, platform: str | None) -> str | None:
    """Sekmeler arasında gez; sekme dışı bir seçim (ya da vazgeçme) dönene kadar."""
    tabs = visible_tabs(platform)
    tab = tabs[0]
    for _ in range(_MAX_SWITCHES):
        selected = picker(
            panel_choices(status, tab, platform=platform),
            title=panel_title(tab, platform),
            hotkeys=HOTKEYS,
        )
        if selected is None or not selected.startswith(_TAB_PREFIX):
            return selected
        tab = _switch(selected, tab, tabs)
    return None


def sandbox_panel(
    config: Config, root: Path, *, picker: Picker, platform: str | None = None
) -> FlowResult:
    """Paneli göster; seçimi uygula (yerel ayar dosyasına) ya da istenen metni ver."""
    status = sandbox_status(config, root)
    selected = _choose(status, picker, platform)
    if selected is None or selected == SHOW_CONFIG:
        return FlowResult(config, format_status(status))
    if selected == SHOW_DEPENDENCIES:
        return FlowResult(config, dependency_report(platform))
    lines: list[str] = []
    try:
        for action, value in _actions(selected):
            change = apply_sandbox_action(config, action, value, root=root, local=True)
            config = change.config
            lines.append(format_change(change))
    except ConfigError as error:
        return FlowResult(config, str(error))
    return FlowResult(config, "\n".join(lines))
