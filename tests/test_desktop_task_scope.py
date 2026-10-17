"""Masaüstü isteği algılanınca arka plan araçları sunulur; sıradan istekte sunulmaz."""

from __future__ import annotations

import pytest

from fusion_cli.engines.agent.expertise import is_desktop_task


@pytest.mark.parametrize(
    "metin",
    [
        "ChatGPT'ye şunu sor: bugün hava nasıl",
        "Chrome'da meta ads sayfasını aç",
        "bilgisayarımda Finder'dan dosyayı bul",
        "arka planda Slack penceresine yaz",
        "Codex uygulamasına bu görevi ver",
    ],
)
def test_masaustu_istegi_algilanir(metin: str) -> None:
    assert is_desktop_task(metin)


@pytest.mark.parametrize(
    "metin",
    ["bu fonksiyonu yeniden adlandır", "README'ye kurulum bölümü ekle", "merhaba nasılsın"],
)
def test_sıradan_istek_masaustu_degildir(metin: str) -> None:
    assert not is_desktop_task(metin)
