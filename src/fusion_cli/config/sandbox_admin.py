"""Sandbox durumu ve ayar eylemleri: `/sandbox`, `fusion sandbox`, masaüstü `sandbox.*` (P-010).

Üç yüzey aynı işlevleri kullanır. Durum, sandbox'ın bu makinede GERÇEKTEN kurulabilir
olup olmadığını planlayıcıya sorarak söyler (proxy başlatılmaz, komut çalıştırılmaz).
Eylemler `settings_access.write_setting` üzerinden kullanıcı dosyasına yazar; alan adı
doğrulaması ve kanonik biçim oradan gelir.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, replace
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
from .sandbox_config import effective_deny_read, fusion_secret_paths, sandbox_policy
from .settings_access import write_setting

__all__ = [
    "SANDBOX_ACTIONS",
    "SandboxChange",
    "SandboxStatus",
    "apply_sandbox_action",
    "debug_port_guard",
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
    "sir",
    "localhost",
)
_PROBE_SOCKET = Path("fusion-sandbox-durum.sock")
_FLAG_PATHS = {
    "oto": "sandbox.auto_allow",
    "zorunlu": "sandbox.fail_if_unavailable",
    "disari": "sandbox.allow_unsandboxed",
    "sir": "sandbox.hide_secret_env",
    "localhost": "sandbox.allow_localhost",
}
#: Eylem sonucuna eklenen açıklamalar (kullanıcıya görünür; `/sandbox`, CLI, masaüstü).
NOTE_NETWORK_SWITCHED = (
    "Ağ kipi allowlist'e geçti: sandbox içindeki komutlar artık yalnız {domains} adreslerine "
    "erişir, diğer tüm trafik (npm, pip dahil) kapalı. Geri almak: /sandbox ag open"
)
NOTE_UNAVAILABLE = "Uyarı: sandbox bu makinede kurulamıyor ({reason})."
#: Fusion Chrome'larının CDP portu korumasının platforma/ağ kipine göre kapsamı.
GUARD_DARWIN = "her kipte kapalı (Seatbelt + proxy)"
GUARD_LINUX_ALLOWLIST = "kapalı (komut ayrı ağ ad alanında; proxy de reddeder)"
GUARD_LINUX_OPEN = (
    "korunmaz: Linux'ta ağ open iken komut ana makinenin localhost'una ulaşır; "
    "oturumlu web profilleriyle /sandbox ag allowlist kullanın"
)
GUARD_NONE = "sandbox yok"
NOTE_AUTO_OPEN = (
    "Not: sorusuz çalıştırma yalnız ağ allowlist'teyken etkilidir; ağ şu an açık "
    "(/sandbox ag allowlist)."
)


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
    #: Etkin okuma engeli: varsayılan + `deny_read` − `allow_read` + Fusion sırları.
    deny_read: tuple[str, ...]
    fail_if_unavailable: bool
    allow_unsandboxed: bool
    auto_allow: bool
    excluded_commands: tuple[str, ...]
    hide_secret_env: bool
    #: Fusion Chrome'larının hata ayıklama (CDP) portu korumasının kapsamı (metin).
    debug_ports: str = ""
    #: Varsayılan okuma engelinden bilerek açılan yollar (`sandbox.allow_read`).
    allow_read: tuple[str, ...] = ()

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
            "okuma_izni": list(self.allow_read),
            "cdp_korumasi": self.debug_ports,
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
    #: Değişikliğin yan etkileri ve uyarılar (ağ kipi değişti, sandbox kurulamıyor…).
    notes: tuple[str, ...] = ()


def _platform_label(system: str) -> str:
    if system == "darwin":
        return "macOS (sandbox-exec)"
    if system.startswith("linux"):
        return "Linux (bubblewrap)"
    return "desteklenmiyor"


def debug_port_guard(system: str, network: str) -> str:
    """CDP portu korumasının bu platform ve ağ kipindeki kapsamı (`tools.sandbox_cdp`)."""
    if system == "darwin":
        return GUARD_DARWIN
    if system.startswith("linux"):
        return GUARD_LINUX_ALLOWLIST if network == NETWORK_ALLOWLIST else GUARD_LINUX_OPEN
    return GUARD_NONE


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
        deny_read=(
            *effective_deny_read(sandbox),
            *(str(path) for path in fusion_secret_paths()),
        ),
        allow_read=sandbox.allow_read,
        debug_ports=debug_port_guard(system, sandbox.network),
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
    notes: tuple[str, ...] = ()
    if action == "izin" and change.config.sandbox.network != NETWORK_ALLOWLIST:
        # Liste yalnız allowlist kipinde anlamlıdır; kullanıcıya ayrı bir adım bırakılmaz,
        # ama ağın daraldığı açıkça söylenir. Ölçüldü (31 Ekim): çıktı yalnız
        # "Kaydedildi: sandbox.izin = …" diyordu (var olmayan ayar adı, kip değişimi yok).
        change = _write(change.config, "sandbox.network", NETWORK_ALLOWLIST, file)
        notes = (
            NOTE_NETWORK_SWITCHED.format(domains=", ".join(change.config.sandbox.allowed_domains)),
        )
    setting = "sandbox.denied_domains" if action == "engelle" else "sandbox.allowed_domains"
    if action == "kaldir":
        setting = "sandbox.allowed_domains, sandbox.denied_domains"
    return SandboxChange(change.config, setting, domain, change.path, notes)


def _with_notes(change: SandboxChange, *notes: str) -> SandboxChange:
    return replace(change, notes=(*change.notes, *notes)) if notes else change


def apply_sandbox_action(
    config: Config,
    action: str,
    value: str = "",
    file: Path | None = None,
    *,
    root: Path | None = None,
) -> SandboxChange:
    """Eylemi uygula ve kullanıcı dosyasına yaz; geçersiz eylem/değer `ConfigError`.

    `root` kurulabilirlik denetimi içindir (sandbox açılırken uyarı); verilmezse çalışma dizini.
    """
    if action not in SANDBOX_ACTIONS:
        raise ConfigError(
            f"Bilinmeyen sandbox eylemi: {action!r}. Eylemler: {', '.join(SANDBOX_ACTIONS)}"
        )
    if action in ("ac", "kapat"):
        mode = SHELL_SANDBOX_WRITE_ROOT if action == "ac" else SHELL_SANDBOX_OFF
        change = _write(config, "runtime.shell_sandbox", mode, file)
        if action == "kapat":
            return change
        status = sandbox_status(change.config, root or Path.cwd())
        return (
            change
            if status.available
            else _with_notes(change, NOTE_UNAVAILABLE.format(reason=status.reason))
        )
    if action == "ag":
        if value not in NETWORK_MODES:
            raise ConfigError(f"Ağ kipi {' ya da '.join(NETWORK_MODES)} olmalı: {value!r}")
        return _write(config, "sandbox.network", value, file)
    if action in _FLAG_PATHS:
        change = _write(config, _FLAG_PATHS[action], value, file)
        sandbox = change.config.sandbox
        if action == "oto" and sandbox.auto_allow and sandbox.network != NETWORK_ALLOWLIST:
            return _with_notes(change, NOTE_AUTO_OPEN)
        return change
    return _domain_lists(config, action, _domain(value), file)
