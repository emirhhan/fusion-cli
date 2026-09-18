"""Düzenleme sözleşmesi: tam metin eşleşmesi ve modele dönen diff.

Ölçüldü (A2): `replace_range` ile yapılan bir eklemede `urun.adet -= adet`
satırı `new` içinde tekrar edilmediği için sessizce silindi. Araç modele yalnız
"düzenlendi: yol" dönüyordu; diff yalnız UI olayına gidiyordu ve model sildiği
satırı hiç görmedi. Sözleşme artık iki şeyi kilitler:

- düzenleme `old` metninin birebir ve benzersiz eşleşmesiyle yapılır;
- başarılı her düzenleme sonucu modele unified diff olarak döner.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.core.constants import MAX_PREVIEW_LINES
from fusion_cli.core.tool_emulation import render_tool_instructions
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import build_registry
from fusion_cli.tools.files import edit_file, multi_edit, read_file, write_file

_STOK = (
    "def sat(urun, adet):\n"
    "    if urun.adet < adet:\n"
    "        raise ValueError('stok yetersiz')\n"
    "    urun.adet -= adet\n"
    "    return urun\n"
)

_SAHNE = '[gd_scene format=3]\n\n[node name="a" type="Node2D"]\n'


@pytest.fixture
def context(tmp_path: Path) -> ToolContext:
    return ToolContext(root=tmp_path)


def test_edit_sonucu_silinen_satiri_modele_diff_olarak_gosterir(
    tmp_path: Path, context: ToolContext
) -> None:
    """A2'nin birebir yeniden üretimi: silinen satır araç sonucunda görünür."""
    (tmp_path / "stok.py").write_text(_STOK, encoding="utf-8")

    sonuc = edit_file(
        {
            "path": "stok.py",
            "old": "    urun.adet -= adet\n    return urun\n",
            "new": "    kaydet(urun)\n    return urun\n",
        },
        context,
    )

    assert sonuc.ok is True, sonuc.output
    assert sonuc.output.startswith("düzenlendi: stok.py (1 değişiklik)\n")
    assert "-    urun.adet -= adet" in sonuc.output.splitlines()
    assert "+    kaydet(urun)" in sonuc.output.splitlines()


def test_edit_file_benzersiz_olmayan_old_reddedilir_ve_dosya_degismez(
    tmp_path: Path, context: ToolContext
) -> None:
    hedef = tmp_path / "a.py"
    ozgun = "x = 1\nx = 1\n"
    hedef.write_text(ozgun, encoding="utf-8")

    sonuc = edit_file({"path": "a.py", "old": "x = 1", "new": "x = 2"}, context)

    assert sonuc.ok is False
    assert "2 kez" in sonuc.output
    assert hedef.read_text(encoding="utf-8") == ozgun


def test_multi_edit_yapi_denetiminden_gecer(tmp_path: Path, context: ToolContext) -> None:
    """`multi_edit` biçim kapısını atlıyordu; `.tscn` başlığı oradan silinebiliyordu."""
    hedef = tmp_path / "main.tscn"
    hedef.write_text(_SAHNE, encoding="utf-8")

    sonuc = multi_edit(
        {"path": "main.tscn", "edits": [{"old": "[gd_scene format=3]\n\n", "new": ""}]},
        context,
    )

    assert sonuc.ok is False
    assert "Yapı geçersiz" in sonuc.output
    assert hedef.read_text(encoding="utf-8") == _SAHNE


def test_multi_edit_sonucu_diff_dondurur(tmp_path: Path, context: ToolContext) -> None:
    (tmp_path / "stok.py").write_text(_STOK, encoding="utf-8")

    sonuc = multi_edit(
        {
            "path": "stok.py",
            "edits": [
                {"old": "'stok yetersiz'", "new": "'yetersiz stok'"},
                {"old": "    return urun\n", "new": "    return None\n"},
            ],
        },
        context,
    )

    assert sonuc.ok is True, sonuc.output
    assert sonuc.output.startswith("düzenlendi: stok.py (2 değişiklik)\n")
    assert "-    return urun" in sonuc.output.splitlines()


def test_write_file_var_olan_dosyada_diff_dondurur(tmp_path: Path, context: ToolContext) -> None:
    (tmp_path / "stok.py").write_text(_STOK, encoding="utf-8")
    read_file({"path": "stok.py"}, context)

    guncelleme = write_file({"path": "stok.py", "content": "def sat():\n    pass\n"}, context)
    yeni = write_file({"path": "yeni.py", "content": "a = 1\nb = 2\n"}, context)

    assert guncelleme.ok is True, guncelleme.output
    assert guncelleme.output.startswith("güncellendi: stok.py\n")
    assert "-    urun.adet -= adet" in guncelleme.output.splitlines()
    assert yeni.ok is True
    assert yeni.output == "oluşturuldu: yeni.py (2 satır)"


def test_duzenleme_diffi_onizleme_tavaniyla_sinirlanir(
    tmp_path: Path, context: ToolContext
) -> None:
    satir_sayisi = MAX_PREVIEW_LINES * 2
    eski = "".join(f"satir_{index}\n" for index in range(satir_sayisi))
    yeni = "".join(f"yeni_{index}\n" for index in range(satir_sayisi))
    (tmp_path / "uzun.txt").write_text(eski, encoding="utf-8")

    sonuc = edit_file({"path": "uzun.txt", "old": eski, "new": yeni}, context)

    assert sonuc.ok is True, sonuc.output
    govde = sonuc.output.splitlines()[1:]
    assert len(govde) == MAX_PREVIEW_LINES + 1
    assert govde[-1].startswith("… (+") and govde[-1].endswith(" satır)")


def test_replace_range_kayit_defterinde_yok() -> None:
    registry = build_registry()

    assert registry.get("replace_range") is None
    assert "replace_range" not in registry.names()


def test_emulasyon_talimatlari_replace_range_onermez() -> None:
    metin = render_tool_instructions(build_registry().schemas())

    assert "replace_range" not in metin
    assert '"name":"edit_file"' in metin.replace(" ", "")
