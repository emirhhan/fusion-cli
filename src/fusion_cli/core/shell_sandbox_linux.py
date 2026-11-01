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
from dataclasses import dataclass
from pathlib import Path

from .sandbox_policy import PROTECTED_ANCHORS, SandboxPolicy, protected_write_paths, read_rules

__all__ = ["LINUX_BRIDGE_PORT", "LinuxSandboxArgv", "LinuxTools", "linux_sandbox_argv"]

#: Ağ ad alanının İÇİNDE proxy köprüsünün dinlediği port (ad alanı özel; çakışma yok).
LINUX_BRIDGE_PORT = 3128
#: Köprü dinlemeye başlamadan komutun bağlanmaması için kısa bekleme (sn).
_BRIDGE_WARMUP_S = "0.1"


@dataclass(frozen=True, slots=True)
class LinuxTools:
    """Bulunan yardımcı programlar (yoksa None)."""

    bwrap: str | None
    socat: str | None = None


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


def _mounts(
    roots: Sequence[Path],
    reads: Sequence[tuple[Path, bool]],
    protected_roots: Sequence[Path] = (),
) -> list[str]:
    """Bağlamalar; okuma kuralları geniş→dar sırada (sonraki bağlama kazanır, #349).

    Engel dizinin üstüne boş tmpfs, dosyanın üstüne /dev/null; `allowRead` yolu engelin
    içinde dış dosya sisteminden salt okunur yeniden bağlanır.
    """
    arguments = ["--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc"]
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


def _bridge(socat: str, socket_path: Path) -> tuple[str, ...]:
    """Ad alanı içinde proxy köprüsünü arka planda başlatıp asıl komutu `exec` eden sarmal."""
    listen = f"TCP-LISTEN:{LINUX_BRIDGE_PORT},bind=127.0.0.1,fork,reuseaddr"
    script = (
        f"{shlex.quote(socat)} {listen} UNIX-CONNECT:{shlex.quote(str(socket_path))} "
        f'>/dev/null 2>&1 & sleep {_BRIDGE_WARMUP_S}; exec "$@"'
    )
    return ("/bin/sh", "-c", script, "fusion-sandbox")


def linux_sandbox_argv(
    roots: Sequence[Path],
    policy: SandboxPolicy,
    tools: LinuxTools,
    *,
    proxy_socket: Path | None = None,
    protected_roots: Sequence[Path] = (),
) -> LinuxSandboxArgv:
    """bwrap önekini kur; kurulamıyorsa nedenini döndür."""
    if tools.bwrap is None:
        return LinuxSandboxArgv(
            unavailable="bubblewrap (bwrap) bulunamadı (kur: apt install bubblewrap)"
        )
    arguments = [tools.bwrap, *_ISOLATION, *_mounts(roots, read_rules(policy), protected_roots)]
    if not policy.restricts_network:
        return LinuxSandboxArgv(prefix=(*arguments, "--"))
    arguments.append("--unshare-net")
    if proxy_socket is None:
        # İzinli alan adı yok: ağ tamamen kapalı, köprüye gerek yok.
        return LinuxSandboxArgv(prefix=(*arguments, "--"))
    if tools.socat is None:
        return LinuxSandboxArgv(
            unavailable="ağ allowlist'i için socat bulunamadı (kur: apt install socat)"
        )
    arguments += ["--bind", str(proxy_socket.parent), str(proxy_socket.parent)]
    return LinuxSandboxArgv(prefix=(*arguments, "--", *_bridge(tools.socat, proxy_socket)))
