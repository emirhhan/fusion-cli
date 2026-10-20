"""Koşu içinde araç üretimi: ajan kendine görev-özel araç yazabilir.

Live-SWE-agent'ın ölçümü: yalnız bash ile başlayıp koşu sırasında kendine Python
araçları yazan ajan, SWE-bench Verified'da %77,4 aldı ve bunun çevrimdışı eğitim
maliyeti sıfır. Kazancın kaynağı, tekrar eden mekanik işi (aynı dizini süzmek,
aynı biçimi ayrıştırmak) bir kez yazıp sonraki adımlarda ÇAĞIRMAK.

Güvenlik gevşetilmez: üretilen araç `EXTERNAL` ailesindedir, onay ve kapsam
kurallarına tabidir ve kök dışına yazamaz.
"""

from __future__ import annotations

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools.forge import forge_tool, load_forged_tools


def test_uretilen_arac_kaydedilir_ve_calisir(tmp_path):
    context = ToolContext(root=tmp_path)
    kaynak = "def run(args):\n    return f\"toplam={args['a'] + args['b']}\"\n"

    sonuc = forge_tool({"name": "topla", "source": kaynak}, context)

    assert sonuc.ok
    araclar = load_forged_tools(tmp_path)
    assert [tool.name for tool in araclar] == ["topla"]
    assert "toplam=5" in araclar[0].run({"a": 2, "b": 3}, context).output


def test_gecersiz_python_reddedilir(tmp_path):
    context = ToolContext(root=tmp_path)

    sonuc = forge_tool({"name": "bozuk", "source": "def run(args:\n"}, context)

    assert not sonuc.ok
    assert "sözdizimi" in sonuc.output.casefold()
    assert load_forged_tools(tmp_path) == ()


def test_run_fonksiyonu_olmayan_kaynak_reddedilir(tmp_path):
    context = ToolContext(root=tmp_path)

    sonuc = forge_tool({"name": "eksik", "source": "deger = 1\n"}, context)

    assert not sonuc.ok
    assert "run" in sonuc.output


def test_arac_adi_yol_kacisi_iceremez(tmp_path):
    context = ToolContext(root=tmp_path)

    sonuc = forge_tool({"name": "../kacis", "source": "def run(args):\n    return ''\n"}, context)

    assert not sonuc.ok
    assert not (tmp_path.parent / "kacis.py").exists()


def test_uretilen_arac_disari_yazamaz(tmp_path):
    """Araç kodu ajan tarafından yazıldı: kök dışına erişim yine kapalı."""
    context = ToolContext(root=tmp_path)
    kaynak = (
        "from pathlib import Path\n\n\n"
        "def run(args):\n"
        "    Path(args['yol']).write_text('sizinti')\n"
        "    return 'yazdim'\n"
    )
    forge_tool({"name": "sizinti", "source": kaynak}, context)
    arac = load_forged_tools(tmp_path)[0]

    sonuc = arac.run({"yol": str(tmp_path.parent / "disari.txt")}, context)

    assert not sonuc.ok
    assert not (tmp_path.parent / "disari.txt").exists()
