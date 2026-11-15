"""Uzmanlık/masaüstü sezgisi yanlış pozitifleri (A1-32)."""

from __future__ import annotations

import pytest

from fusion_cli.engines.agent.expertise import is_desktop_task, is_game_task


@pytest.mark.parametrize(
    "istek",
    [
        "oyuncak mağazası için web sitesi yap",
        "oyuncu istatistiklerini HTML tabloda göster",
        "oyunculuk kursu için web sayfası hazırla",
    ],
)
def test_oyuncak_oyuncu_html_oyun_degildir(istek):
    assert not is_game_task(istek)


def test_gercek_html_oyun_hala_algilanir():
    assert is_game_task("canvas ile HTML yılan oyunu yap")
    assert is_game_task("tarayıcıda oynanan bir oyun yaz")


@pytest.mark.parametrize(
    "istek",
    [
        "CSS arka plan rengini değiştir",
        "window.onload olayını ekle",
        "bir web uygulaması yap",
        "terminal komutu çalıştır ve çıktıyı oku",
    ],
)
def test_siradan_kod_gorevi_masaustu_sayilmaz(istek):
    assert not is_desktop_task(istek)


@pytest.mark.parametrize(
    "istek",
    ["arka plan uygulamasına yaz", "Safari'de sayfayı aç", "Notlar uygulamasını aç"],
)
def test_gercek_masaustu_istegi_algilanir(istek):
    assert is_desktop_task(istek)


def test_olumsuzlanan_kritik_isareti_profili_yukseltmez():
    from fusion_cli.engines.agent.auto_profile import auto_profile

    assert auto_profile("kritik olmayan bir hatayı düzelt").profile == (
        auto_profile("bir hatayı düzelt").profile
    )
    assert auto_profile("kritik bir hatayı düzelt").profile != (
        auto_profile("bir hatayı düzelt").profile
    )


def test_isaret_sozcuk_ortasinda_eslesmez():
    from fusion_cli.engines.agent.auto_profile import _has

    assert _has("rename the file", "rename")
    assert not _has("surenamed value", "rename")
