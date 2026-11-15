"""Araç argüman toleransı: zayıf modelin tip kaymaları araçları düşürmez (A1-22, A1-51)."""

from __future__ import annotations

import pytest

from fusion_cli.engines.agent.arg_coerce import coerce_bool, coerce_int, coerce_list
from fusion_cli.engines.agent.engine_tools import _question_options
from fusion_cli.engines.agent.image_tools import _parse


@pytest.mark.parametrize(
    ("ham", "beklenen"),
    [("3", 3), (" 7 ", 7), (4.0, 4), ("5.0", 5), (True, True), (1.5, 1.5), ("abc", "abc")],
)
def test_coerce_int_yalniz_kayipsiz_donusum_yapar(ham, beklenen):
    sonuc = coerce_int(ham)
    assert sonuc == beklenen and type(sonuc) is type(beklenen)


def test_coerce_bool_metin_degerlerini_tanir():
    assert coerce_bool("true") is True and coerce_bool("False") is False
    assert coerce_bool("belki") == "belki"


def test_coerce_list_json_metnini_acar():
    assert coerce_list('["a", "b"]') == ["a", "b"]
    assert coerce_list("düz metin") == "düz metin"


def test_secenekler_metin_listesi_olarak_gelirse_etikete_cevrilir():
    secenekler = _question_options(["Flask", "Django"])
    assert [s.label for s in secenekler] == ["Flask", "Django"]


def test_secenekler_json_metni_olarak_gelirse_acilir():
    secenekler = _question_options('[{"label": "A", "description": "x"}, "B"]')
    assert [s.label for s in secenekler] == ["A", "B"]


def test_gorsel_olcusu_metin_ya_da_ondalik_gelirse_kabul_edilir():
    sonuc = _parse({"prompt": "p", "path": "a.webp", "width": "1920", "height": 1080.0})
    assert not isinstance(sonuc, str)
    assert sonuc[1] == 1920 and sonuc[2] == 1080


def test_gorsel_olcusu_sema_alt_siniri_ile_uyumlu():
    sonuc = _parse({"prompt": "p", "path": "a.webp", "width": 4, "height": 4})
    assert isinstance(sonuc, str) and "16" in sonuc


def test_gorsel_olcusu_bool_sayi_sayilmaz():
    assert isinstance(_parse({"prompt": "p", "path": "a.webp", "width": True, "height": 32}), str)
