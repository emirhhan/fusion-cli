"""Proje (`.mcp.json`) sunucu onayı Claude Code gibi (#246).

Belge: code.claude.com/docs/en/mcp (Project scope; Project server approvals and workspace trust).

- Etkileşimli oturumda onaylanmamış her sunucu için tek tek sorulur (`⏸ Onay bekliyor`).
  Seçimler kullanıcının `mcp-local.json` dosyasında bu projenin altında tutulur:
  `enabledMcpjsonServers`, `disabledMcpjsonServers`, `enableAllProjectMcpServers`.
  `fusion mcp reset-project-choices` bu üç anahtarı siler.
- Aynı anahtarlar Claude ayar dosyalarından da okunur. Kullanıcının `~/.claude/settings.json`
  dosyası ve yönetilen ayar her zaman geçer; projenin `.claude/settings.json` /
  `.claude/settings.local.json` onayı yalnız klasöre güvenilmişse (`fusion trust`) geçer.
  `disabledMcpjsonServers` hangi dosyada olursa olsun sunucuyu reddeder.
- Etkileşimsiz kipte (`fusion exec`) Claude `-p` gibi sormadan yüklenir; Fusion'ın
  güvenilmeyen klasör kuralı korunur (klasöre hiç güvenilmediyse yüklenmez).
- `fusion trust` ile içeriği güvene alınmış (ya da Fusion'ın yazdığı) dosya onaylanmış sayılır.

Güvenlik davranışı değişti: güvenilen klasörde `.mcp.json` değişse bile sunucu başına onay
ya da etkileşimsiz kip sunucuyu yükler (önceden dosya karması düşünce hiçbiri yüklenmezdi).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from ..core.errors import ConfigError
from . import trust
from .mcp_local import local_project_entry, update_local_project
from .models import McpServerConfig

_LOG = logging.getLogger(__name__)

ENABLE_ALL = "enableAllProjectMcpServers"
ENABLED = "enabledMcpjsonServers"
DISABLED = "disabledMcpjsonServers"
_KEYS = (ENABLE_ALL, ENABLED, DISABLED)

APPROVED = "approved"
REJECTED = "rejected"
PENDING = "pending"

#: İstem seçenekleri (Claude: "Use this and all future…", "Use this MCP server", "Continue without…").
CHOICE_ALL = "all"
CHOICE_ONE = "one"
CHOICE_NO = "no"

_STATE: dict[str, bool] = {"noninteractive": False}


def set_noninteractive(value: bool = True) -> None:
    """Oturum etkileşimsiz mi (`fusion exec`)? Claude `-p` gibi onay sorulmaz."""
    _STATE["noninteractive"] = value


def is_noninteractive() -> bool:
    return _STATE["noninteractive"]


@dataclass(frozen=True, slots=True)
class ApprovalSettings:
    enable_all: bool = False
    enabled: frozenset[str] = frozenset()
    disabled: frozenset[str] = frozenset()
    workspace_trusted: bool = False

    @property
    def may_approve(self) -> bool:
        return self.enable_all or bool(self.enabled)


def _read(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        _LOG.warning("%s okunamadı: %s", path, error)
        return {}
    return raw if isinstance(raw, dict) else {}


def _names(layers: Iterable[Mapping[str, object]], key: str) -> frozenset[str]:
    found: set[str] = set()
    for layer in layers:
        value = layer.get(key)
        if isinstance(value, list):
            found.update(str(item) for item in value)
    return frozenset(found)


def load_approval_settings(root: Path, *, home: Path | None = None) -> ApprovalSettings:
    """Onay anahtarlarını güvenilen kaynaklardan topla; ret her kaynaktan gelir."""
    from .mcp_policy import MANAGED_SETTINGS_FILE, managed_dir

    base = home or Path.home()
    approving = [
        _read(base / ".claude" / "settings.json"),
        _read(managed_dir() / MANAGED_SETTINGS_FILE),
        local_project_entry(root),
    ]
    project = [
        _read(root / ".claude" / "settings.json"),
        _read(root / ".claude" / "settings.local.json"),
    ]
    workspace = trust.was_project_trusted(root)
    sources = [*approving, *project] if workspace else approving
    return ApprovalSettings(
        enable_all=any(layer.get(ENABLE_ALL) is True for layer in sources),
        enabled=_names(sources, ENABLED),
        disabled=_names([*approving, *project], DISABLED),
        workspace_trusted=workspace,
    )


def decide(name: str, settings: ApprovalSettings, *, file_trusted: bool) -> str:
    """Tek sunucunun onay durumu: approved / rejected / pending."""
    if name in settings.disabled:
        return REJECTED
    if file_trusted or settings.enable_all or name in settings.enabled:
        return APPROVED
    if is_noninteractive() and settings.workspace_trusted:
        return APPROVED
    return PENDING


def could_load_any(settings: ApprovalSettings, *, file_trusted: bool) -> bool:
    """Dosyayı ayrıştırmaya değer mi? Değilse güvenilmeyen dosya hiç okunmaz."""
    if file_trusted or settings.may_approve:
        return True
    return is_noninteractive() and settings.workspace_trusted


def _project_servers(root: Path) -> tuple[McpServerConfig, ...]:
    from .mcp_json import read_project_mcp_report

    try:
        return read_project_mcp_report(root)[0]
    except ConfigError as error:
        _LOG.warning("%s", error)
        return ()


def _file_trusted(root: Path) -> bool:
    from .mcp_json import project_mcp_path

    return trust.is_file_trusted(root, project_mcp_path(root))


def pending_project_servers(root: Path) -> tuple[McpServerConfig, ...]:
    """Onay bekleyen `.mcp.json` sunucuları (Claude: ⏸ Pending approval)."""
    settings = load_approval_settings(root)
    trusted = _file_trusted(root)
    return tuple(
        server
        for server in _project_servers(root)
        if decide(server.name, settings, file_trusted=trusted) == PENDING
    )


def record_choice(root: Path, name: str, choice: str) -> Path:
    """İstem seçimini bu projenin yerel kaydına yaz."""

    def _change(entry: dict[str, object]) -> dict[str, object]:
        enabled = set(_names([entry], ENABLED))
        disabled = set(_names([entry], DISABLED))
        if choice == CHOICE_NO:
            disabled.add(name)
            enabled.discard(name)
        else:
            enabled.add(name)
            disabled.discard(name)
        updated: dict[str, object] = {**entry, ENABLED: sorted(enabled), DISABLED: sorted(disabled)}
        if choice == CHOICE_ALL:
            updated[ENABLE_ALL] = True
        return updated

    if choice not in (CHOICE_ALL, CHOICE_ONE, CHOICE_NO):
        raise ConfigError(f"Geçersiz onay seçimi: {choice!r}")
    return update_local_project(root, _change)


def reset_project_choices(root: Path) -> bool:
    """Bu projenin onay seçimlerini sil; silinecek bir şey yoksa False."""
    if not any(key in local_project_entry(root) for key in _KEYS):
        return False
    update_local_project(
        root, lambda entry: {key: value for key, value in entry.items() if key not in _KEYS}
    )
    return True


def prompt_pending(
    root: Path, ask: Callable[[McpServerConfig], str]
) -> tuple[McpServerConfig, ...]:
    """Bekleyen her sunucu için `ask` çağır, seçimi kaydet; sorulanları döndür.

    "Hepsini kullan" seçilince kalan sunucular sorulmaz (onaylanmış olurlar).
    """
    asked: list[McpServerConfig] = []
    for server in pending_project_servers(root):
        choice = ask(server)
        asked.append(server)
        record_choice(root, server.name, choice)
        if choice == CHOICE_ALL:
            break
    return tuple(asked)


def approved_project_servers(root: Path) -> tuple[McpServerConfig, ...]:
    """Yüklenecek `.mcp.json` sunucuları; bekleyen ve reddedilenler düşer."""
    from .mcp_json import project_mcp_path

    path = project_mcp_path(root)
    if not path.is_file():
        return ()
    settings = load_approval_settings(root)
    trusted = _file_trusted(root)
    # Onaylayacak hiçbir şey yoksa güvenilmeyen dosya HİÇ ayrıştırılmaz.
    if not could_load_any(settings, file_trusted=trusted):
        _LOG.warning(
            "%s içindeki MCP sunucuları onay bekliyor; Fusion'ı etkileşimli aç ya da: fusion trust",
            path,
        )
        return ()
    servers = _project_servers(root)
    return tuple(
        server
        for server in servers
        if decide(server.name, settings, file_trusted=trusted) == APPROVED
    )
