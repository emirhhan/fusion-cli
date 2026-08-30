"""Konuşma tanıma yardımcısını derle ve uygulama kaynaklarına koy.

Swift derleyicisi yoksa SESSİZCE geçilmez: sebep söylenir ve paketleme
yardımcısız sürer — konuşma tanıma o pakette kapalı olur.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SOURCE = Path(__file__).resolve().parent / "main.swift"
_OUTPUT = _ROOT / "app" / "src-tauri" / "resources" / "fusion-listen"


def build() -> bool:
    """Yardımcıyı derle. Başarılıysa True döner."""
    if sys.platform != "darwin":
        print("Konuşma yardımcısı yalnız macOS'ta derlenir; atlandı.")
        return False
    if shutil.which("swiftc") is None:
        print("swiftc bulunamadı; konuşma tanıma bu pakette kapalı olacak.")
        return False
    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["swiftc", "-O", "-o", str(_OUTPUT), str(_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"Konuşma yardımcısı derlenemedi:\n{result.stderr}")
        return False
    print(f"Konuşma yardımcısı hazır: {_OUTPUT} ({_OUTPUT.stat().st_size // 1024} KB)")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if build() else 1)
