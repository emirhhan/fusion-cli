"""Nested gerçek proje kaynakları prepared varlık örneklerinden ayrılır."""

from evals.kabul.areas.remotion import _logo_check, _source_checks


def test_nested_fusion_video_src_gercek_kare_logo_ve_css_ihlali(tmp_path):
    source = tmp_path / "fusion-tanitim/video/src/Composition.tsx"
    source.parent.mkdir(parents=True)
    source.write_text(
        "const frame=useCurrentFrame(); const logo='logo.png'; const style={transition:'all 1s'};"
    )
    css, frame = _source_checks(tmp_path)
    assert not css.passed and frame.passed and _logo_check(tmp_path).passed


def test_private_dependency_symlink_prepared_ornek_basari_degil(tmp_path):
    for directory in ("fusion-tanitim/examples", "node_modules/src", ".private/src", "private/src"):
        path = tmp_path / directory / "demo.tsx"
        path.parent.mkdir(parents=True)
        path.write_text("const f=useCurrentFrame(); const logo='logo.png';")
    outside = tmp_path / "outside.tsx"
    outside.write_text("const f=useCurrentFrame(); const logo='logo.png';")
    src = tmp_path / "src"
    src.mkdir()
    (src / "alias.tsx").symlink_to(outside)
    css, frame = _source_checks(tmp_path)
    assert not css.passed and not frame.passed and not _logo_check(tmp_path).passed


def test_izinli_src_ustune_symlink_yolundan_girilmez(tmp_path):
    external = tmp_path / "external"
    (external / "src").mkdir(parents=True)
    (external / "src/demo.tsx").write_text("const frame=useCurrentFrame(); const logo='logo.png';")
    root = tmp_path / "work"
    root.mkdir()
    (root / "project").symlink_to(external, target_is_directory=True)
    assert not _logo_check(root).passed


def test_derin_agac_ve_buyuk_paket_kaynak_kaniti_degildir(tmp_path):
    from evals.kabul.areas._sources import MAX_FILE_BYTES

    deep = tmp_path / "one/two/three/src/demo.tsx"
    deep.parent.mkdir(parents=True)
    deep.write_text("const frame=useCurrentFrame(); const logo='logo.png';")
    big = tmp_path / "src/huge.tsx"
    big.parent.mkdir()
    big.write_text("const logo='logo.png';" + " " * MAX_FILE_BYTES)
    assert not _logo_check(tmp_path).passed
    assert not _source_checks(tmp_path)[1].passed
