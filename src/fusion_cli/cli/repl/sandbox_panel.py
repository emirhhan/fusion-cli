"""`/sandbox` paneli: Kip / Geçersiz kılmalar / Yapılandırma / Bağımlılıklar (Claude, #352).

Claude Code (sandboxing › Enabling; commands › /sandbox): argümansız `/sandbox` sekmeli bir panel
açar — Mode (auto-allow ya da regular permissions), Overrides (`allowUnsandboxedCommands`;
kapalıyken "Strict sandbox mode"), Config (etkin ayarlar) ve Linux'ta Dependencies. Kip ve
geçersiz kılma seçimi projenin `.claude/settings.local.json`'ına yazılır.

Fusion'ın seçicisi (REPL `pick`, TUI modalı) tek listedir: sekmeler listede başlıklı bölüm
olarak sıralanır; Yapılandırma ve Bağımlılıklar seçilince ilgili metin gösterilir. Argümanlı
metin alt komutları (`/sandbox on`, `/sandbox izin x.com`…) betiklenebilir yol olarak kalır.
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

__all__ = ["dependency_report", "panel_choices", "sandbox_panel"]

MODE_AUTO = "kip:oto"
MODE_REGULAR = "kip:normal"
MODE_OFF = "kip:kapali"
OVERRIDE_ALLOW = "gecersiz:izin"
OVERRIDE_STRICT = "gecersiz:kati"
SHOW_CONFIG = "yapilandirma"
SHOW_DEPENDENCIES = "bagimliliklar"
TITLE = "Sandbox — Kip · Geçersiz kılmalar · Yapılandırma · Bağımlılıklar"


def _mark(active: bool) -> str:
    return "● " if active else "  "


def panel_choices(status: SandboxStatus) -> list[Choice]:
    """Sekmeler sırasıyla; etkin seçim ● ile işaretli."""
    auto = status.enabled and status.auto_allow
    regular = status.enabled and not status.auto_allow
    return [
        Choice(MODE_AUTO, f"Kip › {_mark(auto)}Sandbox, otomatik izinle", "auto-allow"),
        Choice(MODE_REGULAR, f"Kip › {_mark(regular)}Sandbox, normal izinlerle", "regular"),
        Choice(MODE_OFF, f"Kip › {_mark(not status.enabled)}Sandbox kapalı", ""),
        Choice(
            OVERRIDE_ALLOW,
            f"Geçersiz kılma › {_mark(status.allow_unsandboxed)}Sandbox dışı yeniden denemeye izin",
            "allowUnsandboxedCommands: true",
        ),
        Choice(
            OVERRIDE_STRICT,
            f"Geçersiz kılma › {_mark(not status.allow_unsandboxed)}Katı sandbox kipi",
            "Strict sandbox mode: dangerouslyDisableSandbox yok sayılır",
        ),
        Choice(SHOW_CONFIG, "Yapılandırma › etkin ayarları göster", ""),
        Choice(SHOW_DEPENDENCIES, "Bağımlılıklar › denetle", sys.platform),
    ]


def dependency_report(platform: str | None = None) -> str:
    """Sandbox araçlarının bu makinedeki durumu (Linux: bwrap, socat; macOS: sandbox-exec)."""
    name = platform or sys.platform
    tools = ("bwrap", "socat") if name.startswith("linux") else ("sandbox-exec",)
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


def sandbox_panel(config: Config, root: Path, *, picker: Picker) -> FlowResult:
    """Paneli göster; seçimi uygula (yerel ayar dosyasına) ya da istenen metni ver."""
    status = sandbox_status(config, root)
    selected = picker(panel_choices(status), title=TITLE)
    if selected is None:
        return FlowResult(config, format_status(status))
    if selected == SHOW_CONFIG:
        return FlowResult(config, format_status(status))
    if selected == SHOW_DEPENDENCIES:
        return FlowResult(config, dependency_report())
    lines: list[str] = []
    try:
        for action, value in _actions(selected):
            change = apply_sandbox_action(config, action, value, root=root, local=True)
            config = change.config
            lines.append(format_change(change))
    except ConfigError as error:
        return FlowResult(config, str(error))
    return FlowResult(config, "\n".join(lines))
