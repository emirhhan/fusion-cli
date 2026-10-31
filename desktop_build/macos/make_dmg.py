"""Fusion.app için DMG'yi Finder'a (AppleScript) bağlı olmadan üret.

Tauri'nin `bundle_dmg.sh` betiği kurulum penceresini AppleScript ile Finder'a düzenletir;
Finder meşgulken (-15260) paketleme düşüp yarım `rw.*.dmg` bırakıyordu (ölçüldü, 1 Kasım 2026).
Burada DMG doğrudan `hdiutil` ile kurulur: içinde uygulama ve `Applications` kısayolu vardır,
adı Tauri'ninkiyle aynıdır (`Fusion_<sürüm>_<mimari>.dmg`), böylece sonraki kararlı imza,
duman ve güncelleme adımları değişmeden çalışır.
"""

from __future__ import annotations

import argparse
import platform
import plistlib
import subprocess
import tempfile
from pathlib import Path

VOLUME_NAME = "Fusion"
COMMAND_TIMEOUT_SECONDS = 600
_ARCH_NAMES = {"arm64": "aarch64", "aarch64": "aarch64", "x86_64": "x64"}


def _run(*args: str) -> None:
    subprocess.run(
        args, check=True, capture_output=True, text=True, timeout=COMMAND_TIMEOUT_SECONDS
    )


def make_dmg(bundle_root: Path) -> Path:
    """`<bundle_root>/macos/Fusion.app`'ten `<bundle_root>/dmg/Fusion_<sürüm>_<mimari>.dmg` üret."""
    root = bundle_root.resolve()
    app = root / "macos/Fusion.app"
    plist_path = app / "Contents/Info.plist"
    if not plist_path.is_file():
        raise FileNotFoundError(f"Fusion.app bulunamadı: {app}")
    version = plistlib.loads(plist_path.read_bytes())["CFBundleShortVersionString"]
    arch = _ARCH_NAMES.get(platform.machine(), platform.machine())
    out_dir = root / "dmg"
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in [*out_dir.glob("Fusion_*.dmg"), *(root / "macos").glob("rw.*.dmg")]:
        stale.unlink()
    target = out_dir / f"Fusion_{version}_{arch}.dmg"
    with tempfile.TemporaryDirectory(prefix="fusion-dmg-") as raw:
        staging = Path(raw) / "icerik"
        staging.mkdir()
        # `ditto` imzayı, genişletilmiş öznitelikleri ve sembolik bağlantıları korur.
        _run("ditto", str(app), str(staging / "Fusion.app"))
        (staging / "Applications").symlink_to("/Applications")
        _run(
            "hdiutil", "create", "-volname", VOLUME_NAME, "-srcfolder", str(staging),
            "-fs", "HFS+", "-format", "UDZO", "-ov", str(target),
        )  # fmt: skip
    _run("hdiutil", "verify", str(target))
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, required=True)
    args = parser.parse_args()
    print(f"DMG hazır: {make_dmg(args.bundle_root)}")


if __name__ == "__main__":
    main()
