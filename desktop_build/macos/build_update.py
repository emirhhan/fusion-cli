"""Son imzalanmış Fusion.app paketinden Tauri güncellemesi üret."""

from __future__ import annotations

import argparse
import json
import os
import platform
import plistlib
import subprocess
import sys
import tarfile
from pathlib import Path

# Betik olarak çalıştırıldığında depo kökü içe aktarma yoluna eklenir.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from desktop_build.kits_bundle import describe, inspect_kits

#: Sürüm notu verilmezse manifeste yazılan metin; uygulama bunu "Sürüm notları" olarak gösterir.
DEFAULT_NOTES = "Fusion masaüstü güncellemesi. Çalışan görevleri tamamladıktan sonra kur."


def build_update(
    app: Path,
    destination: Path,
    key: Path | None,
    repository: str,
    notes: str = DEFAULT_NOTES,
) -> None:
    """DMG ile aynı uygulamayı arşivle; özel anahtarı çıktıya kopyalama.

    `notes` manifestin `notes` alanına düz metin olarak yazılır (P-066): masaüstü
    Ayarlar › Güncellemeler bunu "Sürüm notları" başlığında gösterir. HTML yorumlanmaz.
    Kits'siz uygulama güncelleme olarak yayınlanmaz (arşivlemeden önce düşer).
    """
    kits = inspect_kits(app / "Contents/Resources/kits", node_name="node", macos=True)
    print(f"Güncellemeye giren {describe(kits)}")
    version = plistlib.loads((app / "Contents/Info.plist").read_bytes())[
        "CFBundleShortVersionString"
    ]
    architecture = "aarch64" if platform.machine() == "arm64" else "x86_64"
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / f"Fusion-{version}-darwin-{architecture}.app.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        output.add(app, arcname="Fusion.app", recursive=True)
    app_root = Path(__file__).resolve().parents[2] / "app"
    command = [
        str(app_root / "node_modules/.bin/tauri"),
        "signer",
        "sign",
        "-p",
        os.environ.get("TAURI_SIGNING_PRIVATE_KEY_PASSWORD", ""),
    ]
    if key:
        command.extend(["-f", str(key)])
    elif not os.environ.get("TAURI_SIGNING_PRIVATE_KEY"):
        raise ValueError("Güncelleme imza anahtarı verilmedi.")
    command.append(str(archive))
    subprocess.run(
        command,
        check=True,
        stdout=subprocess.DEVNULL,
        timeout=120,
    )
    manifest = {
        "version": version,
        "notes": notes.strip() or DEFAULT_NOTES,
        "platforms": {
            f"darwin-{architecture}": {
                "signature": Path(str(archive) + ".sig").read_text().strip(),
                "url": f"https://github.com/{repository}/releases/download/v{version}/{archive.name}",
            }
        },
    }
    (destination / "latest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--key", type=Path)
    parser.add_argument("--repository", default="emirhhan/fusion-cli")
    parser.add_argument("--notes", help="Sürüm notu (düz metin); uygulamada gösterilir.")
    parser.add_argument(
        "--notes-file", type=Path, help="Sürüm notunu dosyadan oku (ör. CHANGELOG bölümü)."
    )
    args = parser.parse_args()
    release_notes = (
        args.notes_file.read_text(encoding="utf-8")
        if args.notes_file
        else (args.notes or DEFAULT_NOTES)
    )
    build_update(
        args.app.resolve(),
        args.output.resolve(),
        args.key.resolve() if args.key else None,
        args.repository,
        notes=release_notes,
    )
