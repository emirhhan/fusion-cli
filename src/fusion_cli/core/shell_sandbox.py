"""`run_shell` için isteğe bağlı işletim sistemi sandbox'ı (`runtime.shell_sandbox`).

Ölçüldü (30 Ekim): `echo x > ../y` proje kökünün dışına yazabiliyordu; dosya araçları
kök dışına çıkamazken `run_shell` için tek bariyer komut politikası + onay metniydi.
`write_root` kipi macOS'ta `sandbox-exec` ile yazmayı kök (+ `--add-dir`) ve geçici
dizinlerle sınırlar; okuma, ağ ve süreç işlemleri sınırlanmaz. Varsayılan `off`:
davranış değişmez. Linux/Windows'ta sandbox yoktur; kip açık istenirse uyarı verilir ve
komut sandbox'sız çalışır. Yollar profil metnine GÖMÜLMEZ, `-D` parametresiyle geçer
(yolda `"` ya da `)` olsa bile profil enjekte edilemez).

Paket yöneticilerinin önbellekleri (`~/.npm`, `~/.cache`, `~/Library/Caches`) bu kipte
yazılabilir DEĞİLDİR; bunlara yazması gereken komut için kip kapatılır.
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

SHELL_SANDBOX_OFF = "off"
SHELL_SANDBOX_WRITE_ROOT = "write_root"
SHELL_SANDBOX_MODES = (SHELL_SANDBOX_OFF, SHELL_SANDBOX_WRITE_ROOT)

_SANDBOX_EXEC = "/usr/bin/sandbox-exec"
#: Kabuk komutlarının ihtiyaç duyduğu aygıt dosyaları (`2>/dev/null`, terminal).
_DEVICE_FILES = ("/dev/null", "/dev/zero", "/dev/tty", "/dev/dtracehelper")
#: macOS'ta kullanıcı başına geçici/önbellek dizinleri `/private/var/folders` altındadır.
_SYSTEM_TEMP_DIRS = ("/private/tmp", "/private/var/folders")


@dataclass(frozen=True, slots=True)
class SandboxPlan:
    """Komutun önüne konacak argv öneki; boşsa sandbox yok. `notice` bir kez gösterilir."""

    prefix: tuple[str, ...] = ()
    notice: str = ""


def _temporary_directories() -> tuple[Path, ...]:
    """Yazmaya açık geçici dizinler (gerçek yollarıyla: `/tmp` → `/private/tmp`)."""
    candidates = [*_SYSTEM_TEMP_DIRS, tempfile.gettempdir(), os.environ.get("TMPDIR", "")]
    resolved = {Path(item).resolve() for item in candidates if item}
    return tuple(sorted(resolved))


def _profile(count: int) -> str:
    """SBPL profili: her şeye izin ver, yazmayı kapat, verilen kökleri geri aç."""
    allowed = " ".join(f'(subpath (param "W{index}"))' for index in range(count))
    devices = " ".join(f'(literal "{path}")' for path in _DEVICE_FILES)
    return (
        "(version 1)\n(allow default)\n(deny file-write*)\n"
        f'(allow file-write* {allowed} {devices} (regex #"^/dev/fd/[0-9]+$"))'
    )


def plan_shell_sandbox(
    mode: str,
    writable_roots: Sequence[Path],
    *,
    platform: str | None = None,
    executable: str | None = _SANDBOX_EXEC,
) -> SandboxPlan:
    """Kipe göre sandbox önekini kur; bilinmeyen/kapalı kipte sandbox yoktur."""
    if mode != SHELL_SANDBOX_WRITE_ROOT:
        return SandboxPlan()
    if (platform or sys.platform) != "darwin":
        return SandboxPlan(
            notice=(
                "runtime.shell_sandbox=write_root yalnız macOS'ta desteklenir; bu sistemde "
                "komutlar sandbox'sız çalışıyor (kip kapalı)."
            )
        )
    if executable is None or not Path(executable).exists():
        return SandboxPlan(
            notice="sandbox-exec bulunamadı; komutlar sandbox'sız çalışıyor (kip kapalı)."
        )
    paths = tuple(
        dict.fromkeys(path.resolve() for path in (*writable_roots, *_temporary_directories()))
    )
    parameters = [item for index, path in enumerate(paths) for item in ("-D", f"W{index}={path}")]
    return SandboxPlan(prefix=(executable, *parameters, "-p", _profile(len(paths))))
