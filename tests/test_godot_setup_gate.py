"""Kurulmakta olan Godot projesinde kapı ASILMAMALI.

Ölçüldü (7 Eylül canlı koşusu, `project-setup`): ana sahne henüz tanımlı değilken
`godot --headless --path . --quit` hatayı basıp asılı kaldı; kapı 120 saniye
bekledi, adım "komut zaman aşımına uğradı" ile düştü ve kurtarma hakkı tükendi.
Aynı davranış bu makinede yeniden üretildi: `--quit` de `--quit-after 1` de
dönmüyor, `--editor --quit` sıfır çıkışla dönüyor.

Ana sahne tanımlandıktan sonra kapı yine DAVRANIŞI ölçer: proje gerçekten açılmalı.
"""

from __future__ import annotations

from fusion_cli.engines.agent.domains import godot_adapter
from fusion_cli.engines.agent.verify_discovery import discover_commands
from fusion_cli.tools.command_policy import is_unattended_safe

_ANA_SAHNESIZ = '[application]\nconfig/name="Oyun"\n'
_ANA_SAHNELI = '[application]\nconfig/name="Oyun"\nrun/main_scene="res://ana.tscn"\n'


def _proje(tmp_path, icerik, *, sahne_dosyasi: bool = True):
    """Test projesi. Ana sahne BİLDİRİLDİYSE dosyası da yazılır: kapı artık
    dosyanın varlığını istiyor (ölçüldü, koşu 32: bildirilip yazılmamış sahne
    üç satır ERROR'a rağmen sıfır çıkışla geçiyordu)."""
    (tmp_path / "project.godot").write_text(icerik, encoding="utf-8")
    if sahne_dosyasi and "run/main_scene" in icerik:
        (tmp_path / "ana.tscn").write_text("[gd_scene format=3]\n", encoding="utf-8")
    return tmp_path


def test_ana_sahne_yokken_kapi_kurulum_komutuna_duser(tmp_path):
    komutlar = godot_adapter().gate_commands(_proje(tmp_path, _ANA_SAHNESIZ))

    assert komutlar == ("godot --headless --path . --editor --quit",)


def test_ana_sahne_tanimliyken_kapi_davranisi_olcer(tmp_path):
    komutlar = godot_adapter().gate_commands(_proje(tmp_path, _ANA_SAHNELI))

    assert komutlar == ("godot --headless --path . --quit",)


def test_bolumsuz_yazilmis_ana_sahne_sayilmaz(tmp_path):
    """Godot bölümsüz anahtarı yok sayar; kapı da saymamalı."""
    proje = _proje(tmp_path, 'run/main_scene="res://ana.tscn"\n')

    assert godot_adapter().gate_commands(proje) == ("godot --headless --path . --editor --quit",)


def test_kurulum_kapisi_kesif_tablosundan_da_gelir(tmp_path):
    komutlar = discover_commands(_proje(tmp_path, _ANA_SAHNESIZ))

    assert "godot --headless --path . --editor --quit" in komutlar


def test_kurulum_kapisi_onaysiz_calisabilir():
    """Kapı onaya düşerse etkileşimsiz oturumda hiç çalışmaz."""
    assert is_unattended_safe("godot --headless --path . --editor --quit")


# --- Dalga 4: içe aktarma denetimi üst dizin adından etkilenmez, 3B de görür (E1-09) --- #


def test_gizli_ust_dizindeki_proje_icin_aktarma_gerektigi_gorulur(tmp_path):
    """Ölçüldü (30 Ekim): kök `~/.projects/oyun` altındayken mutlak yol parçaları süzüldüğü için
    hiçbir varlık sayılmıyor ve içe aktarma tetiklenmiyordu."""
    from fusion_cli.engines.agent.domain_adapters.godot import godot_needs_import

    kok = tmp_path / ".projects" / "build" / "oyun"
    kok.mkdir(parents=True)
    (kok / "karo.png").write_bytes(b"\x89PNG")

    assert godot_needs_import(kok) is True


def test_uc_boyutlu_varlik_aktarma_ister_aktarilinca_ister_degil(tmp_path):
    from fusion_cli.engines.agent.domain_adapters.godot import godot_needs_import

    (tmp_path / "model.glb").write_bytes(b"glTF")
    assert godot_needs_import(tmp_path) is True

    (tmp_path / "model.glb.import").write_text("[remap]", encoding="utf-8")
    assert godot_needs_import(tmp_path) is False


def test_node_modules_ve_gizli_klasorlere_girilmez(tmp_path):
    from fusion_cli.engines.agent.domain_adapters.godot import godot_needs_import

    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.png").write_bytes(b"png")
    (tmp_path / ".godot").mkdir()
    (tmp_path / ".godot" / "y.svg").write_text("<svg/>", encoding="utf-8")

    assert godot_needs_import(tmp_path) is False
