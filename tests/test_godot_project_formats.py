"""Godot 4 `project.godot` örnekleri yanlış reddedilmemeli.

Gerçek Godot 4 editörünün yazdığı dosya `config_version=5` anahtarını bir bölüm
başlığından ÖNCE, en üstte taşır; ana sahne de `uid://...` ile (ve isteğe bağlı
`res://` yedeğiyle) yazılabilir. Her ikisi geçerli biçimdir.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.core.structured_files import validate_structured
from fusion_cli.engines.agent.domain_adapters.godot import godot_has_main_scene

_BASLIK = (
    "; Engine configuration file.\n"
    "; It's best edited using the editor UI and not directly,\n\n"
    "config_version=5\n\n"
)

_UID_ANA_SAHNE = _BASLIK + (
    '[application]\n\nconfig/name="Oyun"\nrun/main_scene="uid://b8x2k4q7m1n3p"\n'
    'config/features=PackedStringArray("4.3", "Forward Plus")\n'
)

_RES_ANA_SAHNE = _BASLIK + (
    '[application]\n\nconfig/name="Oyun"\nrun/main_scene="res://scenes/main.tscn"\n'
)

#: Editörün yazdığı biçim: uid + res yedek yolu aynı satırda değil, sahne dosyası
#: ilk satırında `uid="uid://..."` taşır; `project.godot` yalnız uid yazar.
_SAHNE = '[gd_scene format=3 uid="uid://b8x2k4q7m1n3p"]\n\n[node name="Main" type="Node2D"]\n'

_CONFIG_VERSION_SURUMLERI = ("4", "5", "6")


def _proje(kok: Path, icerik: str, *, sahne: bool = True) -> Path:
    (kok / "project.godot").write_text(icerik, encoding="utf-8")
    if sahne:
        (kok / "scenes").mkdir(exist_ok=True)
        (kok / "scenes" / "main.tscn").write_text(_SAHNE, encoding="utf-8")
    return kok


@pytest.mark.parametrize("surum", _CONFIG_VERSION_SURUMLERI)
def test_bolum_oncesi_config_version_gecerli_sayilir(surum):
    icerik = _BASLIK.replace("config_version=5", f"config_version={surum}") + "[application]\n"

    assert validate_structured(Path("project.godot"), icerik) is None


def test_bolumsuz_ana_sahne_hala_reddedilir():
    """config_version istisnası bölümsüz `run/main_scene` hatasını gizlememeli."""
    icerik = 'config_version=5\nrun/main_scene="res://a.tscn"\n[application]\n'

    sorun = validate_structured(Path("project.godot"), icerik)

    assert sorun is not None
    assert "run/main_scene" in sorun


def test_yalniz_bolumsuz_anahtar_hala_reddedilir():
    sorun = validate_structured(Path("project.godot"), 'run/main_scene="res://a.tscn"\n')

    assert sorun is not None


def test_uid_ana_sahne_gecerli_sayilir(tmp_path):
    """`uid://` yalnız sahnenin kendi başlığında çözülür; dosya diskte varsa kabul."""
    proje = _proje(tmp_path, _UID_ANA_SAHNE)

    assert godot_has_main_scene(proje) is True


def test_res_ana_sahne_gecerli_sayilir(tmp_path):
    assert godot_has_main_scene(_proje(tmp_path, _RES_ANA_SAHNE)) is True


def test_res_ana_sahne_dosyasi_yoksa_gecersiz(tmp_path):
    assert godot_has_main_scene(_proje(tmp_path, _RES_ANA_SAHNE, sahne=False)) is False


def test_uid_ana_sahne_hicbir_sahne_dosyasi_tasimiyorsa_gecersiz(tmp_path):
    """uid hiçbir .tscn'nin başlığında yoksa Godot da çözemez."""
    proje = _proje(tmp_path, _UID_ANA_SAHNE, sahne=False)

    assert godot_has_main_scene(proje) is False


def test_uid_baska_sahneye_aitse_gecersiz(tmp_path):
    proje = _proje(tmp_path, _UID_ANA_SAHNE)
    (proje / "scenes" / "main.tscn").write_text(
        '[gd_scene format=3 uid="uid://baska"]\n', encoding="utf-8"
    )

    assert godot_has_main_scene(proje) is False


def test_uid_cozumu_motor_ve_gizli_klasorlerin_icine_bakmaz(tmp_path):
    proje = _proje(tmp_path, _UID_ANA_SAHNE, sahne=False)
    (proje / ".godot").mkdir()
    (proje / ".godot" / "onbellek.tscn").write_text(_SAHNE, encoding="utf-8")

    assert godot_has_main_scene(proje) is False
