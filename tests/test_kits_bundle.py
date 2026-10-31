"""Masaüstü paketi Kits'i HER ZAMAN içerir; Kits'siz paket üretmenin yolu yoktur.

Ölçüldü (31 Ekim): `bundle:mac` Kits'siz, `bundle:mac:kits` Kits'li paket üretiyordu.
Kits'siz paket kurulunca uygulama "Bu Fusion paketinde Kits bileşeni bulunamadı"
hatası veriyordu. Kullanıcı kararı: indiren herkes Kits'i kurulu alsın.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
TAURI = APP / "src-tauri"

#: Paket yapılandırması → Kits kaynak eşlemesi (Node ikilisinin adı platforma göre).
KITS_RESOURCES = {
    "tauri.bundle.conf.json": {
        "resources/kits/kits-manifest.json": "kits/kits-manifest.json",
        "resources/kits/node": "kits/node",
        "resources/kits/app/": "kits/app/",
    },
    "tauri.windows.bundle.conf.json": {
        "resources/kits/kits-manifest.json": "kits/kits-manifest.json",
        "resources/kits/node.exe": "kits/node.exe",
        "resources/kits/app/": "kits/app/",
    },
}


def _scripts() -> dict[str, str]:
    package = json.loads((APP / "package.json").read_text(encoding="utf-8"))
    return package["scripts"]


def _resources(config: str) -> dict[str, str]:
    return json.loads((TAURI / config).read_text(encoding="utf-8"))["bundle"]["resources"]


def test_paket_yapilandirmalari_kits_kaynagini_kendisi_esler() -> None:
    """Eşleme paket yapılandırmasının KENDİSİNDE: Kits yoksa her `tauri build` düşer."""
    for config, expected in KITS_RESOURCES.items():
        resources = _resources(config)
        for source, target in expected.items():
            assert resources.get(source) == target, f"{config}: {source} eşlenmemiş"


def test_ayri_kits_yapilandirmasi_kalmadi() -> None:
    assert not (TAURI / "tauri.kits.conf.json").exists()
    assert all("tauri.kits.conf.json" not in command for command in _scripts().values())


def test_paket_komutlari_kits_hazirligiyla_baslar() -> None:
    scripts = _scripts()
    assert scripts["kits:prepare"] == "node scripts/prepare-kits.mjs"
    assert scripts["bundle:mac"].startswith("npm run kits:prepare && ")
    assert scripts["bundle:win"].startswith("npm run kits:prepare && ")
    assert "--config src-tauri/tauri.bundle.conf.json" in scripts["bundle:mac"]
    assert "--config src-tauri/tauri.windows.bundle.conf.json" in scripts["bundle:win"]


def test_eski_kits_komutu_yalniz_takma_addir() -> None:
    assert _scripts()["bundle:mac:kits"] == "npm run bundle:mac"


def test_kitssiz_paket_ureten_komut_yok() -> None:
    """`tauri build` çağıran her komut Kits'i eşleyen bir paket yapılandırması kullanır."""
    for name, command in _scripts().items():
        if "tauri build" not in command:
            continue
        assert "npm run kits:prepare" in command, f"{name} Kits hazırlamadan paketliyor"
        assert any(f"--config src-tauri/{config}" in command for config in KITS_RESOURCES), name
