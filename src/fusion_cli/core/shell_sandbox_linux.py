"""Linux/WSL2 `run_shell` sandbox'ı: bubblewrap (`bwrap`) argv planlayıcısı (P-010).

Claude Code'un Linux sandbox'ı ve Codex'in `codex sandbox` Linux yolu gibi: kök dosya
sistemi SALT OKUNUR bağlanır, yalnız proje kökü (+ `--add-dir`, `sandbox.allow_write`)
ve geçici dizinler yazılabilir bağlanır; `sandbox.deny_read` dizinlerinin üstüne boş
tmpfs, dosyalarının üstüne `/dev/null` bağlanır. Ağ `allowlist` kipinde süreç yeni bir
ağ ad alanında (`--unshare-net`) yalnız loopback görür; izinli alan adı varsa ana
makinedeki Fusion proxy'sinin Unix soketi içeri bağlanır ve `socat` onu ad alanının
içinde `127.0.0.1:<köprü portu>` olarak açar (Claude Code'un bubblewrap+socat düzeni).

Ölçüldü (31 Ekim): bu makinede (macOS) `bwrap` yok; argv yapısı birim testlerle,
gerçek davranış Linux'ta elle doğrulanır (bkz. docs/SANDBOX.md).
"""

from __future__ import annotations

import shlex
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from .linux_sandbox_tools import LinuxTools, discover_linux_tools, nested_protected
from .sandbox_policy import PROTECTED_ANCHORS, SandboxPolicy, protected_write_paths, read_rules

__all__ = [
    "LINUX_BRIDGE_PORT",
    "LINUX_SOCKS_BRIDGE_PORT",
    "LinuxSandboxArgv",
    "LinuxTools",
    "discover_linux_tools",
    "linux_sandbox_argv",
]

#: Ağ ad alanının İÇİNDE proxy köprüsünün dinlediği port (ad alanı özel; çakışma yok).
LINUX_BRIDGE_PORT = 3128
#: Kullanıcının SOCKS5 proxy'sinin ad alanı içindeki köprü portu (Claude `socksProxyPort`).
LINUX_SOCKS_BRIDGE_PORT = 1080
#: Köprü dinlemeye başlamadan komutun bağlanmaması için kısa bekleme (sn).
_BRIDGE_WARMUP_S = "0.1"


@dataclass(frozen=True, slots=True)
class LinuxSandboxArgv:
    """Planlayıcının sonucu: önek ya da neden kurulamadığı."""

    prefix: tuple[str, ...] = ()
    unavailable: str = ""


#: Süreç izolasyonu: PID ve IPC ad alanı, yeni oturum (TIOCSTI ile terminale yazamaz).
#: Ölçüldü (31 Ekim, argv okuması): `--unshare-pid` yoktu; host `/proc/<pid>/environ`
#: görünüyordu ve `socat` köprüsü komut bitince öksüz kalıyordu. PID ad alanında ilk
#: süreç çıkınca ad alanındaki her süreç (köprü dahil) ölür.
_ISOLATION = ("--die-with-parent", "--unshare-pid", "--unshare-ipc", "--new-session")


def _guards(protected_roots: Sequence[Path]) -> list[str]:
    """Kök altında zorunlu yazma engeli (`core.sandbox_policy.PROTECTED_WRITE_PATHS`).

    `.git`/`.claude`/`.fusion` dizinleri kendi üstüne bağlanır: bağlama noktası
    taşınamaz (EBUSY), içleri yazılabilir kalır. Var olan korumalı yol salt okunur
    bağlanır; `.git/hooks` yoksa boş, salt okunur tmpfs konur. Bilinen sınır: bwrap var
    olmayan dosyayı koruyamaz (ör. `.mcp.json` yoksa oluşturulabilir; Fusion'ın güven
    karması bu dosyalar değişince projeyi güvenilmez sayar).
    """
    arguments: list[str] = []
    for root in protected_roots:
        for anchor in PROTECTED_ANCHORS:
            path = root / anchor
            if path.is_dir():
                arguments += ["--bind", str(path), str(path)]
            elif path.exists():
                arguments += ["--ro-bind", str(path), str(path)]
        for path in protected_write_paths((root,)):
            if path.exists():
                arguments += ["--ro-bind", str(path), str(path)]
            elif path.name == "hooks" and path.parent.is_dir():
                arguments += ["--tmpfs", str(path), "--remount-ro", str(path)]
    return arguments


def _base_mounts(policy: SandboxPolicy) -> list[str]:
    """Kök bağlaması: salt okunur (`filesystem.disabled` iken yazılabilir); `/dev`, `/proc`.

    Claude `enableWeakerNestedSandbox` (#350): yetkisiz Docker içinde yeni `/proc`
    bağlanamaz; ana makinenin `/proc`'u kök bağlamasından görünür kalır (daha zayıf).
    """
    arguments = ["--bind" if policy.filesystem_disabled else "--ro-bind", "/", "/"]
    arguments += ["--dev", "/dev"]
    if not policy.enable_weaker_nested_sandbox:
        arguments += ["--proc", "/proc"]
    return arguments


def _mounts(
    roots: Sequence[Path],
    reads: Sequence[tuple[Path, bool]],
    protected_roots: Sequence[Path] = (),
    policy: SandboxPolicy | None = None,
) -> list[str]:
    """Bağlamalar; okuma kuralları geniş→dar sırada (sonraki bağlama kazanır, #349).

    Engel dizinin üstüne boş tmpfs, dosyanın üstüne /dev/null; `allowRead` yolu engelin
    içinde dış dosya sisteminden salt okunur yeniden bağlanır.
    """
    arguments = _base_mounts(policy or SandboxPolicy())
    for root in roots:
        if root.exists():
            arguments += ["--bind", str(root), str(root)]
    arguments += _guards(protected_roots)
    for path, allowed in reads:
        if allowed and path.exists():
            arguments += ["--ro-bind", str(path), str(path)]
        elif not allowed and path.is_dir():
            arguments += ["--tmpfs", str(path)]
        elif not allowed and path.exists():
            arguments += ["--ro-bind", "/dev/null", str(path)]
    return arguments


def _bridge(socat: str, sockets: Sequence[tuple[int, Path]]) -> tuple[str, ...]:
    """Ad alanı içinde proxy köprülerini arka planda başlatıp asıl komutu `exec` eden sarmal."""
    script = "".join(
        f"{shlex.quote(socat)} TCP-LISTEN:{port},bind=127.0.0.1,fork,reuseaddr "
        f"UNIX-CONNECT:{shlex.quote(str(path))} >/dev/null 2>&1 & "
        for port, path in sockets
    )
    script += f'sleep {_BRIDGE_WARMUP_S}; exec "$@"'
    return ("/bin/sh", "-c", script, "fusion-sandbox")


def _hardening(policy: SandboxPolicy, tools: LinuxTools, roots: Sequence[Path]) -> list[str]:
    """İç içe kullanıcı ad alanı engeli ve rg ile bulunan iç içe korumalı yollar (#350).

    Claude `allowNestedUserNamespaces` kapalıyken sandbox içinde yeni kullanıcı ad alanı
    açılamaz (`--unshare-user --disable-userns`, bwrap ≥0.8; desteklemeyen bwrap'te atlanır).
    """
    arguments: list[str] = []
    if not policy.allow_nested_user_namespaces and tools.disable_userns:
        arguments += ["--unshare-user", "--disable-userns"]
    for path in nested_protected(tools.ripgrep, roots):
        arguments += ["--ro-bind", str(path), str(path)]
    return arguments


def linux_sandbox_argv(
    roots: Sequence[Path],
    policy: SandboxPolicy,
    tools: LinuxTools,
    *,
    proxy_socket: Path | None = None,
    socks_socket: Path | None = None,
    protected_roots: Sequence[Path] = (),
) -> LinuxSandboxArgv:
    """bwrap önekini kur; kurulamıyorsa nedenini döndür."""
    if tools.bwrap is None:
        return LinuxSandboxArgv(
            unavailable="bubblewrap (bwrap) bulunamadı (kur: apt install bubblewrap)"
        )
    disabled = policy.filesystem_disabled
    reads = read_rules(replace(policy, deny_read=(), allow_read=()) if disabled else policy)
    arguments = [
        tools.bwrap,
        *_ISOLATION,
        *_mounts(roots, reads, protected_roots, policy),
        *_hardening(policy, tools, protected_roots),
    ]
    # Claude `filesystem.denyWrite` (#350): var olan yol salt okunur yeniden bağlanır.
    for path in () if disabled else policy.deny_write:
        if path.exists():
            arguments += ["--ro-bind", str(path), str(path)]
    if not policy.restricts_network:
        return LinuxSandboxArgv(prefix=(*arguments, "--"))
    arguments.append("--unshare-net")
    bridges = [
        (port, path)
        for port, path in (
            (LINUX_BRIDGE_PORT, proxy_socket),
            (LINUX_SOCKS_BRIDGE_PORT, socks_socket),
        )
        if path is not None
    ]
    if not bridges:
        # İzinli alan adı yok: ağ tamamen kapalı, köprüye gerek yok.
        return LinuxSandboxArgv(prefix=(*arguments, "--"))
    if tools.socat is None:
        return LinuxSandboxArgv(
            unavailable="ağ allowlist'i için socat bulunamadı (kur: apt install socat)"
        )
    for parent in dict.fromkeys(path.parent for _, path in bridges):
        arguments += ["--bind", str(parent), str(parent)]
    return LinuxSandboxArgv(prefix=(*arguments, "--", *_bridge(tools.socat, bridges)))
