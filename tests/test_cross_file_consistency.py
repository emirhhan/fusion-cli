"""Tek dosya doğru, bütün bozuk: çapraz tutarlılık denetimi.

Ölçüldü (6 Eylül Godot koşusu): `player.gd` `velocity` ve `move_and_slide()`
kullanıyordu — bunlar `CharacterBody2D` API'si. Sahnede oyuncu düğümü ise `Area2D`
olarak tanımlıydı. Her iki dosya da KENDİ İÇİNDE geçerliydi; Godot açılışta
`SCRIPT ERROR: Parse Error` bastı ve çıkış kodu yine `0` oldu.

Bu sınıf hatayı ne dil kapısı (her dosya geçerli) ne de çalıştırma kapısı (çıkış
kodu sıfır) yakalar. Çapraz denetim, iki dosyanın BİRLİKTE tutarlı olup olmadığını
sorar.
"""

from __future__ import annotations

from fusion_cli.core.cross_file import scene_script_conflicts

SAHNE = (
    "[gd_scene load_steps=2 format=3]\n\n"
    '[ext_resource type="Script" path="res://player.gd" id="1_player"]\n\n'
    '[node name="Main" type="Node2D"]\n\n'
    '[node name="Player" type="{tip}" parent="."]\n'
    'script = ExtResource("1_player")\n'
)

SCRIPT = (
    "extends {taban}\n\n"
    "func _physics_process(delta):\n"
    "\tvelocity = Vector2.ZERO\n"
    "\tmove_and_slide()\n"
)


def test_area2d_dugumune_baglanan_hareket_scripti_yakalanir(tmp_path):
    (tmp_path / "main.tscn").write_text(SAHNE.format(tip="Area2D"), encoding="utf-8")
    (tmp_path / "player.gd").write_text(SCRIPT.format(taban="CharacterBody2D"), encoding="utf-8")

    catismalar = scene_script_conflicts(tmp_path)

    assert catismalar
    metin = catismalar[0]
    assert "player.gd" in metin
    assert "Area2D" in metin
    assert "CharacterBody2D" in metin


def test_uyumlu_dugum_ve_script_catisma_uretmez(tmp_path):
    (tmp_path / "main.tscn").write_text(SAHNE.format(tip="CharacterBody2D"), encoding="utf-8")
    (tmp_path / "player.gd").write_text(SCRIPT.format(taban="CharacterBody2D"), encoding="utf-8")

    assert scene_script_conflicts(tmp_path) == ()


def test_extends_bildirmeyen_script_hakkinda_uydurma_yapilmaz(tmp_path):
    (tmp_path / "main.tscn").write_text(SAHNE.format(tip="Area2D"), encoding="utf-8")
    (tmp_path / "player.gd").write_text("func _ready():\n\tpass\n", encoding="utf-8")

    assert scene_script_conflicts(tmp_path) == ()


def test_scripti_olmayan_sahne_sorun_uretmez(tmp_path):
    (tmp_path / "main.tscn").write_text(
        '[gd_scene format=3]\n\n[node name="Main" type="Node2D"]\n', encoding="utf-8"
    )

    assert scene_script_conflicts(tmp_path) == ()


def test_godot_olmayan_projede_sessiz_kalir(tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")

    assert scene_script_conflicts(tmp_path) == ()
