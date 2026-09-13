

def test_iceaktarilmamis_varlik_varsa_kapi_once_iceaktarir(tmp_path):
    """Godot bir PNG'yi ancak içe aktardıktan sonra yükleyebilir.

    Ölçüldü (13 Eylül, Godot koşusu): 400 karo indirilip açıldı, kod doğru yolu
    yüklüyordu ve motor `No loader found for resource: .../tile_0000.png` bastı —
    çıkış kodu 0'dı. Kapı "proje açılıyor" derken oyun ilk karede düşüyordu.
    """
    from fusion_cli.engines.agent.domains import godot_adapter

    (tmp_path / "project.godot").write_text(
        '[application]\nrun/main_scene="res://main.tscn"\n', encoding="utf-8"
    )
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/tile.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    komutlar = godot_adapter().gate_commands(tmp_path)

    assert komutlar[0] == "godot --headless --path . --editor --quit"
    assert komutlar[-1] == "godot --headless --path . --quit"


def test_iceaktarilmis_varlikta_fazladan_komut_yok(tmp_path):
    from fusion_cli.engines.agent.domains import godot_adapter

    (tmp_path / "project.godot").write_text(
        '[application]\nrun/main_scene="res://main.tscn"\n', encoding="utf-8"
    )
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/tile.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (tmp_path / "assets/tile.png.import").write_text("[remap]\n", encoding="utf-8")

    assert godot_adapter().gate_commands(tmp_path) == ("godot --headless --path . --quit",)


def test_yukleyici_bulunamadi_sifir_cikisa_ragmen_hata_sayilir():
    from fusion_cli.engines.agent.domains import godot_adapter

    assert "no loader found" in godot_adapter().zero_exit_failure_markers()
