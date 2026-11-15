"""Sistem panosuna yazma (P-028: `/copy`, `/export pano`).

Harici bağımlılık yok: platformun kendi aracı çağrılır (macOS `pbcopy`, Wayland
`wl-copy`, X11 `xclip`/`xsel`, Windows `clip`). Hiçbiri yoksa başarısız döner ve
kullanıcıya söylenir; sessiz başarı YOK.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass

#: Sırayla denenecek pano komutları (ilk kurulu olan kullanılır).
CLIPBOARD_COMMANDS: tuple[tuple[str, ...], ...] = (
    ("pbcopy",),
    ("wl-copy",),
    ("xclip", "-selection", "clipboard"),
    ("xsel", "--clipboard", "--input"),
    ("clip",),
)
#: Pano aracı bu süreden uzun asılırsa vazgeçilir (saniye).
CLIPBOARD_TIMEOUT_S = 3.0


@dataclass(frozen=True, slots=True)
class ClipboardResult:
    ok: bool
    error: str = ""
    tool: str = ""


def copy_to_clipboard(
    text: str, *, commands: Sequence[Sequence[str]] = CLIPBOARD_COMMANDS
) -> ClipboardResult:
    """Metni panoya yaz. Kurulu araç yoksa ya da araç hata verirse `ok=False`."""
    for command in commands:
        if shutil.which(command[0]) is None:
            continue
        try:
            subprocess.run(
                list(command),
                input=text.encode("utf-8"),
                check=True,
                timeout=CLIPBOARD_TIMEOUT_S,
                capture_output=True,
            )
        except (OSError, subprocess.SubprocessError) as error:
            return ClipboardResult(False, f"{command[0]}: {error}", command[0])
        return ClipboardResult(True, tool=command[0])
    return ClipboardResult(False, "pano aracı bulunamadı (pbcopy/wl-copy/xclip/xsel/clip)")
