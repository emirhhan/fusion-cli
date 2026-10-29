"""Godot kapıları proje kökünün ÜST dizin adlarından etkilenmez (C1-04).

Ölçüldü (29 Ekim): `any(part in SKIP_DIRECTORIES or part.startswith("."))` mutlak yolun
tüm bileşenlerine uygulanıyordu; proje `/…/build/oyun` ya da `~/.worktrees/oyun` altındaysa
her dosya atlanıyor, kapılar hayalet geçiyordu. Süzgeç yalnız kökten göreli parçalara bakar.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.core.assets import _locate_by_name, unused_manifest_assets
from fusion_cli.core.cross_file import broken_resource_paths, scripts_without_base

UST_DIZINLER = ["build", ".worktrees", "Application Support"]


def _kok(tmp_path: Path, ust: str) -> Path:
    kok = tmp_path / ust / "oyun"
    kok.mkdir(parents=True)
    return kok


@pytest.mark.parametrize("ust", UST_DIZINLER)
def test_kullanilmayan_varlik_ust_dizin_adindan_etkilenmez(tmp_path, ust):
    kok = _kok(tmp_path, ust)
    (kok / "Tiles").mkdir()
    (kok / "Tiles/tile_0000.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (kok / "main.tscn").write_text('[gd_scene format=3]\n[node name="Main" type="Node2D"]\n')
    manifest = kok / "ASSETS.json"
    manifest.write_text(json.dumps({"license": "CC0", "files": ["Tiles/tile_0000.png"]}))

    assert unused_manifest_assets(manifest, kok) == ("Tiles/tile_0000.png",)


@pytest.mark.parametrize("ust", UST_DIZINLER)
def test_kirik_res_yolu_ust_dizin_adindan_etkilenmez(tmp_path, ust):
    kok = _kok(tmp_path, ust)
    (kok / "player.gd").write_text(
        'extends Node2D\n\nfunc _ready():\n\tvar t = load("res://assets/yanlis.png")\n',
        encoding="utf-8",
    )

    assert len(broken_resource_paths(kok)) == 1


@pytest.mark.parametrize("ust", UST_DIZINLER)
def test_tabansiz_script_ust_dizin_adindan_etkilenmez(tmp_path, ust):
    kok = _kok(tmp_path, ust)
    (kok / "player.gd").write_text(
        "const SPEED = 300.0\n\nfunc _physics_process(_d):\n"
        "\tvelocity.x = SPEED\n\tmove_and_slide()\n",
        encoding="utf-8",
    )

    assert len(scripts_without_base(kok)) == 1


@pytest.mark.parametrize("ust", UST_DIZINLER)
def test_ada_gore_konum_ust_dizin_adindan_etkilenmez(tmp_path, ust):
    kok = _kok(tmp_path, ust)
    (kok / "Tiles").mkdir()
    (kok / "Tiles/tile_0000.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    assert _locate_by_name("tile_0000.png", kok) == "Tiles/tile_0000.png"


def test_kok_icindeki_build_ve_nokta_dizinleri_yine_atlanir(tmp_path):
    """Kökün İÇİNDEKİ nokta dizinleri (.git) kaynak sayılmaz (önceki sözleşme korunur)."""
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git/x.gd").write_text("func f():\n\tmove_and_slide()\n", encoding="utf-8")

    assert scripts_without_base(tmp_path) == ()
