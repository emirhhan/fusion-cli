"""Belirsiz proje notu: sözcük içi eşleşme yanlış pozitifi vermez (A1-31)."""

from __future__ import annotations

import pytest

from fusion_cli.engines.agent.clarify import clarification_hint


@pytest.mark.parametrize(
    "istek",
    [
        "Kuralları opposite sistem listesinden göster",
        "Kurallar sitesini gez ve özetle",
        "Oyun kurallarının metnini özetle",
    ],
)
def test_sozcuk_ici_eslesme_soru_tesvik_etmez(tmp_path, istek):
    assert clarification_hint(istek, tmp_path, can_ask=True, first_turn=True) is None


@pytest.mark.parametrize(
    "istek", ["Bir web uygulaması yap", "Sipariş takip sitesi kur", "Mağaza paneli oluştur"]
)
def test_belirsiz_yeni_proje_hala_sorulur(tmp_path, istek):
    assert clarification_hint(istek, tmp_path, can_ask=True, first_turn=True) is not None
