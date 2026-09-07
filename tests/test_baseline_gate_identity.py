"""Plan ÖNCESİNDE de düşen kapı, adımı çıktısı değişti diye düşürmemeli.

Ölçüldü (7 Eylül canlı Godot koşusu): kapı zaman aşımına uğradığında bulgu metni
"asılmadan önce şunu söyledi:" kuyruğunu taşıyor ve bu kuyruk her koşuda birebir
aynı olmuyor. Baseline karşılaştırması METNE bakıyordu; aynı kapı, aynı sebeple
düşmesine rağmen "yeni kırılma" sayılıp adımı öldürüyordu.

Soru "aynı cümle mi" değil, "AYNI KAPI mı" olmalıdır.
"""

from __future__ import annotations

from fusion_cli.engines.agent.step_verification import new_findings


def test_ayni_komutun_farkli_ciktisi_yeni_kirilma_sayilmaz():
    onceki = ("komut zaman aşımına uğradı (120.0s): godot --headless --path . --quit\nA",)
    simdiki = ("komut zaman aşımına uğradı (120.0s): godot --headless --path . --quit\nB",)

    assert new_findings(simdiki, onceki) == ()


def test_birebir_ayni_bulgu_yeni_sayilmaz():
    assert new_findings(("aynı",), ("aynı",)) == ()


def test_baska_bir_kapinin_bulgusu_yeni_sayilir():
    onceki = ("komut zaman aşımına uğradı (120.0s): godot --headless --path . --quit",)
    simdiki = ("komut başarısız (1): pytest -q\nE   assert 0",)

    assert new_findings(simdiki, onceki) == simdiki


def test_komut_icermeyen_bulgu_metinle_karsilastirilir():
    assert new_findings(("sahne script ile uyumsuz",), ("başka bulgu",)) == (
        "sahne script ile uyumsuz",
    )
