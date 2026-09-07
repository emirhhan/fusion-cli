"""Plan adımı, aynı keşfi ÜÇÜNCÜ kez yapmak zorunda kalmamalı.

Ölçüldü (7 Eylül canlı koşusu, `surum-sabitini-tek-kaynaga-indir`): depo haritası
yalnız üst turda (`depth == 0`) veriliyor; plan adımları alt turda koştuğu için
hiçbir bağlam görmüyordu. Her adım `list_dir` ve `glob **/*` ile baştan başladı,
aynı üç dosyayı üst üste okudu ve bütçe iş bitmeden tükendi.

Blok yalnız ADLARI taşır, içerik taşımaz: yönlendirir, bağlamı şişirmez.
"""

from __future__ import annotations

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.plan_context import (
    MAX_STEP_WORKSPACE_FILES,
    step_prompt,
    workspace_block,
)
from tests.test_plan_repair import _step


def _baglam(tmp_path, okunan=(), degisen=()):
    baglam = ToolContext(tmp_path)
    baglam.fully_read.update(tmp_path / ad for ad in okunan)
    baglam.touched.update(tmp_path / ad for ad in degisen)
    return baglam


def test_okunan_ve_degisen_dosyalar_yazilir(tmp_path):
    blok = workspace_block(_baglam(tmp_path, okunan=("paket/cli.py",), degisen=("paket/rapor.py",)))

    assert "paket/cli.py" in blok
    assert "paket/rapor.py" in blok


def test_hicbir_sey_yapilmamissa_blok_bos(tmp_path):
    """Boş blok yazmak istemi gürültüyle şişirirdi."""
    assert workspace_block(_baglam(tmp_path)) == ""


def test_liste_sinirlanir(tmp_path):
    blok = workspace_block(_baglam(tmp_path, okunan=[f"d{i}.py" for i in range(40)]))

    assert blok.count(".py") <= MAX_STEP_WORKSPACE_FILES


def test_blok_adim_istemine_giriyor(tmp_path):
    """Yardımcının var olması yetmez: istemin İÇİNE girdiği kanıtlanmalı."""
    blok = workspace_block(_baglam(tmp_path, okunan=("paket/cli.py",)))

    istem = step_prompt("iş", _step("adim"), {}, workspace=blok)

    assert "paket/cli.py" in istem
    assert "ÇALIŞMA ALANI" in istem


def test_blok_dosya_icerigi_tasimaz(tmp_path):
    (tmp_path / "gizli.py").write_text("PAROLA = 'sir'\n", encoding="utf-8")

    blok = workspace_block(_baglam(tmp_path, okunan=("gizli.py",)))

    assert "gizli.py" in blok
    assert "PAROLA" not in blok
