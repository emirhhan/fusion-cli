"""Godot içe aktarma hazırlığı kökün üst dizin adlarından etkilenmez (A1-15)."""

from __future__ import annotations

import pytest

from fusion_cli.engines.agent.domain_adapters.godot import godot_needs_import


@pytest.mark.parametrize("ust", ["build", ".worktrees", "Application Support"])
def test_iceri_aktarilmamis_varlik_ust_dizin_adina_takilmaz(tmp_path, ust):
    kok = tmp_path / ust / "oyun"
    kok.mkdir(parents=True)
    (kok / "tile.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    assert godot_needs_import(kok) is True


def test_kok_icindeki_gurultu_dizinleri_atlanir(tmp_path):
    (tmp_path / "node_modules" / "paket").mkdir(parents=True)
    (tmp_path / "node_modules" / "paket" / "x.png").write_bytes(b"x")
    (tmp_path / ".godot" / "imported").mkdir(parents=True)
    (tmp_path / ".godot" / "imported" / "y.png").write_bytes(b"x")

    assert godot_needs_import(tmp_path) is False


def test_import_kaydi_olan_varlik_hazir_sayilir(tmp_path):
    (tmp_path / "tile.png").write_bytes(b"x")
    (tmp_path / "tile.png.import").write_text("[remap]")

    assert godot_needs_import(tmp_path) is False
