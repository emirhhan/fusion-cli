"""Linux sandbox yardımcı programları: bwrap, socat, rg bulma ve yetenek yoklaması (#350).

Claude Code Linux sandbox'ı `bwrapPath`, `socatPath` ve `ripgrep: {command, args}` ayarlarını
okur. rg alt dizinlerdeki korumalı dosyaları (iç içe depoların `.git/config`'i, `.claude`
ayarları, `.mcp.json`) bulmak için kullanılır; bulunanlar sandbox içinde salt okunur bağlanır.
rg yoksa yalnız kök düzeyindeki korumalı yollar bağlanır (önceki davranış). Tarama sonucu
kök başına kısa süre (`SCAN_CACHE_S`) önbelleklenir: aynı komutun onay ve çalıştırma planı tek
taramayı paylaşır, sonraki komutlar yeni oluşan iç içe depoları yine görür.
"""

from __future__ import annotations

import functools
import shutil
import subprocess
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .sandbox_policy import PROTECTED_WRITE_PATHS, SandboxPolicy

__all__ = ["LinuxTools", "discover_linux_tools", "nested_protected"]

#: Claude'un zorunlu engel arama derinliği gibi: kökten en çok bu kadar dizin aşağı bakılır.
SEARCH_DEPTH = 4
_PROBE_TIMEOUT_S = 5.0
_SCAN_TIMEOUT_S = 10.0
#: Korumalı dizinler: içlerinden bir dosya bulunursa dizinin kendisi bağlanır.
_PROTECTED_DIRS = (".git/hooks", ".fusion/tools")
#: Kök başına tarama sonucunun geçerli kaldığı süre (saniye).
SCAN_CACHE_S = 5.0
_clock = time.monotonic
_SCAN_LOCK = threading.Lock()
_SCAN_CACHE: dict[tuple[tuple[str, ...], Path], tuple[float, tuple[Path, ...]]] = {}


@dataclass(frozen=True, slots=True)
class LinuxTools:
    """Bulunan yardımcı programlar (yoksa None) ve bwrap yetenekleri."""

    bwrap: str | None
    socat: str | None = None
    #: bwrap `--disable-userns` destekliyor ve kullanıcı ad alanı açılabiliyor mu?
    disable_userns: bool = False
    #: rg komutu ve ek argümanları; boşsa iç içe tarama yapılmaz.
    ripgrep: tuple[str, ...] = ()


@functools.cache
def _supports_disable_userns(bwrap: str) -> bool:
    """bwrap ≥0.8 `--disable-userns`; gerçek bir deneme ile yoklanır (sonuç süreç boyunca)."""
    try:
        probe = subprocess.run(
            [bwrap, "--unshare-user", "--disable-userns", "--ro-bind", "/", "/", "true"],
            capture_output=True,
            timeout=_PROBE_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0


def discover_linux_tools(policy: SandboxPolicy) -> LinuxTools:
    """Ayardaki yollar (boşsa PATH) ile araçları bul."""
    bwrap = shutil.which(policy.bwrap_path or "bwrap")
    socat = shutil.which(policy.socat_path or "socat")
    rg = shutil.which(policy.ripgrep[0] if policy.ripgrep else "rg")
    return LinuxTools(
        bwrap=bwrap,
        socat=socat,
        disable_userns=bwrap is not None and _supports_disable_userns(bwrap),
        ripgrep=(rg, *policy.ripgrep[1:]) if rg else (),
    )


def _globs() -> list[str]:
    patterns: list[str] = []
    for relative in PROTECTED_WRITE_PATHS:
        suffix = f"{relative}/*" if relative in _PROTECTED_DIRS else relative
        patterns += ["-g", f"**/{suffix}"]
    return patterns


def _protected_target(found: Path, root: Path) -> Path | None:
    """Bulunan dosyanın korunacak yolu (dizin içindeyse dizin); kök düzeyi zaten korunur."""
    for relative in PROTECTED_WRITE_PATHS:
        parts = Path(relative).parts
        text = found.as_posix()
        marker = "/" + "/".join(parts)
        if relative in _PROTECTED_DIRS and f"{marker}/" in text:
            target = Path(text[: text.index(f"{marker}/") + len(marker)])
        elif text.endswith(marker):
            target = found
        else:
            continue
        return None if target.parent == root or target == root / relative else target
    return None


def nested_protected(ripgrep: Sequence[str], roots: Sequence[Path]) -> tuple[Path, ...]:
    """rg ile köklerin alt dizinlerindeki korumalı yolları bul (kök düzeyi hariç)."""
    if not ripgrep:
        return ()
    found: list[Path] = []
    for root in roots:
        found.extend(_scan_cached(tuple(ripgrep), root))
    return tuple(dict.fromkeys(found))


def _scan_cached(ripgrep: tuple[str, ...], root: Path) -> tuple[Path, ...]:
    key, now = (ripgrep, root), _clock()
    with _SCAN_LOCK:
        cached = _SCAN_CACHE.get(key)
    if cached is not None and now - cached[0] < SCAN_CACHE_S:
        return cached[1]
    result = _scan(ripgrep, root)
    with _SCAN_LOCK:
        _SCAN_CACHE[key] = (now, result)
    return result


def _scan(ripgrep: tuple[str, ...], root: Path) -> tuple[Path, ...]:
    argv = [
        *ripgrep,
        "--files",
        "--hidden",
        "--no-ignore",
        "--max-depth",
        str(SEARCH_DEPTH),
        *_globs(),
        str(root),
    ]
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=_SCAN_TIMEOUT_S, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    found: list[Path] = []
    for line in result.stdout.splitlines():
        path = Path(line.strip())
        target = _protected_target(path if path.is_absolute() else root / path, root)
        if target is not None:
            found.append(target)
    return tuple(found)
