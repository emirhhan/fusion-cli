"""Başarısız adım, yarım bıraktığını temizler.

Uzun otonom koşuda her başarısız deneme diske yarım bir durum bırakırsa, sonraki
deneme kendi hatasıyla değil öncekinin enkazıyla uğraşır. Ölçüldü (6 Eylül Godot
koşusu): adım üç kez denendi, her denemede `main.tscn` kısmen yazıldı ve model
kendi önceki çıktısını "mevcut dosya" sanıp üstüne yazmaya çalıştı.

Geri alma SADECE başarısız denemeye aittir: doğrulanmış adımın çıktısı korunur.
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.core.changeset import ChangeSet
from fusion_cli.core.rollback import StepRollback


def test_basarisiz_deneme_geri_alinir(tmp_path: Path):
    dosya = tmp_path / "kod.py"
    dosya.write_text("orijinal\n", encoding="utf-8")
    changes = ChangeSet()
    rollback = StepRollback(changes)

    changes.record(dosya)
    dosya.write_text("yarim\n", encoding="utf-8")
    geri_alinan = rollback.discard()

    assert dosya.read_text(encoding="utf-8") == "orijinal\n"
    assert geri_alinan == (dosya,)


def test_dogrulanan_adim_ciktisi_korunur(tmp_path: Path):
    dosya = tmp_path / "kod.py"
    dosya.write_text("orijinal\n", encoding="utf-8")
    changes = ChangeSet()
    rollback = StepRollback(changes)

    changes.record(dosya)
    dosya.write_text("yeni\n", encoding="utf-8")
    rollback.keep()

    assert dosya.read_text(encoding="utf-8") == "yeni\n"
    assert rollback.discard() == ()


def test_bu_adimda_olusturulan_dosya_silinir(tmp_path: Path):
    yeni = tmp_path / "yeni.py"
    changes = ChangeSet()
    rollback = StepRollback(changes)

    changes.record(yeni)
    yeni.write_text("gecici\n", encoding="utf-8")
    rollback.discard()

    assert not yeni.exists()


def test_geri_alma_sonrasi_yeni_adim_temiz_baslar(tmp_path: Path):
    dosya = tmp_path / "kod.py"
    dosya.write_text("orijinal\n", encoding="utf-8")
    changes = ChangeSet()
    rollback = StepRollback(changes)
    changes.record(dosya)
    dosya.write_text("yarim\n", encoding="utf-8")
    rollback.discard()

    # İkinci deneme: önceki denemenin kaydı temizlendiği için kendi kaydını tutar.
    changes.record(dosya)
    dosya.write_text("ikinci\n", encoding="utf-8")

    assert rollback.discard() == (dosya,)
    assert dosya.read_text(encoding="utf-8") == "orijinal\n"
