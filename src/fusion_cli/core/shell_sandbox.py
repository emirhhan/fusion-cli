"""`run_shell` için isteğe bağlı işletim sistemi sandbox'ı (`runtime.shell_sandbox`).

Ölçüldü (30 Ekim): `echo x > ../y` proje kökünün dışına yazabiliyordu; dosya araçları
kök dışına çıkamazken `run_shell` için tek bariyer komut politikası + onay metniydi.
`write_root` kipi yazmayı kök (+ `--add-dir`, `sandbox.allow_write`) ve geçici
dizinlerle sınırlar. Varsayılan `off`: davranış değişmez.

P-010 (31 Ekim) ile kip `sandbox:` bölümündeki politikayı da uygular
(`core.sandbox_policy.SandboxPolicy`): okuma engeli (`~/.ssh`, `~/.aws`…), ağ allowlist'i
(yalnız Fusion'ın yerel proxy'sine çıkış; proxy alan adını denetler) ve sandbox
kurulamazsa çalıştırmama (`fail_if_unavailable`). macOS'ta `sandbox-exec` (Seatbelt),
Linux/WSL2'de bubblewrap (`core.shell_sandbox_linux`); Windows'ta sandbox yoktur.
Yollar profil metnine GÖMÜLMEZ, `-D` parametresiyle geçer (yolda `"` ya da `)` olsa
bile profil enjekte edilemez); profile giren tek sayı proxy portudur.

Paket yöneticilerinin önbellekleri (`~/.npm`, `~/.cache`, `~/Library/Caches`) bu kipte
yazılabilir DEĞİLDİR; gerekiyorsa `sandbox.allow_write`'a eklenir.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .sandbox_policy import (
    PROTECTED_ANCHORS,
    SandboxPolicy,
    protected_anchors,
    protected_write_paths,
)
from .shell_sandbox_linux import LINUX_BRIDGE_PORT, LinuxTools, linux_sandbox_argv

SHELL_SANDBOX_OFF = "off"
SHELL_SANDBOX_WRITE_ROOT = "write_root"
SHELL_SANDBOX_MODES = (SHELL_SANDBOX_OFF, SHELL_SANDBOX_WRITE_ROOT)

_SANDBOX_EXEC = "/usr/bin/sandbox-exec"
#: Kabuk komutlarının ihtiyaç duyduğu aygıt dosyaları (`2>/dev/null`, terminal).
_DEVICE_FILES = ("/dev/null", "/dev/zero", "/dev/tty", "/dev/dtracehelper")
#: macOS'ta kullanıcı başına geçici/önbellek dizinleri `/private/var/folders` altındadır.
_SYSTEM_TEMP_DIRS = ("/private/tmp", "/private/var/folders")
#: Proxy'yi kullanması için komuta verilen ortam değişkenleri (curl, pip, git, npm, Node 24+).
_PROXY_ENV_NAMES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "npm_config_proxy",
    "npm_config_https_proxy",
)
_LOOPBACK_NO_PROXY = "localhost,127.0.0.1,::1"


@dataclass(frozen=True, slots=True)
class ProxyEndpoint:
    """Fusion'ın alan adı proxy'si: macOS'ta loopback TCP portu, Linux'ta Unix soketi."""

    port: int = 0
    unix_path: Path | None = None


@dataclass(frozen=True, slots=True)
class SandboxPlan:
    """Komutun önüne konacak argv öneki; boşsa sandbox yok. `notice` bir kez gösterilir.

    `refused` doluysa komut ÇALIŞTIRILMAZ (sandbox istendi, kurulamadı ve
    `fail_if_unavailable` açık). `env` komut ortamına eklenir (proxy adresi).
    """

    prefix: tuple[str, ...] = ()
    notice: str = ""
    env: tuple[tuple[str, str], ...] = ()
    refused: str = ""
    hide_secret_env: bool = False

    @property
    def is_active(self) -> bool:
        return bool(self.prefix)


def _temporary_directories() -> tuple[Path, ...]:
    """Yazmaya açık geçici dizinler (gerçek yollarıyla: `/tmp` → `/private/tmp`)."""
    candidates = [*_SYSTEM_TEMP_DIRS, tempfile.gettempdir(), os.environ.get("TMPDIR", "")]
    resolved = {Path(item).resolve() for item in candidates if item}
    return tuple(sorted(resolved))


def temporary_roots() -> tuple[Path, ...]:
    """Sandbox'ta her zaman yazılabilir geçici dizinler (dış modüller için)."""
    return _temporary_directories()


def _network_rules(policy: SandboxPolicy, proxy: ProxyEndpoint | None) -> str:
    """Ağ allowlist'i: her şey kapalı; yalnız proxy portu (ve istenirse localhost) açık."""
    if not policy.restricts_network:
        return ""
    rules = "\n(deny network*)"
    if proxy is not None and proxy.port:
        rules += f'\n(allow network-outbound (remote ip "localhost:{int(proxy.port)}"))'
    if policy.allow_localhost:
        rules += (
            '\n(allow network* (remote ip "localhost:*"))'
            '\n(allow network-bind network-inbound (local ip "localhost:*"))'
        )
    return rules


def _profile(write_count: int, read_count: int, network: str = "", guard: str = "") -> str:
    """SBPL profili: her şeye izin ver, yazmayı kapat, kökleri geri aç, okuma/ağ kısıtla."""
    allowed = " ".join(f'(subpath (param "W{index}"))' for index in range(write_count))
    devices = " ".join(f'(literal "{path}")' for path in _DEVICE_FILES)
    profile = (
        "(version 1)\n(allow default)\n(deny file-write*)\n"
        f'(allow file-write* {allowed} {devices} (regex #"^/dev/fd/[0-9]+$"))'
    )
    if read_count:
        denied = " ".join(f'(subpath (param "R{index}"))' for index in range(read_count))
        profile += f"\n(deny file-read* {denied})"
    return profile + guard + network


def _guard_rules(protected: int, literals: int, anchors: int) -> str:
    """Zorunlu yazma engeli (kök altında da): korumalı yollar, `.git` girdisi, taşıma engeli.

    SBPL'de sonraki kural önceliklidir; bu kurallar köklerin yazma iznini geçersiz kılar.
    `.git` yalnız kendisi (literal) kapalıdır: içine nesne/ref/index yazmak (`git commit`)
    serbest kalır, ama `.git`'i dosya (`gitdir:`) ya da bağlantı yapmak ve taşımak kapanır.
    """
    if not protected:
        return ""
    paths = " ".join(f'(subpath (param "P{index}"))' for index in range(protected))
    paths += "".join(f' (literal (param "G{index}"))' for index in range(literals))
    rules = f"\n(deny file-write* {paths})"
    if anchors:
        moved = " ".join(f'(literal (param "A{index}"))' for index in range(anchors))
        rules += f"\n(deny file-write-unlink {moved})"
    return rules


def _darwin_prefix(
    roots: Sequence[Path],
    policy: SandboxPolicy,
    executable: str,
    proxy: ProxyEndpoint | None,
    guarded: Sequence[Path] = (),
) -> tuple[str, ...]:
    denied = tuple(dict.fromkeys(path.resolve() for path in policy.deny_read))
    protected = protected_write_paths(guarded)
    git_entries = tuple(root / PROTECTED_ANCHORS[0] for root in guarded)
    anchors = tuple(
        path for path in protected_anchors(guarded) if path.name != PROTECTED_ANCHORS[0]
    )
    parameters = [item for index, path in enumerate(roots) for item in ("-D", f"W{index}={path}")]
    parameters += [item for index, path in enumerate(denied) for item in ("-D", f"R{index}={path}")]
    for prefix, paths in (("P", protected), ("G", git_entries), ("A", anchors)):
        parameters += [
            item for index, path in enumerate(paths) for item in ("-D", f"{prefix}{index}={path}")
        ]
    guard = _guard_rules(len(protected), len(git_entries), len(anchors))
    profile = _profile(len(roots), len(denied), _network_rules(policy, proxy), guard)
    return (executable, *parameters, "-p", profile)


def _proxy_env(policy: SandboxPolicy, address: str | None) -> tuple[tuple[str, str], ...]:
    if not policy.restricts_network or address is None:
        return ()
    no_proxy = _LOOPBACK_NO_PROXY if policy.allow_localhost else ""
    return (
        *((name, address) for name in _PROXY_ENV_NAMES),
        ("NO_PROXY", no_proxy),
        ("no_proxy", no_proxy),
        ("NODE_USE_ENV_PROXY", "1"),
    )


def _unavailable(reason: str, policy: SandboxPolicy) -> SandboxPlan:
    if policy.fail_if_unavailable:
        return SandboxPlan(
            refused=(
                f"Sandbox kurulamadı: {reason}. sandbox.fail_if_unavailable açık olduğundan "
                "komut çalıştırılmadı (kapatmak için: /sandbox off ya da ayarı false yap)."
            )
        )
    return SandboxPlan(notice=f"{reason}; komutlar sandbox'sız çalışıyor (kip kapalı).")


def plan_shell_sandbox(
    mode: str,
    writable_roots: Sequence[Path],
    *,
    policy: SandboxPolicy | None = None,
    platform: str | None = None,
    executable: str | None = _SANDBOX_EXEC,
    proxy: ProxyEndpoint | None = None,
    linux_tools: LinuxTools | None = None,
) -> SandboxPlan:
    """Kipe göre sandbox önekini kur; bilinmeyen/kapalı kipte sandbox yoktur."""
    if mode != SHELL_SANDBOX_WRITE_ROOT:
        return SandboxPlan()
    rules = policy or SandboxPolicy()
    system = platform or sys.platform
    roots = tuple(
        dict.fromkeys(
            path.resolve()
            for path in (*writable_roots, *rules.extra_write, *_temporary_directories())
        )
    )
    # Geçici dizinler hariç: korumalı yollar proje kökleri ve kullanıcının ek kökleri içindir.
    guarded = tuple(dict.fromkeys(path.resolve() for path in (*writable_roots, *rules.extra_write)))
    hide = rules.hide_secret_env
    if system == "darwin":
        if executable is None or not Path(executable).exists():
            return _unavailable("sandbox-exec bulunamadı", rules)
        address = f"http://127.0.0.1:{proxy.port}" if proxy is not None and proxy.port else None
        return SandboxPlan(
            prefix=_darwin_prefix(roots, rules, executable, proxy, guarded),
            env=_proxy_env(rules, address),
            hide_secret_env=hide,
        )
    if system.startswith("linux"):
        tools = linux_tools or LinuxTools(shutil.which("bwrap"), shutil.which("socat"))
        socket_path = proxy.unix_path if proxy is not None else None
        argv = linux_sandbox_argv(
            roots, rules, tools, proxy_socket=socket_path, protected_roots=guarded
        )
        if argv.unavailable:
            return _unavailable(argv.unavailable, rules)
        address = f"http://127.0.0.1:{LINUX_BRIDGE_PORT}" if socket_path is not None else None
        return SandboxPlan(prefix=argv.prefix, env=_proxy_env(rules, address), hide_secret_env=hide)
    return _unavailable(
        "runtime.shell_sandbox=write_root yalnız macOS ve Linux'ta desteklenir", rules
    )
