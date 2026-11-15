"""Ctrl+V görüntü yapıştırma (#216, Claude Code `chat:imagePaste`).

Claude Code: Ctrl+V panodaki görüntüyü yapıştırır ve imlecin olduğu yere `[Image #N]`
çipi koyar; gönderimde görüntü mesaja eklenir. Metin yapıştırma terminalin kendi
yapıştırmasıdır (Cmd+V / bracketed paste), Ctrl+V değildir.

Fusion: panodaki görüntü platform aracıyla bir PNG dosyasına yazılır (macOS `osascript`,
Wayland `wl-paste`, X11 `xclip`), çip girdiye girer. Gönderimde satırdaki çiplerin
dosyaları veri URI'sine çevrilip tura iliştirilir; çip metni mesajda kalır (Claude ile aynı).
Harici bağımlılık yoktur; araç yoksa ya da panoda görüntü yoksa `None` döner ve kullanıcıya
söylenir.
"""

from __future__ import annotations

import base64
import logging
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

_LOG = logging.getLogger(__name__)

#: Çip biçimi Claude Code ile aynı.
CHIP = "[Image #{index}]"
_CHIP_RE = re.compile(r"\[Image #(\d+)\]")
#: Pano aracı bu süreden uzun asılırsa vazgeçilir (saniye).
TIMEOUT_S = 5.0
#: Modele gönderilecek en büyük görüntü (bayt); masaüstü ekleriyle aynı sınır.
MAX_IMAGE_BYTES = 20 * 1024 * 1024
NO_IMAGE = "Panoda görüntü yok (Ctrl+V yalnız görüntü yapıştırır; metin için Cmd+V)."

Runner = Callable[..., "subprocess.CompletedProcess[bytes]"]

_MAC_SCRIPT = (
    "on run argv\n"
    "try\n"
    "set png to (the clipboard as «class PNGf»)\n"
    "on error\n"
    'return "yok"\n'
    "end try\n"
    "set handle to open for access (POSIX file (item 1 of argv)) with write permission\n"
    "set eof handle to 0\n"
    "write png to handle\n"
    "close access handle\n"
    'return "tamam"\n'
    "end run"
)


def _commands(target: Path, platform: str) -> list[tuple[tuple[str, ...], bool]]:
    """(komut, çıktı stdout'a mı) çiftleri; ilk kurulu olan denenir."""
    if platform == "darwin":
        return [(("osascript", "-e", _MAC_SCRIPT, str(target)), False)]
    return [
        (("wl-paste", "--no-newline", "--type", "image/png"), True),
        (("xclip", "-selection", "clipboard", "-t", "image/png", "-o"), True),
    ]


def read_clipboard_image(
    target: Path,
    *,
    runner: Runner = subprocess.run,
    which: Callable[[str], str | None] = shutil.which,
    platform: str = sys.platform,
) -> bool:
    """Panodaki görüntüyü `target` PNG dosyasına yaz; görüntü yoksa ya da araç yoksa False."""
    target.parent.mkdir(parents=True, exist_ok=True)
    for command, to_stdout in _commands(target, platform):
        if which(command[0]) is None:
            continue
        try:
            done = runner(list(command), capture_output=True, timeout=TIMEOUT_S, check=False)
        except (OSError, subprocess.SubprocessError) as error:
            _LOG.debug("pano görüntüsü okunamadı (%s): %s", command[0], error)
            continue
        if done.returncode != 0:
            continue
        if to_stdout:
            if not done.stdout.startswith(b"\x89PNG"):
                continue
            target.write_bytes(done.stdout)
        elif not target.is_file() or target.stat().st_size == 0:
            continue
        return True
    return False


def data_uri(path: Path) -> str | None:
    """PNG dosyasını modele iliştirilebilir veri URI'sine çevir; okunamazsa None."""
    try:
        if path.stat().st_size > MAX_IMAGE_BYTES:
            return None
        raw = path.read_bytes()
    except OSError:
        return None
    return f"data:image/png;base64,{base64.b64encode(raw).decode('ascii')}"


class ImageChips:
    """Yapıştırılan görüntüler: çip numarası → dosya. Oturum boyunca numara artar."""

    def __init__(self, directory: Path, reader: Callable[[Path], bool] | None = None) -> None:
        self._directory = directory
        self._reader = reader or read_clipboard_image
        self._paths: dict[int, Path] = {}
        self._seq = 0

    def paste(self) -> str | None:
        """Panodaki görüntüyü kaydet ve çipini döndür; görüntü yoksa None."""
        index = self._seq + 1
        target = self._directory / f"image-{index}.png"
        if not self._reader(target):
            return None
        self._seq = index
        self._paths[index] = target
        return CHIP.format(index=index)

    def take(self, line: str) -> tuple[str, ...]:
        """Satırdaki çiplerin görüntüleri (veri URI); kullanılan çipler bırakılır."""
        images: list[str] = []
        for match in _CHIP_RE.finditer(line):
            path = self._paths.pop(int(match.group(1)), None)
            uri = data_uri(path) if path is not None else None
            if uri is not None:
                images.append(uri)
        return tuple(images)
