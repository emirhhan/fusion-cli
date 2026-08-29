"""Paketlenmiş Fusion.app içeriğini ve temiz kullanıcı açılışını doğrular."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import subprocess
import tempfile
from pathlib import Path
from typing import Any, cast

_TIMEOUT_SECONDS = 120


def inspect_bundle(app: Path) -> dict[str, Any]:
    """Bundle kimliğini, runtime manifestini, hedefi ve arşiv özetini doğrula."""
    plist = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    assert plist["CFBundleIdentifier"] == "com.fusion.desktop"
    resources = app / "Contents/Resources/runtime"
    manifest = cast(
        dict[str, Any],
        json.loads((resources / "runtime-manifest.json").read_text(encoding="utf-8")),
    )
    archive = resources / manifest["archive"]
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == manifest["archive_sha256"]
    assert manifest["target"] in {"aarch64-apple-darwin", "x86_64-apple-darwin"}
    return manifest


def _launch(app: Path, home: Path) -> None:
    """Uygulamayı LaunchServices üzerinden, açık temiz HOME ile başlat ve bekle."""
    result = subprocess.run(
        [
            "open",
            "-W",
            "-n",
            "-j",
            "--env",
            f"HOME={home}",
            str(app),
            "--args",
            "--runtime-smoke",
        ],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        env=os.environ,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def launch_clean(app: Path) -> None:
    """Yeni HOME'da ilk ve ikinci açılışı doğrula; ikinci açılış yeniden kurmamalı."""
    with tempfile.TemporaryDirectory(prefix="fusion-clean-home-") as raw_home:
        home = Path(raw_home)
        runtime = home / "Library/Application Support/Fusion/runtime"
        active = runtime / "active-runtime.json"
        marker = runtime / "runtime-smoke-ok"

        _launch(app, home)
        assert active.is_file(), "İlk açılış etkin runtime kaydını oluşturmadı"
        assert marker.is_file(), "İlk açılış app protokolü smoke kaydını oluşturmadı"
        first_record = active.read_bytes()
        first_mtime = active.stat().st_mtime_ns

        marker.unlink()
        _launch(app, home)
        assert marker.is_file(), "İkinci açılış app protokolünü tamamlamadı"
        assert active.read_bytes() == first_record
        assert active.stat().st_mtime_ns == first_mtime, "İkinci açılış runtime'ı yeniden kurdu"


def main() -> None:
    parser = argparse.ArgumentParser(description="Fusion.app dağıtım paketini doğrular.")
    parser.add_argument("app", type=Path, help="Doğrulanacak Fusion.app yolu")
    parser.add_argument(
        "--inspect-only",
        action="store_true",
        help="Uygulamayı açmadan yalnız bundle içeriğini doğrula",
    )
    args = parser.parse_args()
    app = args.app.resolve()

    manifest = inspect_bundle(app)
    if not args.inspect_only:
        launch_clean(app)
    print(f"Uygulama paketi doğrulandı: {manifest['runtime_version']} · {manifest['target']}")


if __name__ == "__main__":
    main()
