"""Yazılan dosya kendi dilinin sözdizimini geçmeli.

SWE-agent'ın ACI dersi: düzenleme sonrası çalışan bir denetim, sözdizimi hatasını
üretim anında yakalar ve modele hemen geri verir. Fusion'da bu denetim yalnız
yapılandırılmış biçimlerde (JSON/TOML/Godot) vardı; kaynak kod dosyaları bozuk
hâlde diske yazılabiliyordu.

Denetim SAF ve ağsızdır: yalnız dilin kendi ayrıştırıcısı kullanılır, dış araç
kurulmuş olmak zorunda değildir.
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.core.structured_files import validate_structured


def test_bozuk_python_diske_yazilmaz():
    sorun = validate_structured(Path("app.py"), "def topla(a, b:\n    return a + b\n")

    assert sorun is not None
    assert "python" in sorun.casefold()
    assert "satır" in sorun  # hata konumu modele taşınmalı


def test_gecerli_python_kabul_edilir():
    assert validate_structured(Path("app.py"), "def topla(a, b):\n    return a + b\n") is None


def test_bozuk_gdscript_yakalanir():
    """GDScript girintiye dayanır; kapanmamış blok Godot'ta parse error verir."""
    sorun = validate_structured(Path("player.gd"), "func _ready():\nprint('x')\n")

    assert sorun is not None
    assert "gdscript" in sorun.casefold()


def test_gecerli_gdscript_kabul_edilir():
    kaynak = (
        "extends CharacterBody2D\n\n"
        "@export var speed: float = 200.0\n\n"
        "func _physics_process(delta: float) -> void:\n"
        "\tvelocity = Vector2.ZERO\n"
        "\tmove_and_slide()\n"
    )

    assert validate_structured(Path("player.gd"), kaynak) is None


def test_bozuk_yaml_yakalanir():
    sorun = validate_structured(Path("ayar.yaml"), "ad: fusion\n  bozuk: [1, 2\n")

    assert sorun is not None
    assert "yaml" in sorun.casefold()


def test_tanimadigi_dil_reddedilmez():
    """Denetlemediğimiz bir biçimi reddetmek, modeli yapamayacağı düzeltmeye zorlar."""
    assert validate_structured(Path("notlar.md"), "# baslik\n\nserbest metin\n") is None
