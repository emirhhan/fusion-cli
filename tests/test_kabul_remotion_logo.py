"""Logo kaynak taraması prepared asset sınırını proje adıyla karıştırmaz."""

from __future__ import annotations

from pathlib import Path

from evals.kabul.areas.remotion import _logo_check

LOGO_SOURCE = "export const Intro = () => <LogoReveal src={staticFile('logo.png')} />;"


def write_source(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(LOGO_SOURCE, encoding="utf-8")


def test_project_root_named_like_prepared_assets_is_a_real_source(tmp_path: Path) -> None:
    root = tmp_path / "fusion-tanitim"
    write_source(root / "src/Composition.tsx")
    assert _logo_check(root).passed


def test_nested_project_named_like_assets_is_a_real_source(tmp_path: Path) -> None:
    write_source(tmp_path / "video/fusion-tanitim/src/Composition.tsx")
    assert _logo_check(tmp_path).passed


def test_project_src_sharing_prepared_root_is_not_excluded(tmp_path: Path) -> None:
    write_source(tmp_path / "fusion-tanitim/src/Composition.tsx")
    assert _logo_check(tmp_path).passed


def test_prepared_asset_examples_do_not_prove_logo_use(tmp_path: Path) -> None:
    write_source(tmp_path / "fusion-tanitim/examples/Usage.tsx")
    assert not _logo_check(tmp_path).passed


def test_asset_only_png_does_not_prove_logo_use(tmp_path: Path) -> None:
    asset = tmp_path / "fusion-tanitim/logo.png"
    asset.parent.mkdir()
    asset.write_bytes(b"fake public image fixture")
    assert not _logo_check(tmp_path).passed
