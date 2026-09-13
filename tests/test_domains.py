

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
    # Ana sahne DİSKTE olmalı: aksi hâlde proje çalıştırılabilir sayılmaz.
    (tmp_path / "main.tscn").write_text("[gd_scene format=3]\n", encoding="utf-8")
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
    (tmp_path / "main.tscn").write_text("[gd_scene format=3]\n", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/tile.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (tmp_path / "assets/tile.png.import").write_text("[remap]\n", encoding="utf-8")

    assert godot_adapter().gate_commands(tmp_path) == ("godot --headless --path . --quit",)


def test_yukleyici_bulunamadi_sifir_cikisa_ragmen_hata_sayilir():
    from fusion_cli.engines.agent.domains import godot_adapter

    assert "no loader found" in godot_adapter().zero_exit_failure_markers()


def test_tanimli_ama_diskte_olmayan_ana_sahne_calistirilabilir_saymaz(tmp_path):
    """Ana sahne yolu yazılı olsa da dosya yoksa proje çalıştırılabilir değildir.

    Ölçüldü (13 Eylül, koşu 32): `run/main_scene="res://scenes/main.tscn"` yazıyordu,
    dosya hiç yazılmamıştı. Godot üç satır ERROR bastı ve ÇIKIŞ KODU 0 verdi; proje
    çalıştırılabilir sayıldığı için kurulum kapısı atlandı ve hata teslime kadar geldi.
    """
    from fusion_cli.engines.agent.domains import godot_has_main_scene

    (tmp_path / "project.godot").write_text(
        '[application]\nrun/main_scene="res://scenes/main.tscn"\n', encoding="utf-8"
    )

    assert godot_has_main_scene(tmp_path) is False

    (tmp_path / "scenes").mkdir()
    (tmp_path / "scenes/main.tscn").write_text("[gd_scene format=3]\n", encoding="utf-8")

    assert godot_has_main_scene(tmp_path) is True


def test_sifir_cikisli_sahne_yukleme_hatasi_isaret_sayilir():
    from fusion_cli.engines.agent.domains import godot_adapter

    isaretler = godot_adapter().zero_exit_failure_markers()

    assert "cannot open file" in isaretler
    assert "failed loading" in isaretler
