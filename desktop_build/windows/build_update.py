"""Windows NSIS kurucusundan Tauri güncelleme manifesti üret.

macOS tarafının (`desktop_build/macos/build_update.py`) Windows karşılığıdır ve
aynı sözleşmeyi üretir. Ayrı dosya olmasının sebebi biçimin farklı olması: macOS
güncellemesi `.app.tar.gz` arşividir, Windows güncellemesi ise NSIS KURUCUSUNUN
kendisidir (`.exe`); Tauri onu indirip çalıştırır.

Neden gerekli — ölçüldü (alpha.12 release'i): `latest.json` yalnız iki macOS
platformunu taşıyordu. `Fusion-Windows-Kurulum.exe` release'te duruyordu ama
manifestte karşılığı olmadığı için Windows kullanıcıları OTOMATİK GÜNCELLEME
ALAMIYOR, her sürümde elle indirmek zorunda kalıyordu.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

#: Release'e yüklenen dosya adı. Manifestteki URL bununla BİREBİR eşleşmelidir;
#: aksi hâlde updater indiremez (workflow'daki "Kurucuyu anlaşılır bir adla
#: kopyala" adımı bu adı üretir).
ASSET_NAME = "Fusion-Windows-Kurulum.exe"


def build_update(installer: Path, destination: Path, version: str, repository: str) -> Path:
    """Kurucuyu imzala ve `latest.json` yaz; özel anahtarı çıktıya kopyalama."""
    destination.mkdir(parents=True, exist_ok=True)
    hedef = destination / ASSET_NAME
    if installer.resolve() != hedef.resolve():
        shutil.copy2(installer, hedef)

    app_root = Path(__file__).resolve().parents[2] / "app"
    signer = app_root / "node_modules/.bin/tauri"
    command = [
        str(signer),
        "signer",
        "sign",
        "-p",
        os.environ.get("TAURI_SIGNING_PRIVATE_KEY_PASSWORD", ""),
    ]
    if not os.environ.get("TAURI_SIGNING_PRIVATE_KEY"):
        raise ValueError("Güncelleme imza anahtarı verilmedi.")
    command.append(str(hedef))
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, timeout=180)

    imza = Path(str(hedef) + ".sig")
    if not imza.is_file():
        raise FileNotFoundError(f"İmza üretilmedi: {imza}")
    manifest = {
        "version": version,
        "notes": "Fusion masaüstü güncellemesi. Çalışan görevleri tamamladıktan sonra kur.",
        "platforms": {
            "windows-x86_64": {
                "signature": imza.read_text().strip(),
                "url": (
                    f"https://github.com/{repository}/releases/download/v{version}/{ASSET_NAME}"
                ),
            }
        },
    }
    hedef_manifest = destination / "latest.json"
    hedef_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return hedef_manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installer", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument(
        "--repository", default=os.environ.get("GITHUB_REPOSITORY", "emirhhan/fusion-cli")
    )
    args = parser.parse_args()
    build_update(args.installer, args.output, args.version, args.repository)
