"""Modelin bir turda gördüğü bağlam ölçülmüş sınırlarda tutulur.

SWE-agent'ın ölçümü: turda ~100 satır göstermek en iyi sonucu veriyor ve arama
sonuçlarında her eşleşmeyi tek tek göstermek modeli şaşırtıyor — dosya başına
kısa liste daha iyi. Sınır SABİT DEĞİL taşımaya bağlıdır: web yolunda bağlam
pahalıdır, API yolunda mevcut ölçülmüş davranış korunur.
"""

from __future__ import annotations

from dataclasses import replace

from fusion_cli.core.constants import MAX_READ_LINES
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools.files import read_file
from fusion_cli.tools.search import search_code


def _dosya(tmp_path, satir_sayisi: int) -> ToolContext:
    (tmp_path / "buyuk.py").write_text(
        "\n".join(f"# satir {index}" for index in range(1, satir_sayisi + 1)) + "\n",
        encoding="utf-8",
    )
    return ToolContext(root=tmp_path)


def test_okuma_penceresi_baglama_gore_daralir(tmp_path):
    context = replace(_dosya(tmp_path, 400), read_window=100)

    sonuc = read_file({"path": "buyuk.py"}, context)

    assert "satir 100" in sonuc.output
    assert "satir 101" not in sonuc.output
    assert "read_file" in sonuc.output  # devam notu sıradaki çağrıyı yazar


def test_pencere_verilmezse_mevcut_davranis_korunur(tmp_path):
    context = _dosya(tmp_path, 400)

    sonuc = read_file({"path": "buyuk.py"}, context)

    assert "satir 400" in sonuc.output
    assert MAX_READ_LINES == 800


def test_model_istedigi_pencereyi_hala_asamaz(tmp_path):
    """Model `limit` verse bile taşımanın penceresi üst sınırdır."""
    context = replace(_dosya(tmp_path, 400), read_window=100)

    sonuc = read_file({"path": "buyuk.py", "limit": 400}, context)

    assert "satir 101" not in sonuc.output


def test_cok_eslesmede_arama_dosya_basina_ozetlenir(tmp_path):
    for index in range(6):
        (tmp_path / f"modul{index}.py").write_text(
            "\n".join(["hedef = 1"] * 8) + "\n", encoding="utf-8"
        )
    context = ToolContext(root=tmp_path)

    sonuc = search_code({"pattern": "hedef"}, context)

    assert "eşleşme" in sonuc.output
    # Özet biçimde her dosya BİR kez görünür: 48 satırın tamamı basılmaz.
    assert sonuc.output.count("modul0.py") == 1


def test_az_eslesmede_satirlar_aynen_gosterilir(tmp_path):
    (tmp_path / "tek.py").write_text("hedef = 1\nbaska = 2\nhedef = 3\n", encoding="utf-8")
    context = ToolContext(root=tmp_path)

    sonuc = search_code({"pattern": "hedef"}, context)

    assert "tek.py:1" in sonuc.output
    assert "tek.py:3" in sonuc.output
