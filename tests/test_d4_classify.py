"""Görev türü sınıflandırması: gündelik sözcük çakışmaları ve analiz+oyun (A1-28, A1-29)."""

from __future__ import annotations

import pytest

from fusion_cli.engines.agent.classify import TaskKind, classify_task_details


@pytest.mark.parametrize(
    ("istek", "tur"),
    [
        ("projenin kapsamını açıkla", TaskKind.EXPLORE),
        ("hata yönetimi ekle", TaskKind.FEATURE),
        ("hata sayfası tasarla", TaskKind.WEBSITE),
        ("giriş hatasını düzelt", TaskKind.BUGFIX),
        ("hata mesajını düzelt", TaskKind.BUGFIX),
        ("test kapsamını artır", TaskKind.TEST),
    ],
)
def test_gundelik_sozcuk_tur_etiketini_ezmez(istek, tur):
    assert classify_task_details(istek).primary is tur


def test_oyun_analizi_yazma_gorevine_zorlanmaz():
    sonuc = classify_task_details("Godot oyununu incele, nasıl yapılmış rapor çıkar")

    assert sonuc.primary is TaskKind.EXPLORE


def test_oyun_yap_hala_ozellik_gorevidir():
    assert classify_task_details("bir oyun yap").primary is TaskKind.FEATURE
