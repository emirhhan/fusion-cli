"""Paketli macOS runtime teslimatının ölçülmüş sonuç raporunu üretir."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
from pathlib import Path
from typing import Any, cast


def human_size(path: Path) -> str:
    """Dosya veya dizinin toplam dosya boyutunu IEC birimleriyle döndür."""
    size = (
        sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
        if path.is_dir()
        else path.stat().st_size
    )
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("ulaşılamaz")


def parse_results(raw: list[str]) -> list[str]:
    """`Ad=değer` biçimindeki çağıran sonuçlarını doğrula."""
    for item in raw:
        name, separator, value = item.partition("=")
        if not separator or not name.strip() or not value.strip():
            raise ValueError(f"Sonuç 'Ad=değer' biçiminde olmalı: {item!r}")
    return raw


def write_report(root: Path, output: Path, results: list[str] | None = None) -> None:
    """Mevcut artefaktlardan sürüm, mimari ve boyut kanıtı üret.

    Kalite kapısı, smoke ve rollback sonuçları BU modülde ölçülmez. Eskiden
    "Python kalite kapısı: geçti (2.514 test)" gibi sabit dizgiler yazılıyordu ve
    hiçbir sonuç okunmadan rapor yeşil görünüyordu (Q1-04, ölçüldü 30 Ekim).
    Artık yalnız çağıranın `results` ile verdiği, gerçekten ölçülmüş sonuçlar
    yazılır; verilmeyen sonuç "Ölçülmedi" olarak açıkça belirtilir.
    """
    runtime_dir = root / "app/src-tauri/resources/runtime"
    manifest = cast(
        dict[str, Any],
        json.loads((runtime_dir / "runtime-manifest.json").read_text(encoding="utf-8")),
    )
    app = root / "app/src-tauri/target/release/bundle/macos/Fusion.app"
    dmg_candidates = list((root / "app/src-tauri/target/release/bundle/dmg").glob("*.dmg"))
    if not dmg_candidates:
        raise FileNotFoundError("DMG artefaktı bulunamadı")
    dmg = max(dmg_candidates, key=lambda path: path.stat().st_mtime_ns)
    commit = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=root, text=True
    ).strip()
    lines = [
        "# Paketli macOS Runtime Sonuç Raporu",
        "",
        f"- Git commit: `{commit}`",
        f"- Mimari: `{platform.machine()}`",
        f"- Runtime hedefi: `{manifest['target']}`",
        f"- Runtime sürümü: `{manifest['runtime_version']}`",
        f"- Runtime dosya sayısı: {len(manifest['files'])}",
        f"- Runtime arşiv boyutu: {human_size(runtime_dir / manifest['archive'])}",
        f"- Fusion.app boyutu: {human_size(app)}",
        f"- DMG boyutu: {human_size(dmg)}",
        *_result_lines(results or []),
        "",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")


def _result_lines(results: list[str]) -> list[str]:
    if not results:
        return [
            "- Kalite kapısı, smoke ve rollback sonuçları: Ölçülmedi "
            "(bu rapor yalnız artefakt sürüm/boyut kanıtıdır)"
        ]
    lines = []
    for item in results:
        name, _, value = item.partition("=")
        lines.append(f"- {name.strip()}: {value.strip()}")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Fusion macOS runtime raporunu üretir.")
    parser.add_argument("--output", required=True, type=Path, help="Markdown rapor yolu")
    parser.add_argument(
        "--sonuc",
        action="append",
        default=[],
        metavar="AD=DEĞER",
        help="Ölçülmüş sonuç satırı (örn. 'Python kalite kapısı=geçti (N test)'); yinelenebilir",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    write_report(root, args.output.resolve(), parse_results(args.sonuc))
    print(f"Rapor yazıldı: {args.output.resolve()}")


if __name__ == "__main__":
    main()
