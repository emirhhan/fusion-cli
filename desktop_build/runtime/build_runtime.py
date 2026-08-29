"""Deterministik PyInstaller `onedir` paketini üretir ve SHA-256 manifestini yazar.

`onefile` yerine `onedir` seçildi: `onefile` her açılışta kendini geçici dizine
açar (başlangıç gecikir, bütünlük doğrulaması imkânsızlaşır); `onedir` bir kez
kurulur ve bu modülün ürettiği manifestle doğrulanır. Arşiv üyeleri yol adına
göre sıralı yazılır, uid/gid/uname/gname/mtime sabitlenir ve gzip başlığı
mtime=0 ile açılır — aynı girdi her zaman aynı baytları üretir.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

from fusion_cli import __version__

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC_PATH = Path(__file__).resolve().parent / "fusion_runtime.spec"
_BUNDLE_NAME = "fusion-runtime"


def macos_target(machine: str) -> str:
    """Verilen makine mimarisini Tauri hedef üçlüsüne çevirir."""
    names = {
        "arm64": "aarch64-apple-darwin",
        "aarch64": "aarch64-apple-darwin",
        "x86_64": "x86_64-apple-darwin",
    }
    try:
        return names[machine.casefold()]
    except KeyError as error:
        raise ValueError(f"Desteklenmeyen macOS mimarisi: {machine}") from error


def sha256_file(path: Path) -> str:
    """Dosyanın SHA-256 özetini akış halinde hesaplar (büyük ikililer için)."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_archive(root: Path, destination: Path) -> None:
    """`root` altındaki dosyaları deterministik bir tar.gz arşivine yazar."""
    with (
        destination.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive,
    ):
        for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
            relative = path.relative_to(root).as_posix()
            info = archive.gettarinfo(str(path), arcname=relative)
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            if info.isfile():
                with path.open("rb") as source:
                    archive.addfile(info, source)
            else:
                archive.addfile(info)


def _manifest_entry(path: Path, root: Path) -> dict[str, Any]:
    """Tek bir dosya/dizin/symlink için manifest satırı üretir.

    Symlink kontrolü `is_file` kontrolünden ÖNCE yapılır: bir symlink dosyaya
    işaret ediyorsa `is_file()` de True döner ve gerçek hedefi kaçırırız.
    """
    relative = path.relative_to(root).as_posix()
    mode = path.lstat().st_mode & 0o777
    if path.is_symlink():
        return {"path": relative, "kind": "symlink", "mode": mode, "target": str(path.readlink())}
    if path.is_file():
        return {"path": relative, "kind": "file", "mode": mode, "sha256": sha256_file(path)}
    return {"path": relative, "kind": "directory", "mode": mode}


def build_manifest(root: Path, archive: Path, *, version: str, target: str) -> dict[str, Any]:
    """Paketlenmiş çalışma zamanı için SHA-256 bütünlük manifestini üretir."""
    files = [
        _manifest_entry(path, root)
        for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
        if path.is_symlink() or not path.is_dir()
    ]
    return {
        "schema": 1,
        "runtime_version": version,
        "target": target,
        "archive": archive.name,
        "archive_sha256": sha256_file(archive),
        "entrypoint": "fusion",
        "files": files,
    }


def _run_pyinstaller(dist_path: Path, build_path: Path) -> None:
    """PyInstaller'ı depo kökünden `onedir` tarifiyle çalıştırır."""
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            "--distpath",
            str(dist_path),
            "--workpath",
            str(build_path),
            str(_SPEC_PATH),
        ],
        cwd=_REPO_ROOT,
        check=True,
    )


def build_runtime(output_dir: Path, work_dir: Path) -> tuple[Path, Path]:
    """Bağımsız çalışma zamanını derler, deterministik arşivler ve manifesti yazar.

    Her çağrı `output_dir` içindeki yalnızca kendi ürettiği üç yolu ve kendisine
    ait `work_dir` dizinini temizler. Böylece çıktı klasöründeki izlenen README
    gibi depo dosyaları korunur. Smoke testinin doğrudan çalıştırabilmesi için
    `output_dir/unpacked` altına paketin açık kopyası da bırakılır.
    """
    for generated in ("runtime-manifest.json", "fusion-runtime.tar.gz", "unpacked"):
        path = output_dir / generated
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
    shutil.rmtree(work_dir, ignore_errors=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    dist_path = work_dir / "dist"
    build_path = work_dir / "build"
    _run_pyinstaller(dist_path, build_path)

    bundle_root = dist_path / _BUNDLE_NAME
    archive_path = output_dir / "fusion-runtime.tar.gz"
    write_archive(bundle_root, archive_path)

    manifest = build_manifest(
        bundle_root, archive_path, version=__version__, target=macos_target(platform.machine())
    )
    manifest_path = output_dir / "runtime-manifest.json"
    manifest_text = json.dumps(manifest, sort_keys=True, indent=2) + "\n"
    manifest_path.write_text(manifest_text, encoding="utf-8")

    shutil.copytree(bundle_root, output_dir / "unpacked")

    return archive_path, manifest_path


def main() -> None:
    """CLI girişi: `--output` altına deterministik çalışma zamanı paketini üretir."""
    parser = argparse.ArgumentParser(description="Fusion masaüstü çalışma zamanını paketler.")
    parser.add_argument("--output", required=True, type=Path, help="Paket çıktı dizini")
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=_REPO_ROOT / "build" / "desktop-runtime-work",
        help="PyInstaller ara üretim dizini",
    )
    args = parser.parse_args()

    archive_path, manifest_path = build_runtime(args.output.resolve(), args.work_dir.resolve())
    print(f"Arşiv: {archive_path}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
