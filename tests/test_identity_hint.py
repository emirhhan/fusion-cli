"""Aktif model adı/sağlayıcısı sisteme verilir; kullanıcıya uydurma kimlik anlatılmaz."""

from __future__ import annotations

from fusion_cli.engines.agent.turn_hints import identity_hint


def test_kimlik_ipucu_model_ve_saglayiciyi_icerir():
    hint = identity_hint("nvidia_nim/nvidia/nemotron-3-super-120b-a12b")

    assert hint is not None
    assert "nvidia/nemotron-3-super-120b-a12b" in hint
    assert "nvidia_nim" in hint
    assert "Ben Fusion'ım" in hint


def test_kimlik_ipucu_gecersiz_model_adinda_uretilmez():
    assert identity_hint("") is None
    assert identity_hint("tek-parca") is None
