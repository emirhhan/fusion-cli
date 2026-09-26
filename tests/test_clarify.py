"""Belirsiz yeni proje isteğinde koda başlamadan seçenekli soru teşviki.

Ölçüldü (26 Eylül, gemini_web): "Müşterilerin sipariş numarasıyla kargo
durumunu sorgulayabileceği bir web uygulaması yap." isteğinde model teknolojiyi
ve veri kaynağını SORMADAN Flask + uydurma `orders.json` ile 8,5 dakika kodladı.
Sistem talimatındaki kural zayıf modelde yetmedi; yapısal not gerekir.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.engines.agent.clarify import clarification_hint


@pytest.mark.parametrize(
    "gorev",
    [
        "Müşterilerin sipariş numarasıyla kargo durumunu sorgulayabileceği bir web uygulaması yap.",
        "Bana basit bir blog sitesi yap.",
        "Motogate için stok takip paneli oluştur",
        "bir telegram botu geliştir",
    ],
)
def test_bos_klasorde_belirsiz_proje_isteginde_soru_notu_eklenir(tmp_path: Path, gorev: str):
    not_ = clarification_hint(gorev, tmp_path, can_ask=True, first_turn=True)

    assert not_ is not None
    assert "ask_user" in not_


def test_soru_sorulamayan_oturumda_not_yok(tmp_path: Path):
    assert (
        clarification_hint("bir blog sitesi yap", tmp_path, can_ask=False, first_turn=True) is None
    )


def test_takip_turunda_not_yok(tmp_path: Path):
    assert (
        clarification_hint("bir blog sitesi yap", tmp_path, can_ask=True, first_turn=False) is None
    )


def test_var_olan_projede_not_yok(tmp_path: Path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")

    assert (
        clarification_hint("bir blog sitesi yap", tmp_path, can_ask=True, first_turn=True) is None
    )


@pytest.mark.parametrize(
    "gorev",
    [
        "README'deki yazım hatalarını düzelt",
        "merhaba",
        "Bu fonksiyon neden yavaş?",
        # Ayrıntılı şartname zaten kararları veriyor.
        "Next.js 15, TypeScript ve Tailwind ile blog yap: ana sayfa, yazı detay, etiket "
        "filtresi, MDX içerik, karanlık tema, Vercel dağıtımı, vitest testleri, SEO meta "
        "etiketleri, RSS beslemesi ve site haritası olsun; veriyi content/ klasöründen oku.",
    ],
)
def test_belirsiz_proje_istegi_olmayan_gorevde_not_yok(tmp_path: Path, gorev: str):
    assert clarification_hint(gorev, tmp_path, can_ask=True, first_turn=True) is None
