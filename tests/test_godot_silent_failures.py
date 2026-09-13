"""Motorun HİÇ hata basmadığı iki Godot tuzağı.

İkisi de 13 Eylül Godot koşusunda ölçüldü: proje sıfır çıkışla açıldı, bütün
kapılar geçti, kullanıcı oyunu açtı ve karakter hiçbir tuşa cevap vermedi.
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.core.cross_file import promised_key_conflicts, runtime_script_conflicts

RELOADSUZ = '''extends Node2D

func _ready():
\tvar p = CharacterBody2D.new()
\tvar script = GDScript.new()
\tscript.source_code = "extends CharacterBody2D"
\tp.set_script(script)
\tadd_child(p)
'''

RELOADLU = RELOADSUZ.replace("\tp.set_script(script)", "\tscript.reload()\n\tp.set_script(script)")


def _proje(kok: Path, *, input_bolumu: bool = False) -> None:
    metin = '[application]\nconfig/name="oyun"\n'
    if input_bolumu:
        metin += '\n[input]\n\nmove_left={"deadzone": 0.5}\n'
    (kok / "project.godot").write_text(metin, encoding="utf-8")


def test_reloadsuz_uretilen_script_bildirilir(tmp_path):
    """`reload()` yoksa script derlenmez; motor tek satır hata basmaz.

    Ölçüldü: aynı kalıp `reload()` ile ve onsuz çalıştırıldı; yalnız `reload()`
    olan çalıştı, öteki sessizce ölü kaldı.
    """
    (tmp_path / "main.gd").write_text(RELOADSUZ, encoding="utf-8")

    bulgular = runtime_script_conflicts(tmp_path)

    assert len(bulgular) == 1
    assert "reload()" in bulgular[0]
    assert "main.gd" in bulgular[0]


def test_reloadlu_script_bildirilmez(tmp_path):
    (tmp_path / "main.gd").write_text(RELOADLU, encoding="utf-8")

    assert runtime_script_conflicts(tmp_path) == ()


def test_sadece_set_script_kullanan_kod_bildirilmez(tmp_path):
    """Diskteki bir script'i bağlamak farklıdır; onun derlenmişi zaten vardır."""
    (tmp_path / "main.gd").write_text(
        'extends Node2D\n\nfunc _ready():\n\tp.set_script(load("res://player.gd"))\n',
        encoding="utf-8",
    )

    assert runtime_script_conflicts(tmp_path) == ()


def test_soz_verilen_tus_baglanmamissa_bildirilir(tmp_path):
    """Kullanıcıya gösterilen tuş, bağlanmamış tuş olamaz.

    Ölçüldü: HUD "[HAREKET: A/D veya OKLAR]" yazıyordu, `project.godot` içinde hiç
    `[input]` yoktu ve kod yalnız yerleşik `ui_*` eylemlerini okuyordu.
    """
    _proje(tmp_path)
    (tmp_path / "main.gd").write_text(
        'extends Node2D\n\nfunc _ready():\n\tlabel.text = "[HAREKET: A/D veya OKLAR]"\n',
        encoding="utf-8",
    )

    bulgular = promised_key_conflicts(tmp_path)

    assert len(bulgular) == 1
    assert "A, D" in bulgular[0]


def test_kod_tusu_dogrudan_okuyorsa_bildirilmez(tmp_path):
    _proje(tmp_path)
    (tmp_path / "main.gd").write_text(
        'extends Node2D\n\nfunc _ready():\n\tlabel.text = "[SALDIR: A/D]"\n'
        "\nfunc _process(_d):\n\tif Input.is_key_pressed(KEY_A) or Input.is_key_pressed(KEY_D):\n"
        "\t\tpass\n",
        encoding="utf-8",
    )

    assert promised_key_conflicts(tmp_path) == ()


def test_girdi_eslemesi_tanimliysa_kapi_sessiz_kalir(tmp_path):
    """Eşlemenin içeriği burada çözülmez; varsa iddia edilmez."""
    _proje(tmp_path, input_bolumu=True)
    (tmp_path / "main.gd").write_text(
        'extends Node2D\n\nfunc _ready():\n\tlabel.text = "[HAREKET: A/D]"\n', encoding="utf-8"
    )

    assert promised_key_conflicts(tmp_path) == ()


def test_godot_projesi_olmayan_kokte_iddia_yok(tmp_path):
    (tmp_path / "main.gd").write_text('label.text = "[HAREKET: A/D]"\n', encoding="utf-8")

    assert promised_key_conflicts(tmp_path) == ()


SAHNE_SPRITESIZ = '''[gd_scene format=3]

[ext_resource type="Script" path="res://player.gd" id="1"]

[node name="Main" type="Node2D"]

[node name="Player" type="CharacterBody2D" parent="."]
script = ExtResource("1")

[node name="CollisionShape2D" type="CollisionShape2D" parent="Player"]
'''

SAHNE_SPRITELI = SAHNE_SPRITESIZ + '\n[node name="Sprite2D" type="Sprite2D" parent="Player"]\n'

PLAYER_GD = (
    "extends CharacterBody2D\n\n@onready var sprite: Sprite2D = $Sprite2D\n\n"
    "func _physics_process(_d):\n\tsprite.flip_h = true\n"
)


def test_sahnede_olmayan_cocuk_dugum_bildirilir(tmp_path):
    """`$Sprite2D` yoksa değişken null olur ve oyun ilk kullanımda çöker.

    Ölçüldü (13 Eylül, koşu 26): `player.gd` `$Sprite2D` bekliyordu, sahnedeki
    Player düğümünün tek çocuğu `CollisionShape2D` idi. Proje başsız açıldı,
    bütün kapılar geçti ve koşu "tamamlandı" raporlandı.
    """
    from fusion_cli.core.cross_file import missing_node_references

    (tmp_path / "player.gd").write_text(PLAYER_GD, encoding="utf-8")
    (tmp_path / "main.tscn").write_text(SAHNE_SPRITESIZ, encoding="utf-8")

    bulgular = missing_node_references(tmp_path)

    assert len(bulgular) == 1
    assert "$Sprite2D" in bulgular[0]
    assert "player.gd" in bulgular[0]


def test_cocuk_dugum_varsa_bildirilmez(tmp_path):
    from fusion_cli.core.cross_file import missing_node_references

    (tmp_path / "player.gd").write_text(PLAYER_GD, encoding="utf-8")
    (tmp_path / "main.tscn").write_text(SAHNE_SPRITELI, encoding="utf-8")

    assert missing_node_references(tmp_path) == ()


def test_yol_iceren_referans_hakkinda_iddia_edilmez(tmp_path):
    """`$UI/Label` çok parçalıdır; kapı dar kalır ve sessizdir."""
    from fusion_cli.core.cross_file import missing_node_references

    (tmp_path / "player.gd").write_text(
        "extends CharacterBody2D\n\n@onready var l = $UI/Label\n", encoding="utf-8"
    )
    (tmp_path / "main.tscn").write_text(SAHNE_SPRITESIZ, encoding="utf-8")

    assert missing_node_references(tmp_path) == ()


def test_scriptsiz_sahne_hakkinda_iddia_edilmez(tmp_path):
    from fusion_cli.core.cross_file import missing_node_references

    (tmp_path / "main.tscn").write_text(
        '[gd_scene format=3]\n\n[node name="Main" type="Node2D"]\n', encoding="utf-8"
    )

    assert missing_node_references(tmp_path) == ()


def test_diskte_olmayan_res_yolu_bildirilir(tmp_path):
    """Yükleme sessizce başarısız olur; motor tek satır hata basmaz.

    Ölçüldü (13 Eylül, koşu 28): paket `Grassland Platformer Art **With Slopes**`
    klasörüne açıldı (ad yıldızlı), kod yıldızsız yolu yüklüyordu.
    `ResourceLoader.exists()` false döndü, doku hiç yüklenmedi, kapılar geçti ve
    koşu "tamamlandı" dedi; oyun bomboş açıldı.
    """
    from fusion_cli.core.cross_file import broken_resource_paths

    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/gercek.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (tmp_path / "player.gd").write_text(
        'extends Node2D\n\nfunc _ready():\n\tvar t = load("res://assets/yanlis.png")\n',
        encoding="utf-8",
    )

    bulgular = broken_resource_paths(tmp_path)

    assert len(bulgular) == 1
    assert "assets/yanlis.png" in bulgular[0]


def test_var_olan_res_yolu_bildirilmez(tmp_path):
    from fusion_cli.core.cross_file import broken_resource_paths

    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/gercek.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (tmp_path / "player.gd").write_text(
        'extends Node2D\n\nfunc _ready():\n\tvar t = load("res://assets/gercek.png")\n',
        encoding="utf-8",
    )

    assert broken_resource_paths(tmp_path) == ()


def test_degisken_iceren_yol_hakkinda_iddia_edilmez(tmp_path):
    """Biçimlendirilen yol çalışma anında oluşur; kapı dar kalır."""
    from fusion_cli.core.cross_file import broken_resource_paths

    (tmp_path / "player.gd").write_text(
        'extends Node2D\n\nfunc _ready():\n\tvar t = load("res://tiles/%s.png" % ad)\n',
        encoding="utf-8",
    )

    assert broken_resource_paths(tmp_path) == ()


def test_extends_bildirmeyen_dugum_scripti_bildirilir(tmp_path):
    """`extends` yoksa script RefCounted sayılır; `velocity` orada yoktur.

    Ölçüldü (13 Eylül, koşu 28): `player.gd` `const SPEED` ile başlıyordu, hiç
    `extends` yoktu ve `velocity`/`move_and_slide()` kullanıyordu; dosya hiçbir
    sahneye bağlı olmadığı için motor da sessiz kaldı.
    """
    from fusion_cli.core.cross_file import scripts_without_base

    (tmp_path / "player.gd").write_text(
        "const SPEED = 300.0\n\nfunc _physics_process(_d):\n"
        "\tvelocity.x = SPEED\n\tmove_and_slide()\n",
        encoding="utf-8",
    )

    bulgular = scripts_without_base(tmp_path)

    assert len(bulgular) == 1
    assert "extends" in bulgular[0]


def test_taban_bildiren_script_bildirilmez(tmp_path):
    from fusion_cli.core.cross_file import scripts_without_base

    (tmp_path / "player.gd").write_text(
        "extends CharacterBody2D\n\nfunc _physics_process(_d):\n\tmove_and_slide()\n",
        encoding="utf-8",
    )

    assert scripts_without_base(tmp_path) == ()


def test_dugum_api_kullanmayan_script_hakkinda_iddia_edilmez(tmp_path):
    """Saf veri/yardımcı script'in tabanı olmak zorunda değildir."""
    from fusion_cli.core.cross_file import scripts_without_base

    (tmp_path / "hesap.gd").write_text(
        "static func topla(a, b):\n\treturn a + b\n", encoding="utf-8"
    )

    assert scripts_without_base(tmp_path) == ()


def test_project_godot_icindeki_kirik_yol_da_bildirilir(tmp_path):
    """Projenin en kritik `res://` yolu ana sahnedir; tarama onu da kapsar.

    Ölçüldü (13 Eylül, koşu 32): ana sahne dosyası hiç yazılmamıştı; Godot üç satır
    ERROR bastı ve çıkış kodu 0 verdi. Hatayı yalnız öz denetim gördü.
    """
    from fusion_cli.core.cross_file import broken_resource_paths

    (tmp_path / "project.godot").write_text(
        '[application]\nrun/main_scene="res://scenes/main.tscn"\n', encoding="utf-8"
    )

    bulgular = broken_resource_paths(tmp_path)

    assert len(bulgular) == 1
    assert "scenes/main.tscn" in bulgular[0]
