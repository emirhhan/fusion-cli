"""Yarıda kalan turun kullanıcı özeti."""

from __future__ import annotations

from fusion_cli.core.tools import TodoItem, TodoStatus
from fusion_cli.ui.turn_stop import turn_stopped_summary


def test_ozet_sebebi_gorev_ilerlemesini_ve_devam_ipucunu_verir():
    metin = turn_stopped_summary(
        "no_progress",
        (
            TodoItem("sunucuyu kur", TodoStatus.COMPLETED),
            TodoItem("arayüzü düzenle", TodoStatus.PENDING),
        ),
    )

    assert "İş yarıda kaldı: art arda turlarda ilerleme olmadı." in metin
    assert "Görevler: 1/2 tamamlandı." in metin
    assert "☒ sunucuyu kur" in metin
    assert "☐ arayüzü düzenle" in metin
    assert "devam et" in metin


def test_gorev_listesi_yoksa_yalniz_sebep_ve_ipucu_yazilir():
    metin = turn_stopped_summary("deadline", ())

    assert metin.splitlines()[0] == "İş yarıda kaldı: turun süre sınırı doldu."
    assert "Görevler" not in metin


def test_bilinmeyen_sebep_sessiz_kalmaz():
    assert "yeni_sebep" in turn_stopped_summary("yeni_sebep", ())
