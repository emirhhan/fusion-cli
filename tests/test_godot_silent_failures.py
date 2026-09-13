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
