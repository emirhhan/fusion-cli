"""Kullanıcı koşan işe araya girip yön verebilmeli.

Codex/Claude Code paritesi yalnız başarı oranı değil: kullanıcı uzun bir işi
izlerken "şunu da yap", "oraya dokunma" diyebiliyor ve iş kaldığı yerden doğru
biçimde sürüyor. Fusion'da duraklatma ve devam vardı; ARAYA GİRME yoktu — tek yol
turu öldürüp baştan başlamaktı ve o ana kadarki iş çöpe gidiyordu.

Yönlendirme mesajı bir sonraki alt tura harness notu olarak girer: modelin cevabına
karışmaz, kullanıcının sözü olarak taşınır.
"""

from __future__ import annotations

from fusion_cli.core.steering import SteeringQueue


def test_bekleyen_yonerge_sonraki_tura_gecer():
    kuyruk = SteeringQueue()
    kuyruk.push("testleri de çalıştır")

    notlar = kuyruk.drain()

    assert len(notlar) == 1
    assert "testleri de çalıştır" in notlar[0].content
    assert notlar[0].harness_note is True


def test_kuyruk_bosaltilinca_tekrar_gonderilmez():
    kuyruk = SteeringQueue()
    kuyruk.push("şunu yap")
    kuyruk.drain()

    assert kuyruk.drain() == ()


def test_sira_korunur():
    kuyruk = SteeringQueue()
    kuyruk.push("önce bu")
    kuyruk.push("sonra bu")

    notlar = kuyruk.drain()

    assert [not_.content.count("önce bu") for not_ in notlar] == [1, 0]


def test_bos_mesaj_kuyruga_girmez():
    kuyruk = SteeringQueue()
    kuyruk.push("   ")

    assert kuyruk.drain() == ()


def test_bekleyen_var_mi_sorulabilir():
    kuyruk = SteeringQueue()

    assert not kuyruk.pending
    kuyruk.push("dur")
    assert kuyruk.pending
