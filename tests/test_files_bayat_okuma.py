"""Okunduktan sonra dışarıdan değişen dosya toptan ezilemez (T1-22).

Ölçüldü (29 Ekim): `fully_read` yalnız yol kümesiydi; kullanıcı editörde ya da bir
formatter/kod üretici `run_shell` ile dosyayı değiştirse de `write_file` eski okumaya
dayanıp araya giren değişikliği siliyordu. Okuma anındaki (mtime_ns, boyut) imzası
yazmadan önce karşılaştırılır.
"""

from __future__ import annotations

import os

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import files


@pytest.fixture
def context(tmp_path):
    return ToolContext(root=tmp_path)


def _disaridan_degistir(yol, metin: str) -> None:
    """Başka bir süreç gibi yaz: içerik ve mtime farklı olsun."""
    yol.write_text(metin, encoding="utf-8")
    eski = yol.stat().st_mtime_ns
    os.utime(yol, ns=(eski + 5_000_000_000, eski + 5_000_000_000))


def test_okuduktan_sonra_dis_degisen_dosya_ezilmez(context, tmp_path):
    hedef = tmp_path / "app.py"
    hedef.write_text("a = 1\n", encoding="utf-8")
    files.read_file({"path": "app.py"}, context)
    _disaridan_degistir(hedef, "a = 1\nkullanici_ekledi = True\n")

    sonuc = files.write_file({"path": "app.py", "content": "a = 2\n"}, context)

    assert not sonuc.ok and "okuduktan sonra değişti" in sonuc.output
    assert "kullanici_ekledi" in hedef.read_text(encoding="utf-8")


def test_yeniden_okuyunca_yazma_acilir(context, tmp_path):
    hedef = tmp_path / "app.py"
    hedef.write_text("a = 1\n", encoding="utf-8")
    files.read_file({"path": "app.py"}, context)
    _disaridan_degistir(hedef, "a = 1\nb = 2\n")
    files.read_file({"path": "app.py"}, context)

    sonuc = files.write_file({"path": "app.py", "content": "a = 3\n"}, context)

    assert sonuc.ok, sonuc.output


def test_ajanin_kendi_yazmasi_okumayi_bayatlatmaz(context, tmp_path):
    hedef = tmp_path / "app.py"
    hedef.write_text("eski\n", encoding="utf-8")
    files.read_file({"path": "app.py"}, context)

    ilk = files.write_file({"path": "app.py", "content": "bir\n"}, context)
    ikinci = files.write_file({"path": "app.py", "content": "iki\n"}, context)

    assert ilk.ok and ikinci.ok, ikinci.output
    assert hedef.read_text(encoding="utf-8") == "iki\n"


def test_ajanin_kendi_duzenlemesi_okumayi_bayatlatmaz(context, tmp_path):
    hedef = tmp_path / "app.py"
    hedef.write_text("a = 1\nb = 2\n", encoding="utf-8")
    files.read_file({"path": "app.py"}, context)

    duzenleme = files.edit_file({"path": "app.py", "old": "b = 2", "new": "b = 3"}, context)
    yazma = files.write_file({"path": "app.py", "content": "a = 9\n"}, context)

    assert duzenleme.ok and yazma.ok, yazma.output
