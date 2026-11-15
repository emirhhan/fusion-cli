"""Türkçe büyük harf küçültme sınıflayıcıları bozmaz (A1-27, A2-12)."""

from __future__ import annotations

import pytest

from fusion_cli.core.text_fold import fold_tr
from fusion_cli.engines.agent.classify import TaskKind, classify_task_details
from fusion_cli.engines.agent.learning import contradicts, is_near_duplicate


def test_fold_tr_birlesik_nokta_birakmaz():
    assert fold_tr("İNCELE İyileştir") == "incele iyileştir"
    assert "̇" not in fold_tr("İ")


@pytest.mark.parametrize("istek", ["İNCELE projeyi", "İncele projeyi", "incele projeyi"])
def test_buyuk_harfli_incele_ayni_turu_verir(istek):
    assert classify_task_details(istek).primary is TaskKind.EXPLORE


def test_buyuk_harfli_ders_metni_kopya_sayilir():
    assert is_near_duplicate(
        "İşlem sonrası önbelleği temizle", ("işlem sonrası önbelleği temizle",)
    )


def test_buyuk_harfli_olumsuz_ders_celiski_sayilir():
    assert contradicts("İşlem önbelleğini sil", "işlem önbelleğini silme")
