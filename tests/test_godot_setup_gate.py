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


def _proje(tmp_path, icerik):
    (tmp_path / "project.godot").write_text(icerik, encoding="utf-8")
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
