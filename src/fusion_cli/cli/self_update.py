"""`fusion update` ve `fusion install [sürüm]` — Claude Code gibi kendini günceller (#308).

Claude Code `claude update` en son sürüme kendini günceller, `claude install [version]`
belirli sürümü (ya da `stable`/`latest`) kurar. Fusion'da güncelleme kurulum yöntemine
göre paket yöneticisine devredilir (`uv tool upgrade`, `pipx upgrade`): çalışan süreç kendi
dosyalarını değiştirmez, işi yöneticinin ayrı süreci yapar. Yöntem bilinmiyorsa (depo içi
`.venv`, elle kurulum) komut çalıştırılmaz, ne yapılacağı gösterilir ve 1 ile çıkılır.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence

from ..install import InstallMethod, update_command
from ..install.methods import PACKAGE

Runner = Callable[[Sequence[str]], int]
#: Claude'un sürüm takma adları: sabit sürüm iğnelemez.
_UNPINNED = frozenset({"", "latest", "stable"})


def update_argv(method: InstallMethod) -> list[str] | None:
    """Bu kurulumu en son sürüme getiren komut; yöntem bilinmiyorsa None."""
    if method is InstallMethod.UV:
        return ["uv", "tool", "upgrade", PACKAGE]
    if method is InstallMethod.PIPX:
        return ["pipx", "upgrade", PACKAGE]
    return None


def install_argv(method: InstallMethod, version: str = "") -> list[str] | None:
    """Belirli sürümü (ya da en sonu) kuran komut; yöntem bilinmiyorsa None."""
    wanted = version.strip().lower()
    spec = PACKAGE if wanted in _UNPINNED else f"{PACKAGE}=={version.strip()}"
    if method is InstallMethod.UV:
        return ["uv", "tool", "install", "--force", spec]
    if method is InstallMethod.PIPX:
        return ["pipx", "install", "--force", spec]
    return None


def default_runner(argv: Sequence[str]) -> int:
    """Komutu çalıştır; çıktısı doğrudan kullanıcının terminaline akar."""
    try:
        return subprocess.run(list(argv), check=False).returncode
    except OSError:
        return 127


def run_maintenance(
    argv: list[str] | None, method: InstallMethod, *, runner: Runner = default_runner
) -> tuple[int, str]:
    """Komutu çalıştır: (çıkış kodu, kullanıcıya gösterilecek ek metin)."""
    if argv is None:
        return 1, update_command(method)
    code = runner(argv)
    if code == 0:
        return 0, ""
    return code, update_command(method)
