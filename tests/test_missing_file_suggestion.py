"""Bulunamayan dosyada komşu ad önerilir — yönsüz "dosya yok" tur harcatıyordu.

Ölçüldü (7 Eylül canlı koşusu, `surum-sabitini-tek-kaynaga-indir`): model
`paket/init.py` okumaya çalıştı; doğru ad `paket/__init__.py` idi. Cevap yalnız
"Dosya yok" dedi ve model üç tur boyunca `list_dir`, `glob` ve yeniden okuma
denedi. Komşu adı SÖYLEMEK o turları tamamen ortadan kaldırır.

Öneri bir İDDİA değildir: yeterince benzer ad yoksa hiçbir şey söylenmez —
yanlış öneri, öneri olmamasından kötüdür.
"""

from __future__ import annotations

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools.files import read_file, replace_range


def test_benzer_ad_onerilir(tmp_path):
    (tmp_path / "paket").mkdir()
    (tmp_path / "paket" / "__init__.py").write_text("SURUM = '1.0'\n", encoding="utf-8")

    sonuc = read_file({"path": "paket/init.py"}, ToolContext(tmp_path))

    assert not sonuc.ok
    assert "__init__.py" in sonuc.output


def test_alakasiz_dosyalar_onerilmez(tmp_path):
    (tmp_path / "tamamen-baska-bir-sey.md").write_text("x", encoding="utf-8")

    sonuc = read_file({"path": "kod.py"}, ToolContext(tmp_path))

    assert not sonuc.ok
    assert "benzer ad" not in sonuc.output


def test_bos_dizinde_oneri_yok(tmp_path):
    sonuc = read_file({"path": "kod.py"}, ToolContext(tmp_path))

    assert not sonuc.ok
    assert "benzer ad" not in sonuc.output


def test_duzenleme_araci_da_oneri_verir(tmp_path):
    """Aynı kayıp aynı şekilde `replace_range` yolunda da yaşanıyordu."""
    (tmp_path / "ayarlar.py").write_text("A = 1\n", encoding="utf-8")

    sonuc = replace_range(
        {"path": "ayarlar.pyy", "start_line": 1, "end_line": 1, "new": "A = 2"},
        ToolContext(tmp_path),
    )

    assert not sonuc.ok
    assert "ayarlar.py" in sonuc.output
