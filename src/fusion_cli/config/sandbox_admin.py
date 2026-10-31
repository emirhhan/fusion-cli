"""Sandbox durumu ve ayar eylemleri: `/sandbox`, `fusion sandbox`, masaüstü `sandbox.*` (P-010).

Üç yüzey aynı işlevleri kullanır. Durum, sandbox'ın bu makinede GERÇEKTEN kurulabilir
olup olmadığını planlayıcıya sorarak söyler (proxy başlatılmaz, komut çalıştırılmaz).
Eylemler `settings_access.write_setting` üzerinden kullanıcı dosyasına yazar; alan adı
doğrulaması ve kanonik biçim oradan gelir.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from ..core.errors import ConfigError
from ..core.sandbox_policy import NETWORK_ALLOWLIST, NETWORK_MODES, normalize_domain
from ..core.shell_sandbox import (
    SHELL_SANDBOX_OFF,
    SHELL_SANDBOX_WRITE_ROOT,
    ProxyEndpoint,
    plan_shell_sandbox,
)
from .models import Config
from .sandbox_config import fusion_secret_paths, sandbox_policy
from .settings_access import write_setting

__all__ = [
    "SANDBOX_ACTIONS",
    "SandboxChange",
    "SandboxStatus",
    "apply_sandbox_action",
    "sandbox_status",
]

#: Eylem kimlikleri: aç/kapat, ağ kipi, alan adı listeleri ve üç bayrak.
SANDBOX_ACTIONS = (
    "ac",
    "kapat",
    "ag",
    "izin",
    "engelle",
    "kaldir",
    "oto",
    "zorunlu",
    "disari",
)
_PROBE_SOCKET = Path("fusion-sandbox-durum.sock")
_FLAG_PATHS = {
    "oto": "sandbox.auto_allow",
    "zorunlu": "sandbox.fail_if_unavailable",
    "disari": "sandbox.allow_unsandboxed",
}


@dataclass(frozen=True, slots=True)
class SandboxStatus:
    """Sandbox'ın bu makinedeki durumu ve etkin politikası (sırsız)."""

    enabled: bool
    platform: str
    available: bool
    reason: str
    network: str
    allowed_domains: tuple[str, ...]
    denied_domains: tuple[str, ...]
    allow_localhost: bool
    allow_write: tuple[str, ...]
    deny_read: tuple[str, ...]
    fail_if_unavailable: bool
    allow_unsandboxed: bool
    auto_allow: bool
    excluded_commands: tuple[str, ...]
    hide_secret_env: bool

    def as_dict(self) -> dict[str, object]:
        """Masaüstü RPC biçimi (Türkçe anahtarlar, listeler JSON dizisi)."""
        return {
            "ok": True,
            "acik": self.enabled,
            "platform": self.platform,
            "kullanilabilir": self.available,
            "neden": self.reason,
            "ag": self.network,
            "izinli_alanlar": list(self.allowed_domains),
            "yasak_alanlar": list(self.denied_domains),
            "localhost": self.allow_localhost,
            "ek_yazma": list(self.allow_write),
            "okuma_engeli": list(self.deny_read),
            "zorunlu": self.fail_if_unavailable,
            "disari_izinli": self.allow_unsandboxed,
            "oto_izin": self.auto_allow,
            "disari_komutlar": list(self.excluded_commands),
            "sir_ortami_gizli": self.hide_secret_env,
        }


@dataclass(frozen=True, slots=True)
class SandboxChange:
    """Bir eylemin sonucu: güncel yapılandırma, yazılan ayar ve dosya."""

    config: Config
    setting: str
    value: str
    path: Path


def _platform_label(system: str) -> str:
    if system == "darwin":
        return "macOS (sandbox-exec)"
    if system.startswith("linux"):
        return "Linux (bubblewrap)"
    return "desteklenmiyor"


def sandbox_status(config: Config, root: Path, *, platform: str | None = None) -> SandboxStatus:
    """Durumu planlayıcıya sorarak kur; kip kapalıyken de "açılsa kurulur mu" söylenir."""
    system = platform or sys.platform
    policy = sandbox_policy(config.sandbox, home=Path.home(), root=root)
    needs_proxy = policy.restricts_network and bool(policy.allowed_domains)
    # Yalnız "proxy gerekir" bilgisini taşıyan sahte uç: socat denetimi için; soket açılmaz.
    probe = ProxyEndpoint(port=1, unix_path=_PROBE_SOCKET) if needs_proxy else None
    plan = plan_shell_sandbox(
        SHELL_SANDBOX_WRITE_ROOT, (root,), policy=policy, platform=system, proxy=probe
    )
    sandbox = config.sandbox
    return SandboxStatus(
        enabled=config.runtime.shell_sandbox == SHELL_SANDBOX_WRITE_ROOT,
        platform=_platform_label(system),
        available=plan.is_active,
        reason=plan.notice or plan.refused,
        network=sandbox.network,
        allowed_domains=sandbox.allowed_domains,
        denied_domains=sandbox.denied_domains,
        allow_localhost=sandbox.allow_localhost,
        allow_write=sandbox.allow_write,
        deny_read=(*sandbox.deny_read, *(str(path) for path in fusion_secret_paths())),
        fail_if_unavailable=sandbox.fail_if_unavailable,
        allow_unsandboxed=sandbox.allow_unsandboxed,
        auto_allow=sandbox.auto_allow,
        excluded_commands=sandbox.excluded_commands,
        hide_secret_env=sandbox.hide_secret_env,
    )


def _domain(value: str) -> str:
    domain = normalize_domain(value)
    if domain is None:
        raise ConfigError(
            f"Geçerli bir alan adı değil: {value!r} (ör. github.com, *.npmjs.org, 127.0.0.1)."
        )
    return domain


def _write(config: Config, path: str, raw: str, file: Path | None) -> SandboxChange:
    updated, target = write_setting(config, path, raw, file)
    return SandboxChange(updated, path, raw, target)


def _domain_lists(config: Config, action: str, domain: str, file: Path | None) -> SandboxChange:
    allowed = [item for item in config.sandbox.allowed_domains if item != domain]
    denied = [item for item in config.sandbox.denied_domains if item != domain]
    if action == "izin":
        allowed.append(domain)
    elif action == "engelle":
        denied.append(domain)
    change = _write(config, "sandbox.denied_domains", ",".join(denied), file)
    change = _write(change.config, "sandbox.allowed_domains", ",".join(allowed), file)
    if action == "izin" and change.config.sandbox.network != NETWORK_ALLOWLIST:
        # Liste yalnız allowlist kipinde anlamlıdır; kullanıcıya ayrı bir adım bırakılmaz.
        change = _write(change.config, "sandbox.network", NETWORK_ALLOWLIST, file)
    return SandboxChange(change.config, f"sandbox.{action}", domain, change.path)


def apply_sandbox_action(
    config: Config, action: str, value: str = "", file: Path | None = None
) -> SandboxChange:
    """Eylemi uygula ve kullanıcı dosyasına yaz; geçersiz eylem/değer `ConfigError`."""
    if action not in SANDBOX_ACTIONS:
        raise ConfigError(
            f"Bilinmeyen sandbox eylemi: {action!r}. Eylemler: {', '.join(SANDBOX_ACTIONS)}"
        )
    if action in ("ac", "kapat"):
        mode = SHELL_SANDBOX_WRITE_ROOT if action == "ac" else SHELL_SANDBOX_OFF
        return _write(config, "runtime.shell_sandbox", mode, file)
    if action == "ag":
        if value not in NETWORK_MODES:
            raise ConfigError(f"Ağ kipi {' ya da '.join(NETWORK_MODES)} olmalı: {value!r}")
        return _write(config, "sandbox.network", value, file)
    if action in _FLAG_PATHS:
        return _write(config, _FLAG_PATHS[action], value, file)
    return _domain_lists(config, action, _domain(value), file)
