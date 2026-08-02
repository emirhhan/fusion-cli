"""Profil ↔ kademe çözümlemesi — alias ve büyük/küçük harf toleransı."""

from __future__ import annotations

import pytest

from fusion_cli.config.loader import load_config
from fusion_cli.config.profile import resolve_tier_name


@pytest.fixture
def config(tmp_path):
    hedef = tmp_path / "config.yaml"
    hedef.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    return load_config(hedef)


def test_kademe_adi_kendine_cozulur(config):
    assert resolve_tier_name(config, "high") == "high"


def test_max_premium_kademesine_alias_lanir(config):
    assert resolve_tier_name(config, "max") == "premium"


def test_cozumleme_buyuk_kucuk_harf_duyarsiz(config):
    assert resolve_tier_name(config, "MAX") == "premium"
    assert resolve_tier_name(config, "  High ") == "high"


def test_bilinmeyen_profil_none_dondurur(config):
    assert resolve_tier_name(config, "efsanevi") is None


def test_bos_ad_none_dondurur(config):
    assert resolve_tier_name(config, "   ") is None
