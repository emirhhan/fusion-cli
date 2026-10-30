"""Tauri paket yapılandırması: Chrome eklentisi dosyaları eklenti dizinindekilerle birebir aynıdır.

Ölçüldü (30 Ekim): eklenti dosyaları iki paket dosyasında tek tek listeli; eklenti dizinine
yeni betik eklenip listeye yazılmazsa paketli uygulamada sessizce eksik kalırdı (R2-21).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAURI = ROOT / "app" / "src-tauri"
EXTENSION = ROOT / "chrome-extension"
PREFIX = "../../chrome-extension/"
BUNDLES = ("tauri.bundle.conf.json", "tauri.windows.bundle.conf.json")


def _listed(config: str) -> set[str]:
    resources = json.loads((TAURI / config).read_text(encoding="utf-8"))["bundle"]["resources"]
    return {source.removeprefix(PREFIX) for source in resources if source.startswith(PREFIX)}


def _on_disk() -> set[str]:
    return {
        path.relative_to(EXTENSION).as_posix()
        for path in EXTENSION.rglob("*")
        if path.is_file() and not path.name.startswith(".")
    }


def test_paketlenen_eklenti_dosyalari_dizindekilerle_birebir_ayni() -> None:
    disk = _on_disk()
    for config in BUNDLES:
        listed = _listed(config)
        assert listed == disk, (
            f"{config}: eksik={sorted(disk - listed)} fazla={sorted(listed - disk)}"
        )


def test_iki_platformun_eklenti_listesi_ayni() -> None:
    assert _listed(BUNDLES[0]) == _listed(BUNDLES[1])
